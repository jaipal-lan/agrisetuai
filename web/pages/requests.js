import { useRouter } from "next/router";
import { useEffect, useMemo, useState } from "react";

import { api, getUser } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

const AGENT_ROLES = ["field_agent", "field_leader", "field_manager", "superadmin"];

// Inline "offer into this RFQ" form for sellers.
function SellerOffer({ rfq }) {
  const [open, setOpen] = useState(false);
  const [price, setPrice] = useState(rfq.price_max || rfq.target_price || "");
  const [qty, setQty] = useState(rfq.requested_qty);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  async function submit() {
    setErr(null); setBusy(true);
    try {
      const offer = await api(`/rfqs/${rfq.id}/offers`, {
        method: "POST",
        body: { price_per_unit: Number(price), quantity: Number(qty) },
      });
      router.push(`/offers?focus=${offer.id}`);
    } catch (e) { setErr(e.message); setBusy(false); }
  }

  if (!open) return <button className="ghost" onClick={() => setOpen(true)}>Offer</button>;
  return (
    <div style={{ marginTop: 10 }}>
      {err && <div className="error">{err}</div>}
      <div className="row">
        <div style={{ flex: 1 }}>
          <label>₹/{rfq.unit}</label>
          <input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" />
        </div>
        <div style={{ flex: 1 }}>
          <label>Quantity {rfq.unit}</label>
          <input value={qty} onChange={(e) => setQty(e.target.value)} inputMode="decimal" />
        </div>
        <div style={{ alignSelf: "flex-end" }}>
          <button disabled={busy || !price || !qty} onClick={submit}>Send offer</button>
        </div>
      </div>
    </div>
  );
}

