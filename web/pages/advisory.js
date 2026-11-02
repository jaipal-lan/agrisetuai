import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { useI18n } from "../lib/i18n";

function Triage({ ai }) {
  if (!ai) return null;
  return (
    <div style={{ marginTop: 12 }}>
      <div className="row" style={{ gap: 8 }}>
        <span className={`badge ${ai.confidence === "high" ? "" : ai.confidence === "medium" ? "amber" : "grey"}`}>
          confidence: {ai.confidence}
        </span>
        {ai.escalate && <span className="badge amber">escalate to agronomist</span>}
        {ai.source_name && <span className="pill-tag">source: {ai.source_name}</span>}
      </div>

      <h4 style={{ margin: "14px 0 6px" }}>Likely causes (not a diagnosis)</h4>
      <ul>
        {ai.likely_causes.map((c, i) => (
          <li key={i}>
            <b>{c.label}</b> — {c.likelihood} · uncertainty {c.uncertainty}
          </li>
        ))}
      </ul>

      {ai.immediate_steps && (
        <>
          <h4 style={{ margin: "14px 0 6px" }}>Immediate low-risk steps</h4>
          <ul>{ai.immediate_steps.map((s, i) => <li key={i}>{s}</li>)}</ul>
        </>
      )}
      {ai.ipm_order && (
        <>
          <h4 style={{ margin: "14px 0 6px" }}>IPM-first order</h4>
          <ol>{ai.ipm_order.map((s, i) => <li key={i}>{s}</li>)}</ol>
        </>
      )}
      <div className="ok" style={{ fontSize: 13 }}>
        {ai.pesticide_note}
      </div>
      <div className="disclaimer">{ai.disclaimer}</div>
    </div>
  );
}

export default function Advisory() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [cases, setCases] = useState([]);
  const [form, setForm] = useState({ crop: "paddy", growth_stage: "", notes: "" });
  const [result, setResult] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function load() {
    try {
      setCases(await api("/ai/crop-cases"));
    } catch (e) {
      setErr(e.message);
    }
  }
  useEffect(() => {
    setMe(getUser());
    load();
  }, []);

  async function submit() {
    setErr(null);
    setResult(null);
    setBusy(true);
    try {
      const c = await api("/ai/crop-cases", {
        method: "POST",
        body: {
          crop: form.crop,
          growth_stage: form.growth_stage || undefined,
          notes: form.notes || undefined,
        },
      });
      setResult(c.ai_output);
      load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!me) {
    return (
      <div>
        <p className="muted">Log in to use the crop assistant.</p>
        <Link href="/login" className="btn">{t("login")}</Link>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 700 }}>
      <h1>{t("advisory")}</h1>
      <p className="tagline">
        Decision-support, not a diagnosis. We never invent pesticide doses — only
        reviewed, label-sourced guidance, with escalation to a qualified agronomist.
      </p>
      {err && <div className="error">{err}</div>}

      <div className="card">
        <div className="row">
          <div style={{ flex: 1 }}>
            <label>{t("commodity")} / crop</label>
            <input value={form.crop} onChange={(e) => set("crop", e.target.value)} placeholder="paddy, red chilli…" />
          </div>
          <div style={{ flex: 1 }}>
            <label>Growth stage</label>
            <input value={form.growth_stage} onChange={(e) => set("growth_stage", e.target.value)} placeholder="tillering, panicle…" />
          </div>
        </div>
        <label>What do you see? (symptoms)</label>
        <textarea rows={3} value={form.notes} onChange={(e) => set("notes", e.target.value)}
          placeholder="e.g. spreading leaf spots and lesions on tillers" />
        <div style={{ marginTop: 12 }}>
          <button onClick={submit} disabled={busy || !form.crop}>Get guidance</button>
        </div>
        <Triage ai={result} />
      </div>

      <h2>Recent cases</h2>
      {cases.length === 0 ? (
        <p className="muted">No cases yet.</p>
      ) : (
        cases.map((c) => (
          <div className="card" key={c.id} style={{ marginBottom: 12 }}>
            <div className="between">
              <h3>{c.crop} {c.growth_stage ? `· ${c.growth_stage}` : ""}</h3>
              <span className={`badge ${c.status === "reviewed" ? "" : c.escalated ? "amber" : "grey"}`}>{c.status}</span>
            </div>
            {c.notes && <div className="muted" style={{ fontSize: 14 }}>{c.notes}</div>}
            {c.expert_review && (
              <div className="ok" style={{ marginTop: 8, fontSize: 14 }}>
                <b>Agronomist:</b> {c.expert_review.note}
                {c.expert_review.approved_advice ? ` — ${c.expert_review.approved_advice}` : ""}
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
}
