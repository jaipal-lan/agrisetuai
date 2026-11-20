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
      setMsg(t("sp_ticket_submitted"));
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
      setMsg(`${t("sp_dispute_resolved")} ${decision.replace(/_/g, " ")}.`);
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function partialRefund(id) {
    const amt = window.prompt(t("sp_partial_prompt"));
    if (amt === null || amt.trim() === "") return;
    decide(id, "partial_refund", Number(amt));
  }

  if (!me) {
    return (
      <div>
        <p className="muted">{t("sp_login")}</p>
        <Link href="/login" className="btn">{t("login")}</Link>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 760 }}>
      <h1>{t("support")}</h1>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok">{msg}</div>}

      <h2>{t("pf_notifications")}</h2>
      {notes.length === 0 ? (
        <p className="muted">{t("sp_no_notifications")}</p>
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

      <h2>{isOps ? t("sp_all_tickets") : t("sp_my_tickets")}</h2>
      {!isOps && (
        <div className="card">
          <h3>{t("sp_raise_ticket")}</h3>
          <label>{t("sp_subject")}</label>
          <input value={form.subject} onChange={(e) => set("subject", e.target.value)} />
          <label>{t("sp_issue_type")}</label>
          <select value={form.issue_type} onChange={(e) => set("issue_type", e.target.value)}>
            <option value="general">{t("it_general")}</option>
            <option value="quantity">{t("it_quantity")}</option>
            <option value="quality">{t("it_quality")}</option>
            <option value="payment">{t("it_payment")}</option>
            <option value="delivery">{t("it_delivery")}</option>
          </select>
          <label>{t("sp_details")}</label>
          <textarea rows={3} value={form.body} onChange={(e) => set("body", e.target.value)} />
          <div style={{ marginTop: 12 }}>
            <button onClick={createTicket} disabled={!form.subject || !form.body}>{t("sp_submit_ticket")}</button>
          </div>
        </div>
      )}
      {tickets.length === 0 ? (
        <p className="muted">{t("sp_no_tickets")}</p>
      ) : (
        <table>
          <thead>
            <tr><th>#</th><th>{t("sp_subject")}</th><th>{t("sp_col_type")}</th><th>{t("status")}</th></tr>
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

      <h2>{t("sp_disputes")}</h2>
      {disputes.length === 0 ? (
        <p className="muted">{t("sp_no_disputes")}</p>
      ) : (
        <div>
          {disputes.map((d) => {
            const media = (d.evidence && d.evidence.media) || [];
            return (
              <div className="card" key={d.id} style={{ marginBottom: 12 }}>
                <div className="between">
                  <div>
                    <b>{d.public_id}</b> ·{" "}
                    <Link href={`/order/${d.order_id}`}>{t("sp_order")} #{d.order_id}</Link>{" "}
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
                {d.decision_note && <p className="muted" style={{ marginTop: 6 }}>{t("sp_resolution_note")} {d.decision_note}</p>}
                {isOps && d.status !== "decided" && (
                  <div className="row" style={{ marginTop: 12, gap: 8, flexWrap: "wrap" }}>
                    <button className="ghost" onClick={() => decide(d.id, "uphold")}>{t("sp_uphold")}</button>
                    <button className="ghost" onClick={() => decide(d.id, "reject")}>{t("sp_reject")}</button>
                    {canRefund && (
                      <>
                        <button className="amber" onClick={() => partialRefund(d.id)}>{t("sp_partial_refund")}</button>
                        <button className="amber" onClick={() => decide(d.id, "full_refund")}>{t("sp_full_refund")}</button>
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
