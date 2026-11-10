import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api, getUser, uploadMedia } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

// Offline-first field capture for agents. Drafts (inspections incl. downscaled
// photos, and advisory logs) are held in localStorage and flushed when
// connectivity returns; the backend dedupes on client_draft_id, so re-sending a
// draft never creates a duplicate.
const QUEUE_KEY = "agri_insp_queue";
const ADV_QUEUE_KEY = "agri_adv_queue";
const MAX_PHOTOS = 4;

function readQ(key) {
  try { return JSON.parse(window.localStorage.getItem(key) || "[]"); }
  catch { return []; }
}
// Returns true on success; false if the device rejected the write (e.g. storage
// full from too many queued photos) so the caller can warn the agent.
function writeQ(key, q) {
  try { window.localStorage.setItem(key, JSON.stringify(q)); return true; }
  catch { return false; }
}
const readQueue = () => readQ(QUEUE_KEY);
const writeQueue = (q) => writeQ(QUEUE_KEY, q);

function newDraftId() {
  try { if (window.crypto?.randomUUID) return window.crypto.randomUUID(); } catch {}
  return `draft-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

// Shrink a camera photo to a small JPEG data URL so it survives in localStorage
// while offline and uploads quickly on a weak connection.
function downscaleToDataUrl(file, maxDim = 1024, quality = 0.6) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
      const w = Math.max(1, Math.round(img.width * scale));
      const h = Math.max(1, Math.round(img.height * scale));
      const canvas = document.createElement("canvas");
      canvas.width = w; canvas.height = h;
      canvas.getContext("2d").drawImage(img, 0, 0, w, h);
      try { resolve(canvas.toDataURL("image/jpeg", quality)); }
      catch (e) { reject(e); }
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Could not read image")); };
    img.src = url;
  });
}

async function dataUrlToFile(dataUrl, name) {
  const res = await fetch(dataUrl);
  const blob = await res.blob();
  return new File([blob], name, { type: blob.type || "image/jpeg" });
}

function InspectForm({ job, onQueued, online }) {
  const [gross, setGross] = useState("");
  const [tare, setTare] = useState("0");
  const [outcome, setOutcome] = useState("pass");
  const [cl, setCl] = useState({ moisture: "", foreign_matter: "", damaged: "", variety_match: true });
  const [photos, setPhotos] = useState([]); // data URLs
  const [note, setNote] = useState(null);
  const setClv = (k, v) => setCl((c) => ({ ...c, [k]: v }));

  const net = gross ? (Number(gross) - Number(tare || 0)) : null;

  async function addPhotos(fileList) {
    const files = Array.from(fileList || []);
    for (const f of files) {
      if (photos.length >= MAX_PHOTOS) break;
      try {
        const d = await downscaleToDataUrl(f);
        setPhotos((p) => (p.length >= MAX_PHOTOS ? p : [...p, d]));
      } catch { setNote({ kind: "muted", text: "Couldn't read that photo." }); }
    }
  }

  function buildChecklist() {
    const out = {};
    if (cl.moisture !== "") out.moisture_pct = Number(cl.moisture);
    if (cl.foreign_matter !== "") out.foreign_matter_pct = Number(cl.foreign_matter);
    if (cl.damaged !== "") out.damaged_pct = Number(cl.damaged);
    out.variety_match = !!cl.variety_match;
    return out;
  }

  function submit() {
    setNote(null);
    const draftId = newDraftId();
    const body = {
      client_draft_id: draftId,
      gross_weight: gross ? Number(gross) : undefined,
      tare_weight: tare ? Number(tare) : 0,
      outcome,
      checklist: buildChecklist(),
    };
    const item = {
      id: draftId, order_id: job.order_id, public_id: job.public_id,
      outcome, body, photos, uploaded: [], created_at: new Date().toISOString(),
    };
    // Save to the queue first so a crash/refresh mid-send never loses the draft.
    const q = readQueue();
    q.push(item);
    if (!writeQueue(q)) {
      setNote({ kind: "muted", text: "Device storage is full — sync now to free space, then retry." });
      return;
    }
    onQueued(!online);
    setNote(online
      ? { kind: "ok", text: "Captured — syncing…" }
      : { kind: "muted", text: "Saved on this device — will sync when back online." });
  }

  const inspectable = ["inspection_assigned", "inspection_in_progress", "inspection_hold"].includes(job.status);
  if (!inspectable) return null;

  return (
    <div className="inspect-form">
      <div className="row">
        <div style={{ flex: 1 }}>
          <label>Gross weight (kg)</label>
          <input value={gross} onChange={(e) => setGross(e.target.value)} inputMode="decimal" placeholder="e.g. 505" />
        </div>
        <div style={{ flex: 1 }}>
          <label>Tare (kg)</label>
          <input value={tare} onChange={(e) => setTare(e.target.value)} inputMode="decimal" />
        </div>
      </div>
      {net !== null && !Number.isNaN(net) && (
        <div className="net-weight">Net weight: <b>{net} kg</b>
          {job.accepted_terms?.quantity && <span className="muted"> · declared {job.accepted_terms.quantity} kg</span>}
        </div>
      )}

      <label style={{ marginTop: 10 }}>Quality checklist</label>
      <div className="check-grid">
        <div><label className="sub">Moisture %</label>
          <input value={cl.moisture} onChange={(e) => setClv("moisture", e.target.value)} inputMode="decimal" /></div>
        <div><label className="sub">Foreign matter %</label>
          <input value={cl.foreign_matter} onChange={(e) => setClv("foreign_matter", e.target.value)} inputMode="decimal" /></div>
        <div><label className="sub">Damaged %</label>
          <input value={cl.damaged} onChange={(e) => setClv("damaged", e.target.value)} inputMode="decimal" /></div>
        <label className="variety-check">
          <input type="checkbox" checked={cl.variety_match} onChange={(e) => setClv("variety_match", e.target.checked)} />
          Variety matches listing
        </label>
      </div>

      <label style={{ marginTop: 12 }}>Photos ({photos.length}/{MAX_PHOTOS})</label>
      <div className="photo-row">
        {photos.map((p, i) => (
          <div key={i} className="photo-thumb">
            <img src={p} alt={`evidence ${i + 1}`} />
            <button type="button" className="photo-x" onClick={() => setPhotos((ps) => ps.filter((_, j) => j !== i))}>×</button>
          </div>
        ))}
        {photos.length < MAX_PHOTOS && (
          <label className="photo-add">
            <span>＋<br />Photo</span>
            <input type="file" accept="image/*" capture="environment" multiple
                   onChange={(e) => { addPhotos(e.target.files); e.target.value = ""; }}
                   style={{ display: "none" }} />
          </label>
        )}
      </div>
      <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>
        Photos are shrunk and stored on this device, then uploaded on sync — safe to shoot offline.
      </p>

      <label style={{ marginTop: 12 }}>Outcome</label>
      <div className="bigseg">
        {[["pass", "✓ Pass"], ["pass_with_adjustment", "± Adjust"], ["hold", "⏸ Hold"], ["fail", "✕ Fail"]].map(([v, label]) => (
          <button key={v} type="button" className={outcome === v ? `on ${v}` : ""} onClick={() => setOutcome(v)}>{label}</button>
        ))}
      </div>

      <button className="submit-insp" onClick={submit}>
        {online ? "Submit inspection" : "Save offline"}
      </button>
      {note && <div className={note.kind === "ok" ? "ok" : "muted"} style={{ marginTop: 8 }}>{note.text}</div>}
    </div>
  );
}

function AdvisoryLog({ online, queueAdvisory, pending, syncedAt }) {
  const [logs, setLogs] = useState([]);
  const [form, setForm] = useState({ farmer_phone: "", crop: "", observation: "", recommendation: "", follow_up_on: "" });
  const [msg, setMsg] = useState(null);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function load() {
    try { setLogs(await api("/agent/advisory-logs")); } catch {}
  }
  // Reload after each successful sync so freshly-flushed drafts appear as saved.
  useEffect(() => { load(); }, [syncedAt]);

  function save() {
    setMsg(null);
    if (!form.observation && !form.recommendation) return;
    const draftId = newDraftId();
    const body = {
      client_draft_id: draftId,
      farmer_phone: form.farmer_phone || undefined,
      crop: form.crop || undefined,
      topic: "advisory",
      observation: form.observation || undefined,
      recommendation: form.recommendation || undefined,
      follow_up_on: form.follow_up_on || undefined,
    };
    const item = {
      id: draftId, body, crop: form.crop, observation: form.observation,
      recommendation: form.recommendation, follow_up_on: form.follow_up_on,
      created_at: new Date().toISOString(),
    };
    if (!queueAdvisory(item)) {
      setMsg("Device storage is full — sync now to free space, then retry.");
      return;
    }
    setForm({ farmer_phone: "", crop: "", observation: "", recommendation: "", follow_up_on: "" });
    setMsg(online ? "Logged — syncing…" : "Saved on this device — will sync when back online.");
  }

  return (
    <div style={{ marginTop: 28 }}>
      <h2>Advisory & farmer education log</h2>
      <p className="muted" style={{ fontSize: 13 }}>
        You are also the local agricultural expert. Record what you advised and any
        follow-up — works offline, syncs when you are back online.
      </p>
      <div className="card">
        <div className="row">
          <div style={{ flex: 1 }}><label>Farmer phone</label>
            <input value={form.farmer_phone} onChange={(e) => set("farmer_phone", e.target.value)} inputMode="numeric" /></div>
          <div style={{ flex: 1 }}><label>Crop</label>
            <input value={form.crop} onChange={(e) => set("crop", e.target.value)} /></div>
          <div style={{ flex: 1 }}><label>Follow-up date</label>
            <input value={form.follow_up_on} onChange={(e) => set("follow_up_on", e.target.value)} placeholder="2026-11-20" /></div>
        </div>
        <label>Observation</label>
        <textarea rows={2} value={form.observation} onChange={(e) => set("observation", e.target.value)} />
        <label>Recommendation (IPM-first; no invented doses)</label>
        <textarea rows={2} value={form.recommendation} onChange={(e) => set("recommendation", e.target.value)} />
        <div style={{ marginTop: 10 }}>
          <button onClick={save} disabled={!form.observation && !form.recommendation}>
            {online ? "Log advisory" : "Save offline"}
          </button>
        </div>
        {msg && <div className="ok" style={{ marginTop: 8 }}>{msg}</div>}
      </div>

      {/* Advisory drafts captured on this device, not yet synced */}
      {pending.map((p) => (
        <div className="card" key={p.id} style={{ marginTop: 10, borderLeft: "4px solid var(--amber-600)" }}>
          <div className="between">
            <b>{p.crop || "general"}</b>
            <span className="badge amber">{p.error ? "retrying" : "waiting to sync"}</span>
          </div>
          {p.observation && <div style={{ fontSize: 14 }}>{p.observation}</div>}
          {p.recommendation && <div className="ok" style={{ fontSize: 14, marginTop: 6 }}>→ {p.recommendation}</div>}
          {p.error && <div className="muted" style={{ fontSize: 12 }}>⚠ {p.error}</div>}
        </div>
      ))}

      {logs.map((l) => (
        <div className="card" key={l.id} style={{ marginTop: 10 }}>
          <div className="between">
            <b>{l.crop || "general"}</b>
            <span className="muted" style={{ fontSize: 12 }}>{l.created_at ? new Date(l.created_at).toLocaleDateString() : ""}</span>
          </div>
          {l.observation && <div style={{ fontSize: 14 }}>{l.observation}</div>}
          {l.recommendation && <div className="ok" style={{ fontSize: 14, marginTop: 6 }}>→ {l.recommendation}</div>}
          {l.follow_up_on && <div className="muted" style={{ fontSize: 13 }}>Follow up: {l.follow_up_on}</div>}
        </div>
      ))}
    </div>
  );
}

function FollowUps({ online, syncedAt }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(null);

  async function load() {
    try { setData(await api("/agent/follow-ups")); } catch {}
  }
  // Reload on mount and after a sync (a freshly-synced note may add a follow-up).
  useEffect(() => { load(); }, [syncedAt]);

  async function markDone(id) {
    setBusy(id);
    try { await api(`/agent/advisory-logs/${id}/follow-up-done`, { method: "POST" }); await load(); }
    catch {} finally { setBusy(null); }
  }

  if (!data || (data.due.length === 0 && data.upcoming.length === 0)) return null;

  const Row = ({ f, badge }) => (
    <div className="between followup-row">
      <div>
        <b>{f.crop || "general"}</b> {badge}
        {(f.recommendation || f.observation) && (
          <div style={{ fontSize: 14 }}>{f.recommendation || f.observation}</div>
        )}
        <div className="muted" style={{ fontSize: 12 }}>due {f.follow_up_date}</div>
      </div>
      <button className="ghost" disabled={!online || busy === f.id} onClick={() => markDone(f.id)}>
        {busy === f.id ? "…" : "Mark done"}
      </button>
    </div>
  );

  return (
    <div className="card followups" style={{ borderLeft: "4px solid var(--amber-600)", marginBottom: 16 }}>
      <h3 style={{ marginTop: 0 }}>📌 Follow-ups {data.due.length > 0 && <span className="badge danger">{data.due.length} due</span>}</h3>
      {data.due.map((f) => (
        <Row key={f.id} f={f}
             badge={<span className="badge danger">{f.overdue ? `${-f.days_until}d overdue` : "due today"}</span>} />
      ))}
      {data.upcoming.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary className="muted">Upcoming ({data.upcoming.length})</summary>
          {data.upcoming.map((f) => (
            <Row key={f.id} f={f} badge={<span className="muted" style={{ fontSize: 12 }}>in {f.days_until}d</span>} />
          ))}
        </details>
      )}
      {!online && <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>Reconnect to mark follow-ups done.</p>}
    </div>
  );
}

export default function AgentJobs() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [queue, setQueue] = useState([]);       // inspection drafts
  const [advQueue, setAdvQueue] = useState([]); // advisory drafts
  const [online, setOnline] = useState(true);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [syncedAt, setSyncedAt] = useState(0);

  const refreshQueues = useCallback(() => {
    setQueue(readQ(QUEUE_KEY));
    setAdvQueue(readQ(ADV_QUEUE_KEY));
  }, []);

  const loadJobs = useCallback(async () => {
    try {
      const rows = await api("/agent/jobs");
      setJobs(rows);
      try { window.localStorage.setItem("agri_jobs_cache", JSON.stringify(rows)); } catch {}
      setErr(null);
    } catch (e) {
      // Offline / failed: fall back to the last cached job list.
      try { setJobs(JSON.parse(window.localStorage.getItem("agri_jobs_cache") || "[]")); } catch {}
      setErr(e.message);
    }
  }, []);

  // Flush all queued drafts. Inspections upload their photos first (tracking
  // per-photo progress so a partial upload survives), then submit; advisory logs
  // POST directly. Safe to call repeatedly — the backend dedupes on draft id.
  const sync = useCallback(async () => {
    const iq = readQ(QUEUE_KEY);
    const aq = readQ(ADV_QUEUE_KEY);
    if (iq.length === 0 && aq.length === 0) return;
    setBusy(true);

    for (const item of iq) {
      try {
        const refs = [...(item.uploaded || [])];
        const stillPending = [];
        for (const dataUrl of (item.photos || [])) {
          try {
            const f = await dataUrlToFile(dataUrl, `inspection-${item.id}.jpg`);
            const r = await uploadMedia(f);
            refs.push(r.object_key);
          } catch { stillPending.push(dataUrl); }
        }
        item.uploaded = refs;
        item.photos = stillPending;
        writeQ(QUEUE_KEY, iq); // persist upload progress before the (riskier) submit
        if (stillPending.length) { item.error = "photo upload pending"; continue; }
        const body = { ...item.body };
        if (refs.length) body.evidence = refs;
        await api(`/agent/orders/${item.order_id}/inspection`, { method: "POST", body });
        item._done = true;
        item.error = null;
      } catch (e) { item.error = e.message; }
    }
    writeQ(QUEUE_KEY, iq.filter((x) => !x._done));

    for (const item of aq) {
      try {
        await api("/agent/advisory-logs", { method: "POST", body: item.body });
        item._done = true;
        item.error = null;
      } catch (e) { item.error = e.message; }
    }
    writeQ(ADV_QUEUE_KEY, aq.filter((x) => !x._done));

    refreshQueues();
    setBusy(false);
    setSyncedAt((n) => n + 1);
    await loadJobs();
  }, [loadJobs, refreshQueues]);

  useEffect(() => {
    setMe(getUser());
    refreshQueues();
    if (typeof navigator !== "undefined") setOnline(navigator.onLine);
    loadJobs();

    const goOnline = () => { setOnline(true); sync(); };
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, [loadJobs, sync, refreshQueues]);

  usePoll(() => { if (online) loadJobs(); }, 20000, [online]);

  // After queuing an inspection draft, try to sync immediately when online.
  const onQueued = useCallback((savedOffline) => {
    refreshQueues();
    if (!savedOffline) sync();
  }, [refreshQueues, sync]);

  // Queue an advisory draft (returns false if storage is full); sync if online.
  const queueAdvisory = useCallback((item) => {
    const q = readQ(ADV_QUEUE_KEY);
    q.push(item);
    const ok = writeQ(ADV_QUEUE_KEY, q);
    refreshQueues();
    if (ok && online) sync();
    return ok;
  }, [online, sync, refreshQueues]);

  function discardDraft(id) {
    writeQ(QUEUE_KEY, readQ(QUEUE_KEY).filter((x) => x.id !== id));
    refreshQueues();
  }

  async function packingComplete(orderId) {
    setBusy(true);
    try { await api(`/orders/${orderId}/packing-complete`, { method: "POST" }); await loadJobs(); }
    catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  const gate = roleGate(me, GROUPS.agent, { label: "inspection jobs" });
  if (gate) return gate;

  const queued = queue.length + advQueue.length;
  const pendingByOrder = {};
  for (const it of queue) (pendingByOrder[it.order_id] ||= []).push(it);

  return (
    <div className="agent-page" style={{ maxWidth: 680 }}>
      <div className={`field-status ${online ? "" : "off"}`}>
        <span className="dot" /> {online ? "Online" : "Offline — working on this device"}
        {queued > 0 && <> · <b>{queued}</b> waiting to sync</>}
        {queued > 0 && (
          <button disabled={busy || !online} onClick={sync} className="sync-btn">
            {busy ? "Syncing…" : "Sync now"}
          </button>
        )}
      </div>

      <h1>{t("agent_jobs")}</h1>
      <p className="tagline">
        Inspections, photos and advisory notes are saved on this device first, so
        you can work in low-signal fields. They sync automatically when you are
        back online.
      </p>

      <FollowUps online={online} syncedAt={syncedAt} />

      {/* Inspection drafts captured on this device */}
      {queue.length > 0 && (
        <div className="card draft-panel">
          <h3 style={{ marginTop: 0 }}>Inspections not yet synced</h3>
          {queue.map((it) => (
            <div key={it.id} className="between draft-row">
              <div>
                <b>{it.public_id}</b> · {it.outcome?.replace(/_/g, " ")}
                {(it.photos?.length || it.uploaded?.length) ? ` · 📷 ${(it.photos?.length || 0) + (it.uploaded?.length || 0)}` : ""}
                {it.error && <div className="muted" style={{ fontSize: 12 }}>⚠ {it.error}</div>}
              </div>
              <button className="ghost" onClick={() => discardDraft(it.id)}>Discard</button>
            </div>
          ))}
        </div>
      )}

      {err && <div className="muted" style={{ marginTop: 8 }}>Showing last saved jobs (offline).</div>}

      {jobs.length === 0 ? (
        <p className="muted">No assigned jobs right now.</p>
      ) : (
        jobs.map((j) => {
          const pending = pendingByOrder[j.order_id];
          return (
            <div className="card" key={j.order_id} style={{ marginBottom: 12 }}>
              <div className="between">
                <Link href={`/order/${j.order_id}`}><b>{j.public_id}</b></Link>
                <span className="badge grey">{j.status.replace(/_/g, " ")}</span>
              </div>
              <div className="muted" style={{ fontSize: 14 }}>
                {j.accepted_terms?.quantity} {j.accepted_terms?.unit} · ₹{j.accepted_terms?.price_per_unit}/unit
              </div>
              {pending ? (
                <div className="captured-note">
                  ✓ Inspection captured on this device ({pending.length}) — waiting to sync.
                </div>
              ) : (
                <InspectForm job={j} online={online} onQueued={onQueued} />
              )}
              {j.status === "paid" && (
                <div style={{ marginTop: 10 }}>
                  <button disabled={busy || !online} onClick={() => packingComplete(j.order_id)}>
                    Seal lot & complete packing
                  </button>
                </div>
              )}
            </div>
          );
        })
      )}

      <AdvisoryLog online={online} queueAdvisory={queueAdvisory} pending={advQueue} syncedAt={syncedAt} />
    </div>
  );
}
