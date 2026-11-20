import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";

import { api, setSession } from "../lib/api";
import { useI18n } from "../lib/i18n";

// Login is phone + password (the primary path). OTP login stays as a fallback
// for staff accounts and anyone who hasn't set a password. New members of the
// public sign up at /register.
export default function Login() {
  const { t } = useI18n();
  const router = useRouter();
  const [mode, setMode] = useState("password"); // password | otp
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [devCode, setDevCode] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  function onSuccess(r) {
    setSession(r.token, r.user);
    const next = typeof router.query.next === "string" ? router.query.next : "/dashboard";
    router.push(next);
  }

  async function loginPassword(e) {
    e.preventDefault();
    setErr(null); setBusy(true);
    try {
      onSuccess(await api("/auth/login", { method: "POST", body: { phone, password } }));
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  async function sendOtp() {
    setErr(null); setBusy(true);
    try {
      const r = await api("/auth/otp/request", { method: "POST", body: { phone } });
      setSent(true);
      setDevCode(r.dev_code || null);
      if (r.dev_code) setCode(r.dev_code);
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  async function verifyOtp() {
    setErr(null); setBusy(true);
    try {
      onSuccess(await api("/auth/otp/verify", { method: "POST", body: { phone, code } }));
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  return (
    <div style={{ maxWidth: 420, margin: "0 auto" }}>
      <h1>{t("login")}</h1>
      <p className="tagline">{t("tagline")}</p>
      {router.query.registered && (
        <div className="ok">{t("auth_acct_created")}</div>
      )}
      {router.query.reset && (
        <div className="ok">{t("auth_pwd_updated")}</div>
      )}
      {err && <div className="error">{err}</div>}

      <div className="card">
        <label>{t("phone")}</label>
        <input
          value={phone}
          onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))}
          placeholder="91XXXXXXXXXX"
          inputMode="numeric"
          autoComplete="tel"
        />

        {mode === "password" ? (
          <form onSubmit={loginPassword}>
            <label>{t("auth_password")}</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
            <div style={{ marginTop: 16 }}>
              <button type="submit" disabled={busy || phone.length < 8 || !password}>
                {t("login")}
              </button>
            </div>
            <div className="between" style={{ marginTop: 12, fontSize: 13 }}>
              <Link href="/reset-password">{t("auth_forgot")}</Link>
              <a role="button" tabIndex={0} className="linklike"
                 onClick={() => { setMode("otp"); setErr(null); }}>
                {t("auth_login_otp")}
              </a>
            </div>
          </form>
        ) : (
          <>
            {!sent ? (
              <div style={{ marginTop: 16 }}>
                <p className="muted" style={{ fontSize: 13 }}>
                  {t("auth_otp_hint")}
                </p>
                <button onClick={sendOtp} disabled={busy || phone.length < 8}>
                  {t("send_otp")}
                </button>
              </div>
            ) : (
              <>
                {devCode && (
                  <div className="ok" style={{ fontSize: 13 }}>
                    Dev OTP: <b>{devCode}</b> (shown only in DEV_MODE)
                  </div>
                )}
                <label>{t("enter_otp")}</label>
                <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" />
                <div style={{ marginTop: 16 }} className="row">
                  <button onClick={verifyOtp} disabled={busy || !code}>{t("verify")}</button>
                  <button className="ghost" onClick={() => setSent(false)}>←</button>
                </div>
              </>
            )}
            <div style={{ marginTop: 12, fontSize: 13 }}>
              <a role="button" tabIndex={0} className="linklike"
                 onClick={() => { setMode("password"); setErr(null); setSent(false); }}>
                ← {t("auth_login_password")}
              </a>
            </div>
          </>
        )}
      </div>

      <div className="card" style={{ textAlign: "center" }}>
        {t("auth_new_here")} <Link href="/register"><b>{t("auth_create_account")}</b></Link>
      </div>
    </div>
  );
}
