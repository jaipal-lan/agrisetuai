import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { useI18n } from "../lib/i18n";

export default function Admin() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [kpis, setKpis] = useState(null);
  const [ledger, setLedger] = useState(null);
  const [rules, setRules] = useState([]);
  const [err, setErr] = useState(null);
  const [draft, setDraft] = useState({
    handling_class: "dry_grain",
    rate_per_kg: "0.8",
    rate_per_km: "12",
    min_transport_charge: "300",
    seller_commission_pct: "0.7",
    service_fee_pct: "0",
    inspection_fee: "300",
    packing_fee: "500",
    reason: "",
  });
  const [sim, setSim] = useState(null);
  const [lastDraftId, setLastDraftId] = useState(null);
  const [commodities, setCommodities] = useState([]);

  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }));

  async function load() {
    try {
      const [k, l, r, c] = await Promise.all([
        api("/admin/kpis"),
        api("/admin/ledger/accounts"),
        api("/pricing/rules"),
        api("/catalog/commodities"),
      ]);
      setKpis(k);
      setLedger(l);
      setRules(r);
      setCommodities(c);
    } catch (e) {
      setErr(e.message);
    }
  }

  async function saveMoq(id, value) {
    setErr(null);
    try {
      await api(`/catalog/commodities/${id}/moq`, {
        method: "PATCH",
        body: { min_order_qty: Number(value) },
      });
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    setMe(getUser());
    load();
  }, []);

  function body() {
    return {
      handling_class: draft.handling_class || null,
      rate_per_kg: Number(draft.rate_per_kg),
      rate_per_km: Number(draft.rate_per_km),
      min_transport_charge: Number(draft.min_transport_charge),
      seller_commission_pct: Number(draft.seller_commission_pct),
      service_fee_pct: Number(draft.service_fee_pct),
      inspection_fee: Number(draft.inspection_fee),
      packing_fee: Number(draft.packing_fee),
      reason: draft.reason || undefined,
    };
  }

  async function createDraft() {
    setErr(null);
    try {
      const r = await api("/admin/pricing-rules/draft", { method: "POST", body: body() });
      setLastDraftId(r.id);
      load();
    } catch (e) {
      setErr(e.message);
    }
  }
  async function simulate() {
    setErr(null);
    if (!lastDraftId) return setErr("Create a draft first.");
    try {
      setSim(
        await api(`/admin/pricing-rules/${lastDraftId}/simulate`, {
          method: "POST",
          body: { product_value: 12000, billable_kg: 500, route_km: 40 },
        })
      );
    } catch (e) {
      setErr(e.message);
    }
  }
  async function publish() {
    setErr(null);
    if (!lastDraftId) return setErr("Create a draft first.");
    try {
      await api(`/admin/pricing-rules/${lastDraftId}/publish`, { method: "POST" });
      setSim(null);
      setLastDraftId(null);
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  if (!me) {
    return (
      <div>
        <p className="muted">Staff login required.</p>
        <Link href="/login" className="btn">{t("login")}</Link>
      </div>
    );
  }

  return (
    <div>
      <h1>{t("admin")}</h1>
      {err && <div className="error">{err}</div>}

      <div className="grid">
        {kpis &&
          [
            ["Orders", kpis.total_orders],
            ["Settled", kpis.settled_orders],
            ["Cancelled", kpis.cancelled_orders],
            ["Open listings", kpis.open_listings],
            ["GMV (settled)", `₹${kpis.gmv_settled}`],
          ].map(([label, val]) => (
            <div className="card" key={label}>
              <div className="muted" style={{ fontSize: 13 }}>{label}</div>
              <div className="price" style={{ fontSize: 24 }}>{val}</div>
            </div>
          ))}
      </div>

      <h2>Ledger</h2>
      {ledger && (
        <div className="card">
          <div className="between">
            <b>Balance check</b>
            <span className={`badge ${ledger.balanced ? "" : "amber"}`}>
              {ledger.balanced ? "balanced ✓" : "UNBALANCED"}
            </span>
          </div>
          {Object.entries(ledger.accounts).map(([acct, bal]) => (
            <div className="quote-line" key={acct}>
              <span>{acct.replace(/_/g, " ")}</span><span>₹{bal}</span>
            </div>
          ))}
        </div>
      )}

      <h2>Pricing rules</h2>
      <table>
        <thead>
          <tr><th>v</th><th>Status</th><th>Scope</th><th>₹/kg</th><th>₹/km</th><th>Comm %</th><th>Svc %</th></tr>
        </thead>
        <tbody>
          {rules.map((r) => (
            <tr key={r.id}>
              <td>{r.version}</td>
              <td><span className={`badge ${r.status === "published" ? "" : "grey"}`}>{r.status}</span></td>
              <td>{r.handling_class || "all"}</td>
              <td>{r.rate_per_kg}</td>
              <td>{r.rate_per_km}</td>
              <td>{r.seller_commission_pct}</td>
              <td>{r.service_fee_pct}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>New pricing rule</h2>
      <div className="card">
        <div className="row">
          {[
            ["rate_per_kg", "₹/kg"],
            ["rate_per_km", "₹/km"],
            ["min_transport_charge", "Min transport ₹"],
            ["seller_commission_pct", "Seller commission %"],
            ["service_fee_pct", "Buyer service fee %"],
            ["inspection_fee", "Inspection ₹"],
            ["packing_fee", "Packing ₹"],
          ].map(([k, label]) => (
            <div key={k} style={{ flex: "1 1 120px" }}>
              <label>{label}</label>
              <input value={draft[k]} onChange={(e) => set(k, e.target.value)} inputMode="decimal" />
            </div>
          ))}
        </div>
        <label>Reason</label>
        <input value={draft.reason} onChange={(e) => set("reason", e.target.value)} />
        <div className="row" style={{ marginTop: 16 }}>
          <button onClick={createDraft}>Create draft</button>
          <button className="ghost" onClick={simulate} disabled={!lastDraftId}>Simulate</button>
          <button className="amber" onClick={publish} disabled={!lastDraftId}>Publish</button>
        </div>
        {sim && (
          <div className="ok" style={{ marginTop: 14 }}>
            Simulated on 500 kg · 40 km · ₹12,000 → buyer pays <b>₹{sim.buyer_total}</b>
            {" "}(transport ₹{sim.transport_charge}, service ₹{sim.service_fee})
            {sim.seller_commission !== undefined && <> · seller commission ₹{sim.seller_commission}</>}
          </div>
        )}
      </div>

      <h2>Product minimum order quantities</h2>
      <table>
        <thead>
          <tr><th>Product</th><th>Category</th><th>MOQ ({"kg"})</th><th></th></tr>
        </thead>
        <tbody>
          {commodities.map((c) => (
            <MoqRow key={c.id} c={c} onSave={saveMoq} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MoqRow({ c, onSave }) {
  const [val, setVal] = useState(c.min_order_qty);
  const changed = String(val) !== String(c.min_order_qty);
  return (
    <tr>
      <td>{c.name}</td>
      <td className="muted">{c.category}</td>
      <td>
        <input value={val} onChange={(e) => setVal(e.target.value)} inputMode="decimal"
               style={{ width: 90 }} />
      </td>
      <td>
        <button className="ghost" disabled={!changed} onClick={() => onSave(c.id, val)}>Save</button>
      </td>
    </tr>
  );
}
