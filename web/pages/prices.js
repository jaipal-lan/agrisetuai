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
          <div className="grid">
            {commodities.map((c) => (
              <button key={c.commodity} className="card stat-card"
                      style={{ textAlign: "left", cursor: "pointer" }}
                      onClick={() => setSelected(c.commodity)}>
                <h3 style={{ margin: "0 0 6px" }}>{c.commodity}</h3>
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
                        <td>{m.market}</td>
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
