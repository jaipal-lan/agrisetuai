import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { api, downloadFile, getUser } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n, tEnum } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

const NEXT = {
  ready_for_pickup: ["picked_up", "tr_mark_picked_up"],
  picked_up: ["in_transit", "tr_mark_in_transit"],
  in_transit: ["out_for_delivery", "tr_out_for_delivery"],
  out_for_delivery: ["delivered", "tr_mark_delivered"],
};
const SHAREABLE = ["picked_up", "in_transit", "out_for_delivery"];

export default function Transport() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [data, setData] = useState(null);
  const [earn, setEarn] = useState(null);
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
    if (sharing === orderId) { stopSharing(); setLocMsg(t("tr_stopped_sharing")); return; }
    stopSharing();
    if (!navigator.geolocation) { setLocMsg(t("tr_cant_share")); return; }
    setLocMsg(t("tr_getting_fix"));
    watchRef.current = navigator.geolocation.watchPosition(
      async (pos) => {
        try {
          await api(`/transport/orders/${orderId}/location`, { method: "POST",
            body: { lat: pos.coords.latitude, lng: pos.coords.longitude } });
          setLocMsg(`${t("tr_live_shared")} ${new Date().toLocaleTimeString()}`);
        } catch (e) { setLocMsg(`${t("tr_share_failed")} ${e.message}`); }
      },
      (e) => setLocMsg(`${t("tr_loc_error")} ${e.message}`),
      { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 },
    );
    setSharing(orderId);
  }

  // Stop the GPS watcher when leaving the page.
  useEffect(() => () => stopSharing(), []);

  async function load() {
    try {
      setData(await api("/transport/jobs?include_done=true"));
      setEarn(await api("/transport/earnings"));
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
      <h1>{t("transport")}</h1>
      {err && <div className="error">{err}</div>}
      {data && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="between">
            <div><b>{data.active_count}</b> {data.active_count === 1 ? t("tr_active_trip") : t("tr_active_trips")}</div>
            <div>{t("tr_active_earnings")} <b>₹{data.active_earning}</b></div>
          </div>
        </div>
      )}
      {!data || data.jobs.length === 0 ? (
        <p className="muted">{t("tr_no_jobs")}</p>
      ) : (
        data.jobs.map((j) => {
          const next = NEXT[j.status];
          return (
            <div className="card" key={j.order_id} style={{ marginBottom: 12 }}>
              <div className="between">
                <Link href={`/order/${j.order_id}`}><b>{j.public_id}</b></Link>
                <span className="badge grey">{t("st_" + j.status)}</span>
              </div>
              <div className="muted" style={{ fontSize: 14 }}>
                {j.quantity} {j.unit} · 🚚 {j.courier_name || t("tr_unassigned")}{j.vehicle_class ? ` · ${tEnum(t, "vc_", j.vehicle_class)}` : ""}
              </div>
              <div className="price" style={{ fontSize: 18, marginTop: 6 }}>₹{j.transport_charge}<small> {t("tr_trip_earning")}</small></div>
              <div className="row" style={{ marginTop: 10, gap: 8, flexWrap: "wrap" }}>
                {next && (
                  <button disabled={busy} onClick={() => milestone(j.order_id, next[0])}>{t(next[1])}</button>
                )}
                {SHAREABLE.includes(j.status) && (
                  <button className={sharing === j.order_id ? "" : "ghost"}
                          onClick={() => toggleShare(j.order_id)}>
                    {sharing === j.order_id ? t("tr_stop_sharing") : t("tr_share_location")}
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

      {earn && (
        <div style={{ marginTop: 24 }}>
          <div className="between">
            <h2 style={{ margin: 0 }}>{t("tr_my_earnings")}</h2>
            <button className="ghost" onClick={() => downloadFile("/transport/earnings.csv", "transport-earnings.csv")}
                    style={{ padding: "4px 10px", fontSize: 13 }}>{t("tr_download_csv")}</button>
          </div>
          <div className="stat-strip" style={{ marginTop: 10 }}>
            <div><b>₹{earn.paid_total}</b> {t("tr_paid")}</div>
            <div><b>₹{earn.pending_total}</b> {t("tr_awaiting_payout")}</div>
            <div><b>₹{earn.in_progress_total}</b> {t("tr_in_progress")}</div>
            <div><b>{earn.trip_count}</b> {t("tr_trips_count")}</div>
          </div>
          {earn.trips.length > 0 && (
            <div className="table-wrap" style={{ marginTop: 10 }}>
              <table>
                <thead><tr><th>{t("tr_th_order")}</th><th>{t("tr_th_product")}</th><th>{t("tr_th_qty")}</th><th>{t("tr_th_amount")}</th><th>{t("tr_th_status")}</th></tr></thead>
                <tbody>
                  {earn.trips.map((tp, i) => (
                    <tr key={i}>
                      <td>{tp.public_id ? <Link href={`/order/${tp.order_id}`}>{tp.public_id}</Link> : "—"}</td>
                      <td>{tp.commodity || "—"}</td>
                      <td>{tp.quantity} {tp.unit}</td>
                      <td>₹{tp.amount}</td>
                      <td><span className={`badge ${tp.status === "paid" ? "green" : "grey"}`}>{tp.status === "paid" ? t("tr_paid") : t("tr_awaiting_payout")}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
