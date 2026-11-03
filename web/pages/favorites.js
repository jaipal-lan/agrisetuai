import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

export default function Favorites() {
  const { t, lang } = useI18n();
  const [me, setMe] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => { setMe(getUser()); }, []);
  usePoll(() => {
    api("/watchlist").then(setRows).catch((e) => setErr(e.message)).finally(() => setLoading(false));
  }, 20000);

  const gate = roleGate(me, GROUPS.buyer, { label: "favorites" });
  if (gate) return gate;

  async function saveTarget(commodity_id, target_price) {
    setErr(null);
    try {
      await api("/watchlist", { method: "POST", body: { commodity_id, target_price: target_price ? Number(target_price) : undefined } });
      api("/watchlist").then(setRows);
    } catch (e) { setErr(e.message); }
  }
  async function remove(commodity_id) {
    setErr(null);
    try { await api(`/watchlist/${commodity_id}`, { method: "DELETE" }); setRows((r) => r.filter((x) => x.commodity_id !== commodity_id)); }
    catch (e) { setErr(e.message); }
  }

  const name = (r) => (lang === "te" && r.commodity_te ? r.commodity_te : r.commodity);

  return (
    <div>
      <h1>{t("favorites")}</h1>
      <p className="tagline">Watched products — we alert you when a new or cheaper offering appears.</p>
      {err && <div className="error">{err}</div>}

      {loading ? (
        <p className="muted">{t("loading")}</p>
      ) : rows.length === 0 ? (
        <div className="empty">
          <span className="emoji">⭐</span>
          <p>No favorites yet. Open any product and tap “Watch this product”.</p>
          <Link href="/" className="btn">Browse the market</Link>
        </div>
      ) : (
        <div className="grid">
          {rows.map((r) => (
            <WatchCard key={r.commodity_id} r={r} name={name(r)} t={t}
                       onSave={saveTarget} onRemove={remove} />
          ))}
        </div>
      )}
    </div>
  );
}

function WatchCard({ r, name, t, onSave, onRemove }) {
  const [target, setTarget] = useState(r.target_price || "");
  return (
    <div className="card" style={{ borderLeft: r.target_met ? "4px solid var(--green-600)" : undefined }}>
      <div className="between">
        <h3 style={{ margin: 0 }}><Link href={`/product/${r.commodity_id}`}>{name}</Link></h3>
        <button className="ghost" onClick={() => onRemove(r.commodity_id)}>✕</button>
      </div>
      <div className="muted" style={{ fontSize: 13 }}>{r.category}</div>
      {r.best_price != null ? (
        <div className="price" style={{ marginTop: 8 }}>₹{r.best_price}<small> {t("per_kg")} best</small></div>
      ) : (
        <div className="badge grey" style={{ marginTop: 8 }}>Out of stock</div>
      )}
      <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
        {r.offering_count} offering{r.offering_count === 1 ? "" : "s"} · {r.place_count} place{r.place_count === 1 ? "" : "s"}
      </div>
      {r.target_met && <div className="ok" style={{ fontSize: 13, marginTop: 8 }}>✓ At or below your target!</div>}
      <label>Alert target (₹/kg)</label>
      <div className="row" style={{ alignItems: "flex-end" }}>
        <input value={target} onChange={(e) => setTarget(e.target.value)} inputMode="decimal" placeholder="none" style={{ flex: 1 }} />
        <button className="ghost" onClick={() => onSave(r.commodity_id, target)}>Save</button>
      </div>
    </div>
  );
}
