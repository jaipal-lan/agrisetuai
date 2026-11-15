import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, getUser, setSession, getToken } from "../lib/api";
import { useI18n } from "../lib/i18n";

export default function Onboarding() {
  const { t } = useI18n();
  const router = useRouter();
  const [me, setMe] = useState(null);
  const [mandals, setMandals] = useState([]);
  const [form, setForm] = useState({});
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    api("/auth/me").then((u) => {
      setMe(u);
      setForm({
        name: u.name || "",
        district: u.district || "",
        state: u.state || "",
        pincode: u.pincode || "",
        aadhaar: u.has_aadhaar ? "" : "",
        pan: u.has_pan ? "" : "",
        village: u.farmer?.village || "",
        pickup_point: u.farmer?.pickup_point || "",
        mandal_id: u.farmer?.mandal_id || "",
        farm_size: u.farmer?.farm_size || "",
        crops_grown: (u.farmer?.crops_grown || []).join(", "),
        soil_type: u.farmer?.soil_type || "",
        irrigation_type: u.farmer?.irrigation_type || "",
        experience_years: u.farmer?.experience_years || "",
        buyer_type: u.buyer?.buyer_type || "household",
        skill_level: u.agent?.skill_level || "",
        languages: u.agent?.languages || "te,en",
      });
    }).catch((e) => setErr(e.message));
    api("/locations/mandals").then(setMandals).catch(() => {});
  }, []);

  const role = me?.role;
  const isFarmer = role === "farmer" || role === "fpo";
  const isBuyer = role === "buyer_household" || role === "buyer_business";
  const isAgent = role === "field_agent";
  const isTransport = role === "transport";

  async function submit() {
    setErr(null);
    setMsg(null);
    const body = { name: form.name || undefined, submit_kyc: true,
      district: form.district || undefined, state: form.state || undefined,
      pincode: form.pincode || undefined,
      aadhaar: form.aadhaar || undefined, pan: form.pan || undefined };
    if (isFarmer) {
      body.village = form.village || undefined;
      body.pickup_point = form.pickup_point || undefined;
      if (form.mandal_id) body.mandal_id = Number(form.mandal_id);
      if (form.farm_size !== "") body.farm_size = Number(form.farm_size);
      body.crops_grown = form.crops_grown ? form.crops_grown.split(",").map((s) => s.trim()).filter(Boolean) : undefined;
      body.soil_type = form.soil_type || undefined;
      body.irrigation_type = form.irrigation_type || undefined;
      if (form.experience_years !== "") body.experience_years = Number(form.experience_years);
    }
    if (isBuyer) body.buyer_type = form.buyer_type;
    if (isAgent) {
      body.skill_level = form.skill_level || undefined;
      body.languages = form.languages || undefined;
    }
    try {
      const u = await api("/auth/me", { method: "PATCH", body });
      setSession(getToken(), u); // refresh stored session so prompts clear
      setMsg("Profile submitted. KYC is pending review.");
      setTimeout(() => router.push("/"), 1200);
    } catch (e) {
      setErr(e.message);
    }
  }

  if (!me) return <p className="muted">{t("loading")}</p>;

  return (
    <div style={{ maxWidth: 560 }}>
      <h1>Complete your profile</h1>
      <p className="tagline">A few details help us verify you and serve your area.</p>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok">{msg}</div>}

      <div className="card">
        <label>Name</label>
        <input value={form.name} onChange={(e) => set("name", e.target.value)} />

        <div className="form-grid" style={{ marginTop: 8 }}>
          <label>District<input value={form.district} onChange={(e) => set("district", e.target.value)} /></label>
          <label>State<input value={form.state} onChange={(e) => set("state", e.target.value)} /></label>
          <label>PIN code<input value={form.pincode} onChange={(e) => set("pincode", e.target.value)} inputMode="numeric" maxLength={6} /></label>
        </div>
        <div className="form-grid">
          <label>Aadhaar (optional)<input value={form.aadhaar} onChange={(e) => set("aadhaar", e.target.value.replace(/\D/g, ""))} inputMode="numeric" maxLength={12} placeholder={me.has_aadhaar ? "•••• on file" : ""} /></label>
          <label>PAN (optional)<input value={form.pan} onChange={(e) => set("pan", e.target.value.toUpperCase())} maxLength={10} placeholder={me.has_pan ? "•••• on file" : ""} /></label>
        </div>

        {isFarmer && (
          <>
            <label>Village</label>
            <input value={form.village} onChange={(e) => set("village", e.target.value)} />
            <label>Pickup point (landmark)</label>
            <input value={form.pickup_point} onChange={(e) => set("pickup_point", e.target.value)} />
            <label>Mandal</label>
            <select value={form.mandal_id} onChange={(e) => set("mandal_id", e.target.value)}>
              <option value="">—</option>
              {mandals.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
            <div className="form-grid" style={{ marginTop: 8 }}>
              <label>Farm size (acres)<input value={form.farm_size} onChange={(e) => set("farm_size", e.target.value)} inputMode="decimal" /></label>
              <label>Experience (years)<input value={form.experience_years} onChange={(e) => set("experience_years", e.target.value)} inputMode="numeric" /></label>
              <label>Soil type<input value={form.soil_type} onChange={(e) => set("soil_type", e.target.value)} placeholder="e.g. Black cotton" /></label>
              <label>Irrigation<input value={form.irrigation_type} onChange={(e) => set("irrigation_type", e.target.value)} placeholder="e.g. Canal, Borewell" /></label>
            </div>
            <label>Crops grown (comma-separated)</label>
            <input value={form.crops_grown} onChange={(e) => set("crops_grown", e.target.value)} placeholder="Paddy, Red Chilli, Turmeric" />
          </>
        )}
        {isBuyer && (
          <>
            <label>Buyer type</label>
            <select value={form.buyer_type} onChange={(e) => set("buyer_type", e.target.value)}>
              <option value="household">Household</option>
              <option value="business">Business (retailer/wholesaler/hotel)</option>
            </select>
          </>
        )}
        {isAgent && (
          <>
            <label>Expertise / skill level</label>
            <input value={form.skill_level} onChange={(e) => set("skill_level", e.target.value)}
                   placeholder="e.g. Field Agricultural Advisor" />
            <label>Languages</label>
            <input value={form.languages} onChange={(e) => set("languages", e.target.value)} placeholder="te,en" />
          </>
        )}
        {isTransport && (
          <p className="muted" style={{ fontSize: 13 }}>
            Transport partners are onboarded as couriers by the platform admin (KYC, vehicle classes, service areas).
          </p>
        )}

        <div style={{ marginTop: 14 }}>
          <button onClick={submit}>Submit & request verification</button>
        </div>
      </div>
    </div>
  );
}
