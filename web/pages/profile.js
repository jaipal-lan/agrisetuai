import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useRef, useState } from "react";

import AddressPicker from "../components/AddressPicker";
import { absUrl, api, getUser, logout, setSession, uploadMedia } from "../lib/api";
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

  const langLabel = { te: "తెలుగు", en: "English", hi: "हिन्दी" }[lang] || lang;

  const Row = ({ label, children }) => (
    <div className="quote-line"><span className="muted">{label}</span><span>{children}</span></div>
  );

  return (
    <div style={{ maxWidth: 560 }}>
      <h1>{t("profile")}</h1>
      {err && <div className="error">{err}</div>}

      <div className="card">
        <div className="row" style={{ gap: 14, alignItems: "center" }}>
          <ProfilePhoto detail={detail} onSaved={(d) => { setDetail(d); const u = getUser(); if (u) setSession(null, { ...u, avatar_url: d.avatar_url }); }} />
          <div style={{ flex: 1 }}>
            <div className="between">
              <h3 style={{ margin: 0 }}>{detail?.name || me?.name || "—"}</h3>
              <span className="badge">{ROLE_LABEL[me?.role] || me?.role}</span>
            </div>
          </div>
        </div>
        <div style={{ marginTop: 12 }}>
          <Row label="Phone">{detail?.phone || "—"}</Row>
          {detail?.email && <Row label="Email">{detail.email}</Row>}
          <Row label="Account status">
            <span className="badge grey">{detail?.status || "active"}</span>
          </Row>
          {detail?.farmer?.village && <Row label="Village">{detail.farmer.village}</Row>}
          {(detail?.district || detail?.state || detail?.pincode) && (
            <Row label="Area">{[detail.district, detail.state, detail.pincode].filter(Boolean).join(", ")}</Row>
          )}
          {detail?.farmer?.farm_size && <Row label="Farm size">{detail.farmer.farm_size} acres</Row>}
          {detail?.farmer?.crops_grown?.length > 0 && <Row label="Crops">{detail.farmer.crops_grown.join(", ")}</Row>}
          {detail?.farmer?.soil_type && <Row label="Soil">{detail.farmer.soil_type}</Row>}
          {detail?.farmer?.irrigation_type && <Row label="Irrigation">{detail.farmer.irrigation_type}</Row>}
          {detail?.farmer?.experience_years != null && detail?.farmer?.experience_years !== "" && (
            <Row label="Experience">{detail.farmer.experience_years} yrs</Row>
          )}
          {detail?.aadhaar_masked && <Row label="Aadhaar">{detail.aadhaar_masked}</Row>}
          {detail?.pan_masked && <Row label="PAN">{detail.pan_masked}</Row>}
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
        <Link href="/reset-password" className="btn ghost">Change password</Link>
        <Link href="/dashboard" className="btn ghost">My dashboard</Link>
        <button className="danger" onClick={doLogout}>{t("logout")}</button>
      </div>
    </div>
  );
}

