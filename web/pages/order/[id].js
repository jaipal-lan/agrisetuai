import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, getUser } from "../../lib/api";
import { useI18n } from "../../lib/i18n";

function Quote({ q }) {
  if (!q) return null;
  const line = (label, val) => (
    <div className="quote-line"><span>{label}</span><span>₹{val}</span></div>
  );
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3>Itemised quote (rule v{q.rule_version})</h3>
      {line("Product value", q.product_value)}
      {line("Packing", q.packing_fee)}
      {line("Inspection", q.inspection_fee)}
      {line(q.route_km_source ? `Transport (${q.route_km_source} distance)` : "Transport", q.transport_charge)}
      {Number(q.service_fee) > 0 && line(`Service fee (${q.service_fee_payer})`, q.service_fee)}
      {Number(q.tax) > 0 && line("Tax", q.tax)}
      <div className="quote-line total"><span>Buyer pays</span><span>₹{q.buyer_total}</span></div>
      {q.seller_commission !== undefined && (
        <div className="quote-line">
          <span className="muted">Seller commission ({q.seller_commission_pct}%)</span>
          <span className="muted">− ₹{q.seller_commission}</span>
        </div>
      )}
      <div className="quote-line"><span className="muted">Seller receives</span><span className="muted">₹{q.seller_payable}</span></div>
    </div>
  );
}

function Certificate({ orderId }) {
  const [cert, setCert] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    api(`/orders/${orderId}/certificate`)
      .then(setCert)
      .catch((e) => setErr(e.status === 409 ? null : e.message));
  }, [orderId]);
  if (err) return null;
  if (!cert) return null;
  const m = cert.measured || {};
  return (
    <div className="card" style={{ marginTop: 16, borderLeft: "4px solid var(--green-600)" }}>
      <div className="between">
        <h3>✅ AgriSetu Verified Lot</h3>
        <span className="pill-tag">{cert.certificate_id}</span>
      </div>
      <div style={{ fontSize: 14 }}>
        <b>{cert.product?.commodity}</b>
        {cert.product?.grade ? ` · ${cert.product.grade}` : ""}
        {cert.product?.claim_status ? ` · ${cert.product.claim_status}` : ""}
      </div>
      <div className="quote-line"><span>Observed outcome</span><span>{(cert.observed?.outcome || "").replace(/_/g, " ")}</span></div>
      {m.net_qty_kg && <div className="quote-line"><span>Measured net weight</span><span>{m.net_qty_kg} kg</span></div>}
      {m.gross_weight_kg && <div className="quote-line"><span>Gross / tare</span><span>{m.gross_weight_kg} / {m.tare_weight_kg || 0} kg</span></div>}
      {m.moisture_pct != null && <div className="quote-line"><span>Moisture</span><span>{m.moisture_pct}%</span></div>}
      {cert.lot && <div className="quote-line"><span>Lot / seal</span><span>{cert.lot.public_id}</span></div>}
      <div className="quote-line"><span className="muted">Inspected</span><span className="muted">{cert.inspected_at ? new Date(cert.inspected_at).toLocaleString() : ""}</span></div>
      <div className="disclaimer">{cert.not_tested_note}</div>
    </div>
  );
}

