import Link from "next/link";
import { useEffect, useState } from "react";

import MapPicker from "../components/MapPicker";
import CameraCapture from "../components/CameraCapture";
import MediaGallery from "../components/MediaGallery";
import { api, getToken, getUser } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

const UNITS = [["kg", "un_kg"], ["quintal", "un_quintal"], ["piece", "un_piece"], ["dozen", "un_dozen"], ["litre", "un_litre"]];

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/api";

async function uploadImage(file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API_BASE}/media/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${getToken()}` },
    body: fd,
  });
  if (!res.ok) throw new Error((await res.json()).detail || "Upload failed");
  return res.json();
}

export default function Sell() {
  const { t, lang } = useI18n();
  const [user, setUser] = useState(null);
  const [commodities, setCommodities] = useState([]);
  const [grades, setGrades] = useState([]);
  const [listings, setListings] = useState([]);
  const [form, setForm] = useState({
    commodity_id: "",
    grade_spec_id: "",
    unit: "kg",
    total_qty: "",
    min_order_qty: "",
    asking_price: "",
    harvest_year: new Date().getFullYear(),
    claim_status: "conventional",
    specifications: "",
    quality_grade: "A",
    defect_pct: "",
    defect_notes: "",
    latitude: null,
    longitude: null,
  });
  const [newProduct, setNewProduct] = useState("");
  const [orgCert, setOrgCert] = useState(null); // organic certificate file
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const GRADES = [
    ["A", "sl_grade_a"],
    ["B", "sl_grade_b"],
    ["C", "sl_grade_c"],
  ];
  const LST_STATUS = { draft: "lst_draft", open: "lst_open", sold_out: "lst_sold_out", paused: "lst_paused" };

  async function addProduct() {
    const name = newProduct.trim();
    if (!name) return;
    setErr(null);
    try {
      const c = await api("/catalog/commodities", { method: "POST", body: { name } });
      const list = await api("/catalog/commodities");
      setCommodities(list);
      set("commodity_id", String(c.id));
      setNewProduct("");
    } catch (e) { setErr(e.message); }
  }

  const cmap = Object.fromEntries(commodities.map((c) => [c.id, c]));
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function loadMine() {
    try {
      setListings(await api("/listings/mine"));
    } catch (e) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    setUser(getUser());
    api("/catalog/commodities").then(setCommodities).catch(() => {});
  }, []);

  // Auto-refresh my listings (status, verification, image counts) in the
  // background; pauses when the tab is hidden.
  usePoll(loadMine, 20000, []);

  useEffect(() => {
    if (!form.commodity_id) return setGrades([]);
    api(`/catalog/commodities/${form.commodity_id}/grades`).then(setGrades).catch(() => {});
  }, [form.commodity_id]);

  async function create() {
    setErr(null);
    setMsg(null);
    // Organic needs a certificate (govt/agency). Upload it first -> claim_evidence.
    if (form.claim_status === "organic" && !orgCert) {
      setErr(t("sl_organic_needs_cert"));
      return;
    }
    setBusy(true);
    try {
      let claim_evidence;
      if (form.claim_status === "organic" && orgCert) {
        const up = await uploadImage(orgCert);
        claim_evidence = { certificate_object_key: up.object_key, checksum: up.checksum,
                           type: "organic_certificate", uploaded_at: new Date().toISOString() };
      }
      const body = {
        commodity_id: Number(form.commodity_id),
        grade_spec_id: form.grade_spec_id ? Number(form.grade_spec_id) : undefined,
        unit: form.unit || "kg",
        total_qty: Number(form.total_qty),
        min_order_qty: Number(form.min_order_qty || 0),
        asking_price: Number(form.asking_price),
        harvest_year: Number(form.harvest_year),
        latitude: form.latitude ?? undefined,
        longitude: form.longitude ?? undefined,
        claim_status: form.claim_status,
        claim_evidence,
        specifications: form.specifications || undefined,
        quality_grade: form.quality_grade || undefined,
        defect_pct: form.defect_pct ? Number(form.defect_pct) : undefined,
        defect_notes: form.defect_notes || undefined,
      };
      await api("/listings", { method: "POST", body });
      setOrgCert(null);
      setMsg(t("sl_draft_created"));
      setForm((f) => ({ ...f, total_qty: "", asking_price: "" }));
      loadMine();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function act(id, action) {
    setErr(null);
    try {
      await api(`/listings/${id}/${action}`, { method: "POST" });
      loadMine();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function removeMedia(listingId, mediaId) {
    setErr(null);
    try {
      await api(`/listings/${listingId}/media/${mediaId}`, { method: "DELETE" });
      loadMine();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function addMedia(id, files, mediaType) {
    setErr(null);
    setBusy(true);
    try {
      for (const f of files) {
        const up = await uploadImage(f);
        await api(`/listings/${id}/media`, {
          method: "POST",
          body: { object_key: up.object_key, media_type: mediaType, checksum: up.checksum },
        });
      }
      loadMine();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const cname = (c) => (c ? (lang === "te" && c.name_te ? c.name_te : c.name) : "—");

  const gate = roleGate(user, GROUPS.seller, { label: "selling produce" });
  if (gate) return gate;

  return (
    <div>
      <h1>{t("sell")}</h1>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok">{msg}</div>}

      <div className="card">
        <h3>{t("create_listing")}</h3>
        <div className="row">
          <div style={{ flex: 1, minWidth: 180 }}>
            <label>{t("commodity")}</label>
            <select value={form.commodity_id}
                    onChange={(e) => set("commodity_id", e.target.value)}>
              <option value="">—</option>
              {commodities.map((c) => (
                <option key={c.id} value={c.id}>{cname(c)} ({c.category})</option>
              ))}
              <option value="__other">{t("sl_other_add")}</option>
            </select>
            {form.commodity_id === "__other" && (
              <div className="row" style={{ gap: 6, marginTop: 6 }}>
                <input value={newProduct} onChange={(e) => setNewProduct(e.target.value)}
                       placeholder={t("sl_new_product_ph")} style={{ flex: 1 }} />
                <button className="ghost" onClick={addProduct} disabled={!newProduct.trim()}>{t("sl_add")}</button>
              </div>
            )}
          </div>
          <div style={{ flex: 1, minWidth: 140 }}>
            <label>{t("sl_grade")}</label>
            <select value={form.grade_spec_id} onChange={(e) => set("grade_spec_id", e.target.value)}>
              <option value="">—</option>
              {grades.map((g) => (
                <option key={g.id} value={g.id}>{g.code} — {g.label}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="row">
          <div style={{ flex: "0 1 160px" }}>
            <label>{t("sl_sell_by")}</label>
            <select value={form.unit} onChange={(e) => set("unit", e.target.value)}>
              {UNITS.map(([v, label]) => <option key={v} value={v}>{t(label)}</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label>{t("sl_total")} {t("quantity")} ({form.unit})</label>
            <input value={form.total_qty} onChange={(e) => set("total_qty", e.target.value)} inputMode="decimal" />
          </div>
          <div style={{ flex: 1 }}>
            <label>{t("sl_min_order")} ({form.unit})</label>
            <input value={form.min_order_qty} onChange={(e) => set("min_order_qty", e.target.value)} inputMode="decimal" />
          </div>
          <div style={{ flex: 1 }}>
            <label>{t("asking_price")} (₹/{form.unit})</label>
            <input value={form.asking_price} onChange={(e) => set("asking_price", e.target.value)} inputMode="decimal" />
          </div>
        </div>
        <div className="row">
          <div style={{ flex: 1 }}>
            <label>{t("sl_harvest_year")}</label>
            <input value={form.harvest_year} onChange={(e) => set("harvest_year", e.target.value)} inputMode="numeric" />
          </div>
          <div style={{ flex: 1 }}>
            <label>{t("sl_organic_q")}</label>
            <select value={form.claim_status} onChange={(e) => set("claim_status", e.target.value)}>
              <option value="conventional">{t("sl_conventional")}</option>
              <option value="in_conversion">{t("sl_in_conversion")}</option>
              <option value="organic">{t("sl_organic")}</option>
            </select>
          </div>
        </div>
        {form.claim_status === "organic" && (
          <div className="card" style={{ background: "rgba(22,163,74,.06)", borderColor: "rgba(22,163,74,.3)", marginTop: 8 }}>
            <label style={{ fontWeight: 600 }}>{t("sl_org_cert_req")}</label>
            <p className="muted" style={{ fontSize: 12, margin: "2px 0 8px" }}>
              {t("sl_org_cert_help")}
            </p>
            <label className="btn ghost" style={{ cursor: "pointer" }}>
              {orgCert ? `✓ ${orgCert.name}` : t("sl_attach_cert")}
              <input type="file" accept="image/*,application/pdf" style={{ display: "none" }}
                     onChange={(e) => setOrgCert(e.target.files?.[0] || null)} />
            </label>
            {orgCert && <button type="button" className="ghost" style={{ marginLeft: 8, fontSize: 12 }}
                                onClick={() => setOrgCert(null)}>{t("pf_remove")}</button>}
          </div>
        )}
        <label>{t("sl_quality_grade")}</label>
        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          {GRADES.map(([g, label]) => (
            <button key={g} type="button"
                    className={form.quality_grade === g ? "" : "ghost"}
                    onClick={() => set("quality_grade", g)}>{t(label)}</button>
          ))}
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <div style={{ flex: "0 1 160px" }}>
            <label>{t("sl_defects_pct")}</label>
            <input value={form.defect_pct} onChange={(e) => set("defect_pct", e.target.value)}
                   inputMode="decimal" placeholder="e.g. 2" />
          </div>
          <div style={{ flex: "1 1 240px" }}>
            <label>{t("sl_defect_notes")}</label>
            <input value={form.defect_notes} onChange={(e) => set("defect_notes", e.target.value)}
                   placeholder={t("sl_defect_notes_ph")} />
          </div>
        </div>
        <label>{t("sl_specs")}</label>
        <textarea rows={2} value={form.specifications} onChange={(e) => set("specifications", e.target.value)}
          placeholder={t("sl_specs_ph")} />
        <details style={{ marginTop: 10 }}>
          <summary style={{ cursor: "pointer", fontWeight: 600 }}>{t("sl_pin_location")}</summary>
          <div style={{ marginTop: 8 }}>
            <MapPicker value={form.latitude ? { lat: form.latitude, lng: form.longitude } : null}
                       onChange={(ll) => setForm((f) => ({ ...f, latitude: ll.lat, longitude: ll.lng }))} />
          </div>
        </details>
        <div style={{ marginTop: 16 }}>
          <button onClick={create} disabled={busy || !form.commodity_id || form.commodity_id === "__other" || !form.total_qty || !form.asking_price}>
            {t("create_listing")}
          </button>
        </div>
      </div>

      <h2>{t("sl_my_listings")}</h2>
      <p className="muted" style={{ fontSize: 13 }}>
        {t("sl_photos_hint")}
      </p>
      {listings.length === 0 ? (
        <p className="muted">{t("sl_none_yet")}</p>
      ) : (
        <div className="grid">
          {listings.map((l) => {
            const imgs = l.media || [];
            const enough = imgs.length >= 3;
            return (
              <div className="card" key={l.id}>
                <div className="between">
                  <h3 style={{ fontSize: 16 }}>{cname(cmap[l.commodity_id])}</h3>
                  <span className={`badge ${l.status === "open" ? "" : l.status === "sold_out" ? "amber" : "grey"}`}>
                    {t(LST_STATUS[l.status] || l.status)}
                  </span>
                </div>
                <div className="muted" style={{ fontSize: 13 }}>
                  ₹{l.asking_price}/kg · {l.available_qty}/{l.total_qty} {l.unit}
                  {l.is_organic ? ` · ${t("sl_organic_tag")}` : ""}
                  {l.agent_verified ? ` · ${t("sl_verified_tag")}` : ""}
                </div>
                <MediaGallery items={imgs} video={l.video} videoId={l.video_id}
                              onRemove={(m) => removeMedia(l.id, m.id)} />
                <div className="muted" style={{ fontSize: 12 }}>
                  {imgs.length}/3 {t("sl_images")} {enough ? "✓" : t("sl_add_more_publish")}
                  {l.quality_grade ? ` · ${t("sl_grade_short")} ${l.quality_grade}` : ""}
                  {l.defect_pct != null ? ` · ${l.defect_pct}% ${t("sl_defects_suffix")}` : ""}
                  {l.video ? ` · ${t("sl_video_tag")}` : ""}
                </div>
                <div className="row" style={{ marginTop: 10, gap: 8 }}>
                  <CameraCapture onCapture={(file) => addMedia(l.id, [file], "image")} label={t("sl_take_photo")} />
                  <label className="btn ghost" style={{ cursor: "pointer" }}>
                    {t("sl_add_images")}
                    <input type="file" accept="image/*" multiple style={{ display: "none" }}
                           onChange={(e) => addMedia(l.id, Array.from(e.target.files), "image")} />
                  </label>
                  <label className="btn ghost" style={{ cursor: "pointer" }}>
                    {l.video ? t("sl_replace_video") : t("sl_add_video")}
                    <input type="file" accept="video/*" style={{ display: "none" }}
                           onChange={(e) => addMedia(l.id, Array.from(e.target.files), "video")} />
                  </label>
                  {l.status === "draft" && <button disabled={!enough || busy} onClick={() => act(l.id, "publish")}>{t("publish")}</button>}
                  {l.status === "open" && <button className="ghost" onClick={() => act(l.id, "pause")}>{t("sl_pause")}</button>}
                  {l.status === "paused" && <button disabled={!enough} onClick={() => act(l.id, "publish")}>{t("sl_resume")}</button>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
