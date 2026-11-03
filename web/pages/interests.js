import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

export default function Interests() {
  const { t, lang } = useI18n();
  const [me, setMe] = useState(null);
  const [rows, setRows] = useState([]);
  const [commodities, setCommodities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => {
    setMe(getUser());
    api("/catalog/commodities").then(setCommodities).catch(() => {});
  }, []);
  usePoll(() => {
    api("/crop-interests").then(setRows).catch((e) => setErr(e.message)).finally(() => setLoading(false));
  }, 20000);

  const gate = roleGate(me, GROUPS.seller, { label: "request alerts" });
  if (gate) return gate;

  function refresh() { api("/crop-interests").then(setRows).catch((e) => setErr(e.message)); }

  async function add(commodity_id, min_price) {
    setErr(null);
    try {
      await api("/crop-interests", { method: "POST", body: { commodity_id: Number(commodity_id), min_price: min_price ? Number(min_price) : undefined } });
      refresh();
    } catch (e) { setErr(e.message); }
  }
  async function remove(commodity_id) {
    setErr(null);
    try { await api(`/crop-interests/${commodity_id}`, { method: "DELETE" }); setRows((r) => r.filter((x) => x.commodity_id !== commodity_id)); }
    catch (e) { setErr(e.message); }
  }

  const cname = (r) => (lang === "te" && r.commodity_te ? r.commodity_te : r.commodity);
  const watchedIds = new Set(rows.map((r) => r.commodity_id));
  const addable = commodities.filter((c) => !watchedIds.has(c.id));

  return (
    <div>
      <h1>{t("request_alerts")}</h1>
      <p className="tagline">
        Get notified when a buyer posts a request for a crop you grow. You’re already alerted for
        anything you have a live listing in — add more crops here.
      </p>
      {err && <div className="error">{err}</div>}

      <AddInterest commodities={addable} onAdd={add} lang={lang} />

      {loading ? (
        <p className="muted">{t("loading")}</p>
      ) : rows.length === 0 ? (
        <div className="empty">
          <span className="emoji">🔔</span>
          <p>No crop interests yet. Add a crop above to be alerted about matching buyer requests.</p>
          <Link href="/requests" className="btn">See open requests</Link>
        </div>
      ) : (
        <div className="grid" style={{ marginTop: 20 }}>
          {rows.map((r) => (
            <InterestCard key={r.commodity_id} r={r} name={cname(r)} t={t} onSave={add} onRemove={remove} />
          ))}
        </div>
      )}
    </div>
  );
}

function AddInterest({ commodities, onAdd, lang }) {
  const [cid, setCid] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const cname = (c) => (lang === "te" && c.name_te ? c.name_te : c.name);
  return (
    <div className="card" style={{ maxWidth: 560 }}>
      <h3 style={{ marginTop: 0 }}>Add a crop</h3>
      <div className="row" style={{ alignItems: "flex-end" }}>
        <div style={{ flex: "2 1 200px" }}>
          <label>Crop</label>
          <select value={cid} onChange={(e) => setCid(e.target.value)}>
            <option value="">—</option>
            {commodities.map((c) => <option key={c.id} value={c.id}>{cname(c)} ({c.category})</option>)}
          </select>
        </div>
        <div style={{ flex: "1 1 140px" }}>
          <label>Min price ₹/kg (optional)</label>
          <input value={minPrice} onChange={(e) => setMinPrice(e.target.value)} inputMode="decimal" placeholder="any" />
        </div>
        <div>
          <button disabled={!cid} onClick={() => { onAdd(cid, minPrice); setCid(""); setMinPrice(""); }}>Add</button>
        </div>
      </div>
      <p className="muted" style={{ fontSize: 13, marginBottom: 0 }}>
        Set a min price to only hear about requests at or above what’s worth your while.
      </p>
    </div>
  );
}

function InterestCard({ r, name, t, onSave, onRemove }) {
  const [minPrice, setMinPrice] = useState(r.min_price || "");
  return (
    <div className="card" style={{ borderLeft: r.open_request_count > 0 ? "4px solid var(--green-600)" : undefined }}>
      <div className="between">
        <h3 style={{ margin: 0 }}>{name}</h3>
        <button className="ghost" onClick={() => onRemove(r.commodity_id)} aria-label="remove">✕</button>
      </div>
      <div className="muted" style={{ fontSize: 13 }}>{r.category}</div>
      <div className="row" style={{ gap: 8, marginTop: 10, flexWrap: "wrap" }}>
        {r.open_request_count > 0 ? (
          <Link href="/requests" className="badge">{r.open_request_count} open request{r.open_request_count === 1 ? "" : "s"}</Link>
        ) : (
          <span className="badge grey">No open requests</span>
        )}
        {r.best_target != null && <span className="badge grey">best target ₹{r.best_target}{t("per_kg")}</span>}
      </div>
      <label style={{ marginTop: 10 }}>Min price (₹/kg)</label>
      <div className="row" style={{ alignItems: "flex-end" }}>
        <input value={minPrice} onChange={(e) => setMinPrice(e.target.value)} inputMode="decimal" placeholder="any" style={{ flex: 1 }} />
        <button className="ghost" onClick={() => onSave(r.commodity_id, minPrice)}>Save</button>
      </div>
    </div>
  );
}
