import Link from "next/link";
import { useEffect, useState } from "react";

import { api, downloadFile, getUser } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

const METRICS = [
  { value: "inspections", label: "tm_metric_inspections" },
  { value: "orders_assigned", label: "tm_metric_orders" },
];

function todayISO(offsetDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

export default function Team() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [data, setData] = useState(null);
  const [targets, setTargets] = useState([]);
  const [meetings, setMeetings] = useState([]);
  const [board, setBoard] = useState(null);
  const [trend, setTrend] = useState(null);
  const [period, setPeriod] = useState("month");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(null);
  const [pick, setPick] = useState({}); // orderId -> agentId

  // target form
  const [tf, setTf] = useState({ agent_id: "", metric: "inspections", target_value: "", period_start: todayISO(), period_end: todayISO(7), note: "" });
  // meeting form
  const [mf, setMf] = useState({ title: "", scheduled_at: "", location: "", agenda: "", attendee_ids: [] });

  useEffect(() => { setMe(getUser()); }, []);

  function load() {
    api("/team/overview").then(setData).catch((e) => setErr(e.message));
    api("/team/targets").then(setTargets).catch(() => {});
    api("/team/meetings").then(setMeetings).catch(() => {});
    api(`/team/leaderboard?period=${period}`).then(setBoard).catch(() => {});
    api("/team/trends?weeks=6").then(setTrend).catch(() => {});
  }
  usePoll(() => { if (me) load(); }, 20000, [me, period]);

  async function assign(orderId) {
    const agentId = pick[orderId];
    if (!agentId) return;
    setBusy(`assign-${orderId}`); setErr(null);
    try {
      await api(`/orders/${orderId}/assign-inspection`, { method: "POST", body: { agent_id: Number(agentId) } });
      load();
    } catch (e) { setErr(e.message); } finally { setBusy(null); }
  }

  async function createTarget(e) {
    e.preventDefault(); setErr(null);
    if (!tf.agent_id || !tf.target_value) { setErr(t("tm_pick_agent_target")); return; }
    setBusy("target");
    try {
      await api("/team/targets", { method: "POST", body: {
        agent_id: Number(tf.agent_id), metric: tf.metric, target_value: Number(tf.target_value),
        period_start: tf.period_start, period_end: tf.period_end, note: tf.note || null } });
      setTf((f) => ({ ...f, target_value: "", note: "" }));
      load();
    } catch (e) { setErr(e.message); } finally { setBusy(null); }
  }

  async function archiveTarget(id) {
    setBusy(`t-${id}`);
    try { await api(`/team/targets/${id}`, { method: "PATCH", body: { status: "archived" } }); load(); }
    catch (e) { setErr(e.message); } finally { setBusy(null); }
  }

  async function createMeeting(e) {
    e.preventDefault(); setErr(null);
    if (!mf.title.trim() || !mf.scheduled_at) { setErr(t("tm_meeting_needs")); return; }
    setBusy("meeting");
    try {
      await api("/team/meetings", { method: "POST", body: {
        title: mf.title.trim(), scheduled_at: mf.scheduled_at, location: mf.location || null,
        agenda: mf.agenda || null, attendee_ids: mf.attendee_ids.map(Number) } });
      setMf({ title: "", scheduled_at: "", location: "", agenda: "", attendee_ids: [] });
      load();
    } catch (e) { setErr(e.message); } finally { setBusy(null); }
  }

  async function patchMeeting(id, body) {
    setBusy(`m-${id}`);
    try { await api(`/team/meetings/${id}`, { method: "PATCH", body }); load(); }
    catch (e) { setErr(e.message); } finally { setBusy(null); }
  }

  function toggleAttended(m, agentId) {
    const cur = m.attended_ids || [];
    const next = cur.includes(agentId) ? cur.filter((x) => x !== agentId) : [...cur, agentId];
    patchMeeting(m.id, { attended_ids: next });
  }

  function toggleAttendee(id) {
    setMf((f) => {
      const s = f.attendee_ids.includes(id)
        ? f.attendee_ids.filter((x) => x !== id) : [...f.attendee_ids, id];
      return { ...f, attendee_ids: s };
    });
  }

  const gate = roleGate(me, GROUPS.lead, { label: "the team console" });
  if (gate) return gate;
  if (!data) return <p className="muted">{t("loading")}</p>;

  return (
    <div>
      <h1>{t("team")}</h1>
      <p className="tagline">{t("tm_intro")}</p>
      {err && <div className="error">{err}</div>}

      <CollectionCentre />

      <div className="stat-strip">
        <div><b>{data.agents.length}</b> {t("tm_field_agents")}</div>
        <div><b>{data.unassigned}</b> {t("tm_unassigned")}</div>
        <div><b>{data.pipeline.length}</b> {t("tm_in_verification")}</div>
        <div><b>{data.active_orders}</b> {t("tm_active_orders")}</div>
      </div>

      {/* ---- Leaderboard ---- */}
      <div className="between" style={{ marginTop: 22 }}>
        <h2 style={{ margin: 0 }}>{t("tm_leaderboard")}</h2>
        <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
          {["week", "month", "all"].map((p) => (
            <button key={p} className={period === p ? "" : "ghost"} onClick={() => setPeriod(p)}
                    style={{ padding: "4px 10px", fontSize: 13 }}>
              {p === "all" ? t("tm_all_time") : `${t("tm_this")} ${p === "week" ? t("tm_period_week") : t("tm_period_month")}`}
            </button>
          ))}
          <button className="ghost" style={{ padding: "4px 10px", fontSize: 13 }}
                  onClick={() => downloadFile(`/team/leaderboard.csv?period=${period}`, `leaderboard-${period}.csv`)}>
            {t("tm_csv")}
          </button>
        </div>
      </div>

      {trend && trend.series?.some((w) => w.inspections || w.orders) && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>{t("tm_insp_per_week")}</div>
          <div className="row" style={{ alignItems: "flex-end", gap: 8, height: 90 }}>
            {(() => {
              const max = Math.max(1, ...trend.series.map((w) => w.inspections));
              return trend.series.map((w) => (
                <div key={w.week_start} style={{ flex: 1, textAlign: "center" }}>
                  <div className="pbar-fill" title={`${w.inspections} ${t("tm_inspections")}`}
                       style={{ height: `${Math.round((w.inspections / max) * 70)}px`, minHeight: 2, borderRadius: 4 }} />
                  <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{w.week_start.slice(5)}</div>
                  <div style={{ fontSize: 12 }}>{w.inspections}</div>
                </div>
              ));
            })()}
          </div>
        </div>
      )}
      {!board || board.rows.length === 0 ? (
        <p className="muted">{t("tm_no_agents")}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>#</th><th>{t("tm_th_agent")}</th><th>{t("tm_th_attainment")}</th><th>{t("tm_th_targets_met")}</th>
                <th>{t("tm_th_inspections")}</th><th>{t("tm_th_orders")}</th><th>{t("tm_th_attendance")}</th></tr>
            </thead>
            <tbody>
              {board.rows.map((r) => (
                <tr key={r.agent_id}>
                  <td>{r.rank === 1 ? "🥇" : r.rank === 2 ? "🥈" : r.rank === 3 ? "🥉" : r.rank}</td>
                  <td>{r.agent_name}</td>
                  <td><b>{r.attainment_pct}%</b></td>
                  <td>{r.targets_met}/{r.targets_active}</td>
                  <td>{r.inspections}</td>
                  <td>{r.orders}</td>
                  <td>{r.attendance_pct == null ? "—" : `${r.attendance_pct}% (${r.meetings_attended}/${r.meetings_invited})`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2 style={{ marginTop: 20 }}>{t("tm_orders_need_verify")}</h2>
      {data.pipeline.length === 0 ? (
        <p className="muted">{t("tm_nothing_waiting")}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>{t("tr_th_order")}</th><th>{t("tm_th_product")}</th><th>{t("tm_th_qty")}</th><th>{t("status")}</th><th>{t("tm_th_agent")}</th><th></th></tr>
            </thead>
            <tbody>
              {data.pipeline.map((o) => (
                <tr key={o.order_id}>
                  <td><Link href={`/order/${o.order_id}`}>{o.public_id}</Link></td>
                  <td>{o.commodity || "—"}</td>
                  <td>{o.quantity} {o.unit}</td>
                  <td><span className="badge grey">{t("st_" + o.status)}</span></td>
                  <td>{o.assigned_agent_name || <span className="muted">{t("tm_unassigned")}</span>}</td>
                  <td>
                    <div className="row" style={{ gap: 6 }}>
                      <select value={pick[o.order_id] || ""}
                              onChange={(e) => setPick((p) => ({ ...p, [o.order_id]: e.target.value }))}>
                        <option value="">{t("tm_pick_agent")}</option>
                        {data.agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                      </select>
                      <button className="ghost" disabled={busy === `assign-${o.order_id}` || !pick[o.order_id]}
                              onClick={() => assign(o.order_id)}>
                        {o.assigned_agent_id ? t("tm_reassign") : t("tm_assign")}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ---- Targets ---- */}
      <h2 style={{ marginTop: 28 }}>{t("tm_targets")}</h2>
      <form className="card" onSubmit={createTarget} style={{ marginBottom: 14 }}>
        <div className="form-grid">
          <label>{t("tm_th_agent")}
            <select value={tf.agent_id} onChange={(e) => setTf((f) => ({ ...f, agent_id: e.target.value }))}>
              <option value="">{t("tm_pick_agent")}</option>
              {data.agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </label>
          <label>{t("tm_metric")}
            <select value={tf.metric} onChange={(e) => setTf((f) => ({ ...f, metric: e.target.value }))}>
              {METRICS.map((m) => <option key={m.value} value={m.value}>{t(m.label)}</option>)}
            </select>
          </label>
          <label>{t("tm_target")}
            <input type="number" min="1" value={tf.target_value}
                   onChange={(e) => setTf((f) => ({ ...f, target_value: e.target.value }))} placeholder={t("tm_ph_target")} />
          </label>
          <label>{t("tm_from")}
            <input type="date" value={tf.period_start} onChange={(e) => setTf((f) => ({ ...f, period_start: e.target.value }))} />
          </label>
          <label>{t("tm_to")}
            <input type="date" value={tf.period_end} onChange={(e) => setTf((f) => ({ ...f, period_end: e.target.value }))} />
          </label>
          <label>{t("tm_note_opt")}
            <input value={tf.note} onChange={(e) => setTf((f) => ({ ...f, note: e.target.value }))} placeholder={t("tm_ph_note")} />
          </label>
        </div>
        <button type="submit" disabled={busy === "target"} style={{ marginTop: 10 }}>{t("tm_set_target")}</button>
      </form>

      {targets.length === 0 ? (
        <p className="muted">{t("tm_no_targets")}</p>
      ) : (
        <div className="grid">
          {targets.map((tg) => (
            <div className="card" key={tg.id}>
              <div className="between">
                <h3 style={{ margin: 0 }}>{tg.agent_name}</h3>
                <span className={`badge ${tg.met ? "green" : "grey"}`}>{tg.met ? t("ag_met") : `${tg.pct}%`}</span>
              </div>
              <div className="muted" style={{ fontSize: 13, margin: "2px 0 8px" }}>
                {tg.progress} / {tg.target_value} {tg.metric_label} · {tg.period_start} → {tg.period_end}
              </div>
              <div className="pbar"><div className="pbar-fill" style={{ width: `${tg.pct}%` }} /></div>
              {tg.note && <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>{tg.note}</div>}
              <button className="ghost" style={{ marginTop: 8 }} disabled={busy === `t-${tg.id}`}
                      onClick={() => archiveTarget(tg.id)}>{t("tm_archive")}</button>
            </div>
          ))}
        </div>
      )}

      {/* ---- Meetings ---- */}
      <h2 style={{ marginTop: 28 }}>{t("tm_meetings")}</h2>
      <form className="card" onSubmit={createMeeting} style={{ marginBottom: 14 }}>
        <div className="form-grid">
          <label>{t("tm_meeting_title")}
            <input value={mf.title} onChange={(e) => setMf((f) => ({ ...f, title: e.target.value }))} placeholder={t("tm_ph_meeting_title")} />
          </label>
          <label>{t("tm_when")}
            <input type="datetime-local" value={mf.scheduled_at} onChange={(e) => setMf((f) => ({ ...f, scheduled_at: e.target.value }))} />
          </label>
          <label>{t("tm_location_opt")}
            <input value={mf.location} onChange={(e) => setMf((f) => ({ ...f, location: e.target.value }))} placeholder={t("tm_ph_location")} />
          </label>
          <label style={{ gridColumn: "1 / -1" }}>{t("tm_agenda_opt")}
            <input value={mf.agenda} onChange={(e) => setMf((f) => ({ ...f, agenda: e.target.value }))} placeholder={t("tm_ph_agenda")} />
          </label>
        </div>
        <div style={{ marginTop: 8 }}>
          <div className="muted" style={{ fontSize: 13, marginBottom: 4 }}>{t("tm_invite_agents")}</div>
          <div className="row" style={{ flexWrap: "wrap", gap: 10 }}>
            {data.agents.map((a) => (
              <label key={a.id} className="chk">
                <input type="checkbox" checked={mf.attendee_ids.includes(a.id)} onChange={() => toggleAttendee(a.id)} /> {a.name}
              </label>
            ))}
          </div>
        </div>
        <button type="submit" disabled={busy === "meeting"} style={{ marginTop: 10 }}>{t("tm_schedule_meeting")}</button>
      </form>

      {meetings.length === 0 ? (
        <p className="muted">{t("tm_no_meetings")}</p>
      ) : (
        <div className="grid">
          {meetings.map((m) => (
            <div className="card" key={m.id}>
              <div className="between">
                <h3 style={{ margin: 0 }}>{m.title}</h3>
                <span className={`badge ${m.status === "done" ? "green" : m.status === "cancelled" ? "danger" : "grey"}`}>{t("tm_status_" + m.status)}</span>
              </div>
              <div className="muted" style={{ fontSize: 13, margin: "2px 0" }}>
                🕒 {(m.scheduled_at || "").replace("T", " ").slice(0, 16)}{m.location ? ` · ${m.location}` : ""}
              </div>
              {m.agenda && <div style={{ fontSize: 14, margin: "4px 0" }}>{m.agenda}</div>}
              <div className="muted" style={{ fontSize: 13 }}>
                {m.attendee_count} {t("tm_invited")}{m.attendees?.length ? `: ${m.attendees.map((a) => a.name).join(", ")}` : ""}
              </div>
              {m.notes && <div className="top-review" style={{ marginTop: 6 }}>{m.notes}</div>}
              {m.status !== "cancelled" && m.attendees?.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>{t("tm_attendance")}</div>
                  <div className="row" style={{ flexWrap: "wrap", gap: 10 }}>
                    {m.attendees.map((a) => (
                      <label key={a.id} className="chk">
                        <input type="checkbox" checked={(m.attended_ids || []).includes(a.id)}
                               disabled={busy === `m-${m.id}`}
                               onChange={() => toggleAttended(m, a.id)} /> {a.name}
                      </label>
                    ))}
                  </div>
                </div>
              )}
              {m.status === "scheduled" && (
                <div className="row" style={{ gap: 6, marginTop: 8 }}>
                  <button className="ghost" disabled={busy === `m-${m.id}`}
                          onClick={() => {
                            const notes = window.prompt(t("tm_minutes_prompt"), "");
                            patchMeeting(m.id, { status: "done", notes: notes || m.notes || null });
                          }}>{t("tm_mark_done")}</button>
                  <button className="ghost" disabled={busy === `m-${m.id}`}
                          onClick={() => patchMeeting(m.id, { status: "cancelled" })}>{t("tm_cancel")}</button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <h2 style={{ marginTop: 28 }}>{t("tm_field_agents_h")}</h2>
      <div className="grid">
        {data.agents.map((a) => (
          <div className="card" key={a.id}>
            <h3 style={{ margin: "0 0 6px" }}>{a.name}</h3>
            <div className="muted" style={{ fontSize: 14 }}>
              {a.open_jobs} {t("tm_open")} · {a.inspections_done} {t("tm_done")}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Collection-centre reconciliation: expected vs arrived bags per order/agent.
function CollectionCentre() {
  const { t } = useI18n();
  const [rows, setRows] = useState([]);
  function load() { api("/bags/collection-summary").then(setRows).catch(() => {}); }
  usePoll(() => load(), 15000, []);
  if (!rows.length) return null;
  const mism = rows.filter((r) => r.mismatch).length;
  return (
    <>
      <h2>{t("tm_collection_centre")} {mism > 0 && <span className="badge amber">{mism} {t("tm_mismatch")}</span>}</h2>
      <p className="muted" style={{ fontSize: 13, marginTop: -8 }}>{t("tm_collection_hint")}</p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>{t("tr_th_order")}</th><th>{t("tm_th_agent")}</th><th>{t("tm_th_expected")}</th><th>{t("tm_th_arrived")}</th><th>{t("tm_th_pending")}</th><th></th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.order_id} style={r.mismatch ? { background: "rgba(220,38,38,0.08)" } : undefined}>
                <td>{r.order_public_id || r.order_id}</td>
                <td className="muted">{r.agent_name || "—"}</td>
                <td>{r.expected}</td>
                <td>{r.arrived}</td>
                <td>{r.pending > 0 ? <b style={{ color: "var(--red-600, #dc2626)" }}>{r.pending}</b> : 0}</td>
                <td>{r.mismatch ? <span className="badge amber">{t("tm_mismatch")}</span> : <span className="badge green">{t("tm_ok")}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ margin: "8px 0 4px" }}><Link href="/scan" className="btn ghost">{t("tm_open_scanner")}</Link></div>
    </>
  );
}