// Profile photo: upload a file or capture one with the device camera.
function ProfilePhoto({ detail, onSaved }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [cam, setCam] = useState(false);
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const fallbackRef = useRef(null);
  const src = detail?.avatar_url ? absUrl(detail.avatar_url) : null;

  // Live webcam needs a secure context (HTTPS, or localhost). Over plain HTTP on
  // a LAN IP the browser hides mediaDevices, so we fall back to a capture-enabled
  // file input (opens the camera on phones, the file picker on desktop).
  const webcamOk = typeof window !== "undefined" && window.isSecureContext
    && !!navigator.mediaDevices?.getUserMedia;
  const isMobile = typeof navigator !== "undefined" && navigator.maxTouchPoints > 0;

  async function saveKey(objectKey) {
    const d = await api("/auth/me", { method: "PATCH", body: { avatar_object_key: objectKey } });
    onSaved?.(d);
  }

  async function onFile(e) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file
    if (!file) return;
    setErr(null); setBusy(true);
    try {
      const up = await uploadMedia(file);
      await saveKey(up.object_key);
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  function takePhoto() {
    setErr(null);
    if (webcamOk) startCam();
    else fallbackRef.current?.click(); // mobile: opens camera; desktop: file picker
  }

  async function startCam() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } });
      streamRef.current = stream;
      setCam(true);
      setTimeout(() => { if (videoRef.current) { videoRef.current.srcObject = stream; videoRef.current.play(); } }, 50);
    } catch { setErr("Couldn't open the camera. Upload a photo instead."); }
  }

  function stopCam() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCam(false);
  }

  function capture() {
    const v = videoRef.current;
    if (!v) return;
    const canvas = document.createElement("canvas");
    const size = Math.min(v.videoWidth, v.videoHeight) || 480;
    canvas.width = size; canvas.height = size;
    const ctx = canvas.getContext("2d");
    const sx = (v.videoWidth - size) / 2, sy = (v.videoHeight - size) / 2;
    ctx.drawImage(v, sx, sy, size, size, 0, 0, size, size);
    stopCam();
    setBusy(true); setErr(null);
    canvas.toBlob(async (blob) => {
      try {
        const up = await uploadMedia(new File([blob], "photo.jpg", { type: "image/jpeg" }));
        await saveKey(up.object_key);
      } catch (e) { setErr(e.message); } finally { setBusy(false); }
    }, "image/jpeg", 0.9);
  }

  useEffect(() => () => stopCam(), []);

  return (
    <div style={{ textAlign: "center" }}>
      {cam ? (
        <div>
          <video ref={videoRef} playsInline muted
                 style={{ width: 120, height: 120, objectFit: "cover", borderRadius: "50%", background: "#000" }} />
          <div className="row" style={{ justifyContent: "center", marginTop: 6, gap: 6 }}>
            <button onClick={capture} disabled={busy}>Capture</button>
            <button className="ghost" onClick={stopCam}>Cancel</button>
          </div>
        </div>
      ) : (
        <>
          <div style={{
            width: 72, height: 72, borderRadius: "50%", overflow: "hidden",
            background: "var(--line, #e5e7eb)", display: "flex", alignItems: "center",
            justifyContent: "center", fontSize: 28, margin: "0 auto",
          }}>
            {src ? <img src={src} alt="Profile" style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : "🧑‍🌾"}
          </div>
          <div className="row" style={{ justifyContent: "center", marginTop: 6, gap: 6, flexWrap: "wrap" }}>
            <label className="btn ghost" style={{ cursor: "pointer", fontSize: 12, padding: "4px 8px" }}>
              {busy ? "…" : "Upload"}
              <input type="file" accept="image/*" style={{ display: "none" }} onChange={onFile} disabled={busy} />
            </label>
            <button type="button" className="ghost" style={{ fontSize: 12, padding: "4px 8px" }}
                    onClick={takePhoto} disabled={busy}>
              Take photo
            </button>
            {/* Fallback input used when the live webcam isn't available */}
            <input ref={fallbackRef} type="file" accept="image/*" capture="user"
                   style={{ display: "none" }} onChange={onFile} disabled={busy} />
          </div>
          {!webcamOk && !isMobile && (
            <div className="muted" style={{ fontSize: 11, marginTop: 4, maxWidth: 180, marginInline: "auto" }}>
              Live camera needs HTTPS or localhost — on the LAN link it opens file upload.
            </div>
          )}
          {err && <div className="error" style={{ fontSize: 12, marginTop: 4 }}>{err}</div>}
        </>
      )}
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
  const [addr, setAddr] = useState(null);       // from AddressPicker
  const [isDefault, setIsDefault] = useState(false);
  const [adding, setAdding] = useState(false);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  function load() { api("/auth/addresses").then(setList).catch(() => {}); }
  useEffect(() => { load(); }, []);

  async function add(e) {
    e.preventDefault(); setErr(null);
    if (!addr?.mandal_id) { setErr("Move the map to your location so we can find your area."); return; }
    setBusy(true);
    try {
      await api("/auth/addresses", { method: "POST", body: {
        label: addr.label || "Home", mandal_id: Number(addr.mandal_id),
        address_line: addr.address_line || null,
        latitude: addr.lat ?? undefined, longitude: addr.lng ?? undefined,
        is_default: isDefault } });
      setAddr(null); setIsDefault(false); setAdding(false);
      load();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  async function remove(id) {
    try { await api(`/auth/addresses/${id}`, { method: "DELETE" }); load(); } catch (e) { setErr(e.message); }
  }

  const labelIcon = (l) => (l === "Home" ? "🏠" : l === "Work" ? "💼" : "📍");

  return (
    <>
      <h2>Delivery addresses</h2>
      <p className="muted" style={{ fontSize: 14, marginTop: -8 }}>Saved addresses speed up ordering and reorders.</p>
      {list.length > 0 && (
        <div className="card" style={{ marginBottom: 10 }}>
          {list.map((a) => (
            <div key={a.id} className="between" style={{ padding: "8px 0", borderBottom: "1px solid var(--line)", gap: 8 }}>
              <div>
                <b>{labelIcon(a.label)} {a.label}</b>{a.is_default && <span className="badge green" style={{ marginLeft: 6 }}>default</span>}
                <div className="muted" style={{ fontSize: 13 }}>{a.address_line ? `${a.address_line} · ` : ""}{a.mandal}</div>
              </div>
              <button className="ghost" onClick={() => remove(a.id)}>Remove</button>
            </div>
          ))}
        </div>
      )}
      {!adding ? (
        <button className="ghost" onClick={() => setAdding(true)}>➕ Add a new address</button>
      ) : (
        <form className="card" onSubmit={add}>
          <AddressPicker autoLocate showServiceability={false} onChange={setAddr} />
          <label className="chk" style={{ marginTop: 10 }}>
            <input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} /> Set as default
          </label>
          {err && <div className="error" style={{ marginTop: 8 }}>{err}</div>}
          <div className="row" style={{ marginTop: 10, gap: 8 }}>
            <button type="submit" disabled={busy}>Save address</button>
            <button type="button" className="ghost" onClick={() => { setAdding(false); setAddr(null); }}>Cancel</button>
          </div>
        </form>
      )}
    </>
  );
}
