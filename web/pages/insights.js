import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";

export default function Insights() {
  const { t, lang } = useI18n();
  const [prices, setPrices] = useState([]);
  const [schemes, setSchemes] = useState([]);
  const [calendar, setCalendar] = useState([]);
  const [err, setErr] = useState(null);

  useEffect(() => {
    Promise.all([
      api("/market-prices"),
      api("/schemes"),
      api("/crop-calendar?crop=paddy"),
    ])
      .then(([p, s, c]) => {
        setPrices(p);
        setSchemes(s);
        setCalendar(c);
      })
      .catch((e) => setErr(e.message));
  }, []);

  return (
    <div>
      <h1>{t("insights")}</h1>
      <p className="tagline">
        Official market observations & schemes — with source and date. A past modal
        price is not a guaranteed sale price.
      </p>
      {err && <div className="error">{err}</div>}

      <h2>Market prices</h2>
      {prices.length === 0 ? (
        <p className="muted">No prices yet.</p>
      ) : (
        <table>
          <thead>
            <tr><th>Market</th><th>{t("commodity")}</th><th>Min</th><th>Modal</th><th>Max</th><th>As of</th></tr>
          </thead>
          <tbody>
            {prices.map((p) => (
              <tr key={p.id}>
                <td>{p.market}</td>
                <td>{p.commodity}{p.variety ? ` (${p.variety})` : ""}</td>
                <td>₹{p.min_price}</td>
                <td><b>₹{p.modal_price}</b></td>
                <td>₹{p.max_price}</td>
                <td className="muted">{p.as_of}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {prices[0] && <div className="disclaimer">{prices[0].disclaimer} · {prices[0].unit}, {prices[0].source_name}</div>}

      <h2>Crop calendar — paddy</h2>
      <div className="grid">
        {calendar.map((c) => (
          <div className="card" key={c.id}>
            <div className="between">
              <h3 style={{ fontSize: 15 }}>{c.window}</h3>
              <span className={`badge ${c.kind === "reviewed" ? "" : "grey"}`}>{c.kind}</span>
            </div>
            <div style={{ fontSize: 14 }}>{lang === "te" && c.task_te ? c.task_te : c.task}</div>
            <div className="disclaimer">{c.source}</div>
          </div>
        ))}
      </div>

      <h2>Government schemes</h2>
      <div className="grid">
        {schemes.map((s) => (
          <div className="card" key={s.id}>
            <h3 style={{ fontSize: 16 }}>{lang === "te" && s.name_te ? s.name_te : s.name}</h3>
            <div className="muted" style={{ fontSize: 13 }}>{s.department}</div>
            <div style={{ fontSize: 14, marginTop: 8 }}>{s.eligibility}</div>
            {s.documents && <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>Docs: {s.documents}</div>}
            <div style={{ marginTop: 8 }}>
              <a href={s.source_url} target="_blank" rel="noreferrer">Official source ↗</a>
              <span className="muted" style={{ fontSize: 12 }}> · checked {s.last_checked}</span>
            </div>
            <div className="disclaimer">{s.disclaimer}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
