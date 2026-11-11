import Link from "next/link";
import { useEffect, useState } from "react";

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
  const [payouts, setPayouts] = useState(null);
  const [payoutMsg, setPayoutMsg] = useState(null);
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
  }

  async function runPayoutBatch() {
    setErr(null);
    setPayoutMsg(null);
    try {
      const r = await api("/admin/payouts/run", { method: "POST", body: {} });
      setPayoutMsg(`Batch ${r.batch}: disbursed ₹${r.total_amount} across ${r.payout_count} payout(s).`);
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
      setSchedMsg(`Ran ${new Date(r.ran_at).toLocaleTimeString()}: ${r.digests_sent} digest(s) sent, ${r.prices_refreshed || 0} market price(s) refreshed.`);
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

  useEffect(() => {
    setMe(getUser());
    load();
    loadPayouts();
    loadUsers();
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
                  <table>
                    <thead><tr><th></th><th>GMV</th><th>Orders</th></tr></thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr key={r.key}><td>{r.key}</td><td>₹{r.gmv}</td><td>{r.orders}</td></tr>
                      ))}
                    </tbody>
                  </table>
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

      {payouts && (
        <>
          <h2>Seller payouts {payouts.pending_count > 0 && <span className="badge amber">{payouts.pending_count} pending</span>}</h2>
          {payoutMsg && <div className="ok">{payoutMsg}</div>}
          <div className="card">
            <div className="between">
              <div>
                <b>₹{payouts.pending_total}</b> accrued across {payouts.pending_count} payout(s)
                <div className="muted" style={{ fontSize: 13 }}>Settled orders accrue here until a disbursement batch runs.</div>
              </div>
              <button className="amber" disabled={payouts.pending_count === 0} onClick={runPayoutBatch}>
                Run payout batch
              </button>
            </div>
            {payouts.pending.length > 0 && (
              <table>
                <thead><tr><th>Order</th><th>Seller</th><th>Amount</th></tr></thead>
                <tbody>
                  {payouts.pending.map((p) => (
                    <tr key={p.id}><td>{p.order || "—"}</td><td>{p.seller}</td><td>₹{p.amount}</td></tr>
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
        {priceMsg && <div className="ok" style={{ marginBottom: 10 }}>{priceMsg}</div>}
        <button disabled={priceBusy} onClick={refreshPrices}>
          {priceBusy ? "Refreshing…" : "Refresh prices now"}
        </button>
      </div>

      <h2>Scheduled jobs</h2>
      <div className="card">
        <p className="muted" style={{ fontSize: 14, marginTop: 0 }}>
          Compiles each user&apos;s batched alerts into a daily-digest push and raises
          due advisory follow-up reminders — the sandboxed job a timer (or cron)
          runs automatically. Trigger it here to see it work now.
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
              {["farmer", "fpo", "buyer_household", "buyer_business", "field_agent",
                "agronomist", "transport", "support", "mandal_manager", "finance", "superadmin"]
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
