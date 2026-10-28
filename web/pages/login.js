import { useRouter } from "next/router";
import { useState } from "react";

import { api, setSession } from "../lib/api";
import { useI18n } from "../lib/i18n";

const ROLES = [
  ["farmer", "Farmer / రైతు"],
  ["fpo", "FPO / రైతు సంఘం"],
  ["buyer_household", "Household buyer / గృహ కొనుగోలుదారు"],
  ["buyer_business", "Business buyer / వ్యాపార కొనుగోలుదారు"],
  ["field_agent", "Field agent / క్షేత్ర ఏజెంట్"],
  ["mandal_manager", "Mandal manager / మండల్ మేనేజర్"],
  ["transport", "Transport / రవాణా"],
  ["superadmin", "Superadmin"],
];

export default function Login() {
  const { t } = useI18n();
  const router = useRouter();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [role, setRole] = useState("farmer");
  const [name, setName] = useState("");
  const [sent, setSent] = useState(false);
  const [devCode, setDevCode] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  async function sendOtp() {
    setErr(null);
    setBusy(true);
    try {
      const r = await api("/auth/otp/request", { method: "POST", body: { phone } });
      setSent(true);
      setDevCode(r.dev_code || null);
      if (r.dev_code) setCode(r.dev_code);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    setErr(null);
    setBusy(true);
    try {
      const r = await api("/auth/otp/verify", {
        method: "POST",
        body: { phone, code, role, name: name || undefined },
      });
      setSession(r.token, r.user);
      router.push(r.user.role === "farmer" || r.user.role === "fpo" ? "/sell" : "/");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 420, margin: "0 auto" }}>
      <h1>{t("login")}</h1>
      <p className="tagline">{t("tagline")}</p>
      {err && <div className="error">{err}</div>}

      <div className="card">
        <label>{t("phone")}</label>
        <input
          value={phone}
          onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))}
          placeholder="91XXXXXXXXXX"
          inputMode="numeric"
        />

        {!sent ? (
          <>
            <p className="muted" style={{ fontSize: 13 }}>
              New here? Pick a role — it is set once at sign-up.
            </p>
            <label>{t("role")}</label>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map(([v, labelText]) => (
                <option key={v} value={v}>{labelText}</option>
              ))}
            </select>
            <label>{t("name")}</label>
            <input value={name} onChange={(e) => setName(e.target.value)} />
            <div style={{ marginTop: 16 }}>
              <button onClick={sendOtp} disabled={busy || phone.length < 8}>
                {t("send_otp")}
              </button>
            </div>
          </>
        ) : (
          <>
            {devCode && (
              <div className="ok" style={{ fontSize: 13 }}>
                Dev OTP: <b>{devCode}</b> (shown only in DEV_MODE)
              </div>
            )}
            <label>{t("enter_otp")}</label>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              inputMode="numeric"
            />
            <div style={{ marginTop: 16 }} className="row">
              <button onClick={verify} disabled={busy || !code}>{t("verify")}</button>
              <button className="ghost" onClick={() => setSent(false)}>←</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
