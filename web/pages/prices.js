import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";

// Today's government-declared mandi prices, all-India, product-wise.
export default function Prices() {
  const { t } = useI18n();
  const [commodities, setCommodities] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState(null);
  const [query, setQuery] = useState("");
  const [cat, setCat] = useState("all");

  const CAT_LABELS = {
    all: "All", vegetable: "🥬 Vegetables", fruit: "🍎 Fruits", cereal: "🌾 Cereals",
    pulse: "🫘 Pulses", oilseed: "🛢️ Oilseeds", spice: "🌶️ Spices",
    dairy_meat: "🥛 Dairy & meat", other: "Other",
  };
  const cats = ["all", ...Array.from(new Set(commodities.map((c) => c.category || "other")))
    .sort((a, b) => Object.keys(CAT_LABELS).indexOf(a) - Object.keys(CAT_LABELS).indexOf(b))];
  const q = query.trim().toLowerCase();
  const shown = commodities.filter((c) =>
    (cat === "all" || (c.category || "other") === cat) &&
    (!q || (c.commodity || "").toLowerCase().includes(q)));

  useEffect(() => {
    api("/market-prices/commodities").then(setCommodities).catch((e) => setErr(e.message));
  }, []);

  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    api(`/market-prices/all-india?commodity=${encodeURIComponent(selected)}`)
      .then(setDetail).catch((e) => setErr(e.message));
  }, [selected]);

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
          <div className="row" style={{ flexWrap: "wrap", gap: 6, marginBottom: 14 }}>
            {cats.map((cx) => (
              <button key={cx} className={cat === cx ? "" : "ghost"}
                      style={{ padding: "4px 10px", fontSize: 13 }}
                      onClick={() => setCat(cx)}>
                {CAT_LABELS[cx] || cx}
              </button>
            ))}
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
                  ₹{c.modal_min}{c.modal_max !== c.modal_min ? `–${c.modal_max}` : ""}
                  <small> {c.unit}</small>
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
          <h2 style={{ marginTop: 12 }}>{detail.commodity}</h2>
          <div className="stat-strip">
            <div><b>₹{detail.modal_avg}</b> avg modal</div>
            <div><b>₹{detail.modal_min}–{detail.modal_max}</b> range</div>
            <div><b>{detail.market_count}</b> markets</div>
          </div>
          <div className="muted" style={{ fontSize: 13, margin: "6px 0 14px" }}>
            {detail.unit} · as of {detail.as_of} · {detail.source_name}
          </div>
          {detail.states.map((s) => (
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
                        <td>₹{m.min_price}</td>
                        <td><b>₹{m.modal_price}</b></td>
                        <td>₹{m.max_price}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
          <div className="disclaimer">{detail.disclaimer}</div>
        </>
      )}
    </div>
  );
}
