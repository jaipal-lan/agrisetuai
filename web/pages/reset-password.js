import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";

import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";

// Forgot password: verify phone by OTP, then set a new password. Reuses the
// same phone-ownership token the registration flow uses.
export default function ResetPassword() {
  const { t } = useI18n();
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [devCode, setDevCode] = useState(null);
  const [phoneToken, setPhoneToken] = useState(null);
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  async function sendOtp() {
    setErr(null); setBusy(true);
    try {
      const r = await api("/auth/otp/request", { method: "POST", body: { phone } });
      setSent(true);
      setDevCode(r.dev_code || null);
      if (r.dev_code) setCode(r.dev_code);
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  async function verify() {
    setErr(null); setBusy(true);
    try {
      const r = await api("/auth/otp/verify-phone", { method: "POST", body: { phone, code } });
      if (!r.exists) {
        setErr("No account found for this number. Please register instead.");
        return;
      }
      setPhoneToken(r.phone_token);
      setStep(2);
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  async function reset() {
    setErr(null);
    if (password.length < 6) { setErr("Password must be at least 6 characters."); return; }
    if (password !== password2) { setErr("Passwords don't match."); return; }
    setBusy(true);
    try {
      await api("/auth/password/reset", { method: "POST", body: { phone_token: phoneToken, new_password: password } });
      router.push("/login?reset=1");
    } catch (e) { setErr(e.message); setBusy(false); }
  }

  return (
    <div style={{ maxWidth: 420, margin: "0 auto" }}>
      <h1>Reset password</h1>
      {err && <div className="error">{err}</div>}

      {step === 1 ? (
        <div className="card">
          <label>{t("phone")}</label>
          <input value={phone} inputMode="numeric" autoComplete="tel" placeholder="91XXXXXXXXXX"
                 onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))} />
          {!sent ? (
            <div style={{ marginTop: 14 }}>
              <button onClick={sendOtp} disabled={busy || phone.length < 8}>{t("send_otp")}</button>
            </div>
          ) : (
            <>
              {devCode && <div className="ok" style={{ fontSize: 13 }}>Dev OTP: <b>{devCode}</b></div>}
              <label>{t("enter_otp")}</label>
              <input value={code} inputMode="numeric" onChange={(e) => setCode(e.target.value)} />
              <div className="row" style={{ marginTop: 14 }}>
                <button onClick={verify} disabled={busy || !code}>{t("verify")}</button>
                <button className="ghost" onClick={() => setSent(false)}>←</button>
              </div>
            </>
          )}
          <div style={{ marginTop: 14, fontSize: 13 }}>
            <Link href="/login">← Back to login</Link>
          </div>
        </div>
      ) : (
        <div className="card">
          <p className="muted" style={{ fontSize: 13 }}>Phone verified ✓ Choose a new password.</p>
          <label>New password (min 6 characters)</label>
          <input type="password" value={password} autoComplete="new-password"
                 onChange={(e) => setPassword(e.target.value)} />
          <label>Confirm new password</label>
          <input type="password" value={password2} autoComplete="new-password"
                 onChange={(e) => setPassword2(e.target.value)} />
          <div className="row" style={{ marginTop: 14 }}>
            <button onClick={reset} disabled={busy || !password || !password2}>
              {busy ? "Saving…" : "Set new password"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
