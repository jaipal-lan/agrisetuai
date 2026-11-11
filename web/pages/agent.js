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

// Targets a leader set for this agent + meetings they're invited to.
function MyTeam() {
  const [targets, setTargets] = useState([]);
  const [meetings, setMeetings] = useState([]);
  useEffect(() => {
    api("/team/my-targets").then(setTargets).catch(() => {});
    api("/team/my-meetings").then(setMeetings).catch(() => {});
  }, []);
  const upcoming = meetings.filter((m) => m.status === "scheduled");
  if (targets.length === 0 && upcoming.length === 0) return null;
  return (
    <>
      {targets.length > 0 && (
        <div className="card" style={{ marginBottom: 12 }}>
          <h3 style={{ marginTop: 0 }}>🎯 Your targets</h3>
          {targets.map((tg) => (
            <div key={tg.id} style={{ marginBottom: 10 }}>
              <div className="between" style={{ fontSize: 14 }}>
                <span>{tg.progress} / {tg.target_value} {tg.metric_label}</span>
                <span className={`badge ${tg.met ? "green" : "grey"}`}>{tg.met ? "met" : `${tg.pct}%`}</span>
              </div>
              <div className="pbar" style={{ marginTop: 4 }}><div className="pbar-fill" style={{ width: `${tg.pct}%` }} /></div>
              <div className="muted" style={{ fontSize: 12, marginTop: 3 }}>
                by {tg.period_end}{tg.note ? ` · ${tg.note}` : ""}
              </div>
            </div>
          ))}
        </div>
      )}
      {upcoming.length > 0 && (
        <div className="card" style={{ marginBottom: 12 }}>
          <h3 style={{ marginTop: 0 }}>📅 Upcoming meetings</h3>
          {upcoming.map((m) => (
            <div key={m.id} style={{ marginBottom: 8, fontSize: 14 }}>
              <b>{m.title}</b>
              <div className="muted" style={{ fontSize: 13 }}>
                🕒 {(m.scheduled_at || "").replace("T", " ").slice(0, 16)}{m.location ? ` · ${m.location}` : ""}
              </div>
              {m.agenda && <div style={{ fontSize: 13 }}>{m.agenda}</div>}
            </div>
          ))}
        </div>
      )}
    </>
  );
}

export default function AgentJobs() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [queue, setQueue] = useState([]);       // inspection drafts
  const [online, setOnline] = useState(true);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [syncedAt, setSyncedAt] = useState(0);

  const refreshQueues = useCallback(() => {
    setQueue(readQ(QUEUE_KEY));
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
    if (iq.length === 0) return;
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

  function discardDraft(id) {
    writeQ(QUEUE_KEY, readQ(QUEUE_KEY).filter((x) => x.id !== id));
    refreshQueues();
  }

  async function packingComplete(orderId, videoFile) {
    setBusy(true);
    try {
      let packing_video;
      if (videoFile) {
        const up = await uploadMedia(videoFile);
        packing_video = up.object_key;
      }
      await api(`/orders/${orderId}/packing-complete`, { method: "POST", body: { packing_video } });
      await loadJobs();
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  const gate = roleGate(me, GROUPS.agent, { label: "inspection jobs" });
  if (gate) return gate;

  const queued = queue.length;
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

      <MyTeam />

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
                  <p className="muted" style={{ fontSize: 12, margin: "0 0 6px" }}>
                    Record a short packing video (≤2 min), then seal the lot for dispatch.
                  </p>
                  <label className="btn" style={{ cursor: "pointer", display: "inline-block" }}>
                    🎥 Record & seal with video
                    <input type="file" accept="video/*" capture="environment" style={{ display: "none" }}
                           disabled={busy || !online}
                           onChange={(e) => e.target.files[0] && packingComplete(j.order_id, e.target.files[0])} />
                  </label>
                  <button className="ghost" style={{ marginLeft: 8 }} disabled={busy || !online}
                          onClick={() => packingComplete(j.order_id)}>
                    Seal without video
                  </button>
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
