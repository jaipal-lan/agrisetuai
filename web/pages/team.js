import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

export default function Team() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(null);
  const [pick, setPick] = useState({}); // orderId -> agentId

  useEffect(() => { setMe(getUser()); }, []);

  function load() {
    api("/team/overview").then(setData).catch((e) => setErr(e.message));
  }
  usePoll(() => { if (me) load(); }, 20000, [me]);

  async function assign(orderId) {
    const agentId = pick[orderId];
    if (!agentId) return;
    setBusy(orderId); setErr(null);
    try {
      await api(`/orders/${orderId}/assign-inspection`, { method: "POST", body: { agent_id: Number(agentId) } });
      load();
    } catch (e) { setErr(e.message); } finally { setBusy(null); }
  }

  const gate = roleGate(me, GROUPS.lead, { label: "the team console" });
  if (gate) return gate;
  if (!data) return <p className="muted">{t("loading")}</p>;

  return (
    <div>
      <h1>{t("team")}</h1>
      <p className="tagline">Monitor your field agents and pass orders to them for verification.</p>
      {err && <div className="error">{err}</div>}

      <div className="stat-strip">
        <div><b>{data.agents.length}</b> field agents</div>
        <div><b>{data.unassigned}</b> unassigned</div>
        <div><b>{data.pipeline.length}</b> in verification</div>
        <div><b>{data.active_orders}</b> active orders</div>
      </div>

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
                      <button className="ghost" disabled={busy === o.order_id || !pick[o.order_id]}
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

      <h2 style={{ marginTop: 24 }}>Field agents</h2>
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
