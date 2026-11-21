import { useEffect, useRef } from "react";

// Live delivery map (Leaflet + OSM, no API key): pickup (green), drop (red), and
// the courier's live position (blue), with a route line. Updates in place when the
// courier prop changes (the parent polls tracking every ~12s).
const LEAFLET_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";
const LEAFLET_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";

function ensureLeaflet() {
  return new Promise((resolve, reject) => {
    if (window.L) return resolve(window.L);
    if (!document.querySelector(`link[href="${LEAFLET_CSS}"]`)) {
      const l = document.createElement("link");
      l.rel = "stylesheet"; l.href = LEAFLET_CSS; document.head.appendChild(l);
    }
    const ex = document.querySelector(`script[src="${LEAFLET_JS}"]`);
    if (ex) { ex.addEventListener("load", () => resolve(window.L)); if (window.L) resolve(window.L); return; }
    const s = document.createElement("script");
    s.src = LEAFLET_JS; s.onload = () => resolve(window.L);
    s.onerror = () => reject(new Error("map failed")); document.body.appendChild(s);
  });
}

const dot = (color) => ({ radius: 9, color: "#fff", weight: 2, fillColor: color, fillOpacity: 1 });

export default function LiveTrackMap({ from, to, courier, height = 260, labels = {} }) {
  const L10N = { pickup: "Pickup", delivery: "Delivery", courier: "Courier",
    km_away: "km away", min: "min", ...labels };
  const divRef = useRef(null);
  const mapRef = useRef(null);
  const layerRef = useRef(null);
  const firstFit = useRef(true);

  useEffect(() => {
    let alive = true;
    ensureLeaflet().then((L) => {
      if (!alive || !divRef.current || mapRef.current) return;
      const map = L.map(divRef.current, { zoomControl: true });
      mapRef.current = map;
      map.setView([(from?.lat ?? to?.lat ?? 16.5), (from?.lng ?? to?.lng ?? 80.6)], 10);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19, attribution: "© OpenStreetMap",
      }).addTo(map);
      layerRef.current = L.layerGroup().addTo(map);
      setTimeout(() => map.invalidateSize(), 120);
      draw(L);
    }).catch(() => {});
    return () => { alive = false; if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; } };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { if (window.L && layerRef.current) draw(window.L); }, [
    from?.lat, from?.lng, to?.lat, to?.lng, courier?.lat, courier?.lng,
  ]);

  function draw(L) {
    const layer = layerRef.current; const map = mapRef.current;
    if (!layer || !map) return;
    layer.clearLayers();
    const pts = [];
    if (from?.lat != null) { L.circleMarker([from.lat, from.lng], dot("#16a34a")).bindPopup(L10N.pickup).addTo(layer); pts.push([from.lat, from.lng]); }
    if (to?.lat != null) { L.circleMarker([to.lat, to.lng], dot("#dc2626")).bindPopup(L10N.delivery).addTo(layer); pts.push([to.lat, to.lng]); }
    if (courier?.lat != null) {
      const label = `🚚 ${L10N.courier}${courier.distance_km != null ? ` · ${courier.distance_km} ${L10N.km_away}` : ""}${courier.eta_minutes != null ? ` · ~${courier.eta_minutes} ${L10N.min}` : ""}`;
      L.circleMarker([courier.lat, courier.lng], dot("#2563eb")).bindPopup(label).addTo(layer);
      pts.push([courier.lat, courier.lng]);
    }
    // Route line: pickup -> courier -> drop (whatever points exist).
    const line = [from, courier, to].filter((p) => p?.lat != null).map((p) => [p.lat, p.lng]);
    if (line.length >= 2) L.polyline(line, { color: "#2563eb", weight: 3, opacity: 0.6, dashArray: "6 6" }).addTo(layer);
    if (pts.length) {
      if (firstFit.current) { map.fitBounds(L.latLngBounds(pts).pad(0.3)); firstFit.current = false; }
      else if (courier?.lat != null) map.panTo([courier.lat, courier.lng]);
    }
  }

  if (!from && !to && !courier) return null;
  return <div ref={divRef} style={{ height, borderRadius: 8, overflow: "hidden", border: "1px solid var(--line)" }} />;
}
