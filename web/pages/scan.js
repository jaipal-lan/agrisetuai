import { useEffect, useRef, useState } from "react";

import { api, getUser } from "../lib/api";
import { roleGate } from "../lib/roles";

const SCAN_ROLES = ["field_agent", "field_leader", "field_manager", "transport", "superadmin"];

// Which stages each role may scan (mirrors backend STAGE_ROLES).
const STAGES_FOR = {
  field_agent: [["pickup", "Pickup from farmer"]],
  field_leader: [["pickup", "Pickup from farmer"], ["collection", "Collection centre"]],
  field_manager: [["pickup", "Pickup from farmer"], ["collection", "Collection centre"],
                  ["loading", "Loading / in transit"], ["delivery", "Delivery"]],
  superadmin: [["pickup", "Pickup from farmer"], ["collection", "Collection centre"],
               ["loading", "Loading / in transit"], ["delivery", "Delivery"]],
  transport: [["loading", "Loading / in transit"], ["delivery", "Delivery"]],
};

const HTML5_QRCODE = "https://cdnjs.cloudflare.com/ajax/libs/html5-qrcode/2.3.8/html5-qrcode.min.js";

function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) return resolve();
    const s = document.createElement("script");
    s.src = src; s.onload = resolve; s.onerror = () => reject(new Error("load failed"));
    document.body.appendChild(s);
  });
}

