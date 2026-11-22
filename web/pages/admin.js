import Link from "next/link";
import { useEffect, useState } from "react";

import MapView from "../components/MapView";
import { absUrl, api, downloadCsv, getUser } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n, tEnum } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

// Shared sanity check for a pricing draft — keeps a superadmin from saving
// negative fees, an out-of-range percentage, or a cap below the floor, any of
// which would mis-price every order the rule touches. Mirrors the server guard.
function pricingError(b, t) {
  const nonNeg = ["rate_per_kg", "rate_per_km", "fixed_pickup_fee", "min_transport_charge",
                  "service_fee_flat", "inspection_fee", "packing_fee"];
  for (const k of nonNeg) {
    if (b[k] != null && b[k] !== "" && Number(b[k]) < 0) return t("adm_err_negative");
  }
  for (const k of ["seller_commission_pct", "service_fee_pct", "tax_pct"]) {
    const v = b[k];
    if (v != null && v !== "" && (Number.isNaN(Number(v)) || Number(v) < 0 || Number(v) > 100)) return t("adm_err_pct");
  }
  if (b.max_transport_charge != null && b.max_transport_charge !== ""
      && Number(b.max_transport_charge) < Number(b.min_transport_charge || 0)) return t("adm_err_minmax");
  return null;
}

