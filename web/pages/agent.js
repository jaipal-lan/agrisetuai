import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { useI18n } from "../lib/i18n";

// Offline-first inspection capture for field agents. Drafts are held in
// localStorage and flushed when connectivity returns; the backend dedupes on
// client_draft_id, so re-sending a draft never creates a duplicate inspection.
const QUEUE_KEY = "agri_insp_queue";

function readQueue() {
  try {
    return JSON.parse(window.localStorage.getItem(QUEUE_KEY) || "[]");
  } catch {
    return [];
  }
}
function writeQueue(q) {
  try {
    window.localStorage.setItem(QUEUE_KEY, JSON.stringify(q));
  } catch {}
}
function newDraftId() {
  try {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
  } catch {}
  return `draft-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function InspectForm({ job, onQueued, onSynced, online }) {
  const [gross, setGross] = useState("");
  const [tare, setTare] = useState("0");
  const [outcome, setOutcome] = useState("pass");
  const [moisture, setMoisture] = useState("");
  const [note, setNote] = useState(null);

  async function submit() {
    setNote(null);
    const draftId = newDraftId();
    const body = {
      client_draft_id: draftId,
      gross_weight: gross ? Number(gross) : undefined,
      tare_weight: tare ? Number(tare) : 0,
      outcome,
      checklist: moisture ? { moisture_pct: Number(moisture) } : undefined,
    };
    const item = { id: draftId, order_id: job.order_id, public_id: job.public_id, body };

    // Save to the queue first so a crash/refresh mid-send never loses the draft.
    const q = readQueue();
    q.push(item);
    writeQueue(q);
    onQueued();

    if (!online) {
      setNote({ kind: "muted", text: "Saved offline — will sync when back online." });
      return;
    }
    try {
      await api(`/agent/orders/${job.order_id}/inspection`, { method: "POST", body });
      writeQueue(readQueue().filter((x) => x.id !== draftId));
      setNote({ kind: "ok", text: "Submitted." });
      onSynced();
    } catch (e) {
      // Kept in the queue for a later flush.
      setNote({ kind: "muted", text: `Saved offline (${e.message}). Will retry on sync.` });
      onQueued();
    }
  }

  const inspectable = ["inspection_assigned", "inspection_in_progress", "inspection_hold"].includes(job.status);
  if (!inspectable) return null;

  return (
    <div style={{ marginTop: 10 }}>
      <div className="row">
        <div style={{ flex: 1 }}>
          <label>Gross weight (kg)</label>
          <input value={gross} onChange={(e) => setGross(e.target.value)} inputMode="decimal" />
        </div>
        <div style={{ flex: 1 }}>
          <label>Tare (kg)</label>
          <input value={tare} onChange={(e) => setTare(e.target.value)} inputMode="decimal" />
        </div>
      </div>
      <div className="row">
        <div style={{ flex: 1 }}>
          <label>Moisture %</label>
          <input value={moisture} onChange={(e) => setMoisture(e.target.value)} inputMode="decimal" />
        </div>
        <div style={{ flex: 1 }}>
          <label>Outcome</label>
          <select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            <option value="pass">Pass</option>
            <option value="pass_with_adjustment">Pass with adjustment</option>
            <option value="hold">Hold</option>
            <option value="fail">Fail</option>
          </select>
        </div>
      </div>
      <div style={{ marginTop: 10 }}>
        <button onClick={submit}>{online ? "Submit inspection" : "Save offline"}</button>
      </div>
      {note && <div className={note.kind === "ok" ? "ok" : "muted"} style={{ marginTop: 8 }}>{note.text}</div>}
    </div>
  );
}

export default function AgentJobs() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [queued, setQueued] = useState(0);
  const [online, setOnline] = useState(true);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const refreshQueueCount = useCallback(() => setQueued(readQueue().length), []);

  const loadJobs = useCallback(async () => {
    try {
      const rows = await api("/agent/jobs");
      setJobs(rows);
      try {
        window.localStorage.setItem("agri_jobs_cache", JSON.stringify(rows));
      } catch {}
      setErr(null);
    } catch (e) {
      // Offline / failed: fall back to the last cached job list.
      try {
        const cached = JSON.parse(window.localStorage.getItem("agri_jobs_cache") || "[]");
        setJobs(cached);
      } catch {}
      setErr(e.message);
    }
  }, []);

  // Flush any queued drafts. Safe to call repeatedly: the backend dedupes.
  const sync = useCallback(async () => {
    const q = readQueue();
    if (q.length === 0) return;
    setBusy(true);
    const remaining = [];
    for (const item of q) {
      try {
        await api(`/agent/orders/${item.order_id}/inspection`, { method: "POST", body: item.body });
      } catch {
        remaining.push(item); // keep for the next attempt
      }
    }
    writeQueue(remaining);
    refreshQueueCount();
    setBusy(false);
    await loadJobs();
  }, [loadJobs, refreshQueueCount]);

  useEffect(() => {
    setMe(getUser());
    refreshQueueCount();
    if (typeof navigator !== "undefined") setOnline(navigator.onLine);
    loadJobs();

    const goOnline = () => {
      setOnline(true);
      sync();
    };
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, [loadJobs, sync, refreshQueueCount]);

  async function packingComplete(orderId) {
    setBusy(true);
    try {
      await api(`/orders/${orderId}/packing-complete`, { method: "POST" });
      await loadJobs();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!me) {
    return (
      <div>
        <p className="muted">Field agents only. Please log in.</p>
        <Link href="/login" className="btn">{t("login")}</Link>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 680 }}>
      <div className="between">
        <h1>{t("agent_jobs")}</h1>
        <span className={`badge ${online ? "" : "amber"}`}>{online ? "online" : "offline"}</span>
      </div>
      <p className="tagline">
        Inspections are saved on this device first, so you can work in low-signal
        fields. They sync automatically when you are back online.
      </p>

      {queued > 0 && (
        <div className="card" style={{ borderLeft: "4px solid var(--amber-600)" }}>
          <div className="between">
            <div><b>{queued}</b> inspection{queued > 1 ? "s" : ""} waiting to sync</div>
            <button disabled={busy || !online} onClick={sync}>
              {busy ? "Syncing…" : "Sync now"}
            </button>
          </div>
        </div>
      )}

      {err && <div className="muted" style={{ marginTop: 8 }}>Showing last saved jobs ({err}).</div>}

      {jobs.length === 0 ? (
        <p className="muted">No assigned jobs right now.</p>
      ) : (
        jobs.map((j) => (
          <div className="card" key={j.order_id} style={{ marginBottom: 12 }}>
            <div className="between">
              <Link href={`/order/${j.order_id}`}><b>{j.public_id}</b></Link>
              <span className="badge grey">{j.status.replace(/_/g, " ")}</span>
            </div>
            <div className="muted" style={{ fontSize: 14 }}>
              {j.accepted_terms?.quantity} {j.accepted_terms?.unit} · ₹{j.accepted_terms?.price_per_unit}/unit
            </div>
            <InspectForm
              job={j}
              online={online}
              onQueued={refreshQueueCount}
              onSynced={() => { refreshQueueCount(); loadJobs(); }}
            />
            {j.status === "paid" && (
              <div style={{ marginTop: 10 }}>
                <button disabled={busy || !online} onClick={() => packingComplete(j.order_id)}>
                  Seal lot & complete packing
                </button>
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
}
