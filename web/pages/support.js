import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";

export default function Support() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [notes, setNotes] = useState([]);
  const [tickets, setTickets] = useState([]);
  const [disputes, setDisputes] = useState([]);
  const [form, setForm] = useState({ subject: "", body: "", issue_type: "general" });
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const isOps = me && ["support", "finance", "mandal_manager", "superadmin"].includes(me.role);
  const canRefund = me && ["finance", "superadmin", "support"].includes(me.role);

  async function load() {
    try {
      const [n, tk, dp] = await Promise.all([
        api("/auth/notifications"),
        api("/tickets"),
        api("/disputes"),
      ]);
      setNotes(n);
      setTickets(tk);
      setDisputes(dp);
    } catch (e) {
      setErr(e.message);
    }
  }
  useEffect(() => { setMe(getUser()); }, []);
  usePoll(load, 15000);

  async function createTicket() {
    setErr(null);
    setMsg(null);
    try {
      await api("/tickets", { method: "POST", body: form });
      setMsg("Ticket submitted.");
      setForm({ subject: "", body: "", issue_type: "general" });
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function decide(id, decision) {
    setErr(null);
    try {
      await api(`/disputes/${id}/decision`, { method: "POST", body: { decision } });
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function refund(orderId) {
    setErr(null);
    const amt = window.prompt("Refund amount (₹). Leave blank for remaining balance.");
    if (amt === null) return;
    try {
      await api(`/orders/${orderId}/refunds`, {
        method: "POST",
        body: { amount: amt ? Number(amt) : undefined, reason_code: "dispute_resolution" },
        headers: { "Idempotency-Key": `ui-refund-${orderId}-${Date.now()}` },
      });
      setMsg("Refund posted.");
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  if (!me) {
    return (
      <div>
        <p className="muted">Log in to view support.</p>
        <Link href="/login" className="btn">{t("login")}</Link>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 760 }}>
      <h1>{t("support")}</h1>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok">{msg}</div>}

      <h2>Notifications</h2>
      {notes.length === 0 ? (
        <p className="muted">No notifications.</p>
      ) : (
        <ul className="timeline">
          {notes.map((n) => (
            <li key={n.id}>
              <b>{n.title}</b> — {n.body}
              <br />
              <small>{n.created_at ? new Date(n.created_at).toLocaleString() : ""}</small>
            </li>
          ))}
        </ul>
      )}

      <h2>{isOps ? "All tickets" : "My tickets"}</h2>
      {!isOps && (
        <div className="card">
          <h3>Raise a ticket</h3>
          <label>Subject</label>
          <input value={form.subject} onChange={(e) => set("subject", e.target.value)} />
          <label>Issue type</label>
          <select value={form.issue_type} onChange={(e) => set("issue_type", e.target.value)}>
            <option value="general">General</option>
            <option value="quantity">Quantity</option>
            <option value="quality">Quality</option>
            <option value="payment">Payment</option>
            <option value="delivery">Delivery</option>
          </select>
          <label>Details</label>
          <textarea rows={3} value={form.body} onChange={(e) => set("body", e.target.value)} />
          <div style={{ marginTop: 12 }}>
            <button onClick={createTicket} disabled={!form.subject || !form.body}>Submit ticket</button>
          </div>
        </div>
      )}
      {tickets.length === 0 ? (
        <p className="muted">No tickets.</p>
      ) : (
        <table>
          <thead>
            <tr><th>#</th><th>Subject</th><th>Type</th><th>{t("status")}</th></tr>
          </thead>
          <tbody>
            {tickets.map((tk) => (
              <tr key={tk.id}>
                <td>{tk.public_id}</td>
                <td>{tk.subject}</td>
                <td>{tk.issue_type}</td>
                <td><span className="badge grey">{tk.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2>Disputes</h2>
      {disputes.length === 0 ? (
        <p className="muted">No disputes.</p>
      ) : (
        <table>
          <thead>
            <tr><th>#</th><th>Order</th><th>Issue</th><th>{t("status")}</th>{isOps && <th>Action</th>}</tr>
          </thead>
          <tbody>
            {disputes.map((d) => (
              <tr key={d.id}>
                <td>{d.public_id}</td>
                <td><Link href={`/order/${d.order_id}`}>#{d.order_id}</Link></td>
                <td>{d.issue_type}</td>
                <td>
                  <span className="badge grey">{d.status}</span>
                  {d.decision ? <span className="pill-tag" style={{ marginLeft: 6 }}>{d.decision}</span> : null}
                </td>
                {isOps && (
                  <td>
                    {d.status !== "decided" && (
                      <>
                        <button className="ghost" onClick={() => decide(d.id, "reject")}>Reject</button>{" "}
                        <button className="ghost" onClick={() => decide(d.id, "uphold")}>Uphold</button>{" "}
                      </>
                    )}
                    {canRefund && <button className="amber" onClick={() => refund(d.order_id)}>Refund</button>}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
