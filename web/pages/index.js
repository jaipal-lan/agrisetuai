import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";

export default function Marketplace() {
  const { t, lang } = useI18n();
  const [commodities, setCommodities] = useState([]);
  const [listings, setListings] = useState([]);
  const [commodityId, setCommodityId] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  const cmap = Object.fromEntries(commodities.map((c) => [c.id, c]));

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const params = new URLSearchParams();
      if (commodityId) params.set("commodity_id", commodityId);
      if (maxPrice) params.set("max_price", maxPrice);
      const rows = await api(`/listings?${params.toString()}`);
      setListings(rows);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    api("/catalog/commodities").then(setCommodities).catch(() => {});
  }, []);
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [commodityId, maxPrice]);

  function cname(c) {
    if (!c) return "—";
    return lang === "te" && c.name_te ? c.name_te : c.name;
  }

  return (
    <div>
      <h1>{t("marketplace")}</h1>
      <p className="tagline">{t("tagline")}</p>

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="row">
          <div style={{ flex: 1, minWidth: 180 }}>
            <label>{t("commodity")}</label>
            <select value={commodityId} onChange={(e) => setCommodityId(e.target.value)}>
              <option value="">{t("search")}…</option>
              {commodities.map((c) => (
                <option key={c.id} value={c.id}>{cname(c)} ({c.category})</option>
              ))}
            </select>
          </div>
          <div style={{ width: 160 }}>
            <label>{t("price")} ≤</label>
            <input
              value={maxPrice}
              onChange={(e) => setMaxPrice(e.target.value.replace(/[^\d.]/g, ""))}
              placeholder="₹/kg"
              inputMode="decimal"
            />
          </div>
        </div>
      </div>

      {err && <div className="error">{err}</div>}
      {loading ? (
        <p className="muted">{t("loading")}</p>
      ) : listings.length === 0 ? (
        <p className="muted">No open listings yet.</p>
      ) : (
        <div className="grid">
          {listings.map((l) => {
            const c = cmap[l.commodity_id];
            return (
              <Link key={l.id} href={`/listing/${l.id}`} className="card" style={{ color: "inherit" }}>
                <div className="between">
                  <h3>{cname(c)}</h3>
                  <span className={`badge ${l.claim_status === "organic" ? "" : "grey"}`}>
                    {l.claim_status}
                  </span>
                </div>
                <div className="muted" style={{ fontSize: 13, marginBottom: 10 }}>
                  {c ? c.category : ""} · HY {l.harvest_year || "—"}
                </div>
                <div className="price">
                  ₹{l.asking_price}<small> {t("per_kg")}</small>
                </div>
                <div className="muted" style={{ fontSize: 14, marginTop: 6 }}>
                  {t("available")}: {l.available_qty} {l.unit}
                </div>
                {l.negotiable && (
                  <div className="badge amber" style={{ marginTop: 10 }}>Negotiable</div>
                )}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