export default function Scan() {
  const [me, setMe] = useState(null);
  const [stage, setStage] = useState("");
  const [code, setCode] = useState("");
  const [results, setResults] = useState([]); // {ok, text}
  const [busy, setBusy] = useState(false);
  const [camOn, setCamOn] = useState(false);
  const [camErr, setCamErr] = useState(null);
  const [geo, setGeo] = useState(null);
  const [pending, setPending] = useState(0);
  const scannerRef = useRef(null);

  useEffect(() => {
    const u = getUser();
    setMe(u);
    if (u) {
      const st = STAGES_FOR[u.role] || [];
      if (st.length) setStage(st[0][0]);
    }
    // Best-effort GPS to stamp each scan.
    if (typeof navigator !== "undefined" && navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (p) => setGeo({ lat: p.coords.latitude, lng: p.coords.longitude }), () => {},
        { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 });
    }
  }, []);

  useEffect(() => () => stopCam(), []); // cleanup on unmount

  // Offline queue: scans saved on this device sync when connectivity returns.
  const QKEY = "agri_scan_queue";
  const readQ = () => { try { return JSON.parse(window.localStorage.getItem(QKEY) || "[]"); } catch { return []; } };
  const writeQ = (q) => { try { window.localStorage.setItem(QKEY, JSON.stringify(q)); } catch {} setPending(q.length); };

  useEffect(() => {
    setPending(readQ().length);
    const onOnline = () => syncQueue();
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function syncQueue() {
    const q = readQ();
    if (!q.length) return;
    const keep = [];
    for (const it of q) {
      try {
        await api("/bags/scan", { method: "POST", body: it });
        addResult(true, `${it.bag_code}: synced (${it.stage})`);
      } catch (e) {
        if (e.status) addResult(false, `${it.bag_code}: ${e.message}`); // server rejected -> drop
        else keep.push(it); // still offline -> keep
      }
    }
    writeQ(keep);
  }

  const webcamOk = typeof window !== "undefined" && window.isSecureContext
    && !!navigator.mediaDevices?.getUserMedia;

  async function doScan(bagCode) {
    const c = (bagCode || "").trim();
    if (!c || !stage) return;
    setBusy(true);
    const item = { bag_code: c, stage, lat: geo?.lat, lng: geo?.lng };
    try {
      const r = await api("/bags/scan", { method: "POST", body: item });
      addResult(true, r.message || `${c}: scanned`);
    } catch (e) {
      if (e.status === undefined) {
        const q = readQ(); q.push(item); writeQ(q);
        addResult(true, `${c}: saved offline — will sync when online`);
      } else {
        addResult(false, `${c}: ${e.message}`);
      }
    } finally { setBusy(false); setCode(""); }
  }

  function addResult(ok, text) {
    setResults((r) => [{ ok, text, t: new Date().toLocaleTimeString() }, ...r].slice(0, 30));
  }

  async function startCam() {
    setCamErr(null);
    if (!webcamOk) { setCamErr("Live camera needs HTTPS or localhost. Use manual entry below."); return; }
    try {
      await loadScript(HTML5_QRCODE);
      const { Html5Qrcode } = window;
      const scanner = new Html5Qrcode("reader");
      scannerRef.current = scanner;
      setCamOn(true);
      let last = 0;
      await scanner.start({ facingMode: "environment" }, { fps: 10, qrbox: 250 },
        (decoded) => {
          const now = Date.now();
          if (now - last < 2500) return; // debounce repeat decodes
          last = now;
          doScan(decoded);
        }, () => {});
    } catch (e) {
      setCamErr("Couldn't start the camera. Use manual entry below.");
      setCamOn(false);
    }
  }

  function stopCam() {
    const s = scannerRef.current;
    if (s) { try { s.stop().then(() => s.clear()).catch(() => {}); } catch {} }
    scannerRef.current = null;
    setCamOn(false);
  }

  async function torch(on) {
    try { await scannerRef.current?.applyVideoConstraints({ advanced: [{ torch: on }] }); } catch {}
  }

  const gate = roleGate(me, SCAN_ROLES, { label: "the scan screen" });
  if (gate) return gate;

  const stages = STAGES_FOR[me.role] || [];

  return (
    <div style={{ maxWidth: 520, margin: "0 auto" }}>
      <h1>Scan bags</h1>
      <p className="tagline">Scan each bag's barcode/QR to update its status.</p>

      {pending > 0 && (
        <div className="card" style={{ borderLeft: "4px solid var(--amber-600)" }}>
          <div className="between">
            <span><b>{pending}</b> scan(s) saved offline, waiting to sync.</span>
            <button className="ghost" onClick={syncQueue}>Sync now</button>
          </div>
        </div>
      )}

      <div className="card">
        <label>Stage</label>
        <select value={stage} onChange={(e) => setStage(e.target.value)}>
          {stages.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>

        <div style={{ marginTop: 12 }}>
          {!camOn ? (
            <button onClick={startCam} disabled={busy}>📷 Scan with camera</button>
          ) : (
            <div className="row" style={{ gap: 6 }}>
              <button className="ghost" onClick={() => torch(true)}>🔦 Torch on</button>
              <button className="ghost" onClick={() => torch(false)}>Torch off</button>
              <button className="danger" onClick={stopCam}>Stop camera</button>
            </div>
          )}
          {camErr && <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>{camErr}</div>}
          <div id="reader" style={{ width: "100%", marginTop: 10, display: camOn ? "block" : "none" }} />
        </div>

        <div style={{ marginTop: 14, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
          <label>Or enter the barcode manually</label>
          <div className="row" style={{ gap: 6 }}>
            <input value={code} onChange={(e) => setCode(e.target.value)}
                   placeholder="AGRI-1023-BAG-01" style={{ flex: 1 }}
                   onKeyDown={(e) => e.key === "Enter" && doScan(code)} />
            <button disabled={busy || !code.trim()} onClick={() => doScan(code)}>Scan</button>
          </div>
          {geo && <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>📍 Location captured for this scan.</div>}
        </div>
      </div>

      {results.length > 0 && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Recent scans</h3>
          <div style={{ display: "grid", gap: 6 }}>
            {results.map((r, i) => (
              <div key={i} style={{ fontSize: 14 }}>
                <span className={`badge ${r.ok ? "green" : "amber"}`}>{r.ok ? "OK" : "!"}</span>{" "}
                <span className="muted" style={{ fontSize: 12 }}>{r.t}</span> — {r.text}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
