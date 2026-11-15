import { useEffect, useRef, useState } from "react";

// Draggable map pin (Leaflet + OpenStreetMap tiles). Reports {lat, lng} on drag,
// click, or "use my location". Leaflet is loaded from cdnjs on demand.
const LEAFLET_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";
const LEAFLET_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";
const DEFAULT = { lat: 16.51, lng: 80.63 }; // Vijayawada-ish (AP/TG region)

function ensureLeaflet() {
  return new Promise((resolve, reject) => {
    if (window.L) return resolve(window.L);
    if (!document.querySelector(`link[href="${LEAFLET_CSS}"]`)) {
      const link = document.createElement("link");
      link.rel = "stylesheet"; link.href = LEAFLET_CSS;
      document.head.appendChild(link);
    }
    if (document.querySelector(`script[src="${LEAFLET_JS}"]`)) {
      const s = document.querySelector(`script[src="${LEAFLET_JS}"]`);
      s.addEventListener("load", () => resolve(window.L));
      if (window.L) resolve(window.L);
      return;
    }
    const s = document.createElement("script");
    s.src = LEAFLET_JS; s.onload = () => resolve(window.L);
    s.onerror = () => reject(new Error("map failed to load"));
    document.body.appendChild(s);
  });
}

export default function MapPicker({ value, onChange, height = 240 }) {
  const divRef = useRef(null);
  const mapRef = useRef(null);
  const markerRef = useRef(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let alive = true;
    const start = value && value.lat ? value : DEFAULT;
    ensureLeaflet().then((L) => {
      if (!alive || !divRef.current || mapRef.current) return;
      const map = L.map(divRef.current).setView([start.lat, start.lng], 13);
      mapRef.current = map;
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19, attribution: "© OpenStreetMap",
      }).addTo(map);
      const marker = L.marker([start.lat, start.lng], { draggable: true }).addTo(map);
      markerRef.current = marker;
      const emit = (ll) => onChange?.({ lat: +ll.lat.toFixed(6), lng: +ll.lng.toFixed(6) });
      marker.on("dragend", () => emit(marker.getLatLng()));
      map.on("click", (e) => { marker.setLatLng(e.latlng); emit(e.latlng); });
      setTimeout(() => map.invalidateSize(), 100);
    }).catch((e) => setErr(e.message));
    return () => { alive = false; if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; } };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function useMyLocation() {
    if (!navigator.geolocation) { setErr("Location unavailable"); return; }
    navigator.geolocation.getCurrentPosition((p) => {
      const ll = { lat: +p.coords.latitude.toFixed(6), lng: +p.coords.longitude.toFixed(6) };
      if (mapRef.current && markerRef.current) {
        markerRef.current.setLatLng([ll.lat, ll.lng]);
        mapRef.current.setView([ll.lat, ll.lng], 15);
      }
      onChange?.(ll);
    }, () => setErr("Couldn't get your location"), { enableHighAccuracy: true, timeout: 8000 });
  }

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
        <button type="button" className="ghost" style={{ fontSize: 12 }} onClick={useMyLocation}>📍 Use my location</button>
        {value?.lat ? <span className="muted" style={{ fontSize: 12 }}>{value.lat}, {value.lng}</span> : <span className="muted" style={{ fontSize: 12 }}>Tap the map to drop a pin</span>}
      </div>
      <div ref={divRef} style={{ height, borderRadius: 8, overflow: "hidden", border: "1px solid var(--line)" }} />
      {err && <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{err}</div>}
    </div>
  );
}
