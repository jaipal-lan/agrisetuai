import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, apiForm } from "../lib/api";
import { useI18n } from "../lib/i18n";

// Public, role-based sign-up. Steps: verify phone (OTP) -> set password ->
// choose role -> personal details + address (with GPS auto-fill) -> business
// details (business buyers only) -> submit -> redirected to login.
const ROLES = [
  ["farmer", "Farmer — sell & buy", "రైతు — అమ్మకం & కొనుగోలు",
   "List and sell your produce, and buy inputs/goods too."],
  ["buyer_household", "Household buyer", "గృహ కొనుగోలుదారు",
   "Buy fresh produce for your home."],
  ["buyer_business", "Business buyer", "వ్యాపార కొనుగోలుదారు",
   "Buy in bulk for a shop, hotel or company (needs business details)."],
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
    setErr(null); setBusy(true);
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
        setErr("An account already exists for this number. Please log in instead.");
        return;
      }
      setPhoneToken(r.phone_token);
      setStep(2);
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  function nextFromPassword() {
    setErr(null);
    if (password.length < 6) { setErr("Password must be at least 6 characters."); return; }
    if (password !== password2) { setErr("Passwords don't match."); return; }
    setStep(3);
  }

  function nextFromDetails() {
    setErr(null);
    if (!firstName.trim()) { setErr("Please enter your first name."); return; }
    if (isBusiness) { setStep(5); return; }
    submit(); // stays on step 4 so any error is shown in place
  }

  function useMyLocation() {
    setGeoMsg(null); setErr(null);
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setGeoMsg("Location isn't available on this device.");
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
            setGeoMsg(`Detected: ${n.name}${n.serviceable ? "" : " (not yet serviced)"} · ~${n.distance_km} km away`);
          }
        } catch { setGeoMsg("Location captured."); }
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
      () => { setGeoMsg("Couldn't get your location. You can pick your area manually."); setLocating(false); },
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
    if (!bizName.trim()) { setErr("Please enter your business name."); return; }
    if (evidence.length === 0) { setErr("Attach your registration document or organisation PAN."); return; }
    submit();
  }

  const Progress = () => (
    <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
      Step {Math.min(step, lastStep)} of {lastStep}
    </div>
  );

  return (
    <div style={{ maxWidth: 460, margin: "0 auto" }}>
      <h1>Create your account</h1>
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
            Already have an account? <Link href="/login"><b>Log in</b></Link>
          </div>
        </div>
      )}

      {/* Step 2 — password */}
      {step === 2 && (
        <div className="card">
          <Progress />
          <p className="muted" style={{ fontSize: 13 }}>Phone verified ✓ Now set a password.</p>
          <label>Password (min 6 characters)</label>
          <input type="password" value={password} autoComplete="new-password"
                 onChange={(e) => setPassword(e.target.value)} />
          <label>Confirm password</label>
          <input type="password" value={password2} autoComplete="new-password"
                 onChange={(e) => setPassword2(e.target.value)} />
          <div className="row" style={{ marginTop: 14 }}>
            <button onClick={nextFromPassword} disabled={!password || !password2}>Continue</button>
          </div>
        </div>
      )}

      {/* Step 3 — role */}
      {step === 3 && (
        <div className="card">
          <Progress />
          <label>I am a…</label>
          <div style={{ display: "grid", gap: 10, marginTop: 6 }}>
            {ROLES.map(([v, en, te, desc]) => (
              <label key={v}
                     className="role-opt"
                     style={{
                       display: "block", padding: 12, borderRadius: 10, cursor: "pointer",
                       border: `2px solid ${role === v ? "var(--green-600, #16a34a)" : "var(--line, #ddd)"}`,
                     }}>
                <div className="between">
                  <b>{lang === "te" ? te : en}</b>
                  <input type="radio" name="role" checked={role === v}
                         onChange={() => setRole(v)} />
                </div>
                <div className="muted" style={{ fontSize: 13 }}>{desc}</div>
              </label>
            ))}
          </div>
          <div className="row" style={{ marginTop: 14 }}>
            <button className="ghost" onClick={() => setStep(2)}>←</button>
            <button onClick={() => setStep(4)}>Continue</button>
          </div>
        </div>
      )}

      {/* Step 4 — details + address */}
      {step === 4 && (
        <div className="card">
          <Progress />
          <div className="form-grid">
            <label>First name*
              <input value={firstName} onChange={(e) => setFirstName(e.target.value)} />
            </label>
            <label>Last name
              <input value={lastName} onChange={(e) => setLastName(e.target.value)} />
            </label>
            <label style={{ gridColumn: "1 / -1" }}>Email (optional)
              <input type="email" value={email} autoComplete="email"
                     onChange={(e) => setEmail(e.target.value)} />
            </label>
          </div>

          <h3 style={{ marginBottom: 4 }}>Your address</h3>
          <div style={{ marginBottom: 8 }}>
            <button type="button" className="ghost" onClick={useMyLocation} disabled={locating}>
              {locating ? "Locating…" : "📍 Use my current location"}
            </button>
            {geoMsg && <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>{geoMsg}</div>}
          </div>
          <div className="form-grid">
            <label>Label
              <input value={addrLabel} onChange={(e) => setAddrLabel(e.target.value)} />
            </label>
            <label>Area / Mandal
              <select value={mandalId} onChange={(e) => setMandalId(e.target.value)}>
                <option value="">Pick mandal…</option>
                {mandals.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </label>
            <label style={{ gridColumn: "1 / -1" }}>Address
              <input value={addrLine} placeholder="House / street / village"
                     onChange={(e) => setAddrLine(e.target.value)} />
            </label>
          </div>

          <div className="row" style={{ marginTop: 14 }}>
            <button className="ghost" onClick={() => setStep(3)}>←</button>
            <button onClick={nextFromDetails} disabled={busy}>
              {isBusiness ? "Continue" : (busy ? "Creating…" : "Create account")}
            </button>
          </div>
        </div>
      )}

      {/* Step 5 — business details */}
      {step === 5 && (
        <div className="card">
          <Progress />
          <p className="muted" style={{ fontSize: 13 }}>
            Business buyers are verified before trading. Add your business details and
            attach a registration document or your organisation PAN.
          </p>
          <div className="form-grid">
            <label style={{ gridColumn: "1 / -1" }}>Business / organisation name*
              <input value={bizName} onChange={(e) => setBizName(e.target.value)} />
            </label>
            <label>Registration no.
              <input value={bizReg} onChange={(e) => setBizReg(e.target.value)} />
            </label>
            <label>GSTIN (optional)
              <input value={bizGst} onChange={(e) => setBizGst(e.target.value.toUpperCase())} maxLength={15} />
            </label>
            <label style={{ gridColumn: "1 / -1" }}>Business address
              <input value={bizAddr} onChange={(e) => setBizAddr(e.target.value)} />
            </label>
          </div>
          <label style={{ display: "block", marginTop: 10 }}>
            Evidence (registration doc / org PAN)* — PDF or image
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
              {busy ? "Creating…" : "Create account"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
