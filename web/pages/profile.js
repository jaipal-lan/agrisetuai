import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, getUser, logout } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { ROLE_LABEL, roleGate } from "../lib/roles";

export default function Profile() {
  const { t, lang, setLang } = useI18n();
  const router = useRouter();
  const [me, setMe] = useState(null);
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState(null);
  const [prefs, setPrefs] = useState(null);
  const [savingPref, setSavingPref] = useState(null);

  useEffect(() => {
    setMe(getUser());
    api("/auth/me").then(setDetail).catch((e) => setErr(e.message));
    api("/auth/notification-preferences").then(setPrefs).catch(() => {});
  }, []);

  // Set one category to a delivery mode: instant | digest | off.
  async function setMode(key, mode) {
    if (!prefs) return;
    setSavingPref(key);
    const muted = new Set(prefs.categories.filter((c) => c.mode === "off").map((c) => c.key));
    const digest = new Set(prefs.categories.filter((c) => c.mode === "digest").map((c) => c.key));
    muted.delete(key); digest.delete(key);
    if (mode === "off") muted.add(key);
    else if (mode === "digest") digest.add(key);
    try {
      const r = await api("/auth/notification-preferences", {
        method: "PUT", body: { muted: [...muted], digest: [...digest] },
      });
      setPrefs(r);
    } catch (e) { setErr(e.message); }
    finally { setSavingPref(null); }
  }

  const gate = roleGate(me, null, { label: "your profile" });
  if (gate) return gate;

  async function doLogout() {
    try { await api("/auth/logout", { method: "POST" }); } catch {}
    logout();
    router.push("/");
  }

  const prof = detail?.farmer || detail?.buyer || null;
  const vs = prof?.verification_status;
  const langLabel = { te: "తెలుగు", en: "English", hi: "हिन्दी" }[lang] || lang;

  const Row = ({ label, children }) => (
    <div className="quote-line"><span className="muted">{label}</span><span>{children}</span></div>
  );

  return (
    <div style={{ maxWidth: 560 }}>
      <h1>{t("profile")}</h1>
      {err && <div className="error">{err}</div>}

      <div className="card">
        <div className="between">
          <h3 style={{ margin: 0 }}>{detail?.name || me?.name || "—"}</h3>
          <span className="badge">{ROLE_LABEL[me?.role] || me?.role}</span>
        </div>
        <div style={{ marginTop: 12 }}>
          <Row label="Phone">{detail?.phone || "—"}</Row>
          <Row label="Account status">
            <span className="badge grey">{detail?.status || "active"}</span>
          </Row>
          {vs && (
            <Row label="Verification (KYC)">
              <span className={`badge ${vs === "verified" ? "" : "amber"}`}>{vs}</span>
            </Row>
          )}
          {detail?.farmer?.village && <Row label="Village">{detail.farmer.village}</Row>}
          {detail?.buyer?.buyer_type && <Row label="Buyer type">{detail.buyer.buyer_type}</Row>}
          {detail?.agent?.skill_level && <Row label="Role level">{detail.agent.skill_level}</Row>}
          <Row label="Language">{langLabel}</Row>
          <Row label="Onboarding">
            {detail?.onboarding_complete === false
              ? <span className="badge amber">incomplete</span>
              : <span className="badge">complete</span>}
          </Row>
        </div>
      </div>

      {prefs && (
        <>
          <h2>Notifications</h2>
          <p className="muted" style={{ fontSize: 14, marginTop: -8 }}>
            Choose how each proactive alert reaches you. <b>Instant</b> pings the bell,
            <b> Daily</b> batches it into a once-a-day digest, <b>Off</b> silences it.
            Order updates and account messages are always sent instantly.
          </p>
          <div className="card">
            {prefs.categories.map((c) => (
              <div key={c.key} className="between" style={{ padding: "10px 0", borderBottom: "1px solid var(--line)", gap: 10, flexWrap: "wrap" }}>
                <span>{c.label}</span>
                <div className="seg" aria-label={`Delivery for ${c.label}`}>
                  {[["instant", "Instant"], ["digest", "Daily"], ["off", "Off"]].map(([m, label]) => (
                    <button key={m}
                            className={c.mode === m ? "seg-on" : ""}
                            disabled={savingPref === c.key}
                            onClick={() => setMode(c.key, m)}>
                      {savingPref === c.key && c.mode !== m ? "…" : label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {["farmer", "transport"].includes(me?.role) && <PayoutCard />}
      {["farmer", "buyer_household", "buyer_business"].includes(me?.role) && <AddressesCard />}

      <h2>Language</h2>
      <div className="row">
        {[["te", "తెలుగు"], ["en", "English"], ["hi", "हिन्दी"]].map(([code, labelText]) => (
          <button key={code} className={lang === code ? "" : "ghost"} onClick={() => setLang(code)}>
            {labelText}
          </button>
        ))}
      </div>

      <h2>Account</h2>
      <div className="row">
        <Link href="/onboarding" className="btn ghost">Edit profile</Link>
        <Link href="/dashboard" className="btn ghost">My dashboard</Link>
        <button className="danger" onClick={doLogout}>{t("logout")}</button>
      </div>
    </div>
  );
}

function PayoutCard() {
  const [acc, setAcc] = useState(null);
  const [form, setForm] = useState({ method: "upi", upi_id: "", account_name: "", account_number: "", ifsc: "" });
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/auth/payout-account").then((r) => {
      setAcc(r.account);
      if (r.account) setForm((f) => ({ ...f, method: r.account.method, upi_id: r.account.upi_id || "" }));
    }).catch(() => {});
  }, []);

  async function save(e) {
    e.preventDefault(); setErr(null); setMsg(null); setBusy(true);
    try {
      const body = form.method === "upi"
        ? { method: "upi", upi_id: form.upi_id }
        : { method: "bank", account_name: form.account_name, account_number: form.account_number, ifsc: form.ifsc };
      const r = await api("/auth/payout-account", { method: "PUT", body });
      setAcc(r.account); setMsg("Payout details saved.");
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  return (
    <>
      <h2>Payout details</h2>
      <p className="muted" style={{ fontSize: 14, marginTop: -8 }}>
        Where we send your money. {acc ? (acc.verified ? "Verified." : "Pending verification.") : "Not set up yet."}
      </p>
      <form className="card" onSubmit={save}>
        {acc && acc.method === "bank" && acc.account_number_masked && (
          <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>On file: bank {acc.account_number_masked} · {acc.ifsc}</div>
        )}
        {acc && acc.method === "upi" && acc.upi_id && (
          <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>On file: UPI {acc.upi_id}</div>
        )}
        <div className="row" style={{ gap: 8, marginBottom: 8 }}>
          {[["upi", "UPI"], ["bank", "Bank account"]].map(([m, label]) => (
            <button type="button" key={m} className={form.method === m ? "" : "ghost"}
                    onClick={() => setForm((f) => ({ ...f, method: m }))}>{label}</button>
          ))}
        </div>
        {form.method === "upi" ? (
          <label className="muted" style={{ fontSize: 13 }}>UPI ID
            <input value={form.upi_id} placeholder="name@bank"
                   onChange={(e) => setForm((f) => ({ ...f, upi_id: e.target.value }))} />
          </label>
        ) : (
          <div className="form-grid">
            <label>Account holder
              <input value={form.account_name} onChange={(e) => setForm((f) => ({ ...f, account_name: e.target.value }))} />
            </label>
            <label>Account number
              <input value={form.account_number} onChange={(e) => setForm((f) => ({ ...f, account_number: e.target.value }))} />
            </label>
            <label>IFSC
              <input value={form.ifsc} maxLength={11} onChange={(e) => setForm((f) => ({ ...f, ifsc: e.target.value.toUpperCase() }))} />
            </label>
          </div>
        )}
        {err && <div className="error" style={{ marginTop: 8 }}>{err}</div>}
        {msg && <div className="ok" style={{ marginTop: 8 }}>{msg}</div>}
        <button type="submit" disabled={busy} style={{ marginTop: 10 }}>Save payout details</button>
      </form>
    </>
  );
}

function AddressesCard() {
  const [list, setList] = useState([]);
  const [mandals, setMandals] = useState([]);
  const [form, setForm] = useState({ label: "Home", mandal_id: "", address_line: "", is_default: false });
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  function load() { api("/auth/addresses").then(setList).catch(() => {}); }
  useEffect(() => {
    load();
    api("/locations/mandals").then(setMandals).catch(() => {});
  }, []);

  async function add(e) {
    e.preventDefault(); setErr(null);
    if (!form.mandal_id) { setErr("Pick a mandal."); return; }
    setBusy(true);
    try {
      await api("/auth/addresses", { method: "POST", body: {
        label: form.label || "Home", mandal_id: Number(form.mandal_id),
        address_line: form.address_line || null, is_default: form.is_default } });
      setForm({ label: "Home", mandal_id: "", address_line: "", is_default: false });
      load();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  async function remove(id) {
    try { await api(`/auth/addresses/${id}`, { method: "DELETE" }); load(); } catch (e) { setErr(e.message); }
  }

  return (
    <>
      <h2>Delivery addresses</h2>
      <p className="muted" style={{ fontSize: 14, marginTop: -8 }}>Saved addresses speed up ordering and reorders.</p>
      {list.length > 0 && (
        <div className="card" style={{ marginBottom: 10 }}>
          {list.map((a) => (
            <div key={a.id} className="between" style={{ padding: "8px 0", borderBottom: "1px solid var(--line)", gap: 8 }}>
              <div>
                <b>{a.label}</b>{a.is_default && <span className="badge green" style={{ marginLeft: 6 }}>default</span>}
                <div className="muted" style={{ fontSize: 13 }}>{a.mandal}{a.address_line ? ` · ${a.address_line}` : ""}</div>
              </div>
              <button className="ghost" onClick={() => remove(a.id)}>Remove</button>
            </div>
          ))}
        </div>
      )}
      <form className="card" onSubmit={add}>
        <div className="form-grid">
          <label>Label
            <input value={form.label} onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))} />
          </label>
          <label>Mandal
            <select value={form.mandal_id} onChange={(e) => setForm((f) => ({ ...f, mandal_id: e.target.value }))}>
              <option value="">Pick mandal…</option>
              {mandals.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </label>
          <label style={{ gridColumn: "1 / -1" }}>Address (optional)
            <input value={form.address_line} onChange={(e) => setForm((f) => ({ ...f, address_line: e.target.value }))} />
          </label>
        </div>
        <label className="chk" style={{ marginTop: 8 }}>
          <input type="checkbox" checked={form.is_default} onChange={(e) => setForm((f) => ({ ...f, is_default: e.target.checked }))} /> Set as default
        </label>
        {err && <div className="error" style={{ marginTop: 8 }}>{err}</div>}
        <div><button type="submit" disabled={busy} style={{ marginTop: 10 }}>Add address</button></div>
      </form>
    </>
  );
}
