import Link from "next/link";
import { useEffect, useState } from "react";

import MapView from "../components/MapView";
import { api, downloadCsv, getUser } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

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
        `Batch ${r.batch}: disbursed ₹${r.total_amount} across ${r.payout_count} payout(s).`
        + (r.held_unverified ? ` ${r.held_unverified} held (unverified account).` : "")
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
      setPayoutMsg(approve ? "Payout account verified." : "Payout account rejected.");
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
      setAnnMsg(`Sent to ${r.sent} ${r.audience === "all" ? "users" : r.audience}.`);
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
        setPriceMsg("Live feed not configured — set PRICES_PROVIDER=data_gov_in and DATA_GOV_IN_API_KEY. Still serving seeded sample prices.");
      } else if (r.ok === false) {
        setErr(r.message || "Price feed error.");
      } else {
        setPriceMsg(`Refreshed from ${r.source}: ${r.upserted} price(s) updated (${r.new} new)${r.as_of ? `, as of ${r.as_of}` : ""}.`);
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
      setSchedMsg(`Ran ${new Date(r.ran_at).toLocaleTimeString()}: ${r.digests_sent} digest(s) sent, ${r.prices_refreshed || 0} market price(s) refreshed, ${r.meeting_reminders || 0} meeting reminder(s) sent.`);
    } catch (e) {
      setErr(e.message);
    } finally {
      setSchedBusy(false);
    }
  }

  async function kycDecide(userId, approve) {
    setErr(null);
    try {
      await api(`/admin/kyc/${userId}/decision`, { method: "POST", body: { approve } });
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
    load();
    loadPayouts();
    loadUsers();
    loadPriceStatus();
  }, []);

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
    try {
      const r = await api("/admin/pricing-rules/draft", { method: "POST", body: body() });
      setLastDraftId(r.id);
      load();
    } catch (e) {
      setErr(e.message);
    }
  }
  async function simulate() {
    setErr(null);
    if (!lastDraftId) return setErr("Create a draft first.");
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
    if (!lastDraftId) return setErr("Create a draft first.");
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
            ["Orders", kpis.total_orders],
            ["Settled", kpis.settled_orders],
            ["Cancelled", kpis.cancelled_orders],
            ["Open listings", kpis.open_listings],
            ["GMV (settled)", `₹${kpis.gmv_settled}`],
          ].map(([label, val]) => (
            <div className="card" key={label}>
              <div className="muted" style={{ fontSize: 13 }}>{label}</div>
              <div className="price" style={{ fontSize: 24 }}>{val}</div>
            </div>
          ))}
      </div>

      <h2>Ledger</h2>
      {ledger && (
        <div className="card">
          <div className="between">
            <b>Balance check</b>
            <span className={`badge ${ledger.balanced ? "" : "amber"}`}>
              {ledger.balanced ? "balanced ✓" : "UNBALANCED"}
            </span>
          </div>
          {Object.entries(ledger.accounts).map(([acct, bal]) => (
            <div className="quote-line" key={acct}>
              <span>{acct.replace(/_/g, " ")}</span><span>₹{bal}</span>
            </div>
          ))}
        </div>
      )}

      <h2>Pricing rules</h2>
      <table>
        <thead>
          <tr><th>v</th><th>Status</th><th>Scope</th><th>₹/kg</th><th>₹/km</th><th>Comm %</th><th>Svc %</th></tr>
        </thead>
        <tbody>
          {rules.map((r) => (
            <tr key={r.id}>
              <td>{r.version}</td>
              <td><span className={`badge ${r.status === "published" ? "" : "grey"}`}>{r.status}</span></td>
              <td>{r.handling_class || "all"}</td>
              <td>{r.rate_per_kg}</td>
              <td>{r.rate_per_km}</td>
              <td>{r.seller_commission_pct}</td>
              <td>{r.service_fee_pct}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>New pricing rule</h2>
      <div className="card">
        <div className="row">
          {[
            ["rate_per_kg", "₹/kg"],
            ["rate_per_km", "₹/km"],
            ["min_transport_charge", "Min transport ₹"],
            ["seller_commission_pct", "Seller commission %"],
            ["service_fee_pct", "Buyer service fee %"],
            ["inspection_fee", "Inspection ₹"],
            ["packing_fee", "Packing ₹"],
          ].map(([k, label]) => (
            <div key={k} style={{ flex: "1 1 120px" }}>
              <label>{label}</label>
              <input value={draft[k]} onChange={(e) => set(k, e.target.value)} inputMode="decimal" />
            </div>
          ))}
        </div>
        <label>Reason</label>
        <input value={draft.reason} onChange={(e) => set("reason", e.target.value)} />
        <div className="row" style={{ marginTop: 16 }}>
          <button onClick={createDraft}>Create draft</button>
          <button className="ghost" onClick={simulate} disabled={!lastDraftId}>Simulate</button>
          <button className="amber" onClick={publish} disabled={!lastDraftId}>Publish</button>
        </div>
        {sim && (
          <div className="ok" style={{ marginTop: 14 }}>
            Simulated on 500 kg · 40 km · ₹12,000 → buyer pays <b>₹{sim.buyer_total}</b>
            {" "}(transport ₹{sim.transport_charge}, service ₹{sim.service_fee})
            {sim.seller_commission !== undefined && <> · seller commission ₹{sim.seller_commission}</>}
          </div>
        )}
      </div>

      <h2>Reporting period</h2>
      <div className="card">
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ flex: "0 0 auto" }}>
            <label>From</label>
            <input type="date" value={range.from} onChange={(e) => setRange((r) => ({ ...r, from: e.target.value }))} />
          </div>
          <div style={{ flex: "0 0 auto" }}>
            <label>To</label>
            <input type="date" value={range.to} onChange={(e) => setRange((r) => ({ ...r, to: e.target.value }))} />
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button className="ghost" onClick={() => setRange(monthRange(0))}>This month</button>
            <button className="ghost" onClick={() => setRange(monthRange(-1))}>Last month</button>
            <button className="ghost" onClick={() => setRange({ from: "", to: "" })}>All time</button>
          </div>
        </div>
        <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>
          {range.from || range.to ? `Showing ${range.from || "start"} → ${range.to || "today"}` : "Showing all time"}
          {" "}· applies to GMV and operations reports below.
        </div>
      </div>

      {reports && (
        <>
          <div className="between">
            <h2>Reports — GMV ₹{reports.total_gmv} · {reports.total_orders} orders</h2>
            <button className="ghost" onClick={() =>
              downloadCsv(`/admin/reports.csv${rangeQS()}`, "agrisetu-gmv-report.csv").catch((e) => setErr(e.message))}>
              ⬇ Download CSV
            </button>
          </div>
          <div className="grid">
            {[["By commodity", reports.by_commodity], ["By state", reports.by_state],
              ["By mandal", reports.by_mandal], ["By agent", reports.by_agent]].map(([title, rows]) => (
              <div className="card" key={title}>
                <h3 style={{ fontSize: 15 }}>{title}</h3>
                {rows.length === 0 ? <p className="muted">No data.</p> : (
                  <>
                    <BarChart unit="₹" data={rows.slice(0, 8).map((r) => ({ label: r.key, value: Number(r.gmv) }))} />
                    <table style={{ marginTop: 8 }}>
                      <thead><tr><th></th><th>GMV</th><th>Orders</th></tr></thead>
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
            <h2>Operations scorecard</h2>
            <button className="ghost" onClick={() =>
              downloadCsv(`/admin/ops-report.csv${rangeQS()}`, "agrisetu-ops-report.csv").catch((e) => setErr(e.message))}>
              ⬇ Download CSV
            </button>
          </div>

          <div className="grid">
            <div className="card">
              <h3 style={{ fontSize: 15 }}>Disputes</h3>
              <div className="quote-line"><span>Total</span><span>{ops.disputes.total}</span></div>
              <div className="quote-line"><span>Open</span><span>{ops.disputes.open}</span></div>
              <div className="quote-line"><span>Decided</span><span>{ops.disputes.decided}</span></div>
              <div className="quote-line">
                <span>Dispute rate</span>
                <span className={ops.disputes.dispute_rate_pct > 10 ? "badge amber" : ""}>{ops.disputes.dispute_rate_pct}%</span>
              </div>
              {Object.entries(ops.disputes.by_outcome).map(([k, v]) => (
                <div className="quote-line" key={k}>
                  <span className="muted">{k.replace(/_/g, " ")}</span><span className="muted">{v}</span>
                </div>
              ))}
            </div>
            <div className="card">
              <h3 style={{ fontSize: 15 }}>Payouts</h3>
              <div className="quote-line"><span>Pending</span><span>₹{ops.payouts.pending_total} · {ops.payouts.pending_count}</span></div>
              <div className="quote-line"><span>Processed</span><span>₹{ops.payouts.processed_total} · {ops.payouts.processed_count}</span></div>
              <div className="quote-line"><span>Batches run</span><span>{ops.payouts.batches}</span></div>
            </div>
          </div>

          <h3 style={{ fontSize: 15 }}>Field agents</h3>
          {ops.agents.length === 0 ? <p className="muted">No agent activity yet.</p> : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Agent</th><th>Inspections</th><th>Pass</th><th>Hold</th><th>Fail</th><th>Pass rate</th><th>Orders</th><th>Advisories</th></tr></thead>
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

          <h3 style={{ fontSize: 15 }}>Couriers</h3>
          {ops.couriers.length === 0 ? <p className="muted">No shipments yet.</p> : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Courier</th><th>Shipments</th><th>Delivered</th><th>Active</th><th>Failed</th><th>Completion</th><th>Avg transit</th></tr></thead>
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
          <h2>Payout accounts <span className="badge amber">{payoutAccts.length} to verify</span></h2>
          <p className="muted" style={{ fontSize: 13, marginTop: -8 }}>
            Partners are paid only after their UPI/bank account is verified. Check the details against the partner, then approve or reject.
          </p>
          <div className="card">
            <table>
              <thead><tr><th>Partner</th><th>Role</th><th>Method</th><th>Details</th><th>Action</th></tr></thead>
              <tbody>
                {payoutAccts.map((a) => (
                  <tr key={a.user_id}>
                    <td>{a.name}{a.phone ? <div className="muted" style={{ fontSize: 12 }}>{a.phone}</div> : null}</td>
                    <td><span className="badge grey">{(a.role || "").replace(/_/g, " ")}</span></td>
                    <td>{a.method === "upi" ? "UPI" : "Bank"}</td>
                    <td className="muted" style={{ fontSize: 13 }}>
                      {a.method === "upi"
                        ? a.upi_id
                        : `${a.account_name || "—"} · ${a.account_number_masked || "—"} · ${a.ifsc || "—"}`}
                    </td>
                    <td>
                      <div className="row" style={{ gap: 6 }}>
                        <button className="green" style={{ padding: "4px 10px", fontSize: 13 }}
                                onClick={() => verifyPayoutAccount(a.user_id, true)}>Verify</button>
                        <button className="ghost" style={{ padding: "4px 10px", fontSize: 13 }}
                                onClick={() => verifyPayoutAccount(a.user_id, false)}>Reject</button>
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
          <h2>Payouts {payouts.pending_count > 0 && <span className="badge amber">{payouts.pending_count} pending</span>}</h2>
          {payoutMsg && <div className="ok">{payoutMsg}</div>}
          {payouts.missing_payout_accounts > 0 && (
            <div className="error" style={{ marginBottom: 10 }}>
              ⚠ {payouts.missing_payout_accounts} pending payee(s) have no UPI/bank details on file — they can&apos;t be paid until they add them in their profile.
            </div>
          )}
          {payouts.blocked_unverified > 0 && (
            <div className="error" style={{ marginBottom: 10 }}>
              ⚠ {payouts.blocked_unverified} pending payout(s) are held — the payee&apos;s account is not verified yet. Verify it above to release it.
            </div>
          )}
          <div className="card">
            <div className="between">
              <div>
                <b>₹{payouts.pending_total}</b> accrued across {payouts.pending_count} payout(s)
                <div className="muted" style={{ fontSize: 13 }}>Settled orders accrue seller + transport payouts here until a disbursement batch runs.</div>
              </div>
              <button className="amber" disabled={payouts.pending_count === 0} onClick={runPayoutBatch}>
                Run payout batch
              </button>
            </div>
            {payouts.pending.length > 0 && (
              <table>
                <thead><tr><th>Order</th><th>Payee</th><th>Type</th><th>Amount</th><th>Account</th></tr></thead>
                <tbody>
                  {payouts.pending.map((p) => (
                    <tr key={p.id}>
                      <td>{p.order || "—"}</td><td>{p.seller}</td>
                      <td><span className="badge grey">{p.payee_type || "seller"}</span></td>
                      <td>₹{p.amount}</td>
                      <td>{!p.has_account
                        ? <span className="badge amber">missing</span>
                        : p.verified
                          ? <span className="badge green">verified</span>
                          : <span className="badge amber">unverified</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          {payouts.batches.length > 0 && (
            <>
              <h3 style={{ fontSize: 15 }}>Recent batches</h3>
              <table>
                <thead><tr><th>Batch</th><th>Payouts</th><th>Total</th><th>When</th></tr></thead>
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

      <h2>Broadcast announcement</h2>
      <div className="card">
        {annMsg && <div className="ok" style={{ marginBottom: 10 }}>{annMsg}</div>}
        <div className="row">
          <div style={{ flex: 2 }}>
            <label>Title</label>
            <input value={ann.title} onChange={(e) => setA("title", e.target.value)}
                   placeholder="e.g. Market holiday on Sunday" />
          </div>
          <div style={{ flex: 1 }}>
            <label>Audience</label>
            <select value={ann.audience} onChange={(e) => setA("audience", e.target.value)}>
              <option value="all">Everyone</option>
              <option value="farmers">Farmers</option>
              <option value="buyers">Buyers</option>
              <option value="agents">Field agents</option>
              <option value="couriers">Couriers</option>
              <option value="staff">Staff</option>
            </select>
          </div>
        </div>
        <label>Message</label>
        <textarea rows={3} value={ann.body} onChange={(e) => setA("body", e.target.value)}
                  placeholder="This appears as an in-app alert for the chosen audience." />
        <div style={{ marginTop: 12 }}>
          <button disabled={!ann.title.trim() || !ann.body.trim()} onClick={sendAnnouncement}>
            Send announcement
          </button>
        </div>
      </div>

      <h2>Market price feed</h2>
      <div className="card">
        <p className="muted" style={{ fontSize: 14, marginTop: 0 }}>
          Pulls today&apos;s government-declared mandi prices (data.gov.in / AGMARKNET)
          and updates the all-India price screen. Requires a data.gov.in API key in
          the backend config; until then the app serves the seeded sample prices.
        </p>
        {priceStatus && (
          <div className="stat-strip" style={{ marginBottom: 10 }}>
            <div>Feed: <b>{priceStatus.configured ? "live (data.gov.in)" : "sample"}</b></div>
            <div><b>{priceStatus.row_count}</b> prices{priceStatus.stale_rows ? ` · ${priceStatus.stale_rows} stale` : ""}</div>
            <div>Last refresh: <b>{priceStatus.last_refresh_at ? new Date(priceStatus.last_refresh_at).toLocaleString() : "never"}</b></div>
            {priceStatus.feed_is_stale && (
              <div className="badge danger">⚠ feed stale ({priceStatus.stale_after_hours}h+)</div>
            )}
          </div>
        )}
        {priceMsg && <div className="ok" style={{ marginBottom: 10 }}>{priceMsg}</div>}
        <button disabled={priceBusy} onClick={refreshPrices}>
          {priceBusy ? "Refreshing…" : "Refresh prices now"}
        </button>
      </div>

      <h2>Scheduled jobs</h2>
      <div className="card">
        <p className="muted" style={{ fontSize: 14, marginTop: 0 }}>
          Compiles each user&apos;s batched alerts into a daily-digest push, refreshes
          live market prices (if the feed is configured) and sends team-meeting
          reminders — the sandboxed job a timer (or cron) runs automatically.
          Trigger it here to see it work now.
        </p>
        {schedMsg && <div className="ok" style={{ marginBottom: 10 }}>{schedMsg}</div>}
        <button disabled={schedBusy} onClick={runScheduler}>
          {schedBusy ? "Running…" : "Run scheduled jobs now"}
        </button>
      </div>

      <h2>KYC approval queue {kyc.length > 0 && <span className="badge amber">{kyc.length}</span>}</h2>
      {kyc.length === 0 ? (
        <p className="muted">No pending verifications.</p>
      ) : (
        <table>
          <thead>
            <tr><th>Name</th><th>Phone</th><th>Role</th><th>Details</th><th></th></tr>
          </thead>
          <tbody>
            {kyc.map((u) => (
              <tr key={u.user_id}>
                <td>{u.name || "—"}</td>
                <td>{u.phone}</td>
                <td>{u.kind}</td>
                <td className="muted">{u.village || u.buyer_type || ""}</td>
                <td>
                  <button className="ghost" onClick={() => kycDecide(u.user_id, true)}>Approve</button>{" "}
                  <button className="ghost" onClick={() => kycDecide(u.user_id, false)}>Reject</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2>Users</h2>
      <div className="card" style={{ marginBottom: 10 }}>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ flex: "2 1 220px" }}>
            <label>Search name or phone</label>
            <input value={userQ} onChange={(e) => setUserQ(e.target.value)} placeholder="e.g. Ravi or 9190…" />
          </div>
          <div style={{ flex: "1 1 160px" }}>
            <label>Role</label>
            <select value={userRole} onChange={(e) => setUserRole(e.target.value)}>
              <option value="">All roles</option>
              {["farmer", "buyer_household", "buyer_business", "field_agent",
                "field_leader", "field_manager", "transport", "superadmin"]
                .map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
        </div>
      </div>
      {users.length === 0 ? (
        <p className="muted">No users match.</p>
      ) : (
        <table>
          <thead>
            <tr><th>Name</th><th>Phone</th><th>Role</th><th>Status</th>{me.role === "superadmin" && <th></th>}</tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.name || "—"}</td>
                <td>{u.phone}</td>
                <td>{u.role}</td>
                <td><span className={`badge ${u.status === "active" ? "" : "amber"}`}>{u.status}</span></td>
                {me.role === "superadmin" && (
                  <td>
                    {u.status === "active" ? (
                      <button className="ghost" onClick={() => setUserStatus(u.id, "suspended")}>Suspend</button>
                    ) : (
                      <button className="ghost" onClick={() => setUserStatus(u.id, "active")}>Reactivate</button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2>Transport couriers</h2>
      <table>
        <thead>
          <tr><th>Name</th><th>Code</th><th>Areas</th><th>KYC</th><th>Active</th><th></th></tr>
        </thead>
        <tbody>
          {carriers.map((c) => (
            <tr key={c.id}>
              <td>{c.name}</td>
              <td>{c.code}</td>
              <td className="muted">{(c.service_areas || []).join(", ") || "—"}</td>
              <td><span className={`badge ${c.kyc_status === "verified" ? "" : "amber"}`}>{c.kyc_status}</span></td>
              <td>{c.active ? "yes" : "no"}</td>
              <td>
                {c.kyc_status !== "verified" && (
                  <button className="ghost" onClick={() => patchCarrier(c.id, { kyc_status: "verified" })}>Verify</button>
                )}{" "}
                <button className="ghost" onClick={() => patchCarrier(c.id, { active: !c.active })}>
                  {c.active ? "Suspend" : "Enable"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="card" style={{ marginTop: 10 }}>
        <div className="row">
          <div style={{ flex: 2 }}><label>Courier name</label>
            <input value={newCarrier.name} onChange={(e) => setC("name", e.target.value)} /></div>
          <div style={{ flex: 1 }}><label>Code</label>
            <input value={newCarrier.code} onChange={(e) => setC("code", e.target.value)} /></div>
          <div style={{ flex: 1 }}><label>Phone</label>
            <input value={newCarrier.contact_phone} onChange={(e) => setC("contact_phone", e.target.value)} inputMode="numeric" /></div>
        </div>
        <div style={{ marginTop: 10 }}>
          <button disabled={!newCarrier.name || !newCarrier.code} onClick={onboardCarrier}>Onboard courier</button>
        </div>
      </div>

      {["field_manager", "superadmin"].includes(me?.role) && <WithdrawalsAdmin />}

      {["field_manager", "superadmin"].includes(me?.role) && <BarcodeTracking me={me} />}

      <CatalogManager me={me} />

      <h2>Product minimum order quantities</h2>
      <table>
        <thead>
          <tr><th>Product</th><th>Category</th><th>MOQ ({"kg"})</th><th></th></tr>
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
  const [val, setVal] = useState(c.min_order_qty);
  const changed = String(val) !== String(c.min_order_qty);
  return (
    <tr>
      <td>{c.name}</td>
      <td className="muted">{c.category}</td>
      <td>
        <input value={val} onChange={(e) => setVal(e.target.value)} inputMode="decimal"
               style={{ width: 90 }} />
      </td>
      <td>
        <button className="ghost" disabled={!changed} onClick={() => onSave(c.id, val)}>Save</button>
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
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  function load() { api("/admin/withdrawals?status=requested").then(setRows).catch(() => {}); }
  useEffect(() => { load(); }, []);

  async function decide(id, approve) {
    setErr(null); setMsg(null);
    let reason;
    if (!approve) { reason = window.prompt("Reason for rejecting this withdrawal?") || ""; }
    try {
      const r = await api(`/admin/withdrawals/${id}/decision`, { method: "POST", body: { approve, reason } });
      setMsg(approve ? `Paid out (batch ${r.batch}, ₹${r.amount}).` : "Withdrawal rejected.");
      load();
    } catch (e) { setErr(e.message); }
  }

  return (
    <>
      <h2>Withdrawal requests {rows.length > 0 && <span className="badge amber">{rows.length}</span>}</h2>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok">{msg}</div>}
      {rows.length === 0 ? (
        <p className="muted">No pending withdrawal requests.</p>
      ) : (
        <div className="card">
          {rows.map((w) => (
            <div key={w.id} className="between" style={{ padding: "10px 0", borderBottom: "1px solid var(--line)", gap: 8, flexWrap: "wrap" }}>
              <div>
                <b>{w.farmer_name || `User ${w.farmer_id}`}</b> — ₹{w.amount}
                <div className="muted" style={{ fontSize: 13 }}>
                  {w.method || "—"} {w.account_masked || ""} · requested {w.created_at ? new Date(w.created_at).toLocaleDateString("en-IN") : ""}
                </div>
              </div>
              <div className="row" style={{ gap: 6 }}>
                <button onClick={() => decide(w.id, true)}>Approve &amp; pay</button>
                <button className="ghost" onClick={() => decide(w.id, false)}>Reject</button>
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
    const reason = window.prompt(`Reason for correcting ${code} to "${to_status}"?`);
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
      <h2>Barcode / live tracking</h2>
      {err && <div className="error">{err}</div>}
      <div className="grid">
        <TILE label="Scanned today" val={stats?.scanned_today} />
        <TILE label="In transit" val={stats?.in_transit} />
        <TILE label="At collection" val={stats?.at_collection} />
        <TILE label="Delivered" val={stats?.delivered} />
        <TILE label="Total bags" val={stats?.total} />
      </div>
      {stats && stats.total > 0 && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Bags by status</h3>
          <BarChart data={[
            { label: "Created", value: stats.created }, { label: "Picked up", value: stats.picked_up },
            { label: "At collection", value: stats.at_collection }, { label: "In transit", value: stats.in_transit },
            { label: "Delivered", value: stats.delivered },
          ]} />
        </div>
      )}
      {live.length > 0 && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Live map — {live.length} bag(s) in transit</h3>
          <MapView points={live.map((b) => ({
            lat: b.lat, lng: b.lng, label: `${b.bag_code} — ${b.status_label}`,
            color: LIVE_COLOR[b.status] || "#6b7280",
          }))} />
        </div>
      )}

      <div className="card">
        <label>Find a bag (by barcode)</label>
        <div className="row" style={{ gap: 6 }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="AGRI-1023-BAG-01"
                 style={{ flex: 1 }} onKeyDown={(e) => e.key === "Enter" && search(q)} />
          <button onClick={() => search(q)}>Search</button>
        </div>
        {bag && (
          <div style={{ marginTop: 12 }}>
            <div className="between">
              <b>{bag.bag_code}</b>
              <span className="badge">{bag.status_label}</span>
            </div>
            <div className="muted" style={{ fontSize: 13 }}>Order {bag.order_public_id} · bag {bag.bag_no}{bag.weight ? ` · ${bag.weight} kg` : ""}</div>
            <table style={{ marginTop: 8 }}>
              <thead><tr><th>Stage</th><th>Status</th><th>By</th><th>When</th><th>GPS</th></tr></thead>
              <tbody>
                {bag.scans.map((s) => (
                  <tr key={s.id}>
                    <td>{s.stage}{s.corrected ? " ✏️" : ""}</td>
                    <td>{s.status_label}</td>
                    <td className="muted">{s.scanned_by_name || "—"}{s.role ? ` (${s.role.replace(/_/g, " ")})` : ""}</td>
                    <td className="muted">{s.created_at ? new Date(s.created_at).toLocaleString("en-IN") : "—"}</td>
                    <td className="muted">{s.lat != null ? `${s.lat.toFixed(3)}, ${s.lng?.toFixed(3)}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {isSuper && (
              <div className="row" style={{ gap: 6, marginTop: 8, flexWrap: "wrap" }}>
                <span className="muted" style={{ alignSelf: "center", fontSize: 13 }}>Correct to:</span>
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
            <thead><tr><th>Bag</th><th>Status</th><th>Last scan</th></tr></thead>
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

// Staff catalogue management: add products (any staff) and the removal flow
// (leader/manager request -> superadmin approve/reject/restore).
const CAT_OPTS = ["vegetable", "fruit", "cereal", "pulse", "oilseed", "spice", "dairy_meat", "other"];

function CatalogManager({ me }) {
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
      setMsg("Product saved to the catalogue."); load();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }
  async function act(path, body) {
    setErr(null);
    try { await api(path, { method: "POST", body }); load(); } catch (e) { setErr(e.message); }
  }
  function requestDel(c) {
    const reason = window.prompt(`Why should "${c.name}" be removed from the list?`);
    if (reason && reason.trim()) act(`/catalog/commodities/${c.id}/request-deletion`, { reason: reason.trim() });
  }

  const pending = rows.filter((r) => r.pending_deletion);

  return (
    <>
      <h2>Catalogue / products</h2>
      <p className="muted" style={{ fontSize: 14, marginTop: -8 }}>
        Add products so farmers and buyers can list or request them. To remove one,
        a field leader/manager requests it and the superadmin approves.
      </p>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok">{msg}</div>}

      <form className="card" onSubmit={add}>
        <div className="form-grid">
          <label>Product name
            <input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          </label>
          <label>Category
            <select value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}>
              {CAT_OPTS.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <label>Telugu name (optional)
            <input value={form.name_te} onChange={(e) => setForm((f) => ({ ...f, name_te: e.target.value }))} />
          </label>
          <label>Unit
            <select value={form.unit} onChange={(e) => setForm((f) => ({ ...f, unit: e.target.value }))}>
              <option value="kg">kg</option>
              <option value="piece">piece</option>
              <option value="dozen">dozen</option>
              <option value="litre">litre</option>
            </select>
          </label>
        </div>
        <button type="submit" disabled={busy || !form.name.trim()} style={{ marginTop: 10 }}>Add product</button>
      </form>

      {isSuper && pending.length > 0 && (
        <div className="card" style={{ borderLeft: "4px solid var(--amber-600)" }}>
          <h3 style={{ marginTop: 0 }}>Removal requests awaiting your approval ({pending.length})</h3>
          {pending.map((c) => (
            <div key={c.id} className="between" style={{ padding: "8px 0", borderBottom: "1px solid var(--line)", gap: 8, flexWrap: "wrap" }}>
              <div>
                <b>{c.name}</b> <span className="muted">· {c.category}</span>
                <div className="muted" style={{ fontSize: 13 }}>
                  “{c.deletion_reason}” — requested by {c.deletion_requested_by_name || "—"}
                  {c.listing_count > 0 && <span className="badge amber" style={{ marginLeft: 6 }}>{c.listing_count} listings use it</span>}
                </div>
              </div>
              <div className="row" style={{ gap: 6 }}>
                <button onClick={() => act(`/catalog/commodities/${c.id}/deletion-decision`, { approve: true })}>Approve removal</button>
                <button className="ghost" onClick={() => act(`/catalog/commodities/${c.id}/deletion-decision`, { approve: false })}>Reject</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Product</th><th>Category</th><th>Status</th><th>Listings</th><th></th></tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id} style={{ opacity: c.active ? 1 : 0.6 }}>
                <td>{c.name}</td>
                <td className="muted">{c.category}</td>
                <td>
                  {!c.active ? <span className="badge grey">removed</span>
                    : c.pending_deletion ? <span className="badge amber" title={c.deletion_reason}>removal requested</span>
                    : <span className="badge green">active</span>}
                </td>
                <td className="muted">{c.listing_count}</td>
                <td>
                  {c.active && !c.pending_deletion && (
                    <button className="ghost" onClick={() => requestDel(c)}>Request removal</button>
                  )}
                  {c.pending_deletion && !isSuper && <span className="muted" style={{ fontSize: 12 }}>awaiting superadmin</span>}
                  {c.pending_deletion && isSuper && (
                    <span className="row" style={{ gap: 6 }}>
                      <button onClick={() => act(`/catalog/commodities/${c.id}/deletion-decision`, { approve: true })}>Approve</button>
                      <button className="ghost" onClick={() => act(`/catalog/commodities/${c.id}/deletion-decision`, { approve: false })}>Reject</button>
                    </span>
                  )}
                  {!c.active && isSuper && (
                    <button className="ghost" onClick={() => act(`/catalog/commodities/${c.id}/restore`)}>Restore</button>
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