export default function OrderDetail() {
  const { t } = useI18n();
  const router = useRouter();
  const { id } = router.query;
  const [me, setMe] = useState(null);
  const [order, setOrder] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [agentId, setAgentId] = useState("3");
  const [routeKm, setRouteKm] = useState("");
  const [gross, setGross] = useState("");
  const [outcome, setOutcome] = useState("pass");

  useEffect(() => {
    setMe(getUser());
  }, []);

  async function load() {
    try {
      setOrder(await api(`/orders/${id}`));
    } catch (e) {
      setErr(e.message);
    }
  }
  useEffect(() => {
    if (id) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function act(path, body, headers) {
    setErr(null);
    setBusy(true);
    try {
      await api(path, { method: "POST", body, headers });
      await load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function openDispute() {
    const description = window.prompt("Describe the problem (quality, quantity, delivery…)");
    if (!description) return;
    setErr(null);
    setBusy(true);
    try {
      await api("/disputes", {
        method: "POST",
        body: { order_id: Number(id), issue_type: "quality", description },
      });
      await load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (err && !order) return <div className="error">{err}</div>;
  if (!order || !me) return <p className="muted">{t("loading")}</p>;

  const s = order.status;
  const role = me.role;
  const isBuyer = me.id === order.buyer_id;
  const isStaff = ["superadmin", "mandal_manager", "finance"].includes(role);
  const isAgent = ["field_agent", "mandal_manager", "superadmin"].includes(role);
  const isTransport = ["transport", "mandal_manager", "superadmin"].includes(role);

  const Action = ({ children }) => (
    <div className="card" style={{ marginTop: 16, borderLeft: "4px solid var(--green-600)" }}>{children}</div>
  );

  return (
    <div style={{ maxWidth: 620 }}>
      <button className="ghost" onClick={() => router.push("/orders")}>← {t("my_orders")}</button>
      <h1 style={{ marginTop: 14 }}>{order.public_id}</h1>
      <span className="badge">{s.replace(/_/g, " ")}</span>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="between">
          <div><b>₹{order.accepted_terms.price_per_unit}</b>/kg</div>
          <div>{order.accepted_terms.quantity} {order.accepted_terms.unit}</div>
        </div>
      </div>

      <Quote q={order.quote} />
      <Certificate orderId={id} />

      {err && <div className="error">{err}</div>}

      {/* Staff: assign inspection */}
      {isStaff && s === "provisional_agreement" && (
        <Action>
          <h3>Assign inspection</h3>
          <label>Field agent user id</label>
          <input value={agentId} onChange={(e) => setAgentId(e.target.value)} inputMode="numeric" />
          <div style={{ marginTop: 12 }}>
            <button disabled={busy} onClick={() => act(`/orders/${id}/assign-inspection`, { agent_id: Number(agentId) })}>
              Assign
            </button>
          </div>
        </Action>
      )}

      {/* Agent: submit inspection */}
      {isAgent && ["inspection_assigned", "inspection_in_progress", "inspection_hold"].includes(s) && (
        <Action>
          <h3>Inspection</h3>
          <div className="row">
            <div style={{ flex: 1 }}>
              <label>Gross weight (kg)</label>
              <input value={gross} onChange={(e) => setGross(e.target.value)} inputMode="decimal" />
            </div>
            <div style={{ flex: 1 }}>
              <label>Outcome</label>
              <select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
                <option value="pass">Pass</option>
                <option value="pass_with_adjustment">Pass with adjustment</option>
                <option value="hold">Hold</option>
                <option value="fail">Fail</option>
              </select>
            </div>
          </div>
          <div style={{ marginTop: 12 }}>
            <button
              disabled={busy}
              onClick={() =>
                act(`/agent/orders/${id}/inspection`, {
                  gross_weight: gross ? Number(gross) : undefined,
                  tare_weight: 0,
                  outcome,
                })
              }
            >
              Submit inspection
            </button>
          </div>
        </Action>
      )}

      {/* Buyer: approve inspection */}
      {isBuyer && s === "buyer_approval_pending" && (
        <Action>
          <h3>Review inspection & approve</h3>
          <button disabled={busy} onClick={() => act(`/orders/${id}/buyer-approve`)}>Approve</button>
        </Action>
      )}

      {/* Buyer: lock quote */}
      {isBuyer && s === "confirmed" && (
        <Action>
          <h3>Confirm quote</h3>
          <label>Route distance (km) — leave blank to compute from mandal location</label>
          <input value={routeKm} onChange={(e) => setRouteKm(e.target.value)} inputMode="decimal"
                 placeholder="auto" />
          <div style={{ marginTop: 12 }}>
            <button
              disabled={busy}
              onClick={() =>
                act(`/orders/${id}/confirm-quote`,
                    routeKm.trim() === "" ? {} : { route_km: Number(routeKm) })
              }
            >
              Lock quote
            </button>
          </div>
        </Action>
      )}

      {/* Buyer: pay */}
      {isBuyer && s === "payment_pending" && (
        <Action>
          <h3>Pay ₹{order.buyer_total}</h3>
          <p className="muted" style={{ fontSize: 13 }}>Mock payment in dev. Posts the double-entry ledger.</p>
          <button disabled={busy} onClick={() => act(`/orders/${id}/pay`, undefined, { "Idempotency-Key": order.public_id })}>
            Pay now
          </button>
        </Action>
      )}

      {/* Agent/staff: packing */}
      {isAgent && s === "paid" && (
        <Action>
          <h3>Packing</h3>
          <button disabled={busy} onClick={() => act(`/orders/${id}/packing-complete`)}>Seal lot & complete packing</button>
        </Action>
      )}

      {/* Transport: shipment milestones */}
      {isTransport && ["ready_for_pickup", "picked_up", "in_transit", "out_for_delivery"].includes(s) && (
        <Action>
          <h3>Shipment</h3>
          <div className="row">
            {[
              ["ready_for_pickup", "picked_up", "Mark picked up"],
              ["picked_up", "in_transit", "Mark in transit"],
              ["in_transit", "out_for_delivery", "Out for delivery"],
              ["out_for_delivery", "delivered", "Mark delivered"],
            ]
              .filter(([from]) => from === s)
              .map(([, ev, label]) => (
                <button key={ev} disabled={busy} onClick={() => act(`/orders/${id}/shipment/event`, { event: ev })}>
                  {label}
                </button>
              ))}
          </div>
        </Action>
      )}

      {/* Buyer: acceptance */}
      {isBuyer && s === "delivered_pending_acceptance" && (
        <Action>
          <h3>Confirm delivery</h3>
          <button disabled={busy} onClick={() => act(`/orders/${id}/acceptance`)}>Accept delivery</button>
        </Action>
      )}

      {s === "settled" && <div className="ok" style={{ marginTop: 16 }}>Order complete and settled. 🌾</div>}

      <h2>History</h2>
      <ul className="timeline">
        {order.history.map((h, i) => (
          <li key={i}>
            {h.to.replace(/_/g, " ")}
            {h.reason_code ? <span className="muted"> · {h.reason_code}</span> : null}
            <br />
            <small>{new Date(h.at).toLocaleString()}</small>
          </li>
        ))}
      </ul>

      <div className="row" style={{ marginTop: 20 }}>
        {(isBuyer || isStaff) && !["settled", "cancelled", "refunded"].includes(s) && (
          <button className="danger" disabled={busy} onClick={() => act(`/orders/${id}/cancel`, { reason_code: "user_cancelled" })}>
            Cancel order
          </button>
        )}
        {(isBuyer || me.id === order.seller_id) &&
          ["paid", "packing", "ready_for_pickup", "picked_up", "in_transit", "out_for_delivery", "delivered_pending_acceptance"].includes(s) && (
            <button className="ghost" disabled={busy} onClick={openDispute}>Report a problem</button>
          )}
      </div>
    </div>
  );
}
