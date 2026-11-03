import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getToken, getUser, mediaUrl } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

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
    total_qty: "",
    min_order_qty: "",
    asking_price: "",
    harvest_year: new Date().getFullYear(),
    claim_status: "conventional",
    specifications: "",
  });
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

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
    loadMine();
  }, []);

  useEffect(() => {
    if (!form.commodity_id) return setGrades([]);
    api(`/catalog/commodities/${form.commodity_id}/grades`).then(setGrades).catch(() => {});
  }, [form.commodity_id]);

  async function create() {
    setErr(null);
    setMsg(null);
    setBusy(true);
    try {
      const body = {
        commodity_id: Number(form.commodity_id),
        grade_spec_id: form.grade_spec_id ? Number(form.grade_spec_id) : undefined,
        total_qty: Number(form.total_qty),
        min_order_qty: Number(form.min_order_qty || 0),
        asking_price: Number(form.asking_price),
        harvest_year: Number(form.harvest_year),
        claim_status: form.claim_status,
        specifications: form.specifications || undefined,
      };
      await api("/listings", { method: "POST", body });
      setMsg("Listing created as a draft — publish it to go live.");
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

  async function addImages(id, files) {
    setErr(null);
    setBusy(true);
    try {
      for (const f of files) {
        const up = await uploadImage(f);
        await api(`/listings/${id}/media`, {
          method: "POST",
          body: { object_key: up.object_key, media_type: "image", checksum: up.checksum },
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
            <select value={form.commodity_id} onChange={(e) => set("commodity_id", e.target.value)}>
              <option value="">—</option>
              {commodities.map((c) => (
                <option key={c.id} value={c.id}>{cname(c)} ({c.category})</option>
              ))}
            </select>
          </div>
          <div style={{ flex: 1, minWidth: 140 }}>
            <label>Grade</label>
            <select value={form.grade_spec_id} onChange={(e) => set("grade_spec_id", e.target.value)}>
              <option value="">—</option>
              {grades.map((g) => (
                <option key={g.id} value={g.id}>{g.code} — {g.label}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="row">
          <div style={{ flex: 1 }}>
            <label>Total {t("quantity")} (kg)</label>
            <input value={form.total_qty} onChange={(e) => set("total_qty", e.target.value)} inputMode="decimal" />
          </div>
          <div style={{ flex: 1 }}>
            <label>Min order (kg)</label>
            <input value={form.min_order_qty} onChange={(e) => set("min_order_qty", e.target.value)} inputMode="decimal" />
          </div>
          <div style={{ flex: 1 }}>
            <label>{t("asking_price")} (₹/kg)</label>
            <input value={form.asking_price} onChange={(e) => set("asking_price", e.target.value)} inputMode="decimal" />
          </div>
        </div>
        <div className="row">
          <div style={{ flex: 1 }}>
            <label>Harvest year</label>
            <input value={form.harvest_year} onChange={(e) => set("harvest_year", e.target.value)} inputMode="numeric" />
          </div>
          <div style={{ flex: 1 }}>
            <label>Organic / non-organic</label>
            <select value={form.claim_status} onChange={(e) => set("claim_status", e.target.value)}>
              <option value="conventional">Non-organic (conventional)</option>
              <option value="in_conversion">In conversion</option>
              <option value="organic">Organic (needs evidence)</option>
            </select>
          </div>
        </div>
        <label>Product specifications (moisture, drying, cleaning, packing, variety notes…)</label>
        <textarea rows={2} value={form.specifications} onChange={(e) => set("specifications", e.target.value)}
          placeholder="e.g. Moisture 7%, hand-cleaned, single filling, 50 kg bags" />
        <div style={{ marginTop: 16 }}>
          <button onClick={create} disabled={busy || !form.commodity_id || !form.total_qty || !form.asking_price}>
            {t("create_listing")}
          </button>
        </div>
      </div>

      <h2>My listings</h2>
      <p className="muted" style={{ fontSize: 13 }}>
        Add at least 3 quality/sample images before publishing. A field agent may verify your lot at the farm gate.
      </p>
      {listings.length === 0 ? (
        <p className="muted">None yet.</p>
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
                    {l.status.replace(/_/g, " ")}
                  </span>
                </div>
                <div className="muted" style={{ fontSize: 13 }}>
                  ₹{l.asking_price}/kg · {l.available_qty}/{l.total_qty} {l.unit}
                  {l.is_organic ? " · organic" : ""}
                  {l.agent_verified ? " · ✓ verified" : ""}
                </div>
                {imgs.length > 0 && (
                  <div className="row" style={{ gap: 6, margin: "10px 0", flexWrap: "nowrap", overflowX: "auto" }}>
                    {imgs.map((m, i) => (
                      <img key={i} src={mediaUrl(m.object_key)} alt="" loading="lazy"
                           style={{ width: 64, height: 50, objectFit: "cover", borderRadius: 6, flex: "0 0 auto" }} />
                    ))}
                  </div>
                )}
                <div className="muted" style={{ fontSize: 12 }}>
                  {imgs.length}/3 images {enough ? "✓" : "— add more to publish"}
                </div>
                <div className="row" style={{ marginTop: 10, gap: 8 }}>
                  <label className="btn ghost" style={{ cursor: "pointer" }}>
                    + Images
                    <input type="file" accept="image/*" multiple style={{ display: "none" }}
                           onChange={(e) => addImages(l.id, Array.from(e.target.files))} />
                  </label>
                  {l.status === "draft" && <button disabled={!enough || busy} onClick={() => act(l.id, "publish")}>{t("publish")}</button>}
                  {l.status === "open" && <button className="ghost" onClick={() => act(l.id, "pause")}>Pause</button>}
                  {l.status === "paused" && <button disabled={!enough} onClick={() => act(l.id, "publish")}>Resume</button>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
