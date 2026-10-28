import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { useI18n } from "../lib/i18n";

export default function Sell() {
  const { t, lang } = useI18n();
  const [user, setUser] = useState(null);
  const [commodities, setCommodities] = useState([]);
  const [grades, setGrades] = useState([]);
  const [listings, setListings] = useState([]);
  const [form, setForm] = useState({
    commodity_id: "",
    grade_spec_id: "",
    total_qty: "",
    min_order_qty: "",
    asking_price: "",
    harvest_year: new Date().getFullYear(),
    claim_status: "conventional",
  });
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const cmap = Object.fromEntries(commodities.map((c) => [c.id, c]));
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function loadMine() {
    try {
      setListings(await api("/listings/mine"));
    } catch (e) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    setUser(getUser());
    api("/catalog/commodities").then(setCommodities).catch(() => {});
    loadMine();
  }, []);

  useEffect(() => {
    if (!form.commodity_id) return setGrades([]);
    api(`/catalog/commodities/${form.commodity_id}/grades`).then(setGrades).catch(() => {});
  }, [form.commodity_id]);

  async function create() {
    setErr(null);
    setMsg(null);
    setBusy(true);
    try {
      const body = {
        commodity_id: Number(form.commodity_id),
        grade_spec_id: form.grade_spec_id ? Number(form.grade_spec_id) : undefined,
        total_qty: Number(form.total_qty),
        min_order_qty: Number(form.min_order_qty || 0),
        asking_price: Number(form.asking_price),
        harvest_year: Number(form.harvest_year),
        claim_status: form.claim_status,
      };
      await api("/listings", { method: "POST", body });
      setMsg("Listing created as a draft — publish it to go live.");
      setForm((f) => ({ ...f, total_qty: "", asking_price: "" }));
      loadMine();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function act(id, action) {
    setErr(null);
    try {
      await api(`/listings/${id}/${action}`, { method: "POST" });
      loadMine();
    } catch (e) {
      setErr(e.message);
    }
  }

  const cname = (c) => (c ? (lang === "te" && c.name_te ? c.name_te : c.name) : "—");

  if (!user) {
    return (
      <div>
        <p className="muted">Log in as a farmer to manage listings.</p>
        <Link href="/login" className="btn">{t("login")}</Link>
      </div>
    );
  }

  return (
    <div>
      <h1>{t("sell")}</h1>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok">{msg}</div>}

      <div className="card">
        <h3>{t("create_listing")}</h3>
        <div className="row">
          <div style={{ flex: 1, minWidth: 180 }}>
            <label>{t("commodity")}</label>
            <select value={form.commodity_id} onChange={(e) => set("commodity_id", e.target.value)}>
              <option value="">—</option>
              {commodities.map((c) => (
                <option key={c.id} value={c.id}>{cname(c)} ({c.category})</option>
              ))}
            </select>
          </div>
          <div style={{ flex: 1, minWidth: 140 }}>
            <label>Grade</label>
            <select value={form.grade_spec_id} onChange={(e) => set("grade_spec_id", e.target.value)}>
              <option value="">—</option>
              {grades.map((g) => (
                <option key={g.id} value={g.id}>{g.code} — {g.label}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="row">
          <div style={{ flex: 1 }}>
            <label>Total {t("quantity")} (kg)</label>
            <input value={form.total_qty} onChange={(e) => set("total_qty", e.target.value)} inputMode="decimal" />
          </div>
          <div style={{ flex: 1 }}>
            <label>Min order (kg)</label>
            <input value={form.min_order_qty} onChange={(e) => set("min_order_qty", e.target.value)} inputMode="decimal" />
          </div>
          <div style={{ flex: 1 }}>
            <label>{t("asking_price")} (₹/kg)</label>
            <input value={form.asking_price} onChange={(e) => set("asking_price", e.target.value)} inputMode="decimal" />
          </div>
        </div>
        <div className="row">
          <div style={{ flex: 1 }}>
            <label>Harvest year</label>
            <input value={form.harvest_year} onChange={(e) => set("harvest_year", e.target.value)} inputMode="numeric" />
          </div>
          <div style={{ flex: 1 }}>
            <label>Cultivation claim</label>
            <select value={form.claim_status} onChange={(e) => set("claim_status", e.target.value)}>
              <option value="conventional">Conventional</option>
              <option value="in_conversion">In conversion</option>
              <option value="organic">Organic (needs evidence)</option>
            </select>
          </div>
        </div>
        <div style={{ marginTop: 16 }}>
          <button onClick={create} disabled={busy || !form.commodity_id || !form.total_qty || !form.asking_price}>
            {t("create_listing")}
          </button>
        </div>
      </div>

      <h2>My listings</h2>
      {listings.length === 0 ? (
        <p className="muted">None yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>{t("commodity")}</th>
              <th>{t("price")}</th>
              <th>{t("available")}</th>
              <th>{t("status")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {listings.map((l) => (
              <tr key={l.id}>
                <td>{cname(cmap[l.commodity_id])}</td>
                <td>₹{l.asking_price}</td>
                <td>{l.available_qty} / {l.total_qty}</td>
                <td><span className="badge grey">{l.status}</span></td>
                <td>
                  {l.status === "draft" && <button onClick={() => act(l.id, "publish")}>{t("publish")}</button>}
                  {l.status === "open" && <button className="ghost" onClick={() => act(l.id, "pause")}>Pause</button>}
                  {l.status === "paused" && <button onClick={() => act(l.id, "publish")}>Resume</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
