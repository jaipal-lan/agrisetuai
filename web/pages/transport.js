import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { api, getUser } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

const NEXT = {
  ready_for_pickup: ["picked_up", "Mark picked up"],
  picked_up: ["in_transit", "Mark in transit"],
  in_transit: ["out_for_delivery", "Out for delivery"],
  out_for_delivery: ["delivered", "Mark delivered"],
};
const SHAREABLE = ["picked_up", "in_transit", "out_for_delivery"];

export default function Transport() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sharing, setSharing] = useState(null); // order_id currently broadcasting
  const [locMsg, setLocMsg] = useState(null);
  const watchRef = useRef(null);

  function stopSharing() {
    if (watchRef.current != null && navigator.geolocation) {
      navigator.geolocation.clearWatch(watchRef.current);
    }
    watchRef.current = null;
    setSharing(null);
  }

  function toggleShare(orderId) {
    if (sharing === orderId) { stopSharing(); setLocMsg("Stopped sharing location."); return; }
    stopSharing();
    if (!navigator.geolocation) { setLocMsg("This device can't share location."); return; }
    setLocMsg("Getting a GPS fix…");
    watchRef.current = navigator.geolocation.watchPosition(
      async (pos) => {
        try {
          await api(`/transport/orders/${orderId}/location`, { method: "POST",
            body: { lat: pos.coords.latitude, lng: pos.coords.longitude } });
          setLocMsg(`Live location shared · ${new Date().toLocaleTimeString()}`);
        } catch (e) { setLocMsg(`Share failed: ${e.message}`); }
      },
      (e) => setLocMsg(`Location error: ${e.message}`),
      { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 },
    );
    setSharing(orderId);
  }

  // Stop the GPS watcher when leaving the page.
  useEffect(() => () => stopSharing(), []);

  async function load() {
    try {
      setData(await api("/transport/jobs?include_done=true"));
    } catch (e) {
      setErr(e.message);
    }
  }
  useEffect(() => { setMe(getUser()); }, []);
  usePoll(load, 15000);

  async function milestone(orderId, event) {
    setBusy(true);
    setErr(null);
    try {
      await api(`/orders/${orderId}/shipment/event`, { method: "POST", body: { event } });
      await load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const gate = roleGate(me, GROUPS.carrier, { label: "transport jobs" });
  if (gate) return gate;

  return (
    <div style={{ maxWidth: 720 }}>
      <h1>Transport</h1>
      {err && <div className="error">{err}</div>}
      {data && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="between">
            <div><b>{data.active_count}</b> active trip{data.active_count === 1 ? "" : "s"}</div>
            <div>Active earnings: <b>₹{data.active_earning}</b></div>
          </div>
        </div>
      )}
      {!data || data.jobs.length === 0 ? (
        <p className="muted">No transport jobs right now.</p>
      ) : (
        data.jobs.map((j) => {
          const next = NEXT[j.status];
          return (
            <div className="card" key={j.order_id} style={{ marginBottom: 12 }}>
              <div className="between">
                <Link href={`/order/${j.order_id}`}><b>{j.public_id}</b></Link>
                <span className="badge grey">{j.status.replace(/_/g, " ")}</span>
              </div>
              <div className="muted" style={{ fontSize: 14 }}>
                {j.quantity} {j.unit} · 🚚 {j.courier_name || "unassigned"}{j.vehicle_class ? ` · ${j.vehicle_class}` : ""}
              </div>
              <div className="price" style={{ fontSize: 18, marginTop: 6 }}>₹{j.transport_charge}<small> trip earning</small></div>
              <div className="row" style={{ marginTop: 10, gap: 8, flexWrap: "wrap" }}>
                {next && (
                  <button disabled={busy} onClick={() => milestone(j.order_id, next[0])}>{next[1]}</button>
                )}
                {SHAREABLE.includes(j.status) && (
                  <button className={sharing === j.order_id ? "" : "ghost"}
                          onClick={() => toggleShare(j.order_id)}>
                    {sharing === j.order_id ? "📍 Stop sharing" : "📍 Share live location"}
                  </button>
                )}
              </div>
              {sharing === j.order_id && locMsg && (
                <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>{locMsg}</div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
