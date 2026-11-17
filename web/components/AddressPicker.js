import { useEffect, useRef, useState, useCallback } from "react";
import { api } from "../lib/api";

// Zepto/Rapido-style address picker (Leaflet + OpenStreetMap, no API key):
//  - a map with a FIXED centre pin; the map moves under the pin
//  - "Use current location" (device GPS) + a search box (OSM place search)
//  - on every map move it reverse-geocodes the centre and finds the mandal,
//    and shows a clear "we deliver here" / "not serviced yet" banner
//  - one "House / flat / landmark" field + the auto-filled area line (editable)
//  - Home / Work / Other label chips
//
// Emits onChange({ lat, lng, mandal_id, mandal_name, address_line, label,
//                  serviceable, within_service_area }).
const LEAFLET_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";
const LEAFLET_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";
const DEFAULT = { lat: 16.51, lng: 80.63 }; // Vijayawada-ish (AP/TG region)

function ensureLeaflet() {
  return new Promise((resolve, reject) => {
    if (window.L) return resolve(window.L);
    if (!document.querySelector(`link[href="${LEAFLET_CSS}"]`)) {
      const link = document.createElement("link");
      link.rel = "stylesheet"; link.href = LEAFLET_CSS; document.head.appendChild(link);
    }
    const ex = document.querySelector(`script[src="${LEAFLET_JS}"]`);
    if (ex) { ex.addEventListener("load", () => resolve(window.L)); if (window.L) resolve(window.L); return; }
    const s = document.createElement("script");
    s.src = LEAFLET_JS; s.onload = () => resolve(window.L);
    s.onerror = () => reject(new Error("map failed to load")); document.body.appendChild(s);
  });
}

// Build a short, human address line from a Nominatim reverse-geocode result,
// instead of its very long display_name.
function shortAddress(j) {
  const a = j?.address || {};
  const parts = [
    a.road || a.pedestrian || a.neighbourhood || a.suburb,
    a.suburb && a.suburb !== (a.road || "") ? a.suburb : null,
    a.village || a.town || a.city || a.city_district || a.county,
    a.postcode,
  ].filter(Boolean);
  // de-dup consecutive repeats
  const seen = [];
  for (const p of parts) if (!seen.includes(p)) seen.push(p);
  return seen.join(", ") || (j?.display_name || "").split(",").slice(0, 3).join(", ");
}

const LABELS = ["Home", "Work", "Other"];

