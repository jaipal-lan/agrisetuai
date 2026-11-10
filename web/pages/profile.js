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
