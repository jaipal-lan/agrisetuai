import { useEffect, useRef, useState } from "react";

import { useI18n } from "../lib/i18n";

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
  const { t } = useI18n();
  const divRef = useRef(null);
  const mapRef = useRef(null);
  const markerRef = useRef(null);
  const roRef = useRef(null);
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
      // Re-measure when the container becomes visible/resizes (e.g. opened inside
      // a <details>), plus a couple of early nudges — without this the map tiles
      // render grey and clicks map to the wrong point until the next resize.
      [60, 250, 600].forEach((d) => setTimeout(() => { try { map.invalidateSize(); } catch {} }, d));
      if (typeof ResizeObserver !== "undefined") {
        roRef.current = new ResizeObserver(() => { try { map.invalidateSize(); } catch {} });
        roRef.current.observe(divRef.current);
      }
    }).catch((e) => setErr(e.message));
    return () => {
      alive = false;
      if (roRef.current) { roRef.current.disconnect(); roRef.current = null; }
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function useMyLocation() {
    if (!navigator.geolocation) { setErr(t("geo_unavailable")); return; }
    navigator.geolocation.getCurrentPosition((p) => {
      const ll = { lat: +p.coords.latitude.toFixed(6), lng: +p.coords.longitude.toFixed(6) };
      if (mapRef.current && markerRef.current) {
        markerRef.current.setLatLng([ll.lat, ll.lng]);
        mapRef.current.setView([ll.lat, ll.lng], 15);
      }
      onChange?.(ll);
    }, () => setErr(t("ap_geo_fail")), { enableHighAccuracy: true, timeout: 8000 });
  }

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
        <button type="button" className="ghost" style={{ fontSize: 12 }} onClick={useMyLocation}>{t("ap_use_location")}</button>
        {value?.lat ? <span className="muted" style={{ fontSize: 12 }}>{value.lat}, {value.lng}</span> : <span className="muted" style={{ fontSize: 12 }}>{t("mp_tap")}</span>}
      </div>
      <div ref={divRef} style={{ height, borderRadius: 8, overflow: "hidden", border: "1px solid var(--line)" }} />
      {err && <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{err}</div>}
    </div>
  );
}
