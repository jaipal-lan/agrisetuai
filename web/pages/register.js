import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import AddressPicker from "../components/AddressPicker";
import { api, apiForm } from "../lib/api";
import { useI18n } from "../lib/i18n";

// Public, role-based sign-up. Steps: verify phone (OTP) -> set password ->
// choose role -> personal details + address (with GPS auto-fill) -> business
// details (business buyers only) -> submit -> redirected to login.
// [value, label-key, description-key] — rendered via t() so they localize.
const ROLES = [
  ["farmer", "role_farmer_opt", "role_farmer_sub"],
  ["buyer_household", "role_household", "role_household_sub"],
  ["buyer_business", "role_business", "role_business_sub"],
];

export default function Register() {
  const { t, lang } = useI18n();
  const router = useRouter();

  const [step, setStep] = useState(1);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  // Step 1 — phone / OTP
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [devCode, setDevCode] = useState(null);
  const [phoneToken, setPhoneToken] = useState(null);

  // Step 2 — password
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");

  // Step 3 — role
  const [role, setRole] = useState("farmer");

  // Step 4 — details + address
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [mandals, setMandals] = useState([]);
  const [addrLabel, setAddrLabel] = useState("Home");
  const [mandalId, setMandalId] = useState("");
  const [addrLine, setAddrLine] = useState("");
  const [lat, setLat] = useState(null);
  const [lng, setLng] = useState(null);
  const [geoMsg, setGeoMsg] = useState(null);
  const [locating, setLocating] = useState(false);

  // Step 5 — business
  const [bizName, setBizName] = useState("");
  const [bizReg, setBizReg] = useState("");
  const [bizGst, setBizGst] = useState("");
  const [bizAddr, setBizAddr] = useState("");
  const [evidence, setEvidence] = useState([]);

  const isBusiness = role === "buyer_business";
  const lastStep = isBusiness ? 5 : 4;

  useEffect(() => {
    api("/locations/mandals").then(setMandals).catch(() => {});
  }, []);

  async function sendOtp() {
    setErr(null);
    // Strict 10-digit Indian mobile (6-9 start). Backend OTP also validates;
    // this catches typos before an OTP is spent.
    if (!/^[6-9]\d{9}$/.test((phone || "").trim())) { setErr(t("err_phone_invalid")); return; }
    setBusy(true);
    try {
      const r = await api("/auth/otp/request", { method: "POST", body: { phone } });
      setSent(true);
      setDevCode(r.dev_code || null);
      if (r.dev_code) setCode(r.dev_code);
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  async function verifyPhone() {
    setErr(null); setBusy(true);
    try {
      const r = await api("/auth/otp/verify-phone", { method: "POST", body: { phone, code } });
      if (r.exists) {
        setErr(t("err_acct_exists"));
        return;
      }
      setPhoneToken(r.phone_token);
      setStep(2);
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  function nextFromPassword() {
    setErr(null);
    if (password.length < 6) { setErr(t("err_pwd_min")); return; }
    if (password !== password2) { setErr(t("err_pwd_match")); return; }
    setStep(3);
  }

  function nextFromDetails() {
    setErr(null);
    if (!firstName.trim()) { setErr(t("err_first_name")); return; }
    if (isBusiness) { setStep(5); return; }
    submit(); // stays on step 4 so any error is shown in place
  }

  function useMyLocation() {
    setGeoMsg(null); setErr(null);
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setGeoMsg(t("geo_unavailable"));
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude, longitude } = pos.coords;
        setLat(latitude); setLng(longitude);
        try {
          const n = await api(`/locations/nearest?lat=${latitude}&lng=${longitude}`);
          if (n?.mandal_id) {
            setMandalId(String(n.mandal_id));
            setGeoMsg(`${t("geo_detected")} ${n.name}${n.serviceable ? "" : " " + t("geo_not_serviced")} · ~${n.distance_km} ${t("geo_km_away")}`);
          }
        } catch { setGeoMsg(t("geo_captured")); }
        // Best-effort street address prefill (OpenStreetMap, free).
        try {
          const res = await fetch(
            `https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=18&lat=${latitude}&lon=${longitude}`,
            { headers: { Accept: "application/json" } }
          );
          const j = await res.json();
          if (j?.display_name && !addrLine) setAddrLine(j.display_name);
        } catch {}
        setLocating(false);
      },
      () => { setGeoMsg(t("geo_failed")); setLocating(false); },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
  }

  async function submit() {
    setErr(null); setBusy(true);
    try {
      const fd = new FormData();
      fd.append("phone_token", phoneToken);
      fd.append("password", password);
      fd.append("role", role);
      fd.append("first_name", firstName.trim());
      if (lastName.trim()) fd.append("last_name", lastName.trim());
      if (email.trim()) fd.append("email", email.trim());
      fd.append("preferred_language", lang || "te");
      fd.append("address_label", addrLabel || "Home");
      if (mandalId) fd.append("address_mandal_id", mandalId);
      if (addrLine.trim()) fd.append("address_line", addrLine.trim());
      if (lat != null) fd.append("address_lat", lat);
      if (lng != null) fd.append("address_lng", lng);
      if (isBusiness) {
        fd.append("biz_legal_name", bizName.trim());
        if (bizReg.trim()) fd.append("biz_registration_number", bizReg.trim());
        if (bizGst.trim()) fd.append("biz_gst", bizGst.trim());
        if (bizAddr.trim()) fd.append("biz_address_line", bizAddr.trim());
        if (mandalId) fd.append("biz_mandal_id", mandalId);
        evidence.forEach((f) => fd.append("evidence", f));
      }
      await apiForm("/auth/register", fd);
      router.push("/login?registered=1");
    } catch (e) { setErr(e.message); setBusy(false); }
  }

  function submitBusiness() {
    setErr(null);
    if (!bizName.trim()) { setErr(t("err_biz_name")); return; }
    if (evidence.length === 0) { setErr(t("err_biz_evidence")); return; }
    submit();
  }

  const Progress = () => (
    <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
      {t("auth_step")} {Math.min(step, lastStep)} {t("word_of")} {lastStep}
    </div>
  );

  return (
    <div style={{ maxWidth: 460, margin: "0 auto" }}>
      <h1>{t("auth_create_your_account")}</h1>
      <p className="tagline">{t("tagline")}</p>
      {err && <div className="error">{err}</div>}

      {/* Step 1 — phone */}
      {step === 1 && (
        <div className="card">
          <Progress />
          <label>{t("phone")}</label>
          <input value={phone} inputMode="numeric" autoComplete="tel"
                 placeholder="91XXXXXXXXXX"
                 onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))} />
          {!sent ? (
            <div style={{ marginTop: 14 }}>
              <button onClick={sendOtp} disabled={busy || phone.length < 8}>{t("send_otp")}</button>
            </div>
          ) : (
            <>
              {devCode && (
                <div className="ok" style={{ fontSize: 13 }}>Dev OTP: <b>{devCode}</b></div>
              )}
              <label>{t("enter_otp")}</label>
              <input value={code} inputMode="numeric" onChange={(e) => setCode(e.target.value)} />
              <div className="row" style={{ marginTop: 14 }}>
                <button onClick={verifyPhone} disabled={busy || !code}>{t("verify")}</button>
                <button className="ghost" onClick={() => setSent(false)}>←</button>
              </div>
            </>
          )}
          <div style={{ marginTop: 14, fontSize: 13 }}>
            {t("auth_have_account")} <Link href="/login"><b>{t("login")}</b></Link>
          </div>
        </div>
      )}

      {/* Step 2 — password */}
      {step === 2 && (
        <div className="card">
          <Progress />
          <p className="muted" style={{ fontSize: 13 }}>{t("auth_phone_verified_pwd")}</p>
          <label>{t("auth_password_min")}</label>
          <input type="password" value={password} autoComplete="new-password"
                 onChange={(e) => setPassword(e.target.value)} />
          <label>{t("auth_confirm_password")}</label>
          <input type="password" value={password2} autoComplete="new-password"
                 onChange={(e) => setPassword2(e.target.value)} />
          <div className="row" style={{ marginTop: 14 }}>
            <button onClick={nextFromPassword} disabled={!password || !password2}>{t("auth_continue")}</button>
          </div>
        </div>
      )}

      {/* Step 3 — role */}
      {step === 3 && (
        <div className="card">
          <Progress />
          <label>{t("auth_i_am")}</label>
          <div style={{ display: "grid", gap: 10, marginTop: 6 }}>
            {ROLES.map(([v, labelKey, descKey]) => (
              <label key={v}
                     className="role-opt"
                     style={{
                       display: "block", padding: 12, borderRadius: 10, cursor: "pointer",
                       border: `2px solid ${role === v ? "var(--green-600, #16a34a)" : "var(--line, #ddd)"}`,
                     }}>
                <div className="between">
                  <b>{t(labelKey)}</b>
                  <input type="radio" name="role" checked={role === v}
                         onChange={() => setRole(v)} />
                </div>
                <div className="muted" style={{ fontSize: 13 }}>{t(descKey)}</div>
              </label>
            ))}
          </div>
          <div className="row" style={{ marginTop: 14 }}>
            <button className="ghost" onClick={() => setStep(2)}>←</button>
            <button onClick={() => setStep(4)}>{t("auth_continue")}</button>
          </div>
        </div>
      )}

      {/* Step 4 — details + address */}
      {step === 4 && (
        <div className="card">
          <Progress />
          <div className="form-grid">
            <label>{t("auth_first_name")}*
              <input value={firstName} onChange={(e) => setFirstName(e.target.value)} />
            </label>
            <label>{t("auth_last_name")}
              <input value={lastName} onChange={(e) => setLastName(e.target.value)} />
            </label>
            <label style={{ gridColumn: "1 / -1" }}>{t("auth_email_opt")}
              <input type="email" value={email} autoComplete="email"
                     onChange={(e) => setEmail(e.target.value)} />
            </label>
          </div>

          <h3 style={{ marginBottom: 4 }}>{t("auth_your_address")}</h3>
          <AddressPicker
            autoLocate
            showServiceability={false}
            onChange={(a) => {
              if (a.lat != null) { setLat(a.lat); setLng(a.lng); }
              if (a.mandal_id) setMandalId(String(a.mandal_id));
              setAddrLine(a.address_line || "");
              setAddrLabel(a.label || "Home");
            }}
          />

          <div className="row" style={{ marginTop: 14 }}>
            <button className="ghost" onClick={() => setStep(3)}>←</button>
            <button onClick={nextFromDetails} disabled={busy}>
              {isBusiness ? t("auth_continue") : (busy ? t("auth_creating") : t("auth_create_account_btn"))}
            </button>
          </div>
        </div>
      )}

      {/* Step 5 — business details */}
      {step === 5 && (
        <div className="card">
          <Progress />
          <p className="muted" style={{ fontSize: 13 }}>
            {t("auth_biz_intro")}
          </p>
          <div className="form-grid">
            <label style={{ gridColumn: "1 / -1" }}>{t("auth_biz_name")}*
              <input value={bizName} onChange={(e) => setBizName(e.target.value)} />
            </label>
            <label>{t("auth_reg_no")}
              <input value={bizReg} onChange={(e) => setBizReg(e.target.value)} />
            </label>
            <label>{t("auth_gstin")}
              <input value={bizGst} onChange={(e) => setBizGst(e.target.value.toUpperCase())} maxLength={15} />
            </label>
            <label style={{ gridColumn: "1 / -1" }}>{t("auth_biz_address")}
              <input value={bizAddr} onChange={(e) => setBizAddr(e.target.value)} />
            </label>
          </div>
          <label style={{ display: "block", marginTop: 10 }}>
            {t("auth_evidence_label")}
            <input type="file" accept="image/*,application/pdf" multiple
                   onChange={(e) => setEvidence(Array.from(e.target.files || []))} />
          </label>
          {evidence.length > 0 && (
            <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
              {evidence.map((f) => f.name).join(", ")}
            </div>
          )}
          <div className="row" style={{ marginTop: 14 }}>
            <button className="ghost" onClick={() => setStep(4)}>←</button>
            <button onClick={submitBusiness} disabled={busy}>
              {busy ? t("auth_creating") : t("auth_create_account_btn")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
