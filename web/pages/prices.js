import { useEffect, useMemo, useState } from "react";

import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";

// Is this a per-quintal unit (so it can be shown per-kg)? AGMARKNET is mostly
// ₹/quintal, but a few commodities (eggs, coconut) report per piece/unit — those
// keep their native unit and the kg toggle doesn't apply to them.
const isQuintal = (unit) => /qtl|quintal/i.test(unit || "");

// Format a numeric price for display under the chosen unit mode.
function priceText(value, unit, unitMode) {
  const n = Number(value);
  if (!isFinite(n)) return "—";
  if (unitMode === "kg" && isQuintal(unit)) return `₹${(n / 100).toFixed(2)}`;
  return `₹${Number.isInteger(n) ? n : n.toFixed(2)}`;
}
const unitLabel = (unit, unitMode) =>
  unitMode === "kg" && isQuintal(unit) ? "₹/kg" : (unit || "₹/qtl");

// Today's government-declared mandi prices, all-India, product-wise.
export default function Prices() {
  const { t } = useI18n();
  const [commodities, setCommodities] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState(null);
  const [query, setQuery] = useState("");
  const [cat, setCat] = useState("all");
  const [unitMode, setUnitMode] = useState("qtl");   // qtl | kg
  const [sortBy, setSortBy] = useState("name");      // product list sort
  const [stateFilter, setStateFilter] = useState("all"); // detail area filter
  const [mktSort, setMktSort] = useState("state");   // detail market sort

  const CAT_LABELS = {
    all: "All", vegetable: "🥬 Vegetables", fruit: "🍎 Fruits", cereal: "🌾 Cereals",
    pulse: "🫘 Pulses", oilseed: "🛢️ Oilseeds", spice: "🌶️ Spices",
    dairy_meat: "🥛 Dairy & meat", other: "Other",
  };
  const cats = ["all", ...Array.from(new Set(commodities.map((c) => c.category || "other")))
    .sort((a, b) => Object.keys(CAT_LABELS).indexOf(a) - Object.keys(CAT_LABELS).indexOf(b))];
  const q = query.trim().toLowerCase();
  const shown = useMemo(() => {
    const mid = (c) => (Number(c.modal_min) + Number(c.modal_max)) / 2;
    const list = commodities.filter((c) =>
      (cat === "all" || (c.category || "other") === cat) &&
      (!q || (c.commodity || "").toLowerCase().includes(q)));
    if (sortBy === "price_lo") list.sort((a, b) => Number(a.modal_min) - Number(b.modal_min));
    else if (sortBy === "price_hi") list.sort((a, b) => Number(b.modal_max) - Number(a.modal_max));
    else list.sort((a, b) => (a.commodity || "").localeCompare(b.commodity || ""));
    return list;
  }, [commodities, cat, q, sortBy]);

  useEffect(() => {
    api("/market-prices/commodities").then(setCommodities).catch((e) => setErr(e.message));
  }, []);

  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    setStateFilter("all"); setMktSort("state");
    api(`/market-prices/all-india?commodity=${encodeURIComponent(selected)}`)
      .then(setDetail).catch((e) => setErr(e.message));
  }, [selected]);

  // Flattened + filtered + sorted markets for the detail view.
  const flatMarkets = useMemo(() => {
    if (!detail) return [];
    let rows = detail.states.flatMap((s) => s.markets.map((m) => ({ ...m, state: m.state || s.state })));
    if (stateFilter !== "all") rows = rows.filter((m) => m.state === stateFilter);
    if (mktSort === "modal_lo") rows.sort((a, b) => Number(a.modal_price) - Number(b.modal_price));
    else if (mktSort === "modal_hi") rows.sort((a, b) => Number(b.modal_price) - Number(a.modal_price));
    return rows;
  }, [detail, stateFilter, mktSort]);

  const detailStates = detail ? detail.states.map((s) => s.state) : [];
  const cheapest = flatMarkets.length
    ? Math.min(...flatMarkets.map((m) => Number(m.modal_price))) : null;

  const UnitToggle = ({ unit }) => (
    isQuintal(unit) ? (
      <div className="seg" aria-label="price unit" style={{ display: "inline-flex" }}>
        <button className={unitMode === "qtl" ? "seg-on" : ""} onClick={() => setUnitMode("qtl")}>₹/quintal</button>
        <button className={unitMode === "kg" ? "seg-on" : ""} onClick={() => setUnitMode("kg")}>₹/kg</button>
      </div>
    ) : null
  );

  return (
    <div>
      <h1>{t("market_prices")}</h1>
      <p className="tagline">
        Today's government-declared mandi prices across India. A past modal price is
        not a guaranteed sale price on this platform.
      </p>
      {err && <div className="error">{err}</div>}

      {!selected ? (
        <>
          <p className="muted" style={{ fontSize: 14 }}>Tap a product to see its price across all markets.</p>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search a product (e.g. tomato, paddy, apple)…"
            style={{ fontSize: 16, width: "100%", maxWidth: 420, marginBottom: 10 }}
          />
          <div className="row" style={{ flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
            {cats.map((cx) => (
              <button key={cx} className={cat === cx ? "" : "ghost"}
                      style={{ padding: "4px 10px", fontSize: 13 }}
                      onClick={() => setCat(cx)}>
                {CAT_LABELS[cx] || cx}
              </button>
            ))}
          </div>
          <div className="row" style={{ flexWrap: "wrap", gap: 10, marginBottom: 12, alignItems: "center" }}>
            <label className="muted" style={{ fontSize: 13 }}>
              Sort:{" "}
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
                <option value="name">Name (A–Z)</option>
                <option value="price_lo">Price: low → high</option>
                <option value="price_hi">Price: high → low</option>
              </select>
            </label>
            <div className="seg" aria-label="price unit">
              <button className={unitMode === "qtl" ? "seg-on" : ""} onClick={() => setUnitMode("qtl")}>₹/quintal</button>
              <button className={unitMode === "kg" ? "seg-on" : ""} onClick={() => setUnitMode("kg")}>₹/kg</button>
            </div>
          </div>
          <p className="muted" style={{ fontSize: 13, marginTop: -6 }}>
            {shown.length} of {commodities.length} products
          </p>
          <div className="grid">
            {shown.map((c) => (
              <button key={c.commodity} className="card stat-card"
                      style={{ textAlign: "left", cursor: "pointer", color: "var(--ink)" }}
                      onClick={() => setSelected(c.commodity)}>
                <div className="between" style={{ alignItems: "flex-start" }}>
                  <h3 style={{ margin: "0 0 6px", color: "var(--ink)" }}>{c.commodity}</h3>
                  {c.category && c.category !== "other" && (
                    <span className="pill-tag">{(CAT_LABELS[c.category] || c.category).replace(/^\S+\s/, "")}</span>
                  )}
                </div>
                <div className="price" style={{ fontSize: 20 }}>
                  {priceText(c.modal_min, c.unit, unitMode)}
                  {Number(c.modal_max) !== Number(c.modal_min)
                    ? `–${priceText(c.modal_max, c.unit, unitMode).replace("₹", "")}` : ""}
                  <small> {unitLabel(c.unit, unitMode)}</small>
                </div>
                <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                  {c.market_count} markets · {c.state_count} states · {c.as_of}
                </div>
              </button>
            ))}
          </div>
          {shown.length === 0 && <p className="muted">No products match that search.</p>}
        </>
      ) : !detail ? (
        <p className="muted">{t("loading")}</p>
      ) : (
        <>
          <button className="ghost" onClick={() => setSelected(null)}>← All products</button>
          <div className="between" style={{ marginTop: 12, flexWrap: "wrap", gap: 8 }}>
            <h2 style={{ margin: 0 }}>{detail.commodity}</h2>
            <UnitToggle unit={detail.unit} />
          </div>
          <div className="stat-strip">
            <div><b>{priceText(detail.modal_avg, detail.unit, unitMode)}</b> avg modal</div>
            <div><b>{priceText(detail.modal_min, detail.unit, unitMode)}–{priceText(detail.modal_max, detail.unit, unitMode).replace("₹", "")}</b> range</div>
            <div><b>{detail.market_count}</b> markets</div>
          </div>
          <div className="muted" style={{ fontSize: 13, margin: "6px 0 14px" }}>
            {unitLabel(detail.unit, unitMode)} · as of {detail.as_of} · {detail.source_name}
          </div>

          {/* Sort + area filter */}
          <div className="row" style={{ flexWrap: "wrap", gap: 10, marginBottom: 12, alignItems: "center" }}>
            <label className="muted" style={{ fontSize: 13 }}>
              Area:{" "}
              <select value={stateFilter} onChange={(e) => setStateFilter(e.target.value)}>
                <option value="all">All states</option>
                {detailStates.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <label className="muted" style={{ fontSize: 13 }}>
              Sort markets:{" "}
              <select value={mktSort} onChange={(e) => setMktSort(e.target.value)}>
                <option value="state">By state</option>
                <option value="modal_lo">Modal: low → high (best buy)</option>
                <option value="modal_hi">Modal: high → low (best sell)</option>
              </select>
            </label>
            <span className="muted" style={{ fontSize: 13 }}>{flatMarkets.length} markets</span>
          </div>

          {mktSort === "state" ? (
            // Grouped by state (respecting the area filter).
            detail.states
              .filter((s) => stateFilter === "all" || s.state === stateFilter)
              .map((s) => (
                <div key={s.state} style={{ marginBottom: 16 }}>
                  <h3 style={{ margin: "6px 0" }}>{s.state}</h3>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr><th>Market</th><th>Variety</th><th>Min</th><th>Modal</th><th>Max</th></tr>
                      </thead>
                      <tbody>
                        {s.markets.map((m) => (
                          <tr key={m.id}>
                            <td>{m.market}{m.stale && <span className="pill-tag" style={{ marginLeft: 6 }}>stale</span>}</td>
                            <td className="muted">{m.variety || "—"}</td>
                            <td>{priceText(m.min_price, detail.unit, unitMode)}</td>
                            <td><b>{priceText(m.modal_price, detail.unit, unitMode)}</b></td>
                            <td>{priceText(m.max_price, detail.unit, unitMode)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))
          ) : (
            // Flat, price-sorted — cheapest/priciest market across all areas.
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Market</th><th>State</th><th>Variety</th><th>Min</th><th>Modal</th><th>Max</th></tr>
                </thead>
                <tbody>
                  {flatMarkets.map((m) => (
                    <tr key={m.id}>
                      <td>
                        {m.market}
                        {Number(m.modal_price) === cheapest && (
                          <span className="badge green" style={{ marginLeft: 6 }}>best</span>
                        )}
                        {m.stale && <span className="pill-tag" style={{ marginLeft: 6 }}>stale</span>}
                      </td>
                      <td className="muted">{m.state}</td>
                      <td className="muted">{m.variety || "—"}</td>
                      <td>{priceText(m.min_price, detail.unit, unitMode)}</td>
                      <td><b>{priceText(m.modal_price, detail.unit, unitMode)}</b></td>
                      <td>{priceText(m.max_price, detail.unit, unitMode)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="disclaimer">{detail.disclaimer}</div>
        </>
      )}
    </div>
  );
}