export default function Admin() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [kpis, setKpis] = useState(null);
  const [ledger, setLedger] = useState(null);
  const [rules, setRules] = useState([]);
  const [err, setErr] = useState(null);
  const [draft, setDraft] = useState({
    handling_class: "dry_grain",
    rate_per_kg: "0.8",
    rate_per_km: "12",
    min_transport_charge: "300",
    seller_commission_pct: "0.7",
    service_fee_pct: "0",
    inspection_fee: "300",
    packing_fee: "500",
    reason: "",
  });
  const [sim, setSim] = useState(null);
  const [lastDraftId, setLastDraftId] = useState(null);
  const [commodities, setCommodities] = useState([]);
  const [carriers, setCarriers] = useState([]);
  const [newCarrier, setNewCarrier] = useState({ name: "", code: "", contact_phone: "" });
  const [reports, setReports] = useState(null);
  const [ops, setOps] = useState(null);
  const [range, setRange] = useState({ from: "", to: "" });
  const [kyc, setKyc] = useState([]);
  const [ann, setAnn] = useState({ title: "", body: "", audience: "all" });
  const [annMsg, setAnnMsg] = useState(null);
  const [schedMsg, setSchedMsg] = useState(null);
  const [schedBusy, setSchedBusy] = useState(false);
  const [priceMsg, setPriceMsg] = useState(null);
  const [priceBusy, setPriceBusy] = useState(false);
  const [priceStatus, setPriceStatus] = useState(null);
  const [payouts, setPayouts] = useState(null);
  const [payoutMsg, setPayoutMsg] = useState(null);
  const [payoutAccts, setPayoutAccts] = useState(null);
  const [users, setUsers] = useState([]);
  const [userQ, setUserQ] = useState("");
  const [userRole, setUserRole] = useState("");

  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
  const setA = (k, v) => setAnn((a) => ({ ...a, [k]: v }));
  const setC = (k, v) => setNewCarrier((c) => ({ ...c, [k]: v }));

  async function load() {
    try {
      const [k, l, r, c, cr, kq] = await Promise.all([
        api("/admin/kpis"),
        api("/admin/ledger/accounts"),
        api("/pricing/rules"),
        api("/catalog/commodities"),
        api("/carriers"),
        api("/admin/kyc"),
      ]);
      setKpis(k);
      setLedger(l);
      setRules(r);
      setCommodities(c);
      setCarriers(cr);
      setKyc(kq);
    } catch (e) {
      setErr(e.message);
    }
  }

  async function onboardCarrier() {
    setErr(null);
    try {
      await api("/carriers", {
        method: "POST",
        body: {
          name: newCarrier.name,
          code: newCarrier.code.toUpperCase(),
          contact_phone: newCarrier.contact_phone || undefined,
          vehicle_classes: ["bike", "auto", "mini_truck"],
        },
      });
      setNewCarrier({ name: "", code: "", contact_phone: "" });
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function patchCarrier(id, patch) {
    setErr(null);
    try {
      await api(`/carriers/${id}`, { method: "PATCH", body: patch });
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  function rangeQS() {
    const p = new URLSearchParams();
    if (range.from) p.set("from", range.from);
    if (range.to) p.set("to", range.to);
    const s = p.toString();
    return s ? `?${s}` : "";
  }

  async function loadReports() {
    try {
      const qs = rangeQS();
      const [rep, op] = await Promise.all([api(`/admin/reports${qs}`), api(`/admin/ops-report${qs}`)]);
      setReports(rep);
      setOps(op);
    } catch (e) {
      setErr(e.message);
    }
  }

  async function loadUsers() {
    try {
      const p = new URLSearchParams();
      if (userQ.trim()) p.set("q", userQ.trim());
      if (userRole) p.set("role", userRole);
      setUsers(await api(`/admin/users?${p.toString()}`));
    } catch {
      setUsers([]);
    }
  }

  async function setUserStatus(id, status) {
    setErr(null);
    try {
      await api(`/admin/users/${id}/status`, { method: "POST", body: { status } });
      loadUsers();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function loadPayouts() {
    // Finance/superadmin only; tolerate 403 for other staff so the page still loads.
    try {
      setPayouts(await api("/admin/payouts"));
    } catch {
      setPayouts(null);
    }
    try {
      setPayoutAccts(await api("/admin/payout-accounts?status_filter=unverified"));
    } catch {
      setPayoutAccts(null);
    }
  }

  async function runPayoutBatch() {
    setErr(null);
    setPayoutMsg(null);
    try {
      const r = await api("/admin/payouts/run", { method: "POST", body: {} });
      setPayoutMsg(
        `${t("adm_batch")} ${r.batch}: ${t("adm_disbursed")} ₹${r.total_amount} ${t("adm_across")} ${r.payout_count} ${t("adm_payouts_word")}.`
        + (r.held_unverified ? ` ${r.held_unverified} ${t("adm_held")}` : "")
      );
      loadPayouts();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function verifyPayoutAccount(userId, approve) {
    setErr(null);
    setPayoutMsg(null);
    try {
      await api(`/admin/payout-accounts/${userId}/verify`, { method: "POST", body: { approve } });
      setPayoutMsg(approve ? t("adm_payout_verified") : t("adm_payout_rejected"));
      loadPayouts();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function sendAnnouncement() {
    setErr(null);
    setAnnMsg(null);
    try {
      const r = await api("/admin/broadcast", { method: "POST", body: ann });
      setAnnMsg(`${t("adm_sent_to")} ${r.sent} ${r.audience === "all" ? t("adm_users_word") : r.audience}.`);
      setAnn({ title: "", body: "", audience: ann.audience });
    } catch (e) {
      setErr(e.message);
    }
  }

  async function refreshPrices() {
    setErr(null);
    setPriceMsg(null);
    setPriceBusy(true);
    try {
      const r = await api("/admin/prices/refresh", { method: "POST" });
      if (r.configured === false) {
        setPriceMsg(t("adm_feed_not_configured"));
      } else if (r.ok === false) {
        setErr(r.message || t("adm_feed_error"));
      } else {
        setPriceMsg(`${t("adm_refreshed_from")} ${r.source}: ${r.upserted} ${t("adm_prices_updated")} (${r.new} ${t("adm_new_word")})${r.as_of ? `, ${t("adm_as_of")} ${r.as_of}` : ""}.`);
      }
      loadPriceStatus();
    } catch (e) {
      setErr(e.message);
    } finally {
      setPriceBusy(false);
    }
  }

  async function runScheduler() {
    setErr(null);
    setSchedMsg(null);
    setSchedBusy(true);
    try {
      const r = await api("/admin/scheduler/run", { method: "POST" });
      setSchedMsg(`${t("adm_ran")} ${new Date(r.ran_at).toLocaleTimeString()}: ${r.digests_sent} ${t("adm_digests_sent")}, ${r.prices_refreshed || 0} ${t("adm_prices_refreshed")}, ${r.meeting_reminders || 0} ${t("adm_reminders_sent")}.`);
    } catch (e) {
      setErr(e.message);
    } finally {
      setSchedBusy(false);
    }
  }

  async function kycDecide(userId, approve) {
    setErr(null);
    let reason;
    if (!approve) {
      reason = window.prompt(t("adm_kyc_reject_prompt")) || "";
      if (!reason.trim()) return; // cancelled / empty — don't reject silently
    }
    try {
      await api(`/admin/kyc/${userId}/decision`, { method: "POST", body: { approve, reason } });
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function saveMoq(id, value) {
    setErr(null);
    try {
      await api(`/catalog/commodities/${id}/moq`, {
        method: "PATCH",
        body: { min_order_qty: Number(value) },
      });
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  function loadPriceStatus() {
    api("/admin/prices/status").then(setPriceStatus).catch(() => {});
  }

  useEffect(() => {
    setMe(getUser());
    loadUsers();
    loadPriceStatus();
  }, []);

  // Auto-refresh the live queues (KPIs, KYC, carriers, payouts) in the
  // background; pauses when the tab is hidden.
  usePoll(() => { load(); loadPayouts(); }, 20000, []);

  // Refetch both report surfaces whenever the date range changes.
  useEffect(() => {
    loadReports();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range.from, range.to]);

  // Re-query the user directory when the search/role filter changes.
  useEffect(() => {
    const id = setTimeout(loadUsers, 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userQ, userRole]);

  function body() {
    return {
      handling_class: draft.handling_class || null,
      rate_per_kg: Number(draft.rate_per_kg),
      rate_per_km: Number(draft.rate_per_km),
      min_transport_charge: Number(draft.min_transport_charge),
      seller_commission_pct: Number(draft.seller_commission_pct),
      service_fee_pct: Number(draft.service_fee_pct),
      inspection_fee: Number(draft.inspection_fee),
      packing_fee: Number(draft.packing_fee),
      reason: draft.reason || undefined,
    };
  }

  async function createDraft() {
    setErr(null);
    const b = body();
    const ve = pricingError(b, t);
    if (ve) { setErr(ve); return; }
    try {
      const r = await api("/admin/pricing-rules/draft", { method: "POST", body: b });
      setLastDraftId(r.id);
      load();
    } catch (e) {
      setErr(e.message);
    }
  }
  async function simulate() {
    setErr(null);
    if (!lastDraftId) return setErr(t("adm_create_draft_first"));
    try {
      setSim(
        await api(`/admin/pricing-rules/${lastDraftId}/simulate`, {
          method: "POST",
          body: { product_value: 12000, billable_kg: 500, route_km: 40 },
        })
      );
    } catch (e) {
      setErr(e.message);
    }
  }
  async function publish() {
    setErr(null);
    if (!lastDraftId) return setErr(t("adm_create_draft_first"));
    try {
      await api(`/admin/pricing-rules/${lastDraftId}/publish`, { method: "POST" });
      setSim(null);
      setLastDraftId(null);
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  const gate = roleGate(me, GROUPS.staff, { label: "the admin console" });
  if (gate) return gate;

  return (
    <div>
      <h1>{t("admin")}</h1>
      {err && <div className="error">{err}</div>}

      <div className="grid">
        {kpis &&
          [
            [t("adm_orders"), kpis.total_orders],
            [t("adm_settled"), kpis.settled_orders],
            [t("adm_cancelled"), kpis.cancelled_orders],
            [t("dl_open_listings"), kpis.open_listings],
            [t("dl_gmv"), `₹${kpis.gmv_settled}`],
          ].map(([label, val]) => (
            <div className="card" key={label}>
              <div className="muted" style={{ fontSize: 13 }}>{label}</div>
              <div className="price" style={{ fontSize: 24 }}>{val}</div>
            </div>
          ))}
      </div>

      <h2>{t("adm_ledger")}</h2>
      {ledger && (
        <div className="card">
          <div className="between">
            <b>{t("adm_balance_check")}</b>
            <span className={`badge ${ledger.balanced ? "" : "amber"}`}>
              {ledger.balanced ? t("adm_balanced") : t("adm_unbalanced")}
            </span>
          </div>
          {Object.entries(ledger.accounts).map(([acct, bal]) => (
            <div className="quote-line" key={acct}>
              <span>{tEnum(t, "acct_", acct)}</span><span>₹{bal}</span>
            </div>
          ))}
        </div>
      )}

      <h2>{t("adm_pricing_rules")}</h2>
      <table>
        <thead>
          <tr><th>{t("adm_th_v")}</th><th>{t("status")}</th><th>{t("adm_th_scope")}</th><th>{t("adm_th_per_kg")}</th><th>{t("adm_th_per_km")}</th><th>{t("adm_th_comm")}</th><th>{t("adm_th_svc")}</th></tr>
        </thead>
        <tbody>
          {rules.map((r) => (
            <tr key={r.id}>
              <td>{r.version}</td>
              <td><span className={`badge ${r.status === "published" ? "" : "grey"}`}>{t("prs_" + r.status) || r.status}</span></td>
              <td>{r.handling_class || t("adm_scope_all")}</td>
              <td>{r.rate_per_kg}</td>
              <td>{r.rate_per_km}</td>
              <td>{r.seller_commission_pct}</td>
              <td>{r.service_fee_pct}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>{t("adm_new_pricing_rule")}</h2>
      <div className="card">
        <div className="row">
          {[
            ["rate_per_kg", t("adm_th_per_kg")],
            ["rate_per_km", t("adm_th_per_km")],
            ["min_transport_charge", t("adm_lbl_min_transport")],
            ["seller_commission_pct", t("adm_lbl_seller_comm")],
            ["service_fee_pct", t("adm_lbl_buyer_svc")],
            ["inspection_fee", t("adm_lbl_inspection")],
            ["packing_fee", t("adm_lbl_packing")],
          ].map(([k, label]) => (
            <div key={k} style={{ flex: "1 1 120px" }}>
              <label>{label}</label>
              <input value={draft[k]} onChange={(e) => set(k, e.target.value)} inputMode="decimal" />
            </div>
          ))}
        </div>
        <label>{t("adm_reason")}</label>
        <input value={draft.reason} onChange={(e) => set("reason", e.target.value)} />
        <div className="row" style={{ marginTop: 16 }}>
          <button onClick={createDraft}>{t("adm_create_draft")}</button>
          <button className="ghost" onClick={simulate} disabled={!lastDraftId}>{t("adm_simulate")}</button>
          <button className="amber" onClick={publish} disabled={!lastDraftId}>{t("adm_publish")}</button>
        </div>
        {sim && (
          <div className="ok" style={{ marginTop: 14 }}>
            {t("adm_sim_pre")} <b>₹{sim.buyer_total}</b>
            {" "}({t("adm_sim_transport")} ₹{sim.transport_charge}, {t("adm_sim_service")} ₹{sim.service_fee})
            {sim.seller_commission !== undefined && <> · {t("adm_sim_commission")} ₹{sim.seller_commission}</>}
          </div>
        )}
      </div>

      <h2>{t("adm_reporting_period")}</h2>
      <div className="card">
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ flex: "0 0 auto" }}>
            <label>{t("tm_from")}</label>
            <input type="date" value={range.from} onChange={(e) => setRange((r) => ({ ...r, from: e.target.value }))} />
          </div>
          <div style={{ flex: "0 0 auto" }}>
            <label>{t("tm_to")}</label>
            <input type="date" value={range.to} onChange={(e) => setRange((r) => ({ ...r, to: e.target.value }))} />
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button className="ghost" onClick={() => setRange(monthRange(0))}>{t("adm_this_month")}</button>
            <button className="ghost" onClick={() => setRange(monthRange(-1))}>{t("adm_last_month")}</button>
            <button className="ghost" onClick={() => setRange({ from: "", to: "" })}>{t("tm_all_time")}</button>
          </div>
        </div>
        <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>
          {range.from || range.to ? `${t("adm_showing")} ${range.from || t("adm_start")} → ${range.to || t("adm_today")}` : t("adm_showing_all")}
          {" "}{t("adm_applies")}
        </div>
      </div>

      {reports && (
        <>
          <div className="between">
            <h2>{t("adm_reports_gmv")} ₹{reports.total_gmv} · {reports.total_orders} {t("adm_orders_word")}</h2>
            <button className="ghost" onClick={() =>
              downloadCsv(`/admin/reports.csv${rangeQS()}`, "kissansetu-gmv-report.csv").catch((e) => setErr(e.message))}>
              {t("ea_download_csv")}
            </button>
          </div>
          <div className="grid">
            {[[t("adm_by_commodity"), reports.by_commodity], [t("adm_by_state"), reports.by_state],
              [t("adm_by_mandal"), reports.by_mandal], [t("adm_by_agent"), reports.by_agent]].map(([title, rows]) => (
              <div className="card" key={title}>
                <h3 style={{ fontSize: 15 }}>{title}</h3>
                {rows.length === 0 ? <p className="muted">{t("adm_no_data")}</p> : (
                  <>
                    <BarChart unit="₹" data={rows.slice(0, 8).map((r) => ({ label: r.key, value: Number(r.gmv) }))} />
                    <table style={{ marginTop: 8 }}>
                      <thead><tr><th></th><th>{t("adm_gmv")}</th><th>{t("adm_orders")}</th></tr></thead>
                      <tbody>
                        {rows.map((r) => (
                          <tr key={r.key}><td>{r.key}</td><td>₹{r.gmv}</td><td>{r.orders}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {ops && (
        <>
          <div className="between">
            <h2>{t("adm_ops_scorecard")}</h2>
            <button className="ghost" onClick={() =>
              downloadCsv(`/admin/ops-report.csv${rangeQS()}`, "kissansetu-ops-report.csv").catch((e) => setErr(e.message))}>
              {t("ea_download_csv")}
            </button>
          </div>

          <div className="grid">
            <div className="card">
              <h3 style={{ fontSize: 15 }}>{t("sp_disputes")}</h3>
              <div className="quote-line"><span>{t("adm_total")}</span><span>{ops.disputes.total}</span></div>
              <div className="quote-line"><span>{t("adm_open")}</span><span>{ops.disputes.open}</span></div>
              <div className="quote-line"><span>{t("adm_decided")}</span><span>{ops.disputes.decided}</span></div>
              <div className="quote-line">
                <span>{t("adm_dispute_rate")}</span>
                <span className={ops.disputes.dispute_rate_pct > 10 ? "badge amber" : ""}>{ops.disputes.dispute_rate_pct}%</span>
              </div>
              {Object.entries(ops.disputes.by_outcome).map(([k, v]) => (
                <div className="quote-line" key={k}>
                  <span className="muted">{tEnum(t, "do_", k)}</span><span className="muted">{v}</span>
                </div>
              ))}
            </div>
            <div className="card">
              <h3 style={{ fontSize: 15 }}>{t("adm_payouts")}</h3>
              <div className="quote-line"><span>{t("adm_pending")}</span><span>₹{ops.payouts.pending_total} · {ops.payouts.pending_count}</span></div>
              <div className="quote-line"><span>{t("adm_processed")}</span><span>₹{ops.payouts.processed_total} · {ops.payouts.processed_count}</span></div>
              <div className="quote-line"><span>{t("adm_batches_run")}</span><span>{ops.payouts.batches}</span></div>
            </div>
          </div>

          <h3 style={{ fontSize: 15 }}>{t("tm_field_agents_h")}</h3>
          {ops.agents.length === 0 ? <p className="muted">{t("adm_no_agent_activity")}</p> : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>{t("tm_th_agent")}</th><th>{t("tm_th_inspections")}</th><th>{t("adm_pass")}</th><th>{t("adm_hold")}</th><th>{t("adm_fail")}</th><th>{t("adm_pass_rate")}</th><th>{t("tm_th_orders")}</th><th>{t("adm_advisories")}</th></tr></thead>
                <tbody>
                  {ops.agents.map((a) => (
                    <tr key={a.agent_id}>
                      <td>{a.name}</td><td>{a.inspections}</td><td>{a.pass}</td><td>{a.hold}</td><td>{a.fail}</td>
                      <td>{a.pass_rate_pct}%</td><td>{a.orders_assigned}</td><td>{a.advisories}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h3 style={{ fontSize: 15 }}>{t("adm_couriers")}</h3>
          {ops.couriers.length === 0 ? <p className="muted">{t("adm_no_shipments")}</p> : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>{t("adm_couriers")}</th><th>{t("adm_shipments")}</th><th>{t("adm_delivered")}</th><th>{t("adm_active")}</th><th>{t("adm_failed")}</th><th>{t("adm_completion")}</th><th>{t("adm_avg_transit")}</th></tr></thead>
                <tbody>
                  {ops.couriers.map((c) => (
                    <tr key={c.courier_id}>
                      <td>{c.name}</td><td>{c.shipments}</td><td>{c.delivered}</td><td>{c.active}</td><td>{c.failed}</td>
                      <td>{c.completion_rate_pct}%</td>
                      <td>{c.avg_transit_hours != null ? `${c.avg_transit_hours}h` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {payoutAccts && payoutAccts.length > 0 && (
        <>
          <h2>{t("adm_payout_accounts")} <span className="badge amber">{payoutAccts.length} {t("adm_to_verify")}</span></h2>
          <p className="muted" style={{ fontSize: 13, marginTop: -8 }}>
            {t("adm_payout_acct_help")}
          </p>
          <div className="card">
            <table>
              <thead><tr><th>{t("adm_partner")}</th><th>{t("role")}</th><th>{t("adm_method")}</th><th>{t("adm_details")}</th><th>{t("adm_action")}</th></tr></thead>
              <tbody>
                {payoutAccts.map((a) => (
                  <tr key={a.user_id}>
                    <td>{a.name}{a.phone ? <div className="muted" style={{ fontSize: 12 }}>{a.phone}</div> : null}</td>
                    <td><span className="badge grey">{tEnum(t, "role_", a.role)}</span></td>
                    <td>{a.method === "upi" ? t("pf_upi") : t("adm_bank")}</td>
                    <td className="muted" style={{ fontSize: 13 }}>
                      {a.method === "upi"
                        ? a.upi_id
                        : `${a.account_name || "—"} · ${a.account_number_masked || "—"} · ${a.ifsc || "—"}`}
                    </td>
                    <td>
                      <div className="row" style={{ gap: 6 }}>
                        <button className="green" style={{ padding: "4px 10px", fontSize: 13 }}
                                onClick={() => verifyPayoutAccount(a.user_id, true)}>{t("adm_verify")}</button>
                        <button className="ghost" style={{ padding: "4px 10px", fontSize: 13 }}
                                onClick={() => verifyPayoutAccount(a.user_id, false)}>{t("sp_reject")}</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {payouts && (
        <>
          <h2>{t("adm_payouts")} {payouts.pending_count > 0 && <span className="badge amber">{payouts.pending_count} {t("adm_pending_badge")}</span>}</h2>
          {payoutMsg && <div className="ok">{payoutMsg}</div>}
          {payouts.missing_payout_accounts > 0 && (
            <div className="error" style={{ marginBottom: 10 }}>
              ⚠ {payouts.missing_payout_accounts} {t("adm_warn_missing")}
            </div>
          )}
          {payouts.blocked_unverified > 0 && (
            <div className="error" style={{ marginBottom: 10 }}>
              ⚠ {payouts.blocked_unverified} {t("adm_warn_blocked")}
            </div>
          )}
          {payouts.blocked_unverified_identity > 0 && (
            <div className="error" style={{ marginBottom: 10 }}>
              ⚠ {payouts.blocked_unverified_identity} {t("adm_warn_blocked_identity")}
            </div>
          )}
          <div className="card">
            <div className="between">
              <div>
                <b>₹{payouts.pending_total}</b> {t("adm_accrued_across")} {payouts.pending_count} {t("adm_payouts_word")}
                <div className="muted" style={{ fontSize: 13 }}>{t("adm_accrue_help")}</div>
              </div>
              <button className="amber" disabled={payouts.pending_count === 0} onClick={runPayoutBatch}>
                {t("adm_run_payout_batch")}
              </button>
            </div>
            {payouts.pending.length > 0 && (
              <table>
                <thead><tr><th>{t("iv_col_order")}</th><th>{t("adm_payee")}</th><th>{t("sp_col_type")}</th><th>{t("tr_th_amount")}</th><th>{t("adm_account")}</th><th>{t("adm_identity")}</th></tr></thead>
                <tbody>
                  {payouts.pending.map((p) => (
                    <tr key={p.id}>
                      <td>{p.order || "—"}</td><td>{p.seller}</td>
                      <td><span className="badge grey">{p.payee_type === "transport" ? t("adm_payee_transport") : t("adm_payee_seller")}</span></td>
                      <td>₹{p.amount}</td>
                      <td>{!p.has_account
                        ? <span className="badge amber">{t("adm_missing")}</span>
                        : p.verified
                          ? <span className="badge green">{t("adm_verified")}</span>
                          : <span className="badge amber">{t("adm_unverified")}</span>}</td>
                      <td>{p.payee_type === "transport"
                        ? <span className="badge grey">{t("adm_na")}</span>
                        : p.identity_verified
                          ? <span className="badge green">{t("adm_verified")}</span>
                          : <span className="badge amber">{t("adm_unverified")}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          {payouts.batches.length > 0 && (
            <>
              <h3 style={{ fontSize: 15 }}>{t("adm_recent_batches")}</h3>
              <table>
                <thead><tr><th>{t("adm_batch")}</th><th>{t("adm_payouts")}</th><th>{t("adm_total")}</th><th>{t("adm_when")}</th></tr></thead>
                <tbody>
                  {payouts.batches.map((b) => (
                    <tr key={b.public_id}>
                      <td>{b.public_id}</td>
                      <td>{b.payout_count}</td>
                      <td>₹{b.total_amount}</td>
                      <td className="muted">{b.created_at ? new Date(b.created_at).toLocaleString() : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}

      <h2>{t("adm_broadcast")}</h2>
      <div className="card">
        {annMsg && <div className="ok" style={{ marginBottom: 10 }}>{annMsg}</div>}
        <div className="row">
          <div style={{ flex: 2 }}>
            <label>{t("tm_meeting_title")}</label>
            <input value={ann.title} onChange={(e) => setA("title", e.target.value)}
                   placeholder={t("adm_ann_title_ph")} />
          </div>
          <div style={{ flex: 1 }}>
            <label>{t("adm_audience")}</label>
            <select value={ann.audience} onChange={(e) => setA("audience", e.target.value)}>
              <option value="all">{t("adm_aud_all")}</option>
              <option value="farmers">{t("adm_aud_farmers")}</option>
              <option value="buyers">{t("adm_aud_buyers")}</option>
              <option value="agents">{t("adm_aud_agents")}</option>
              <option value="couriers">{t("adm_aud_couriers")}</option>
              <option value="staff">{t("adm_aud_staff")}</option>
            </select>
          </div>
        </div>
        <label>{t("adm_message")}</label>
        <textarea rows={3} value={ann.body} onChange={(e) => setA("body", e.target.value)}
                  placeholder={t("adm_ann_body_ph")} />
        <div style={{ marginTop: 12 }}>
          <button disabled={!ann.title.trim() || !ann.body.trim()} onClick={sendAnnouncement}>
            {t("adm_send_announcement")}
          </button>
        </div>
      </div>

      <h2>{t("adm_price_feed")}</h2>
      <div className="card">
        <p className="muted" style={{ fontSize: 14, marginTop: 0 }}>
          {t("adm_price_feed_help")}
        </p>
        {priceStatus && (
          <div className="stat-strip" style={{ marginBottom: 10 }}>
            <div>{t("adm_feed")} <b>{priceStatus.configured ? t("adm_feed_live") : t("adm_feed_sample")}</b></div>
            <div><b>{priceStatus.row_count}</b> {t("adm_prices_word")}{priceStatus.stale_rows ? ` · ${priceStatus.stale_rows} ${t("adm_stale")}` : ""}</div>
            <div>{t("adm_last_refresh")} <b>{priceStatus.last_refresh_at ? new Date(priceStatus.last_refresh_at).toLocaleString() : t("adm_never")}</b></div>
            {priceStatus.feed_is_stale && (
              <div className="badge danger">{t("adm_feed_stale")} ({priceStatus.stale_after_hours}h+)</div>
            )}
          </div>
        )}
        {priceMsg && <div className="ok" style={{ marginBottom: 10 }}>{priceMsg}</div>}
        <button disabled={priceBusy} onClick={refreshPrices}>
          {priceBusy ? t("adm_refreshing") : t("adm_refresh_now")}
        </button>
      </div>

      <h2>{t("adm_scheduled_jobs")}</h2>
      <div className="card">
        <p className="muted" style={{ fontSize: 14, marginTop: 0 }}>
          {t("adm_sched_help")}
        </p>
        {schedMsg && <div className="ok" style={{ marginBottom: 10 }}>{schedMsg}</div>}
        <button disabled={schedBusy} onClick={runScheduler}>
          {schedBusy ? t("adm_running") : t("adm_run_sched_now")}
        </button>
      </div>

      <h2>{t("adm_kyc_queue")} {kyc.length > 0 && <span className="badge amber">{kyc.length}</span>}</h2>
      <p className="muted" style={{ fontSize: 13, marginTop: -8 }}>
        {t("adm_kyc_help")}
      </p>
      {kyc.length === 0 ? (
        <p className="muted">{t("adm_no_kyc")}</p>
      ) : (
        <div className="grid">
          {kyc.map((u) => (
            <div className="card" key={u.user_id}>
              <div className="between" style={{ gap: 8, flexWrap: "wrap" }}>
                <div>
                  <b>{u.name || "—"}</b>{" "}
                  <span className="badge grey">{tEnum(t, "role_", u.role || u.kind)}</span>
                  <div className="muted" style={{ fontSize: 13 }}>
                    {u.phone}{u.village ? ` · ${u.village}` : ""}{u.buyer_type ? ` · ${u.buyer_type}` : ""}
                  </div>
                  {(u.aadhaar_masked || u.pan_masked) && (
                    <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                      {u.aadhaar_masked ? `${t("pf_aadhaar")} ${u.aadhaar_masked}` : ""}
                      {u.aadhaar_masked && u.pan_masked ? " · " : ""}
                      {u.pan_masked ? `${t("pf_pan")} ${u.pan_masked}` : ""}
                    </div>
                  )}
                </div>
                <div className="row" style={{ gap: 6 }}>
                  <button className="green" style={{ padding: "4px 12px", fontSize: 13 }}
                          onClick={() => kycDecide(u.user_id, true)}>{t("adm_approve")}</button>
                  <button className="ghost" style={{ padding: "4px 12px", fontSize: 13 }}
                          onClick={() => kycDecide(u.user_id, false)}>{t("sp_reject")}</button>
                </div>
              </div>

              {u.business && (
                <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px dashed var(--line, #e5e7eb)" }}>
                  <div style={{ fontSize: 13 }}>
                    <b>{u.business.legal_name || t("adm_business")}</b>
                    {u.business.registration_number ? ` · ${t("adm_reg")} ${u.business.registration_number}` : ""}
                    {u.business.gst ? ` · ${t("adm_gst")} ${u.business.gst}` : ""}
                  </div>
                  {u.business.evidence && u.business.evidence.length > 0 ? (
                    <div className="row" style={{ gap: 10, marginTop: 6, flexWrap: "wrap" }}>
                      {u.business.evidence.map((d, i) => {
                        const href = absUrl(d.url || d.object_key);
                        const isImg = !/\.pdf($|\?)/i.test(d.url || d.object_key || "");
                        return (
                          <a key={i} href={href} target="_blank" rel="noopener noreferrer"
                             title="Business registration evidence — open full size"
                             style={{ display: "block", textAlign: "center", textDecoration: "none" }}>
                            {isImg ? (
                              <img src={href} alt={t("adm_reg_evidence_alt")}
                                   style={{ width: 120, height: 90, objectFit: "cover", borderRadius: 8,
                                            border: "1px solid var(--line, #e5e7eb)", background: "#f3f4f6" }} />
                            ) : (
                              <div style={{ width: 120, height: 90, borderRadius: 8, border: "1px solid var(--line, #e5e7eb)",
                                            display: "flex", alignItems: "center", justifyContent: "center",
                                            fontSize: 13, background: "#f3f4f6", color: "#374151" }}>📄 PDF</div>
                            )}
                            <div className="muted" style={{ fontSize: 11, marginTop: 3 }}>{t("adm_reg_evidence")}</div>
                          </a>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{t("adm_no_reg_evidence")}</div>
                  )}
                </div>
              )}

              {(u.id_documents && u.id_documents.length > 0) ? (
                <div className="row" style={{ gap: 10, marginTop: 10, flexWrap: "wrap" }}>
                  {u.id_documents.map((d, i) => {
                    const href = absUrl(d.url || d.object_key);
                    const isImg = !/\.pdf($|\?)/i.test(d.url || d.object_key || "");
                    return (
                      <a key={i} href={href} target="_blank" rel="noopener noreferrer"
                         title={`${(d.doc_type || "document").replace(/_/g, " ")} — open full size`}
                         style={{ display: "block", textAlign: "center", textDecoration: "none" }}>
                        {isImg ? (
                          <img src={href} alt={d.doc_type || "ID"}
                               style={{ width: 120, height: 90, objectFit: "cover", borderRadius: 8,
                                        border: "1px solid var(--line, #e5e7eb)", background: "#f3f4f6" }} />
                        ) : (
                          <div style={{ width: 120, height: 90, borderRadius: 8, border: "1px solid var(--line, #e5e7eb)",
                                        display: "flex", alignItems: "center", justifyContent: "center",
                                        fontSize: 13, background: "#f3f4f6", color: "#374151" }}>📄 PDF</div>
                        )}
                        <div className="muted" style={{ fontSize: 11, marginTop: 3 }}>
                          {(d.doc_type || "document").replace(/_/g, " ")}
                        </div>
                      </a>
                    );
                  })}
                </div>
              ) : (
                <div className="muted" style={{ fontSize: 13, marginTop: 10 }}>
                  {t("adm_no_id_doc")}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <h2>{t("adm_users")}</h2>
      <div className="card" style={{ marginBottom: 10 }}>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ flex: "2 1 220px" }}>
            <label>{t("adm_search_user")}</label>
            <input value={userQ} onChange={(e) => setUserQ(e.target.value)} placeholder={t("adm_search_user_ph")} />
          </div>
          <div style={{ flex: "1 1 160px" }}>
            <label>{t("role")}</label>
            <select value={userRole} onChange={(e) => setUserRole(e.target.value)}>
              <option value="">{t("adm_all_roles")}</option>
              {["farmer", "buyer_household", "buyer_business", "field_agent",
                "field_leader", "field_manager", "transport", "superadmin"]
                .map((r) => <option key={r} value={r}>{tEnum(t, "role_", r)}</option>)}
            </select>
          </div>
        </div>
      </div>
      {users.length === 0 ? (
        <p className="muted">{t("adm_no_users")}</p>
      ) : (
        <table>
          <thead>
            <tr><th>{t("name")}</th><th>{t("adm_phone")}</th><th>{t("role")}</th><th>{t("status")}</th>{me.role === "superadmin" && <th></th>}</tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.name || "—"}</td>
                <td>{u.phone}</td>
                <td>{tEnum(t, "role_", u.role)}</td>
                <td><span className={`badge ${u.status === "active" ? "" : "amber"}`}>{u.status === "active" ? t("adm_us_active") : t("adm_us_suspended")}</span></td>
                {me.role === "superadmin" && (
                  <td>
                    {u.status === "active" ? (
                      <button className="ghost" onClick={() => setUserStatus(u.id, "suspended")}>{t("adm_suspend")}</button>
                    ) : (
                      <button className="ghost" onClick={() => setUserStatus(u.id, "active")}>{t("adm_reactivate")}</button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2>{t("adm_transport_couriers")}</h2>
      <table>
        <thead>
          <tr><th>{t("name")}</th><th>{t("adm_code")}</th><th>{t("adm_areas")}</th><th>{t("adm_kyc")}</th><th>{t("adm_active_th")}</th><th></th></tr>
        </thead>
        <tbody>
          {carriers.map((c) => (
            <tr key={c.id}>
              <td>{c.name}</td>
              <td>{c.code}</td>
              <td className="muted">{(c.service_areas || []).join(", ") || "—"}</td>
              <td><span className={`badge ${c.kyc_status === "verified" ? "" : "amber"}`}>{tEnum(t, "cks_", c.kyc_status)}</span></td>
              <td>{c.active ? t("adm_yes") : t("adm_no_word")}</td>
              <td>
                {c.kyc_status !== "verified" && (
                  <button className="ghost" onClick={() => patchCarrier(c.id, { kyc_status: "verified" })}>{t("adm_verify")}</button>
                )}{" "}
                <button className="ghost" onClick={() => patchCarrier(c.id, { active: !c.active })}>
                  {c.active ? t("adm_suspend") : t("adm_enable")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="card" style={{ marginTop: 10 }}>
        <div className="row">
          <div style={{ flex: 2 }}><label>{t("adm_courier_name")}</label>
            <input value={newCarrier.name} onChange={(e) => setC("name", e.target.value)} /></div>
          <div style={{ flex: 1 }}><label>{t("adm_code")}</label>
            <input value={newCarrier.code} onChange={(e) => setC("code", e.target.value)} /></div>
          <div style={{ flex: 1 }}><label>{t("adm_phone")}</label>
            <input value={newCarrier.contact_phone} onChange={(e) => setC("contact_phone", e.target.value)} inputMode="numeric" /></div>
        </div>
        <div style={{ marginTop: 10 }}>
          <button disabled={!newCarrier.name || !newCarrier.code} onClick={onboardCarrier}>{t("adm_onboard_courier")}</button>
        </div>
      </div>

      {["field_manager", "superadmin"].includes(me?.role) && <WithdrawalsAdmin />}

      {["field_manager", "superadmin"].includes(me?.role) && <BarcodeTracking me={me} />}

      <ServiceAreasAdmin me={me} />

      {me?.role === "superadmin" && <PricingAdmin me={me} />}

      <CatalogManager me={me} />

      <h2>{t("adm_product_moq")}</h2>
      <table>
        <thead>
          <tr><th>{t("adm_product")}</th><th>{t("category_label")}</th><th>{t("adm_moq_kg")}</th><th></th></tr>
        </thead>
        <tbody>
          {commodities.map((c) => (
            <MoqRow key={c.id} c={c} onSave={saveMoq} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Local calendar-month window as {from, to} in YYYY-MM-DD (offset 0 = this month).
function monthRange(offset) {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth() + offset, 1);
  const last = new Date(now.getFullYear(), now.getMonth() + offset + 1, 0);
  const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return { from: fmt(first), to: fmt(last) };
}

function MoqRow({ c, onSave }) {
  const { t } = useI18n();
  const [val, setVal] = useState(c.min_order_qty);
  const changed = String(val) !== String(c.min_order_qty);
  return (
    <tr>
      <td>{c.name}</td>
      <td className="muted">{c.category}</td>
      <td>
        <div className="row" style={{ gap: 6, alignItems: "center" }}>
          <input value={val} onChange={(e) => setVal(e.target.value)} inputMode="decimal"
                 style={{ width: 90 }} />
          <span className="muted" style={{ fontSize: 13 }}>{c.unit || "kg"}</span>
        </div>
      </td>
      <td>
        <button className="ghost" disabled={!changed} onClick={() => onSave(c.id, val)}>{t("adm_save")}</button>
      </td>
    </tr>
  );
}

// Lightweight inline horizontal bar chart (no chart library).
function BarChart({ data, unit = "" }) {
  const max = Math.max(1, ...data.map((d) => d.value || 0));
  return (
    <div style={{ display: "grid", gap: 6 }}>
      {data.map((d) => (
        <div key={d.label} className="row" style={{ gap: 8, alignItems: "center" }}>
          <span className="muted" style={{ width: 110, fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.label}</span>
          <div style={{ flex: 1, background: "var(--line, #e5e7eb)", borderRadius: 4, height: 14, minWidth: 40 }}>
            <div style={{ width: `${Math.round((d.value / max) * 100)}%`, background: "var(--green-600, #16a34a)", height: "100%", borderRadius: 4 }} />
          </div>
          <span style={{ width: 72, textAlign: "right", fontSize: 12 }}>{unit}{d.value}</span>
        </div>
      ))}
    </div>
  );
}

// Finance: farmer withdrawal requests — approve (disburses their accrued payouts)
// or reject.
function WithdrawalsAdmin() {
  const { t } = useI18n();
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  function load() { api("/admin/withdrawals?status=requested").then(setRows).catch(() => {}); }
  useEffect(() => { load(); }, []);

  async function decide(id, approve) {
    setErr(null); setMsg(null);
    let reason;
    if (!approve) { reason = window.prompt(t("adm_wd_reject_prompt")) || ""; }
    try {
      const r = await api(`/admin/withdrawals/${id}/decision`, { method: "POST", body: { approve, reason } });
      setMsg(approve ? `${t("adm_paid_out")} ${r.batch}, ₹${r.amount}).` : t("adm_withdrawal_rejected"));
      load();
    } catch (e) { setErr(e.message); }
  }

  return (
    <>
      <h2>{t("adm_withdrawal_requests")} {rows.length > 0 && <span className="badge amber">{rows.length}</span>}</h2>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok">{msg}</div>}
      {rows.length === 0 ? (
        <p className="muted">{t("adm_no_withdrawals")}</p>
      ) : (
        <div className="card">
          {rows.map((w) => (
            <div key={w.id} className="between" style={{ padding: "10px 0", borderBottom: "1px solid var(--line)", gap: 8, flexWrap: "wrap" }}>
              <div>
                <b>{w.farmer_name || `${t("adm_user")} ${w.farmer_id}`}</b> — ₹{w.amount}
                <div className="muted" style={{ fontSize: 13 }}>
                  {w.method || "—"} {w.account_masked || ""} · {t("adm_requested")} {w.created_at ? new Date(w.created_at).toLocaleDateString("en-IN") : ""}
                </div>
              </div>
              <div className="row" style={{ gap: 6 }}>
                <button onClick={() => decide(w.id, true)}>{t("adm_approve_pay")}</button>
                <button className="ghost" onClick={() => decide(w.id, false)}>{t("sp_reject")}</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

// SuperAdmin / manager barcode tracking: live counts, search by code with full
// scan timeline, and manual status correction (superadmin only).
const BAG_STATUSES = ["created", "picked_up", "at_collection", "in_transit", "delivered"];

function BarcodeTracking({ me }) {
  const { t } = useI18n();
  const [stats, setStats] = useState(null);
  const [q, setQ] = useState("");
  const [bag, setBag] = useState(null);
  const [recent, setRecent] = useState([]);
  const [live, setLive] = useState([]);
  const [err, setErr] = useState(null);
  const isSuper = me?.role === "superadmin";

  function loadStats() { api("/bags/stats").then(setStats).catch(() => {}); }
  function loadRecent() { api("/bags?limit=25").then(setRecent).catch(() => {}); }
  function loadLive() { api("/bags/live").then(setLive).catch(() => {}); }
  useEffect(() => { loadStats(); loadRecent(); loadLive(); }, []);

  const LIVE_COLOR = { in_transit: "#16a34a", at_collection: "#2563eb", picked_up: "#f59e0b" };

  async function search(code) {
    setErr(null); setBag(null);
    const c = (code || "").trim();
    if (!c) return;
    try { setBag(await api(`/bags/${encodeURIComponent(c)}`)); }
    catch (e) { setErr(e.message); }
  }
  async function correct(code, to_status) {
    const reason = window.prompt(`${t("adm_correct_prompt_pre")} ${code} ${t("adm_correct_prompt_mid")} "${to_status}"?`);
    if (!reason || !reason.trim()) return;
    try {
      await api(`/bags/${encodeURIComponent(code)}/correct`, { method: "POST", body: { to_status, reason: reason.trim() } });
      search(code); loadStats(); loadRecent();
    } catch (e) { setErr(e.message); }
  }

  const TILE = ({ label, val }) => (
    <div className="card" style={{ minWidth: 120 }}>
      <div className="muted" style={{ fontSize: 12 }}>{label}</div>
      <div className="price" style={{ fontSize: 22 }}>{val ?? "—"}</div>
    </div>
  );

  return (
    <>
      <h2>{t("adm_barcode_tracking")}</h2>
      {err && <div className="error">{err}</div>}
      <div className="grid">
        <TILE label={t("adm_scanned_today")} val={stats?.scanned_today} />
        <TILE label={t("adm_in_transit")} val={stats?.in_transit} />
        <TILE label={t("adm_at_collection")} val={stats?.at_collection} />
        <TILE label={t("adm_delivered")} val={stats?.delivered} />
        <TILE label={t("adm_total_bags")} val={stats?.total} />
      </div>
      {stats && stats.total > 0 && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>{t("adm_bags_by_status")}</h3>
          <BarChart data={[
            { label: t("adm_created"), value: stats.created }, { label: t("adm_picked_up"), value: stats.picked_up },
            { label: t("adm_at_collection"), value: stats.at_collection }, { label: t("adm_in_transit"), value: stats.in_transit },
            { label: t("adm_delivered"), value: stats.delivered },
          ]} />
        </div>
      )}
      {live.length > 0 && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>{t("adm_live_map")} — {live.length} {t("adm_bags_in_transit")}</h3>
          <MapView points={live.map((b) => ({
            lat: b.lat, lng: b.lng, label: `${b.bag_code} — ${b.status_label}`,
            color: LIVE_COLOR[b.status] || "#6b7280",
          }))} />
        </div>
      )}

      <div className="card">
        <label>{t("adm_find_bag")}</label>
        <div className="row" style={{ gap: 6 }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="AGRI-1023-BAG-01"
                 style={{ flex: 1 }} onKeyDown={(e) => e.key === "Enter" && search(q)} />
          <button onClick={() => search(q)}>{t("search")}</button>
        </div>
        {bag && (
          <div style={{ marginTop: 12 }}>
            <div className="between">
              <b>{bag.bag_code}</b>
              <span className="badge">{bag.status_label}</span>
            </div>
            <div className="muted" style={{ fontSize: 13 }}>{t("iv_col_order")} {bag.order_public_id} · {t("bg_bag").toLowerCase()} {bag.bag_no}{bag.weight ? ` · ${bag.weight} kg` : ""}</div>
            <table style={{ marginTop: 8 }}>
              <thead><tr><th>{t("sc_stage")}</th><th>{t("status")}</th><th>{t("adm_by_th")}</th><th>{t("adm_when")}</th><th>{t("adm_gps")}</th></tr></thead>
              <tbody>
                {bag.scans.map((s) => (
                  <tr key={s.id}>
                    <td>{tEnum(t, "sc_stage_", s.stage)}{s.corrected ? " ✏️" : ""}</td>
                    <td>{s.status_label}</td>
                    <td className="muted">{s.scanned_by_name || "—"}{s.role ? ` (${tEnum(t, "role_", s.role)})` : ""}</td>
                    <td className="muted">{s.created_at ? new Date(s.created_at).toLocaleString("en-IN") : "—"}</td>
                    <td className="muted">{s.lat != null ? `${s.lat.toFixed(3)}, ${s.lng?.toFixed(3)}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {isSuper && (
              <div className="row" style={{ gap: 6, marginTop: 8, flexWrap: "wrap" }}>
                <span className="muted" style={{ alignSelf: "center", fontSize: 13 }}>{t("adm_correct_to")}</span>
                {BAG_STATUSES.map((st) => (
                  <button key={st} className="ghost" style={{ fontSize: 12 }}
                          disabled={st === bag.status} onClick={() => correct(bag.bag_code, st)}>{st}</button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {recent.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>{t("bg_bag")}</th><th>{t("status")}</th><th>{t("adm_last_scan")}</th></tr></thead>
            <tbody>
              {recent.map((b) => (
                <tr key={b.id} style={{ cursor: "pointer" }} onClick={() => { setQ(b.bag_code); search(b.bag_code); }}>
                  <td style={{ fontFamily: "monospace" }}>{b.bag_code}</td>
                  <td><span className={`badge ${b.status === "delivered" ? "green" : b.status === "in_transit" ? "amber" : "grey"}`}>{b.status_label}</span></td>
                  <td className="muted">{b.last_scan_at ? new Date(b.last_scan_at).toLocaleString("en-IN") : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

// Delivery coverage: states → districts → mandals with a serviceable toggle, an
// add-mandal form, and a one-click "Add Hyderabad metro" preset (superadmin).
function ServiceAreasAdmin({ me }) {
  const { t } = useI18n();
  const [states, setStates] = useState([]);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ state: "Telangana", district: "", name: "", latitude: "", longitude: "" });
  const isSuper = me?.role === "superadmin";

  function load() { api("/admin/service-areas").then(setStates).catch((e) => setErr(e.message)); }
  useEffect(() => { load(); }, []);

  async function toggle(m) {
    setErr(null);
    try { await api(`/admin/service-areas/mandal/${m.id}`, { method: "PATCH", body: { serviceable: !m.serviceable } }); load(); }
    catch (e) { setErr(e.message); }
  }
  async function addHyderabad() {
    setErr(null); setMsg(null); setBusy(true);
    try {
      const r = await api("/admin/service-areas/preset/hyderabad", { method: "POST" });
      setMsg(`${t("adm_hyd_added")} (${r.added} ${t("adm_new_of")} ${r.total}).`); load();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }
  async function launchHyderabadOnly() {
    if (!confirm(t("adm_launch_confirm"))) return;
    setErr(null); setMsg(null); setBusy(true);
    try {
      const r = await api("/admin/service-areas/preset/launch", { method: "POST" });
      setMsg(`${t("adm_launch_set")} (${r.hyderabad_active} ${t("adm_mandals_word")}), ${r.regions_loaded} ${t("adm_regions_loaded")}, ${r.deactivated} ${t("adm_deactivated")}`);
      load();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }
  async function openAllRegions() {
    if (!confirm(t("adm_open_all_confirm"))) return;
    setErr(null); setMsg(null); setBusy(true);
    try {
      const r = await api("/admin/service-areas/preset/open-all", { method: "POST" });
      setMsg(`${t("adm_open_all_done")} (${r.activated} ${t("adm_mandals_word")}${r.flipped_on ? ` · +${r.flipped_on}` : ""})`);
      load();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }
  async function addMandal(e) {
    e.preventDefault(); setErr(null); setMsg(null);
    if (!form.state.trim() || !form.district.trim() || !form.name.trim()) return;
    setBusy(true);
    try {
      await api("/admin/service-areas/mandal", { method: "POST", body: {
        state: form.state.trim(), district: form.district.trim(), name: form.name.trim(),
        latitude: form.latitude ? Number(form.latitude) : null,
        longitude: form.longitude ? Number(form.longitude) : null, serviceable: true } });
      setForm((f) => ({ ...f, name: "", latitude: "", longitude: "" }));
      setMsg(t("adm_mandal_saved")); load();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }
  const setF = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <>
      <h2>{t("adm_service_areas")}</h2>
      <p className="muted" style={{ fontSize: 14, marginTop: -8 }}>
        {t("adm_service_areas_help")}
      </p>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok">{msg}</div>}

      {isSuper && (
        <div className="card" style={{ marginBottom: 10, borderLeft: "4px solid var(--green-600, #16a34a)" }}>
          <div className="between" style={{ flexWrap: "wrap", gap: 10 }}>
            <div>
              <b>{t("adm_launch_hyd")}</b>
              <div className="muted" style={{ fontSize: 13, maxWidth: 520 }}>
                {t("adm_launch_hyd_help")}
              </div>
            </div>
            <button disabled={busy} onClick={launchHyderabadOnly}>{t("adm_set_hyd_launch")}</button>
          </div>
          <div className="row" style={{ gap: 8, marginTop: 10, flexWrap: "wrap" }}>
            <button className="ghost" disabled={busy} onClick={addHyderabad}>{t("adm_add_hyd_metro")}</button>
            <button disabled={busy} onClick={openAllRegions}>{t("adm_open_all")}</button>
          </div>
          <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>{t("adm_open_all_help")}</div>
        </div>
      )}

      {states.map((s) => (
        <div className="card" key={s.id} style={{ marginBottom: 10 }}>
          <div className="between">
            <b>{s.name} <span className="muted" style={{ fontWeight: 400 }}>({s.code})</span></b>
            <span className="badge grey">{s.serviceable_count} {t("adm_serviceable")}</span>
          </div>
          {s.districts.map((d) => (
            <div key={d.id} style={{ marginTop: 8 }}>
              <div className="muted" style={{ fontSize: 13, marginBottom: 4 }}>{d.name}</div>
              <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                {d.mandals.map((m) => (
                  <button key={m.id} type="button"
                          onClick={() => isSuper && toggle(m)}
                          disabled={!isSuper}
                          title={m.latitude == null ? "No coordinates — add them so distance works" : ""}
                          className={`badge ${m.serviceable ? "green" : "amber"}`}
                          style={{ cursor: isSuper ? "pointer" : "default", border: "none" }}>
                    {m.serviceable ? "✓ " : "✕ "}{m.name}{m.latitude == null ? " ⚠" : ""}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      ))}

      {isSuper && (
        <form className="card" onSubmit={addMandal}>
          <b>{t("adm_add_mandal")}</b>
          <div className="form-grid" style={{ marginTop: 8 }}>
            <label>{t("ob_state")}
              <input value={form.state} onChange={(e) => setF("state", e.target.value)} list="sa-states" />
              <datalist id="sa-states">{states.map((s) => <option key={s.id} value={s.name} />)}</datalist>
            </label>
            <label>{t("ob_district")}
              <input value={form.district} onChange={(e) => setF("district", e.target.value)} />
            </label>
            <label>{t("adm_mandal_area")}
              <input value={form.name} onChange={(e) => setF("name", e.target.value)} />
            </label>
            <label>{t("adm_latitude")}
              <input value={form.latitude} onChange={(e) => setF("latitude", e.target.value)} inputMode="decimal" placeholder="17.49" />
            </label>
            <label>{t("adm_longitude")}
              <input value={form.longitude} onChange={(e) => setF("longitude", e.target.value)} inputMode="decimal" placeholder="78.39" />
            </label>
          </div>
          <button type="submit" disabled={busy || !form.name.trim()} style={{ marginTop: 10 }}>{t("adm_add_serviceable")}</button>
        </form>
      )}
    </>
  );
}

// Superadmin pricing: transport (buyer-paid, by km + weight) + agent commission
// (seller-paid, % of value). Draft -> simulate -> publish; versions are
// immutable and a confirmed order keeps the version it was priced on.
function PricingAdmin() {
  const { t } = useI18n();
  const [rules, setRules] = useState([]);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    rate_per_km: "", rate_per_kg: "", fixed_pickup_fee: "", min_transport_charge: "",
    max_transport_charge: "", seller_commission_pct: "", inspection_fee: "", packing_fee: "",
    service_fee_pct: "", service_fee_flat: "", service_fee_payer: "buyer", tax_pct: "", reason: "",
  });
  const [sim, setSim] = useState({ product_value: "10000", billable_kg: "100", route_km: "20" });
  const [simOut, setSimOut] = useState(null);

  const num = (v) => (v === "" || v == null ? 0 : Number(v));
  function load() { api("/pricing/rules").then(setRules).catch((e) => setErr(e.message)); }
  useEffect(() => { load(); }, []);
  const published = rules.find((r) => r.status === "published");
  const setF = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function saveDraft(e) {
    e.preventDefault(); setErr(null); setMsg(null); setBusy(true);
    try {
      const body = {
        rate_per_km: num(form.rate_per_km), rate_per_kg: num(form.rate_per_kg),
        fixed_pickup_fee: num(form.fixed_pickup_fee), min_transport_charge: num(form.min_transport_charge),
        max_transport_charge: form.max_transport_charge === "" ? null : num(form.max_transport_charge),
        seller_commission_pct: num(form.seller_commission_pct),
        inspection_fee: num(form.inspection_fee), packing_fee: num(form.packing_fee),
        service_fee_pct: num(form.service_fee_pct), service_fee_flat: num(form.service_fee_flat),
        service_fee_payer: form.service_fee_payer, tax_pct: num(form.tax_pct), reason: form.reason || null,
      };
      const ve = pricingError(body, t);
      if (ve) { setErr(ve); setBusy(false); return; }
      const r = await api("/admin/pricing-rules/draft", { method: "POST", body });
      setMsg(`${t("adm_draft_saved_pre")}${r.version} ${t("adm_draft_saved_post")}`); load();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }
  async function simulate(ruleId) {
    setErr(null);
    try {
      setSimOut(await api(`/admin/pricing-rules/${ruleId}/simulate`, { method: "POST", body: {
        product_value: num(sim.product_value), billable_kg: num(sim.billable_kg), route_km: num(sim.route_km) } }));
    } catch (e) { setErr(e.message); }
  }
  async function publish(ruleId) {
    if (!confirm(t("adm_publish_confirm"))) return;
    setErr(null); setMsg(null); setBusy(true);
    try { await api(`/admin/pricing-rules/${ruleId}/publish`, { method: "POST" }); setMsg(t("adm_published_live")); load(); }
    catch (e) { setErr(e.message); } finally { setBusy(false); }
  }
  function prefill(r) {
    setForm({
      rate_per_km: r.rate_per_km, rate_per_kg: r.rate_per_kg, fixed_pickup_fee: r.fixed_pickup_fee,
      min_transport_charge: r.min_transport_charge, max_transport_charge: r.max_transport_charge ?? "",
      seller_commission_pct: r.seller_commission_pct, inspection_fee: r.inspection_fee, packing_fee: r.packing_fee,
      service_fee_pct: r.service_fee_pct, service_fee_flat: r.service_fee_flat,
      service_fee_payer: r.service_fee_payer, tax_pct: r.tax_pct, reason: "",
    });
  }
  // One-click GST preset: clone the live rule into the draft form and set tax to
  // 18%, then let the superadmin review + Save draft + Publish as usual (so the
  // audit, versioning and CA check on the taxable base all stay intact).
  function gstPreset() {
    const b = published || {};
    setErr(null);
    setForm((f) => ({
      ...f,
      rate_per_km: b.rate_per_km ?? f.rate_per_km,
      rate_per_kg: b.rate_per_kg ?? f.rate_per_kg,
      fixed_pickup_fee: b.fixed_pickup_fee ?? f.fixed_pickup_fee,
      min_transport_charge: b.min_transport_charge ?? f.min_transport_charge,
      max_transport_charge: b.max_transport_charge ?? "",
      seller_commission_pct: b.seller_commission_pct ?? f.seller_commission_pct,
      inspection_fee: b.inspection_fee ?? f.inspection_fee,
      packing_fee: b.packing_fee ?? f.packing_fee,
      service_fee_pct: b.service_fee_pct ?? f.service_fee_pct,
      service_fee_flat: b.service_fee_flat ?? f.service_fee_flat,
      service_fee_payer: b.service_fee_payer ?? f.service_fee_payer,
      tax_pct: 18,
      reason: t("adm_gst_preset_reason"),
    }));
    setMsg(t("adm_gst_preset_msg"));
  }

  const F = ({ k, label, step = "0.01" }) => (
    <label>{label}
      <input value={form[k]} onChange={(e) => setF(k, e.target.value)} inputMode="decimal" step={step} placeholder="0" />
    </label>
  );

  return (
    <>
      <h2>{t("adm_pricing_title")}</h2>
      <p className="muted" style={{ fontSize: 14, marginTop: -8, maxWidth: 640 }}>
        {t("adm_pricing_help")}
      </p>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok">{msg}</div>}

      {published && (
        <div className="card" style={{ marginBottom: 10, borderLeft: "4px solid var(--green-600)" }}>
          <b>{t("adm_live_now")} — v{published.version}</b>
          <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
            {t("adm_transport_label")} ₹{published.rate_per_km}/km · ₹{published.rate_per_kg}/kg · {t("adm_pickup")} ₹{published.fixed_pickup_fee}
            · {t("adm_min")} ₹{published.min_transport_charge}{published.max_transport_charge ? ` · ${t("adm_max")} ₹${published.max_transport_charge}` : ""}
            <br />{t("adm_seller_commission")} {published.seller_commission_pct}% · {t("adm_inspection")} ₹{published.inspection_fee} · {t("adm_packing")} ₹{published.packing_fee} · {t("adm_tax")} {published.tax_pct}%
          </div>
          <button className="ghost" style={{ marginTop: 8 }} onClick={() => prefill(published)}>{t("adm_edit_copy")}</button>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "0 0 10px" }}>
        <button type="button" className="ghost" onClick={gstPreset}>{t("adm_gst_preset_btn")}</button>
      </div>

      <form onSubmit={saveDraft} className="card">
        <b>{t("adm_new_pricing_version")}</b>
        <div className="form-grid" style={{ marginTop: 8 }}>
          <F k="rate_per_km" label={t("adm_f_rate_km")} />
          <F k="rate_per_kg" label={t("adm_f_rate_kg")} />
          <F k="fixed_pickup_fee" label={t("adm_f_pickup")} />
          <F k="min_transport_charge" label={t("adm_f_min_transport")} />
          <F k="max_transport_charge" label={t("adm_f_max_transport")} />
          <F k="seller_commission_pct" label={t("adm_f_seller_comm")} step="0.001" />
          <F k="inspection_fee" label={t("adm_f_inspection")} />
          <F k="packing_fee" label={t("adm_f_packing")} />
          <F k="service_fee_pct" label={t("adm_f_service_pct")} step="0.001" />
          <F k="service_fee_flat" label={t("adm_f_service_flat")} />
          <label>{t("adm_svc_payer")}
            <select value={form.service_fee_payer} onChange={(e) => setF("service_fee_payer", e.target.value)}>
              <option value="buyer">{t("adm_payer_buyer")}</option><option value="seller">{t("adm_payer_seller")}</option>
            </select>
          </label>
          <F k="tax_pct" label={t("adm_f_tax")} step="0.001" />
        </div>
        <label>{t("adm_reason_note")}<input value={form.reason} onChange={(e) => setF("reason", e.target.value)} placeholder={t("adm_reason_ph")} /></label>
        <button disabled={busy} style={{ marginTop: 10 }}>{t("adm_save_draft")}</button>
      </form>

      {/* Simulate a quote against any rule */}
      <div className="card" style={{ marginTop: 10 }}>
        <b>{t("adm_simulate_quote")}</b>
        <div className="form-grid" style={{ marginTop: 8 }}>
          <label>{t("adm_produce_value")}<input value={sim.product_value} onChange={(e) => setSim((s) => ({ ...s, product_value: e.target.value }))} inputMode="decimal" /></label>
          <label>{t("adm_weight_kg")}<input value={sim.billable_kg} onChange={(e) => setSim((s) => ({ ...s, billable_kg: e.target.value }))} inputMode="decimal" /></label>
          <label>{t("adm_distance_km")}<input value={sim.route_km} onChange={(e) => setSim((s) => ({ ...s, route_km: e.target.value }))} inputMode="decimal" /></label>
        </div>
        {simOut && (
          <div className="muted" style={{ fontSize: 14, marginTop: 8 }}>
            {t("adm_transport_buyer")} <b>₹{simOut.transport_charge}</b> · {t("adm_commission_seller")} <b>₹{simOut.seller_commission}</b>
            {" · "}{t("adm_buyer_pays")} <b>₹{simOut.buyer_total}</b> · {t("adm_seller_receives")} <b>₹{simOut.seller_payable}</b>
          </div>
        )}
      </div>

      <div className="table-wrap" style={{ marginTop: 10 }}>
        <table>
          <thead><tr><th>{t("adm_ver")}</th><th>{t("status")}</th><th>{t("adm_th_per_km")}</th><th>{t("adm_th_per_kg")}</th><th>{t("adm_pickup_th")}</th><th>{t("adm_comm_th")}</th><th></th></tr></thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.id}>
                <td>v{r.version}</td>
                <td><span className={`badge ${r.status === "published" ? "green" : r.status === "draft" ? "amber" : "grey"}`}>{t("prs_" + r.status) || r.status}</span></td>
                <td>₹{r.rate_per_km}</td><td>₹{r.rate_per_kg}</td><td>₹{r.fixed_pickup_fee}</td><td>{r.seller_commission_pct}%</td>
                <td>
                  <button className="ghost" style={{ padding: "4px 10px", fontSize: 13 }} onClick={() => simulate(r.id)}>{t("adm_simulate")}</button>
                  {r.status === "draft" && (
                    <button style={{ padding: "4px 10px", fontSize: 13, marginLeft: 6 }} disabled={busy} onClick={() => publish(r.id)}>{t("adm_publish")}</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// Staff catalogue management: add products (any staff) and the removal flow
// (leader/manager request -> superadmin approve/reject/restore).
const CAT_OPTS = ["vegetable", "fruit", "cereal", "pulse", "oilseed", "spice", "dairy_meat", "other"];

function CatalogManager({ me }) {
  const { t } = useI18n();
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ name: "", category: "vegetable", name_te: "", unit: "kg" });
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const isSuper = me?.role === "superadmin";

  function load() { api("/catalog/commodities/manage").then(setRows).catch((e) => setErr(e.message)); }
  useEffect(() => { load(); }, []);

  async function add(e) {
    e.preventDefault(); setErr(null); setMsg(null);
    if (!form.name.trim()) return;
    setBusy(true);
    try {
      await api("/catalog/commodities", { method: "POST", body: {
        name: form.name.trim(), category: form.category,
        name_te: form.name_te.trim() || undefined, unit: form.unit } });
      setForm({ name: "", category: form.category, name_te: "", unit: "kg" });
      setMsg(t("adm_product_saved")); load();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }
  async function act(path, body) {
    setErr(null);
    try { await api(path, { method: "POST", body }); load(); } catch (e) { setErr(e.message); }
  }
  function requestDel(c) {
    const reason = window.prompt(`${t("adm_removal_prompt_pre")} "${c.name}" ${t("adm_removal_prompt_post")}`);
    if (reason && reason.trim()) act(`/catalog/commodities/${c.id}/request-deletion`, { reason: reason.trim() });
  }

  const pending = rows.filter((r) => r.pending_deletion);

  return (
    <>
      <h2>{t("adm_catalogue")}</h2>
      <p className="muted" style={{ fontSize: 14, marginTop: -8 }}>
        {t("adm_catalogue_help")}
      </p>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok">{msg}</div>}

      <form className="card" onSubmit={add}>
        <div className="form-grid">
          <label>{t("ag_product_name")}
            <input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          </label>
          <label>{t("category_label")}
            <select value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}>
              {CAT_OPTS.map((c) => <option key={c} value={c}>{t("cat_" + c)}</option>)}
            </select>
          </label>
          <label>{t("ag_telugu_name")}
            <input value={form.name_te} onChange={(e) => setForm((f) => ({ ...f, name_te: e.target.value }))} />
          </label>
          <label>{t("ag_unit")}
            <select value={form.unit} onChange={(e) => setForm((f) => ({ ...f, unit: e.target.value }))}>
              <option value="kg">kg</option>
              <option value="piece">piece</option>
              <option value="dozen">dozen</option>
              <option value="litre">litre</option>
            </select>
          </label>
        </div>
        <button type="submit" disabled={busy || !form.name.trim()} style={{ marginTop: 10 }}>{t("ag_add_product")}</button>
      </form>

      {isSuper && pending.length > 0 && (
        <div className="card" style={{ borderLeft: "4px solid var(--amber-600)" }}>
          <h3 style={{ marginTop: 0 }}>{t("adm_removal_requests")} ({pending.length})</h3>
          {pending.map((c) => (
            <div key={c.id} className="between" style={{ padding: "8px 0", borderBottom: "1px solid var(--line)", gap: 8, flexWrap: "wrap" }}>
              <div>
                <b>{c.name}</b> <span className="muted">· {c.category}</span>
                <div className="muted" style={{ fontSize: 13 }}>
                  “{c.deletion_reason}” — {t("adm_requested_by")} {c.deletion_requested_by_name || "—"}
                  {c.listing_count > 0 && <span className="badge amber" style={{ marginLeft: 6 }}>{c.listing_count} {t("adm_listings_use")}</span>}
                </div>
              </div>
              <div className="row" style={{ gap: 6 }}>
                <button onClick={() => act(`/catalog/commodities/${c.id}/deletion-decision`, { approve: true })}>{t("adm_approve_removal")}</button>
                <button className="ghost" onClick={() => act(`/catalog/commodities/${c.id}/deletion-decision`, { approve: false })}>{t("sp_reject")}</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>{t("adm_product")}</th><th>{t("category_label")}</th><th>{t("status")}</th><th>{t("adm_listings")}</th><th></th></tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id} style={{ opacity: c.active ? 1 : 0.6 }}>
                <td>{c.name}</td>
                <td className="muted">{c.category}</td>
                <td>
                  {!c.active ? <span className="badge grey">{t("adm_removed")}</span>
                    : c.pending_deletion ? <span className="badge amber" title={c.deletion_reason}>{t("adm_removal_requested")}</span>
                    : <span className="badge green">{t("adm_active_status")}</span>}
                </td>
                <td className="muted">{c.listing_count}</td>
                <td>
                  {c.active && !c.pending_deletion && (
                    <button className="ghost" onClick={() => requestDel(c)}>{t("adm_request_removal")}</button>
                  )}
                  {c.pending_deletion && !isSuper && <span className="muted" style={{ fontSize: 12 }}>{t("adm_awaiting_super")}</span>}
                  {c.pending_deletion && isSuper && (
                    <span className="row" style={{ gap: 6 }}>
                      <button onClick={() => act(`/catalog/commodities/${c.id}/deletion-decision`, { approve: true })}>{t("adm_approve")}</button>
                      <button className="ghost" onClick={() => act(`/catalog/commodities/${c.id}/deletion-decision`, { approve: false })}>{t("sp_reject")}</button>
                    </span>
                  )}
                  {!c.active && isSuper && (
                    <button className="ghost" onClick={() => act(`/catalog/commodities/${c.id}/restore`)}>{t("adm_restore")}</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
