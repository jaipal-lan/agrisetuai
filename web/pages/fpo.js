import { useEffect, useState } from "react";

import { api, downloadFile, getUser } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { roleGate } from "../lib/roles";

export default function Fpo() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [data, setData] = useState(null);
  const [earn, setEarn] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => { setMe(getUser()); }, []);

  function reload() {
    api("/fpo").then(setData).catch((e) => setErr(e.message)).finally(() => setLoading(false));
    api("/fpo/earnings").then(setEarn).catch(() => {});
  }
  useEffect(() => { if (me && me.role === "fpo") reload(); }, [me]);

  const gate = roleGate(me, ["fpo"], { label: "the group console" });
  if (gate) return gate;

  async function addMember(body) {
    setErr(null);
    try {
      const res = await api("/fpo/members", { method: "POST", body });
      reload();
      return res;
    } catch (e) { setErr(e.message); throw e; }
  }
  async function removeMember(id) {
    if (!confirm("Remove this member from your group?")) return;
    setErr(null);
    try { await api(`/fpo/members/${id}`, { method: "DELETE" }); reload(); }
    catch (e) { setErr(e.message); }
  }

  if (loading) return <p className="muted">{t("loading")}</p>;
  if (!data) return <div className="error">{err || "Could not load group."}</div>;

  const p = data.pooled;
  return (
    <div>
      <h1>{data.organisation.legal_name}</h1>
      <p className="tagline">
        Your farmer group — pool listings and track every member’s earnings in one place.
      </p>
      {err && <div className="error">{err}</div>}

      <div className="grid stat-grid">
        <Stat label="Members" value={data.member_count} />
        <Stat label="Group listings (open)" value={p.active_listings} />
        <Stat label="Orders in progress" value={p.orders_in_progress} />
        <Stat label="GMV (settled)" value={`₹${p.gross_settled}`} />
        <Stat label="Awaiting payout" value={`₹${p.awaiting_payout}`} />
      </div>

      <section style={{ marginTop: 24 }}>
        <h2>Members</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th><th>Phone</th><th>Village</th><th>KYC</th>
                <th>Listings</th><th>In progress</th><th></th>
              </tr>
            </thead>
            <tbody>
              {data.members.map((m) => (
                <tr key={m.id}>
                  <td>
                    {m.name}
                    {m.is_lead && <span className="badge green" style={{ marginLeft: 6 }}>Lead</span>}
                    {!m.onboarding_complete && !m.is_lead && (
                      <span className="badge grey" style={{ marginLeft: 6 }}>Invited</span>
                    )}
                  </td>
                  <td>{m.phone}</td>
                  <td>{m.village || "—"}</td>
                  <td>
                    <span className={`badge ${m.verification_status === "verified" ? "green" : "grey"}`}>
                      {m.verification_status}
                    </span>
                  </td>
                  <td>{m.active_listings}</td>
                  <td>{m.orders_in_progress}</td>
                  <td>
                    {!m.is_lead && (
                      <button className="ghost" onClick={() => removeMember(m.id)}>Remove</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <AddMemberForm onAdd={addMember} />

      {earn && (
        <section style={{ marginTop: 28 }}>
          <div className="between">
            <h2 style={{ margin: 0 }}>Group earnings</h2>
            <button className="ghost" onClick={() => downloadFile("/fpo/earnings.csv", "agrisetu-fpo-earnings.csv")}>
              ⬇ Export CSV
            </button>
          </div>
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table className="table">
              <thead>
                <tr><th>Member</th><th>Orders</th><th>Gross</th><th>Commission</th><th>Net</th><th>Paid</th></tr>
              </thead>
              <tbody>
                {earn.members.map((m) => (
                  <tr key={m.seller_id}>
                    <td>{m.name}</td><td>{m.orders}</td><td>₹{m.gross}</td>
                    <td>₹{m.commission}</td><td>₹{m.net}</td><td>₹{m.paid}</td>
                  </tr>
                ))}
                <tr style={{ fontWeight: 700 }}>
                  <td>Group total</td><td></td><td>₹{earn.totals.gross}</td>
                  <td>₹{earn.totals.commission}</td><td>₹{earn.totals.net}</td><td>₹{earn.totals.paid}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="card stat-card">
      <div className="muted" style={{ fontSize: 13 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, marginTop: 4 }}>{value}</div>
    </div>
  );
}

function AddMemberForm({ onAdd }) {
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [village, setVillage] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try {
      const res = await onAdd({ phone: phone.trim(), name: name.trim() || undefined, village: village.trim() || undefined });
      setMsg(res.created
        ? `Added ${res.member.name || phone} — they can log in with this phone to activate.`
        : `Linked ${res.member.name || phone} to your group.`);
      setPhone(""); setName(""); setVillage("");
    } catch { /* error shown by parent */ }
    finally { setBusy(false); }
  }

  return (
    <section style={{ marginTop: 24 }}>
      <h2>Add a member</h2>
      <p className="muted" style={{ fontSize: 14 }}>
        Enter an existing farmer’s phone to link them, or a new phone to pre-register them.
      </p>
      <form onSubmit={submit} className="card" style={{ maxWidth: 520 }}>
        <label>Phone number *</label>
        <input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="numeric" placeholder="9000000000" required />
        <label>Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Member name" />
        <label>Village</label>
        <input value={village} onChange={(e) => setVillage(e.target.value)} placeholder="Village" />
        <button className="btn" type="submit" disabled={busy} style={{ marginTop: 12 }}>
          {busy ? "Adding…" : "Add member"}
        </button>
        {msg && <div className="ok" style={{ marginTop: 10 }}>{msg}</div>}
      </form>
    </section>
  );
}