export default function AddressPicker({ value, onChange, autoLocate = false, height = 240,
  showServiceability = true }) {
  const divRef = useRef(null);
  const mapRef = useRef(null);
  const moveTimer = useRef(null);
  const searchTimer = useRef(null);
  const editedArea = useRef(false); // don't overwrite a line the user typed
  const lastPt = useRef(value?.lat ? { lat: value.lat, lng: value.lng } : null);
  const lastMandal = useRef(null);

  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState(null); // {within, mandal, nearest, dist}
  const [resolving, setResolving] = useState(false);
  const [locating, setLocating] = useState(false);
  const [err, setErr] = useState(null);

  const [label, setLabel] = useState(value?.label && LABELS.includes(value.label) ? value.label : "Home");
  const [customLabel, setCustomLabel] = useState(value?.label && !LABELS.includes(value.label) ? value.label : "");
  const [house, setHouse] = useState(value?.house || "");
  const [area, setArea] = useState(value?.address_line || "");

  // Resolve a centre point: reverse-geocode + nearest serviceable mandal.
  const resolvePoint = useCallback(async (lat, lng) => {
    setResolving(true); setErr(null);
    lastPt.current = { lat, lng };
    let mandal = null;
    try {
      const n = await api(`/locations/nearest?lat=${lat}&lng=${lng}`);
      mandal = n;
      lastMandal.current = n;
      setStatus({
        within: !!n.within_service_area,
        mandal_id: n.mandal_id, mandal: n.name, dist: n.distance_km,
        nearest: n.nearest_serviceable,
      });
    } catch { /* keep going; mandal stays null */ }
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=18&lat=${lat}&lon=${lng}`,
        { headers: { Accept: "application/json" } }
      );
      const j = await res.json();
      const line = shortAddress(j);
      if (line && !editedArea.current) setArea(line);
      emit({ lat, lng, mandal, area: !editedArea.current && line ? line : area });
    } catch {
      emit({ lat, lng, mandal, area });
    }
    setResolving(false);
  }, [area]); // eslint-disable-line react-hooks/exhaustive-deps

  function emit(over = {}) {
    const lat = over.lat ?? lastPt.current?.lat ?? null;
    const lng = over.lng ?? lastPt.current?.lng ?? null;
    const mandal = over.mandal ?? lastMandal.current
      ?? (status ? { mandal_id: status.mandal_id, name: status.mandal, within_service_area: status.within } : null);
    const a = over.area !== undefined ? over.area : area;
    const lbl = (label === "Other" ? (customLabel.trim() || "Other") : label);
    const address_line = [house.trim(), (a || "").trim()].filter(Boolean).join(", ");
    onChange?.({
      lat, lng,
      mandal_id: mandal?.mandal_id ?? mandal?.id ?? null,
      mandal_name: mandal?.name ?? null,
      serviceable: mandal?.serviceable ?? null,
      within_service_area: mandal?.within_service_area ?? status?.within ?? null,
      house: house.trim(),
      address_line,
      label: lbl,
    });
  }

  // Init the map once.
  useEffect(() => {
    let alive = true;
    const start = value?.lat ? { lat: value.lat, lng: value.lng } : DEFAULT;
    ensureLeaflet().then((L) => {
      if (!alive || !divRef.current || mapRef.current) return;
      const map = L.map(divRef.current, { zoomControl: true }).setView([start.lat, start.lng], 15);
      mapRef.current = map;
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19, attribution: "© OpenStreetMap",
      }).addTo(map);
      map.on("movestart", () => setResolving(true));
      map.on("moveend", () => {
        clearTimeout(moveTimer.current);
        moveTimer.current = setTimeout(() => {
          const c = map.getCenter();
          resolvePoint(+c.lat.toFixed(6), +c.lng.toFixed(6));
        }, 600);
      });
      setTimeout(() => map.invalidateSize(), 120);
      setReady(true);
      if (value?.lat) resolvePoint(value.lat, value.lng);
      else if (autoLocate) useMyLocation();
    }).catch((e) => setErr(e.message));
    return () => { alive = false; if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; } };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-emit when the hand-typed fields / label change (keeps parent in sync).
  useEffect(() => { if (ready) emit(); }, [house, label, customLabel]); // eslint-disable-line react-hooks/exhaustive-deps

  function recenter(lat, lng) {
    if (mapRef.current) mapRef.current.setView([lat, lng], 16);
    resolvePoint(lat, lng);
  }

  function useMyLocation() {
    setErr(null);
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setErr("Location isn't available on this device."); return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (p) => { setLocating(false); recenter(+p.coords.latitude.toFixed(6), +p.coords.longitude.toFixed(6)); },
      () => { setLocating(false); setErr("Couldn't get your location — move the map pin instead."); },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
  }

  // --- place search (OSM) ---
  const [q, setQ] = useState("");
  const [sugs, setSugs] = useState([]);
  function onSearch(text) {
    setQ(text);
    clearTimeout(searchTimer.current);
    if (text.trim().length < 3) { setSugs([]); return; }
    searchTimer.current = setTimeout(async () => {
      try {
        const res = await fetch(
          `https://nominatim.openstreetmap.org/search?format=jsonv2&limit=5&countrycodes=in&q=${encodeURIComponent(text)}`,
          { headers: { Accept: "application/json" } }
        );
        setSugs(await res.json());
      } catch { setSugs([]); }
    }, 500);
  }
  function pickSug(s) {
    setQ(s.display_name.split(",").slice(0, 2).join(", "));
    setSugs([]);
    recenter(+parseFloat(s.lat).toFixed(6), +parseFloat(s.lon).toFixed(6));
  }

  return (
    <div className="addr-picker">
      {/* search */}
      <div style={{ position: "relative", marginBottom: 8 }}>
        <input value={q} onChange={(e) => onSearch(e.target.value)}
               placeholder="🔍 Search area, street, landmark…" style={{ width: "100%" }} />
        {sugs.length > 0 && (
          <div style={{
            position: "absolute", zIndex: 1000, left: 0, right: 0, background: "var(--card, #fff)",
            border: "1px solid var(--line)", borderRadius: 8, marginTop: 2, overflow: "hidden",
            boxShadow: "0 6px 20px rgba(0,0,0,.12)",
          }}>
            {sugs.map((s, i) => (
              <div key={i} onClick={() => pickSug(s)}
                   style={{ padding: "8px 10px", fontSize: 13, cursor: "pointer", borderBottom: "1px solid var(--line)" }}>
                📍 {s.display_name}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* map with a fixed centre pin */}
      <div style={{ position: "relative" }}>
        <div ref={divRef} style={{ height, borderRadius: 10, overflow: "hidden", border: "1px solid var(--line)" }} />
        {/* centre pin overlay (pointer-events off so the map still drags) */}
        <div style={{
          position: "absolute", left: "50%", top: "50%", transform: "translate(-50%, -100%)",
          pointerEvents: "none", fontSize: 30, lineHeight: 1, zIndex: 500,
          filter: "drop-shadow(0 2px 2px rgba(0,0,0,.35))",
        }}>📍</div>
        <button type="button" className="ghost" onClick={useMyLocation} disabled={locating}
          style={{
            position: "absolute", right: 10, bottom: 10, zIndex: 600, fontSize: 12,
            background: "var(--card, #fff)", boxShadow: "0 2px 8px rgba(0,0,0,.18)",
          }}>
          {locating ? "Locating…" : "📍 Use current location"}
        </button>
      </div>
      <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
        Move the map to place the pin on your exact door.
      </div>

      {/* serviceability banner — only where delivery availability matters
          (checkout). At sign-up/profile we just capture the address. */}
      {showServiceability && resolving && <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>Finding your area…</div>}
      {showServiceability && !resolving && status && (
        status.within ? (
          <div style={{
            marginTop: 8, padding: "8px 10px", borderRadius: 8, fontSize: 13,
            background: "rgba(22,163,74,.10)", border: "1px solid rgba(22,163,74,.35)", color: "var(--green-700, #15803d)",
          }}>✅ We deliver here — <b>{status.mandal}</b></div>
        ) : (
          <div style={{
            marginTop: 8, padding: "8px 10px", borderRadius: 8, fontSize: 13,
            background: "rgba(217,119,6,.10)", border: "1px solid rgba(217,119,6,.35)", color: "#b45309",
          }}>
            ⚠️ We don’t deliver here yet.
            {status.nearest
              ? <> Nearest serviced area: <b>{status.nearest.name}</b> (~{status.nearest.distance_km} km).</>
              : <> No serviced area nearby.</>}
          </div>
        )
      )}
      {err && <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>{err}</div>}

      {/* fields */}
      <div className="form-grid" style={{ marginTop: 10 }}>
        <label style={{ gridColumn: "1 / -1" }}>Flat / House no. / Floor
          <input value={house} onChange={(e) => setHouse(e.target.value)}
                 placeholder="e.g. Flat 302, Sai Residency" />
        </label>
        <label style={{ gridColumn: "1 / -1" }}>Area / Street / Landmark
          <input value={area}
                 onChange={(e) => { editedArea.current = true; setArea(e.target.value); emit({ area: e.target.value }); }}
                 placeholder="Auto-filled from the map — edit if needed" />
        </label>
      </div>

      {/* label chips */}
      <div style={{ marginTop: 8 }}>
        <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>Save address as</div>
        <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
          {LABELS.map((l) => (
            <button type="button" key={l} onClick={() => setLabel(l)}
              className={label === l ? "" : "ghost"} style={{ fontSize: 13, padding: "4px 12px" }}>
              {l === "Home" ? "🏠 " : l === "Work" ? "💼 " : "📍 "}{l}
            </button>
          ))}
        </div>
        {label === "Other" && (
          <input value={customLabel} onChange={(e) => setCustomLabel(e.target.value)}
                 placeholder="Name this address (e.g. Mom's place)" style={{ marginTop: 6, width: "100%" }} />
        )}
      </div>
    </div>
  );
}
