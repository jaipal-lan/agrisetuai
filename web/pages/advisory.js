import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getToken, getUser } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/api";

async function uploadImage(file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API_BASE}/media/upload`, {
    method: "POST", headers: { Authorization: `Bearer ${getToken()}` }, body: fd,
  });
  if (!res.ok) throw new Error((await res.json()).detail || "Upload failed");
  return res.json();
}

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
      {ai.visual_prescreen && (
        <div className="card" style={{ marginTop: 12, borderLeft: "4px solid var(--amber-600)" }}>
          <b>📷 Visual pre-screen (beta)</b>
          <div style={{ fontSize: 14, marginTop: 4 }}>
            {ai.visual_prescreen.images_received > 0
              ? `${ai.visual_prescreen.images_received} image(s): ${ai.visual_prescreen.hint}`
              : ai.visual_prescreen.recommendation}
          </div>
          <div className="disclaimer">{ai.visual_prescreen.note}</div>
        </div>
      )}
      <div className="ok" style={{ fontSize: 13 }}>
        {ai.pesticide_note}
      </div>
      <div className="disclaimer">{ai.disclaimer}</div>
    </div>
  );
}

const ACK_LABEL = { done: "✓ Done", doing: "Working on it", question: "Question" };

// Lets a farmer reply to a piece of advice so the agent knows they acted on it.
function AckBox({ note, onDone }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  if (note.farmer_ack) {
    return (
      <div className="ack-done">
        <b>You replied:</b> {ACK_LABEL[note.farmer_ack_status] || note.farmer_ack_status}
        {note.farmer_ack_note ? ` — “${note.farmer_ack_note}”` : ""}
      </div>
    );
  }
  async function send(status) {
    setBusy(true); setErr(null);
    try {
      await api(`/my-advisory/${note.id}/acknowledge`, {
        method: "POST", body: { status, note: text || undefined },
      });
      onDone();
    } catch (e) { setErr(e.message); setBusy(false); }
  }
  return (
    <div className="ack-box">
      {!open ? (
        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          <button className="ghost" disabled={busy} onClick={() => send("done")}>✓ I did this</button>
          <button className="ghost" disabled={busy} onClick={() => send("doing")}>Working on it</button>
          <button className="ghost" disabled={busy} onClick={() => setOpen(true)}>I have a question</button>
        </div>
      ) : (
        <div>
          <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)}
                    placeholder="Your question for the agent…" />
          <div className="row" style={{ gap: 8, marginTop: 6 }}>
            <button disabled={busy} onClick={() => send("question")}>Send to agent</button>
            <button className="ghost" disabled={busy} onClick={() => setOpen(false)}>Cancel</button>
          </div>
        </div>
      )}
      {err && <div className="error" style={{ marginTop: 6 }}>{err}</div>}
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
  const [images, setImages] = useState([]);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function addPhotos(files) {
    setErr(null);
    try {
      const keys = [];
      for (const f of files) keys.push((await uploadImage(f)).object_key);
      setImages((prev) => [...prev, ...keys]);
    } catch (e) {
      setErr(e.message);
    }
  }

  const [myAdv, setMyAdv] = useState(null);
  const isSeller = me && ["farmer", "fpo"].includes(me.role);

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
  function loadMyAdv() {
    api("/my-advisory").then(setMyAdv).catch(() => {});
  }
  useEffect(() => {
    if (isSeller) loadMyAdv();
  }, [isSeller]);

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
          media_refs: images.length ? images : undefined,
        },
      });
      setResult(c.ai_output);
      setImages([]);
      load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const gate = roleGate(me, GROUPS.advisor, { label: "the crop assistant" });
  if (gate) return gate;

  return (
    <div style={{ maxWidth: 700 }}>
      <h1>{t("advisory")}</h1>
      <p className="tagline">
        Decision-support, not a diagnosis. We never invent pesticide doses — only
        reviewed, label-sourced guidance, with escalation to a qualified agronomist.
      </p>
      {err && <div className="error">{err}</div>}

      {isSeller && myAdv && (myAdv.notes.length > 0 || myAdv.upcoming.length > 0) && (
        <div style={{ marginBottom: 22 }}>
          <h2 style={{ marginTop: 0 }}>Advice from your field agent</h2>
          {myAdv.upcoming.length > 0 && (
            <div className="card" style={{ borderLeft: "4px solid var(--amber-600)", marginBottom: 12 }}>
              <b>📌 Upcoming follow-ups</b>
              {myAdv.upcoming.map((f) => (
                <div key={f.id} className="followup-row">
                  <b>{f.crop || "general"}</b>
                  <span className="muted" style={{ fontSize: 13 }}> · {f.agent_name || "your agent"}</span>
                  {f.recommendation && <div style={{ fontSize: 14 }}>{f.recommendation}</div>}
                  <div className="muted" style={{ fontSize: 12 }}>
                    follow-up {f.follow_up_date} ({f.days_until === 0 ? "today" : `in ${f.days_until}d`})
                  </div>
                  <AckBox note={f} onDone={loadMyAdv} />
                </div>
              ))}
            </div>
          )}
          {myAdv.notes.map((n) => (
            <div className="card" key={n.id} style={{ marginBottom: 10 }}>
              <div className="between">
                <b>{n.crop || "general"}</b>
                <span className="muted" style={{ fontSize: 12 }}>
                  {n.agent_name ? `${n.agent_name} · ` : ""}{n.created_at ? new Date(n.created_at).toLocaleDateString() : ""}
                </span>
              </div>
              {n.observation && <div style={{ fontSize: 14 }}>{n.observation}</div>}
              {n.recommendation && <div className="ok" style={{ fontSize: 14, marginTop: 6 }}>→ {n.recommendation}</div>}
              {n.follow_up_on && (
                <div className="muted" style={{ fontSize: 13 }}>
                  Follow-up: {n.follow_up_on}{n.follow_up_done ? " ✓ done" : ""}
                </div>
              )}
              <AckBox note={n} onDone={loadMyAdv} />
            </div>
          ))}
        </div>
      )}

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
        <div style={{ marginTop: 10 }}>
          <label className="btn ghost" style={{ cursor: "pointer" }}>
            📷 Add crop photos
            <input type="file" accept="image/*" multiple style={{ display: "none" }}
                   onChange={(e) => addPhotos(Array.from(e.target.files))} />
          </label>
          {images.length > 0 && <span className="muted" style={{ marginLeft: 10 }}>{images.length} photo(s) attached</span>}
        </div>
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
