import { useEffect, useState } from "react";

import { api, downloadFile, getUser, uploadMedia } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { roleGate } from "../lib/roles";

export default function Fpo() {
  const { t, lang } = useI18n();
  const [me, setMe] = useState(null);
  const [data, setData] = useState(null);
  const [earn, setEarn] = useState(null);
  const [commodities, setCommodities] = useState([]);
  const [mandals, setMandals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => {
    setMe(getUser());
    api("/catalog/commodities").then(setCommodities).catch(() => {});
    api("/locations/mandals").then(setMandals).catch(() => {});
  }, []);

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
  async function listForMember(body) {
    setErr(null);
    await api("/listings", { method: "POST", body });
    reload();
  }
  async function publishListing(id) {
    setErr(null);
    try { await api(`/listings/${id}/publish`, { method: "POST" }); reload(); }
    catch (e) { setErr(e.message); }
  }
  async function pauseListing(id) {
    setErr(null);
    try { await api(`/listings/${id}/pause`, { method: "POST" }); reload(); }
    catch (e) { setErr(e.message); }
  }
  async function addImage(id, file) {
    setErr(null);
    try {
      const up = await uploadMedia(file);
      await api(`/listings/${id}/media`, { method: "POST", body: { object_key: up.object_key, media_type: "image" } });
      reload();
    } catch (e) { setErr(e.message); }
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

      <ListForMember members={data.members} commodities={commodities} mandals={mandals}
                     lang={lang} onList={listForMember} />

      <GroupListings listings={data.listings || []} onPublish={publishListing}
                     onPause={pauseListing} onAddImage={addImage} />

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

function ListForMember({ members, commodities, mandals, lang, onList }) {
  const sellers = members.filter((m) => m.status !== "suspended");
  const [memberId, setMemberId] = useState("");
  const [cid, setCid] = useState("");
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [moq, setMoq] = useState("");
  const [mandalId, setMandalId] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const cname = (c) => (lang === "te" && c.name_te ? c.name_te : c.name);

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try {
      await onList({
        on_behalf_of: Number(memberId),
        commodity_id: Number(cid),
        total_qty: Number(qty),
        asking_price: Number(price),
        min_order_qty: moq ? Number(moq) : 0,
        mandal_id: mandalId ? Number(mandalId) : undefined,
        harvest_year: new Date().getFullYear(),
      });
      setMsg("Draft listing created. Add 3 photos below, then publish it.");
      setQty(""); setPrice(""); setMoq("");
    } catch { setMsg(null); }
    finally { setBusy(false); }
  }

  return (
    <section style={{ marginTop: 24 }}>
      <h2>List produce for a member</h2>
      <p className="muted" style={{ fontSize: 14 }}>
        Pool a member’s crop under the group. The listing stays owned by that member; you manage it.
      </p>
      <form onSubmit={submit} className="card" style={{ maxWidth: 620 }}>
        <div className="row">
          <div style={{ flex: "2 1 200px" }}>
            <label>Member *</label>
            <select value={memberId} onChange={(e) => setMemberId(e.target.value)} required>
              <option value="">—</option>
              {sellers.map((m) => <option key={m.id} value={m.id}>{m.name}{m.is_lead ? " (you)" : ""}</option>)}
            </select>
          </div>
          <div style={{ flex: "2 1 200px" }}>
            <label>Crop *</label>
            <select value={cid} onChange={(e) => setCid(e.target.value)} required>
              <option value="">—</option>
              {commodities.map((c) => <option key={c.id} value={c.id}>{cname(c)} ({c.category})</option>)}
            </select>
          </div>
          <div style={{ flex: "1 1 120px" }}>
            <label>Place</label>
            <select value={mandalId} onChange={(e) => setMandalId(e.target.value)}>
              <option value="">—</option>
              {mandals.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>
        </div>
        <div className="row">
          <div style={{ flex: 1 }}><label>Quantity (kg) *</label>
            <input value={qty} onChange={(e) => setQty(e.target.value)} inputMode="decimal" required /></div>
          <div style={{ flex: 1 }}><label>Asking ₹/kg *</label>
            <input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" required /></div>
          <div style={{ flex: 1 }}><label>Min order (kg)</label>
            <input value={moq} onChange={(e) => setMoq(e.target.value)} inputMode="decimal" placeholder="0" /></div>
        </div>
        <button className="btn" type="submit" style={{ marginTop: 12 }}
                disabled={busy || !memberId || !cid || !qty || !price}>
          {busy ? "Creating…" : "Create draft listing"}
        </button>
        {msg && <div className="ok" style={{ marginTop: 10 }}>{msg}</div>}
      </form>
    </section>
  );
}

function GroupListings({ listings, onPublish, onPause, onAddImage }) {
  if (!listings.length) return null;
  return (
    <section style={{ marginTop: 24 }}>
      <h2>Group listings</h2>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr><th>Crop</th><th>Member</th><th>Status</th><th>Qty</th><th>₹/kg</th><th>Photos</th><th></th></tr>
          </thead>
          <tbody>
            {listings.map((l) => {
              const draft = l.status === "draft" || l.status === "paused";
              const canPublish = draft && l.image_count >= 3;
              return (
                <tr key={l.id}>
                  <td>{l.commodity || "—"}</td>
                  <td>{l.seller}</td>
                  <td><span className={`badge ${l.status === "open" ? "green" : "grey"}`}>{l.status}</span></td>
                  <td>{l.available_qty}</td>
                  <td>₹{l.asking_price}</td>
                  <td>{l.image_count}</td>
                  <td>
                    {draft && (
                      <label className="btn ghost" style={{ cursor: "pointer", marginRight: 6 }}>
                        + Photo
                        <input type="file" accept="image/*" style={{ display: "none" }}
                               onChange={(e) => e.target.files[0] && onAddImage(l.id, e.target.files[0])} />
                      </label>
                    )}
                    {draft && (
                      <button className="ghost" disabled={!canPublish} onClick={() => onPublish(l.id)}
                              title={canPublish ? "" : "Add 3 photos first"}>Publish</button>
                    )}
                    {l.status === "open" && (
                      <button className="ghost" onClick={() => onPause(l.id)}>Pause</button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