// Shared request activity + comment thread (buyer, farmers, agents).
function RfqThread({ rfqId }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function load() {
    try { setRows(await api(`/rfqs/${rfqId}/comments`)); } catch (e) { setErr(e.message); }
  }
  useEffect(() => { if (open && rows === null) load(); }, [open]);

  async function send() {
    if (!text.trim()) return;
    setBusy(true); setErr(null);
    try {
      await api(`/rfqs/${rfqId}/comments`, { method: "POST", body: { body: text.trim() } });
      setText(""); await load();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  return (
    <div style={{ marginTop: 10 }}>
      <button className="ghost" style={{ fontSize: 13, padding: "3px 8px" }} onClick={() => setOpen((o) => !o)}>
        💬 {open ? "Hide" : "Activity & comments"}
      </button>
      {open && (
        <div style={{ marginTop: 8, borderTop: "1px solid var(--line)", paddingTop: 8 }}>
          {err && <div className="error">{err}</div>}
          {rows === null ? <p className="muted" style={{ fontSize: 13 }}>Loading…</p> : (
            rows.length === 0 ? <p className="muted" style={{ fontSize: 13 }}>No activity yet.</p> : (
              <div style={{ display: "grid", gap: 6, maxHeight: 220, overflowY: "auto" }}>
                {rows.map((c) => (
                  <div key={c.id} style={{ fontSize: 13 }}>
                    {c.is_system ? (
                      <span className="muted">• {c.body}</span>
                    ) : (
                      <span><b>{c.author_name}</b>
                        {c.author_role ? <span className="muted"> ({c.author_role.replace(/_/g, " ")})</span> : null}
                        : {c.body}</span>
                    )}
                  </div>
                ))}
              </div>
            )
          )}
          <div className="row" style={{ gap: 6, marginTop: 8 }}>
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a comment…"
                   style={{ flex: 1 }} onKeyDown={(e) => e.key === "Enter" && send()} />
            <button disabled={busy || !text.trim()} onClick={send}>Post</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Requests() {
  const { t, lang } = useI18n();
  const [me, setMe] = useState(null);
  const [commodities, setCommodities] = useState([]);
  const [mandals, setMandals] = useState([]);
  const [prices, setPrices] = useState([]);
  const [rfqs, setRfqs] = useState([]);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const [form, setForm] = useState({
    commodity_id: "", requested_qty: "", unit: "kg",
    price_min: "", price_max: "", note: "", source_mandal_ids: [],
  });
  const [areaFilter, setAreaFilter] = useState("");

  const cmap = Object.fromEntries(commodities.map((c) => [c.id, c]));
  const mmap = Object.fromEntries(mandals.map((m) => [m.id, m.name]));
  const isBuyer = me && ["buyer_household", "buyer_business"].includes(me.role);
  const isFarmer = me && me.role === "farmer";
  const isAgent = me && AGENT_ROLES.includes(me.role);
  const isShopper = isBuyer || isFarmer;      // can post a request
  const canOffer = isFarmer;                   // can offer into one
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const cname = (c) => (c ? (lang === "te" && c.name_te ? c.name_te : c.name) : "—");

  // Market-price reference for the picked commodity (AGMARKNET, matched by name).
  const picked = cmap[form.commodity_id];
  const marketRef = useMemo(() => {
    if (!picked) return null;
    const n = picked.name.toLowerCase();
    const hit = prices.find((p) => {
      const pn = (p.commodity || "").toLowerCase();
      return pn.includes(n) || n.includes(pn);
    });
    if (!hit) return null;
    const perKg = (v) => (Number(v) / 100).toFixed(2);
    return {
      name: hit.commodity, qtlMin: hit.modal_min, qtlMax: hit.modal_max,
      kgMin: perKg(hit.modal_min), kgMax: perKg(hit.modal_max), as_of: hit.as_of,
    };
  }, [picked, prices]);

  async function load(role) {
    try {
      const path = role && role === "farmer" ? "/rfqs" : (AGENT_ROLES.includes(role) ? "/rfqs" : "/rfqs/mine");
      setRfqs(await api(path));
    } catch (e) { setErr(e.message); }
  }

  useEffect(() => {
    const u = getUser();
    setMe(u);
    api("/catalog/commodities").then(setCommodities).catch(() => {});
    api("/locations/mandals").then(setMandals).catch(() => {});
    api("/market-prices/commodities").then(setPrices).catch(() => {});
    if (u) load(u.role);
  }, []);

  function toggleArea(id) {
    setForm((f) => {
      const has = f.source_mandal_ids.includes(id);
      return { ...f, source_mandal_ids: has
        ? f.source_mandal_ids.filter((x) => x !== id)
        : [...f.source_mandal_ids, id] };
    });
  }

  async function createRfq() {
    setErr(null); setMsg(null);
    try {
      await api("/rfqs", { method: "POST", body: {
        commodity_id: Number(form.commodity_id),
        requested_qty: Number(form.requested_qty),
        unit: form.unit || "kg",
        price_min: form.price_min ? Number(form.price_min) : undefined,
        price_max: form.price_max ? Number(form.price_max) : undefined,
        source_mandal_ids: form.source_mandal_ids.length ? form.source_mandal_ids : undefined,
        note: form.note || undefined,
      } });
      setMsg("Request posted. Nearby farmers and agents have been alerted.");
      setForm({ commodity_id: "", requested_qty: "", unit: "kg", price_min: "", price_max: "", note: "", source_mandal_ids: [] });
      load(me.role);
    } catch (e) { setErr(e.message); }
  }

  const gate = roleGate(me, [...GROUPS.shopper, ...AGENT_ROLES], { label: "requests (RFQ)" });
  if (gate) return gate;

  const shownMandals = mandals.filter((m) =>
    !areaFilter || m.name.toLowerCase().includes(areaFilter.toLowerCase()));

  return (
    <div>
      <h1>{t("requests")}</h1>
      <p className="tagline">
        {isShopper ? "Post what you need; nearby farmers and agents are alerted and come to you."
          : "Open buyer requests you can help source."}
      </p>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok">{msg}</div>}

      {isShopper && (
        <div className="card">
          <h3>New request (RFQ)</h3>
          <div className="form-grid">
            <label>{t("commodity")}
              <select value={form.commodity_id} onChange={(e) => set("commodity_id", e.target.value)}>
                <option value="">—</option>
                {commodities.map((c) => (
                  <option key={c.id} value={c.id}>{cname(c)} ({c.category})</option>
                ))}
              </select>
            </label>
            <label>{t("quantity")}
              <input value={form.requested_qty} onChange={(e) => set("requested_qty", e.target.value)} inputMode="decimal" />
            </label>
            <label>Unit
              <select value={form.unit} onChange={(e) => set("unit", e.target.value)}>
                <option value="kg">kg</option>
                <option value="quintal">quintal</option>
                <option value="piece">piece</option>
                <option value="dozen">dozen</option>
                <option value="litre">litre</option>
              </select>
            </label>
          </div>

          {/* Live market-price reference, shown once a commodity is picked */}
          {picked && (
            <div className="card" style={{ background: "var(--card-alt, #f3f4f6)", margin: "10px 0", padding: 12 }}>
              {marketRef ? (
                <div style={{ fontSize: 14 }}>
                  📊 Today's mandi price for <b>{marketRef.name}</b>:{" "}
                  <b>₹{marketRef.kgMin}–{marketRef.kgMax}/kg</b>{" "}
                  <span className="muted">(₹{marketRef.qtlMin}–{marketRef.qtlMax}/qtl · AGMARKNET {marketRef.as_of})</span>
                  <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                    A reference only — set your target band below.
                  </div>
                </div>
              ) : (
                <div className="muted" style={{ fontSize: 13 }}>No government mandi price available for this product today.</div>
              )}
            </div>
          )}

          <div className="form-grid">
            <label>Target price min (₹/{form.unit})
              <input value={form.price_min} onChange={(e) => set("price_min", e.target.value)} inputMode="decimal" />
            </label>
            <label>Target price max (₹/{form.unit})
              <input value={form.price_max} onChange={(e) => set("price_max", e.target.value)} inputMode="decimal" />
            </label>
          </div>

          <label style={{ display: "block", marginTop: 10 }}>Which areas do you want it from? (optional)</label>
          <input value={areaFilter} onChange={(e) => setAreaFilter(e.target.value)}
                 placeholder="Filter areas…" style={{ maxWidth: 260, marginBottom: 6 }} />
          <div style={{ maxHeight: 150, overflowY: "auto", border: "1px solid var(--line)", borderRadius: 8, padding: 8 }}>
            <div className="row" style={{ flexWrap: "wrap", gap: 10 }}>
              {shownMandals.map((m) => (
                <label key={m.id} className="chk" style={{ fontSize: 13 }}>
                  <input type="checkbox" checked={form.source_mandal_ids.includes(m.id)}
                         onChange={() => toggleArea(m.id)} /> {m.name}
                </label>
              ))}
              {shownMandals.length === 0 && <span className="muted" style={{ fontSize: 13 }}>No areas match.</span>}
            </div>
          </div>
          {form.source_mandal_ids.length > 0 && (
            <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
              Selected: {form.source_mandal_ids.map((id) => mmap[id]).filter(Boolean).join(", ")}
            </div>
          )}

          <label style={{ display: "block", marginTop: 10 }}>Note (optional)
            <input value={form.note} onChange={(e) => set("note", e.target.value)}
                   placeholder="Quality, packing, timing…" />
          </label>

          <div style={{ marginTop: 16 }}>
            <button onClick={createRfq} disabled={!form.commodity_id || !form.requested_qty}>Post request</button>
          </div>
        </div>
      )}

      <h2>{isShopper ? "My requests" : "Open requests"}{isAgent && " to help source"}</h2>
      {rfqs.length === 0 ? (
        <p className="muted">None yet.</p>
      ) : (
        <div className="grid">
          {rfqs.map((r) => {
            const band = (r.price_min || r.price_max)
              ? `₹${r.price_min || "?"}–${r.price_max || "?"}/${r.unit}`
              : (r.target_price ? `₹${r.target_price}/${r.unit}` : null);
            const areas = (r.source_mandals && r.source_mandals.length)
              ? r.source_mandals.join(", ")
              : (r.source_mandal_ids || []).map((id) => mmap[id]).filter(Boolean).join(", ");
            return (
              <div className="card" key={r.id}>
                <div className="between">
                  <h3>{cname(cmap[r.commodity_id])}</h3>
                  <span className="row" style={{ gap: 4 }}>
                    {r.escalated && <span className="badge amber">escalated</span>}
                    <span className={`badge ${r.status === "open" ? "" : "grey"}`}>{r.status}</span>
                  </span>
                </div>
                <div className="muted" style={{ fontSize: 14 }}>
                  Wants <b>{r.requested_qty}</b> {r.unit}
                  {band ? <> · target {band}</> : null}
                </div>
                {areas && <div className="muted" style={{ fontSize: 13 }}>From: {areas}</div>}
                {canOffer && r.status === "open" && <SellerOffer rfq={r} />}
                <RfqThread rfqId={r.id} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
