import Link from "next/link";
import { useEffect, useState } from "react";

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

export default function Transport() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

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
              {next && (
                <div style={{ marginTop: 10 }}>
                  <button disabled={busy} onClick={() => milestone(j.order_id, next[0])}>{next[1]}</button>
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
