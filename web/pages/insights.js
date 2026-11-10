import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { useI18n } from "../lib/i18n";

const MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Personalised plan for a farmer: their crops' current-season tasks, matched
// government schemes and reviewed knowledge.
function FarmPlan({ plan, lang }) {
  if (!plan) return null;
  if (!plan.has_profile) {
    return (
      <div className="card" style={{ borderLeft: "4px solid var(--amber-600)", marginBottom: 20 }}>
        <b>📋 Your farm plan</b>
        <p className="muted" style={{ margin: "6px 0 0", fontSize: 14 }}>
          List your produce or complete your profile, and we’ll tailor the crop
          calendar, government schemes and advice to your crops and district.
        </p>
        <div style={{ marginTop: 10 }}>
          <Link href="/sell" className="btn ghost">List produce</Link>{" "}
          <Link href="/onboarding" className="btn ghost">Complete profile</Link>
        </div>
      </div>
    );
  }
  return (
    <section className="disc-section" style={{ marginBottom: 8 }}>
      <div className="section-head">
        <h2 style={{ marginBottom: 2 }}>📋 Your farm plan</h2>
      </div>
      <p className="muted" style={{ marginTop: 0, fontSize: 14 }}>
        For your crops{plan.crops.length ? ` (${plan.crops.join(", ")})` : ""}
        {plan.district ? ` · ${plan.district}${plan.state ? `, ${plan.state}` : ""}` : ""}
        {" "}· {MONTHS[plan.month]}
      </p>

      {/* Weather + plain cautions for the farmer's locality */}
      {plan.weather && (
        <div className="card" style={{ marginBottom: 14 }}>
          <div className="between">
            <b>🌦️ Weather</b>
            <span className="muted" style={{ fontSize: 12 }}>
              {plan.weather.observed_at} · {plan.weather.forecast_horizon}
            </span>
          </div>
          {plan.weather.payload && (
            <div className="muted" style={{ fontSize: 14, marginTop: 4 }}>
              {plan.weather.payload.rain_prob_pct != null && <>🌧️ {plan.weather.payload.rain_prob_pct}% rain · </>}
              {plan.weather.payload.temp_max_c != null && <>🌡️ {plan.weather.payload.temp_min_c}–{plan.weather.payload.temp_max_c}°C</>}
              {plan.weather.payload.wind_kmph != null && <> · 💨 {plan.weather.payload.wind_kmph} km/h</>}
            </div>
          )}
          {plan.weather.advice.map((a, i) => (
            <div key={i} className={a.level === "warning" ? "error" : "ok"}
                 style={{ fontSize: 13, marginTop: 6 }}>
              {a.level === "warning" ? "⚠️ " : "• "}{a.text}
            </div>
          ))}
          <div className="disclaimer">{plan.weather.source_note}</div>
        </div>
      )}

      {/* This season's tasks */}
      {plan.current_tasks.length > 0 && (
        <div className="card" style={{ borderLeft: "4px solid var(--amber-600)", marginBottom: 14 }}>
          <b>🌱 Do this season ({MONTHS[plan.month]})</b>
          {plan.current_tasks.map((t) => (
            <div key={t.id} className="followup-row">
              <b style={{ textTransform: "capitalize" }}>{t.crop}</b>
              <span className="muted" style={{ fontSize: 13 }}> · {t.window}</span>
              <div style={{ fontSize: 14 }}>{lang === "te" && t.task_te ? t.task_te : t.task}</div>
            </div>
          ))}
        </div>
      )}

      {/* Matched schemes */}
      {plan.schemes.length > 0 && (
        <>
          <h3 style={{ margin: "6px 0" }}>Schemes you may be eligible for</h3>
          <div className="grid">
            {plan.schemes.map((s) => (
              <div className="card" key={s.id}>
                <div className="between">
                  <h3 style={{ fontSize: 16 }}>{lang === "te" && s.name_te ? s.name_te : s.name}</h3>
                  {s.match_reason && <span className="badge">{s.match_reason}</span>}
                </div>
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
        </>
      )}

      {/* Per-crop calendar with the current window highlighted */}
      {plan.calendar.map((grp) => (
        <div key={grp.crop} style={{ marginTop: 16 }}>
          <h3 style={{ margin: "6px 0", textTransform: "capitalize" }}>{grp.crop} calendar</h3>
          <div className="grid">
            {grp.tasks.map((c) => (
              <div className="card" key={c.id}
                   style={c.current ? { borderLeft: "4px solid var(--amber-600)" } : {}}>
                <div className="between">
                  <h3 style={{ fontSize: 15 }}>{c.window}</h3>
                  {c.current ? <span className="badge amber">now</span>
                             : <span className={`badge ${c.kind === "reviewed" ? "" : "grey"}`}>{c.kind}</span>}
                </div>
                <div style={{ fontSize: 14 }}>{lang === "te" && c.task_te ? c.task_te : c.task}</div>
                {c.months?.length > 0 && (
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                    {c.months.map((m) => MONTHS[m]).join(", ")}
                  </div>
                )}
                <div className="disclaimer">{c.source}</div>
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* Reviewed knowledge for the farmer's crops */}
      {plan.knowledge.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h3 style={{ margin: "6px 0" }}>Reviewed guidance for your crops</h3>
          <div className="pill-row">
            {plan.knowledge.map((k) => (
              k.source_url
                ? <a key={k.id} className="pill" href={k.source_url} target="_blank" rel="noreferrer">
                    {lang === "te" && k.title_te ? k.title_te : k.title} ↗
                  </a>
                : <span key={k.id} className="pill">{lang === "te" && k.title_te ? k.title_te : k.title}</span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

export default function Insights() {
  const { t, lang } = useI18n();
  const [me, setMe] = useState(null);
  const [plan, setPlan] = useState(null);
  const [prices, setPrices] = useState([]);
  const [schemes, setSchemes] = useState([]);
  const [err, setErr] = useState(null);

  const isSeller = me && ["farmer", "fpo"].includes(me.role);

  useEffect(() => { setMe(getUser()); }, []);

  useEffect(() => {
    Promise.all([api("/market-prices"), api("/schemes")])
      .then(([p, s]) => { setPrices(p); setSchemes(s); })
      .catch((e) => setErr(e.message));
  }, []);

  useEffect(() => {
    if (isSeller) api("/my-farm-plan").then(setPlan).catch(() => {});
  }, [isSeller]);

  return (
    <div>
      <h1>{t("insights")}</h1>
      <p className="tagline">
        Official market observations & schemes — with source and date. A past modal
        price is not a guaranteed sale price.
      </p>
      {err && <div className="error">{err}</div>}

      {isSeller && <FarmPlan plan={plan} lang={lang} />}

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

      <h2 style={{ marginTop: 24 }}>All government schemes</h2>
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
