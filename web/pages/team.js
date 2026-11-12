import Link from "next/link";
import { useEffect, useState } from "react";

import { api, downloadFile, getUser } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

const METRICS = [
  { value: "inspections", label: "Inspections done" },
  { value: "orders_assigned", label: "Orders handled" },
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
    if (!tf.agent_id || !tf.target_value) { setErr("Pick an agent and a target value."); return; }
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
    if (!mf.title.trim() || !mf.scheduled_at) { setErr("A meeting needs a title and a time."); return; }
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
      <p className="tagline">Monitor your field agents, pass orders, set targets and run meetings.</p>
      {err && <div className="error">{err}</div>}

      <div className="stat-strip">
        <div><b>{data.agents.length}</b> field agents</div>
        <div><b>{data.unassigned}</b> unassigned</div>
        <div><b>{data.pipeline.length}</b> in verification</div>
        <div><b>{data.active_orders}</b> active orders</div>
      </div>

      {/* ---- Leaderboard ---- */}
      <div className="between" style={{ marginTop: 22 }}>
        <h2 style={{ margin: 0 }}>🏆 Agent leaderboard</h2>
        <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
          {["week", "month", "all"].map((p) => (
            <button key={p} className={period === p ? "" : "ghost"} onClick={() => setPeriod(p)}
                    style={{ padding: "4px 10px", fontSize: 13 }}>
              {p === "all" ? "All time" : `This ${p}`}
            </button>
          ))}
          <button className="ghost" style={{ padding: "4px 10px", fontSize: 13 }}
                  onClick={() => downloadFile(`/team/leaderboard.csv?period=${period}`, `leaderboard-${period}.csv`)}>
            CSV
          </button>
        </div>
      </div>

      {trend && trend.series?.some((w) => w.inspections || w.orders) && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>📈 Inspections per week (last 6)</div>
          <div className="row" style={{ alignItems: "flex-end", gap: 8, height: 90 }}>
            {(() => {
              const max = Math.max(1, ...trend.series.map((w) => w.inspections));
              return trend.series.map((w) => (
                <div key={w.week_start} style={{ flex: 1, textAlign: "center" }}>
                  <div className="pbar-fill" title={`${w.inspections} inspections`}
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
        <p className="muted">No field agents yet.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>#</th><th>Agent</th><th>Attainment</th><th>Targets met</th>
                <th>Inspections</th><th>Orders</th><th>Attendance</th></tr>
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

      <h2 style={{ marginTop: 20 }}>Orders needing verification</h2>
      {data.pipeline.length === 0 ? (
        <p className="muted">Nothing waiting for inspection right now.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Order</th><th>Product</th><th>Qty</th><th>Status</th><th>Agent</th><th></th></tr>
            </thead>
            <tbody>
              {data.pipeline.map((o) => (
                <tr key={o.order_id}>
                  <td><Link href={`/order/${o.order_id}`}>{o.public_id}</Link></td>
                  <td>{o.commodity || "—"}</td>
                  <td>{o.quantity} {o.unit}</td>
                  <td><span className="badge grey">{o.status.replace(/_/g, " ")}</span></td>
                  <td>{o.assigned_agent_name || <span className="muted">unassigned</span>}</td>
                  <td>
                    <div className="row" style={{ gap: 6 }}>
                      <select value={pick[o.order_id] || ""}
                              onChange={(e) => setPick((p) => ({ ...p, [o.order_id]: e.target.value }))}>
                        <option value="">Pick agent…</option>
                        {data.agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                      </select>
                      <button className="ghost" disabled={busy === `assign-${o.order_id}` || !pick[o.order_id]}
                              onClick={() => assign(o.order_id)}>
                        {o.assigned_agent_id ? "Reassign" : "Assign"}
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
      <h2 style={{ marginTop: 28 }}>🎯 Targets</h2>
      <form className="card" onSubmit={createTarget} style={{ marginBottom: 14 }}>
        <div className="form-grid">
          <label>Agent
            <select value={tf.agent_id} onChange={(e) => setTf((f) => ({ ...f, agent_id: e.target.value }))}>
              <option value="">Pick agent…</option>
              {data.agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </label>
          <label>Metric
            <select value={tf.metric} onChange={(e) => setTf((f) => ({ ...f, metric: e.target.value }))}>
              {METRICS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
          </label>
          <label>Target
            <input type="number" min="1" value={tf.target_value}
                   onChange={(e) => setTf((f) => ({ ...f, target_value: e.target.value }))} placeholder="e.g. 20" />
          </label>
          <label>From
            <input type="date" value={tf.period_start} onChange={(e) => setTf((f) => ({ ...f, period_start: e.target.value }))} />
          </label>
          <label>To
            <input type="date" value={tf.period_end} onChange={(e) => setTf((f) => ({ ...f, period_end: e.target.value }))} />
          </label>
          <label>Note (optional)
            <input value={tf.note} onChange={(e) => setTf((f) => ({ ...f, note: e.target.value }))} placeholder="e.g. harvest push" />
          </label>
        </div>
        <button type="submit" disabled={busy === "target"} style={{ marginTop: 10 }}>Set target</button>
      </form>

      {targets.length === 0 ? (
        <p className="muted">No active targets. Set one above.</p>
      ) : (
        <div className="grid">
          {targets.map((tg) => (
            <div className="card" key={tg.id}>
              <div className="between">
                <h3 style={{ margin: 0 }}>{tg.agent_name}</h3>
                <span className={`badge ${tg.met ? "green" : "grey"}`}>{tg.met ? "met" : `${tg.pct}%`}</span>
              </div>
              <div className="muted" style={{ fontSize: 13, margin: "2px 0 8px" }}>
                {tg.progress} / {tg.target_value} {tg.metric_label} · {tg.period_start} → {tg.period_end}
              </div>
              <div className="pbar"><div className="pbar-fill" style={{ width: `${tg.pct}%` }} /></div>
              {tg.note && <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>{tg.note}</div>}
              <button className="ghost" style={{ marginTop: 8 }} disabled={busy === `t-${tg.id}`}
                      onClick={() => archiveTarget(tg.id)}>Archive</button>
            </div>
          ))}
        </div>
      )}

      {/* ---- Meetings ---- */}
      <h2 style={{ marginTop: 28 }}>📅 Meetings</h2>
      <form className="card" onSubmit={createMeeting} style={{ marginBottom: 14 }}>
        <div className="form-grid">
          <label>Title
            <input value={mf.title} onChange={(e) => setMf((f) => ({ ...f, title: e.target.value }))} placeholder="Weekly mandal sync" />
          </label>
          <label>When
            <input type="datetime-local" value={mf.scheduled_at} onChange={(e) => setMf((f) => ({ ...f, scheduled_at: e.target.value }))} />
          </label>
          <label>Location (optional)
            <input value={mf.location} onChange={(e) => setMf((f) => ({ ...f, location: e.target.value }))} placeholder="Office / Online" />
          </label>
          <label style={{ gridColumn: "1 / -1" }}>Agenda (optional)
            <input value={mf.agenda} onChange={(e) => setMf((f) => ({ ...f, agenda: e.target.value }))} placeholder="Targets, pending verifications, issues" />
          </label>
        </div>
        <div style={{ marginTop: 8 }}>
          <div className="muted" style={{ fontSize: 13, marginBottom: 4 }}>Invite agents</div>
          <div className="row" style={{ flexWrap: "wrap", gap: 10 }}>
            {data.agents.map((a) => (
              <label key={a.id} className="chk">
                <input type="checkbox" checked={mf.attendee_ids.includes(a.id)} onChange={() => toggleAttendee(a.id)} /> {a.name}
              </label>
            ))}
          </div>
        </div>
        <button type="submit" disabled={busy === "meeting"} style={{ marginTop: 10 }}>Schedule meeting</button>
      </form>

      {meetings.length === 0 ? (
        <p className="muted">No meetings yet.</p>
      ) : (
        <div className="grid">
          {meetings.map((m) => (
            <div className="card" key={m.id}>
              <div className="between">
                <h3 style={{ margin: 0 }}>{m.title}</h3>
                <span className={`badge ${m.status === "done" ? "green" : m.status === "cancelled" ? "danger" : "grey"}`}>{m.status}</span>
              </div>
              <div className="muted" style={{ fontSize: 13, margin: "2px 0" }}>
                🕒 {(m.scheduled_at || "").replace("T", " ").slice(0, 16)}{m.location ? ` · ${m.location}` : ""}
              </div>
              {m.agenda && <div style={{ fontSize: 14, margin: "4px 0" }}>{m.agenda}</div>}
              <div className="muted" style={{ fontSize: 13 }}>
                {m.attendee_count} invited{m.attendees?.length ? `: ${m.attendees.map((a) => a.name).join(", ")}` : ""}
              </div>
              {m.notes && <div className="top-review" style={{ marginTop: 6 }}>{m.notes}</div>}
              {m.status !== "cancelled" && m.attendees?.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>Attendance</div>
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
                            const notes = window.prompt("Meeting minutes (optional):", "");
                            patchMeeting(m.id, { status: "done", notes: notes || m.notes || null });
                          }}>Mark done</button>
                  <button className="ghost" disabled={busy === `m-${m.id}`}
                          onClick={() => patchMeeting(m.id, { status: "cancelled" })}>Cancel</button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <h2 style={{ marginTop: 28 }}>Field agents</h2>
      <div className="grid">
        {data.agents.map((a) => (
          <div className="card" key={a.id}>
            <h3 style={{ margin: "0 0 6px" }}>{a.name}</h3>
            <div className="muted" style={{ fontSize: 14 }}>
              {a.open_jobs} open · {a.inspections_done} done
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
