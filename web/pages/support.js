import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getUser, mediaUrl } from "../lib/api";
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

  async function decide(id, decision, refund_amount) {
    setErr(null);
    setMsg(null);
    try {
      await api(`/disputes/${id}/decision`, {
        method: "POST",
        body: { decision, refund_amount },
      });
      setMsg(`Dispute resolved: ${decision.replace(/_/g, " ")}.`);
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function partialRefund(id) {
    const amt = window.prompt("Partial refund amount (₹) to the buyer:");
    if (amt === null || amt.trim() === "") return;
    decide(id, "partial_refund", Number(amt));
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
        <div>
          {disputes.map((d) => {
            const media = (d.evidence && d.evidence.media) || [];
            return (
              <div className="card" key={d.id} style={{ marginBottom: 12 }}>
                <div className="between">
                  <div>
                    <b>{d.public_id}</b> ·{" "}
                    <Link href={`/order/${d.order_id}`}>order #{d.order_id}</Link>{" "}
                    <span className="pill-tag">{d.issue_type}</span>
                  </div>
                  <div>
                    <span className="badge grey">{d.status}</span>
                    {d.decision && <span className="pill-tag" style={{ marginLeft: 6 }}>{d.decision.replace(/_/g, " ")}</span>}
                  </div>
                </div>
                {d.description && <p style={{ marginTop: 8 }}>{d.description}</p>}
                {media.length > 0 && (
                  <div className="thumb-row" style={{ marginTop: 8 }}>
                    {media.map((k) => (
                      <a key={k} href={mediaUrl(k)} target="_blank" rel="noreferrer">
                        <img src={mediaUrl(k)} alt="evidence"
                             style={{ width: 72, height: 72, objectFit: "cover", borderRadius: 6, marginRight: 6 }} />
                      </a>
                    ))}
                  </div>
                )}
                {d.decision_note && <p className="muted" style={{ marginTop: 6 }}>Resolution note: {d.decision_note}</p>}
                {isOps && d.status !== "decided" && (
                  <div className="row" style={{ marginTop: 12, gap: 8, flexWrap: "wrap" }}>
                    <button className="ghost" onClick={() => decide(d.id, "uphold")}>Uphold (no refund)</button>
                    <button className="ghost" onClick={() => decide(d.id, "reject")}>Reject</button>
                    {canRefund && (
                      <>
                        <button className="amber" onClick={() => partialRefund(d.id)}>Partial refund…</button>
                        <button className="amber" onClick={() => decide(d.id, "full_refund")}>Full refund</button>
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
