import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

// Inline "offer into this RFQ" form for sellers.
function SellerOffer({ rfq, onDone }) {
  const [open, setOpen] = useState(false);
  const [price, setPrice] = useState(rfq.target_price || "");
  const [qty, setQty] = useState(rfq.requested_qty);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  async function submit() {
    setErr(null);
    setBusy(true);
    try {
      const offer = await api(`/rfqs/${rfq.id}/offers`, {
        method: "POST",
        body: { price_per_unit: Number(price), quantity: Number(qty) },
      });
      router.push(`/offers?focus=${offer.id}`);
    } catch (e) {
      setErr(e.message);
      setBusy(false);
    }
  }

  if (!open) return <button className="ghost" onClick={() => setOpen(true)}>Offer</button>;
  return (
    <div style={{ marginTop: 10 }}>
      {err && <div className="error">{err}</div>}
      <div className="row">
        <div style={{ flex: 1 }}>
          <label>₹/kg</label>
          <input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" />
        </div>
        <div style={{ flex: 1 }}>
          <label>Quantity kg</label>
          <input value={qty} onChange={(e) => setQty(e.target.value)} inputMode="decimal" />
        </div>
        <div style={{ alignSelf: "flex-end" }}>
          <button disabled={busy || !price || !qty} onClick={submit}>Send offer</button>
        </div>
      </div>
    </div>
  );
}

export default function Requests() {
  const { t, lang } = useI18n();
  const [me, setMe] = useState(null);
  const [commodities, setCommodities] = useState([]);
  const [rfqs, setRfqs] = useState([]);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const [form, setForm] = useState({ commodity_id: "", requested_qty: "", target_price: "" });

  const cmap = Object.fromEntries(commodities.map((c) => [c.id, c]));
  const isBuyer = me && ["buyer_household", "buyer_business"].includes(me.role);
  const isSeller = me && ["farmer", "fpo"].includes(me.role);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const cname = (c) => (c ? (lang === "te" && c.name_te ? c.name_te : c.name) : "—");

  async function load(role) {
    try {
      // Buyers see their own RFQs; sellers see the open market of RFQs.
      const path = role && ["farmer", "fpo"].includes(role) ? "/rfqs" : "/rfqs/mine";
      setRfqs(await api(path));
    } catch (e) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    const u = getUser();
    setMe(u);
    api("/catalog/commodities").then(setCommodities).catch(() => {});
    if (u) load(u.role);
  }, []);

  async function createRfq() {
    setErr(null);
    setMsg(null);
    try {
      await api("/rfqs", {
        method: "POST",
        body: {
          commodity_id: Number(form.commodity_id),
          requested_qty: Number(form.requested_qty),
          target_price: form.target_price ? Number(form.target_price) : undefined,
        },
      });
      setMsg("Request posted. Sellers can now offer into it.");
      setForm({ commodity_id: "", requested_qty: "", target_price: "" });
      load(me.role);
    } catch (e) {
      setErr(e.message);
    }
  }

  const gate = roleGate(me, GROUPS.shopper, { label: "requests (RFQ)" });
  if (gate) return gate;

  return (
    <div>
      <h1>{t("requests")}</h1>
      <p className="tagline">
        {isSeller
          ? "Open buyer requests you can offer into."
          : "Post what you need; sellers come to you."}
      </p>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok">{msg}</div>}

      {isBuyer && (
        <div className="card">
          <h3>New request (RFQ)</h3>
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
            <div style={{ flex: 1 }}>
              <label>{t("quantity")} (kg)</label>
              <input value={form.requested_qty} onChange={(e) => set("requested_qty", e.target.value)} inputMode="decimal" />
            </div>
            <div style={{ flex: 1 }}>
              <label>Target {t("price")} (₹/kg)</label>
              <input value={form.target_price} onChange={(e) => set("target_price", e.target.value)} inputMode="decimal" />
            </div>
          </div>
          <div style={{ marginTop: 16 }}>
            <button onClick={createRfq} disabled={!form.commodity_id || !form.requested_qty}>Post request</button>
          </div>
        </div>
      )}

      <h2>{isSeller ? "Open requests" : "My requests"}</h2>
      {rfqs.length === 0 ? (
        <p className="muted">None yet.</p>
      ) : (
        <div className="grid">
          {rfqs.map((r) => (
            <div className="card" key={r.id}>
              <div className="between">
                <h3>{cname(cmap[r.commodity_id])}</h3>
                <span className={`badge ${r.status === "open" ? "" : "grey"}`}>{r.status}</span>
              </div>
              <div className="muted" style={{ fontSize: 14 }}>
                Wants <b>{r.requested_qty}</b> {r.unit}
                {r.target_price ? <> · target ₹{r.target_price}/kg</> : null}
              </div>
              {isSeller && r.status === "open" && (
                <SellerOffer rfq={r} onDone={() => load(me.role)} />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
