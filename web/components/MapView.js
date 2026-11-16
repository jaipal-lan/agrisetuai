import { useEffect, useRef } from "react";

// Read-only map with colored dots (Leaflet + OSM). points: [{lat,lng,label,color}].
const LEAFLET_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";
const LEAFLET_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";

function ensureLeaflet() {
  return new Promise((resolve, reject) => {
    if (window.L) return resolve(window.L);
    if (!document.querySelector(`link[href="${LEAFLET_CSS}"]`)) {
      const link = document.createElement("link");
      link.rel = "stylesheet"; link.href = LEAFLET_CSS;
      document.head.appendChild(link);
    }
    const existing = document.querySelector(`script[src="${LEAFLET_JS}"]`);
    if (existing) { existing.addEventListener("load", () => resolve(window.L)); if (window.L) resolve(window.L); return; }
    const s = document.createElement("script");
    s.src = LEAFLET_JS; s.onload = () => resolve(window.L);
    s.onerror = () => reject(new Error("map failed to load"));
    document.body.appendChild(s);
  });
}

export default function MapView({ points = [], height = 300 }) {
  const divRef = useRef(null);
  const mapRef = useRef(null);
  const layerRef = useRef(null);

  useEffect(() => {
    let alive = true;
    ensureLeaflet().then((L) => {
      if (!alive || !divRef.current || mapRef.current) return;
      const map = L.map(divRef.current).setView([16.51, 80.63], 7);
      mapRef.current = map;
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19, attribution: "© OpenStreetMap",
      }).addTo(map);
      layerRef.current = L.layerGroup().addTo(map);
      setTimeout(() => map.invalidateSize(), 100);
      draw(L);
    }).catch(() => {});
    return () => { alive = false; if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; } };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { if (window.L && layerRef.current) draw(window.L); }, [points]);

  function draw(L) {
    const layer = layerRef.current;
    if (!layer) return;
    layer.clearLayers();
    const pts = points.filter((p) => p.lat != null && p.lng != null);
    pts.forEach((p) => {
      L.circleMarker([p.lat, p.lng], {
        radius: 7, color: p.color || "#2563eb", fillColor: p.color || "#2563eb", fillOpacity: 0.8, weight: 1,
      }).bindPopup(p.label || "").addTo(layer);
    });
    if (pts.length && mapRef.current) {
      try { mapRef.current.fitBounds(L.latLngBounds(pts.map((p) => [p.lat, p.lng])).pad(0.3)); } catch {}
    }
  }

  return <div ref={divRef} style={{ height, borderRadius: 8, overflow: "hidden", border: "1px solid var(--line)" }} />;
}
