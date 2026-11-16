import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import MapPicker from "../../components/MapPicker";

import { api, downloadFile, getUser, mediaUrl, uploadMedia } from "../../lib/api";
import { usePoll } from "../../lib/hooks";
import { useI18n } from "../../lib/i18n";

function DisputeBox({ orderId, onDone }) {
  const [issueType, setIssueType] = useState("quality");
  const [description, setDescription] = useState("");
  const [keys, setKeys] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function addFiles(fileList) {
    setErr(null);
    const files = Array.from(fileList || []).slice(0, 5);
    for (const f of files) {
      try {
        const r = await uploadMedia(f);
        setKeys((k) => [...k, r.object_key]);
      } catch (e) {
        setErr(e.message);
      }
    }
  }

  async function submit() {
    if (!description.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      await api("/disputes", {
        method: "POST",
        body: {
          order_id: Number(orderId),
          issue_type: issueType,
          description: description.trim(),
          evidence: keys.length ? { media: keys } : undefined,
        },
      });
      onDone();
    } catch (e) {
      setErr(e.message);
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ marginTop: 16, borderLeft: "4px solid #f59e0b" }}>
      <h3>Report a problem</h3>
      {err && <div className="error">{err}</div>}
      <label>Issue type</label>
      <select value={issueType} onChange={(e) => setIssueType(e.target.value)}>
        <option value="quality">Quality</option>
        <option value="quantity">Quantity / weight</option>
        <option value="delivery">Delivery</option>
        <option value="payment">Payment</option>
        <option value="other">Other</option>
      </select>
      <label>What went wrong?</label>
      <textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe the problem clearly." />
      <label>Evidence photos (optional, up to 5)</label>
      <input type="file" accept="image/*,application/pdf" multiple
             onChange={(e) => addFiles(e.target.files)} />
      {keys.length > 0 && (
        <div className="thumb-row" style={{ marginTop: 8 }}>
          {keys.map((k) => (
            <img key={k} src={mediaUrl(k)} alt="evidence"
                 style={{ width: 64, height: 64, objectFit: "cover", borderRadius: 6, marginRight: 6 }} />
          ))}
        </div>
      )}
      <div style={{ marginTop: 12 }}>
        <button className="amber" disabled={busy || !description.trim()} onClick={submit}>
          Submit dispute
        </button>
      </div>
    </div>
  );
}

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

function Stars({ value, onPick }) {
  return (
    <span style={{ fontSize: 22, cursor: onPick ? "pointer" : "default" }}>
      {[1, 2, 3, 4, 5].map((n) => (
        <span key={n} onClick={onPick ? () => onPick(n) : undefined}
              style={{ color: n <= value ? "#f59e0b" : "#d1d5db" }}>★</span>
      ))}
    </span>
  );
}

function ReviewBox({ order }) {
  const [done, setDone] = useState({});
  const [farmerR, setFarmerR] = useState(0);
  const [courierR, setCourierR] = useState(0);
  const [fc, setFc] = useState("");
  const [cc, setCc] = useState("");
  const [msg, setMsg] = useState(null);
  const hasCourier = !!order.shipment?.courier_name;

  async function loadDone() {
    try { setDone((await api(`/reviews/for-order/${order.id}`)).reviewed || {}); } catch {}
  }
  useEffect(() => { loadDone(); /* eslint-disable-next-line */ }, [order.id]);

  async function submit(subject_type, rating, comment) {
    if (!rating) return;
    setMsg(null);
    try {
      await api("/reviews", { method: "POST", body: { order_id: order.id, subject_type, rating, comment: comment || undefined } });
      setMsg("Thanks for your rating.");
      loadDone();
    } catch (e) { setMsg(e.message); }
  }

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3>Rate your experience</h3>
      <div style={{ marginTop: 8 }}>
        <div className="muted" style={{ fontSize: 13 }}>Farmer {done.farmer ? `· you rated ${done.farmer}★` : ""}</div>
        <Stars value={done.farmer || farmerR} onPick={done.farmer ? null : setFarmerR} />
        {!done.farmer && (
          <>
            <input placeholder="Comment (optional)" value={fc} onChange={(e) => setFc(e.target.value)} />
            <button style={{ marginTop: 8 }} disabled={!farmerR} onClick={() => submit("farmer", farmerR, fc)}>Submit farmer rating</button>
          </>
        )}
      </div>
      {hasCourier && (
        <div style={{ marginTop: 14 }}>
          <div className="muted" style={{ fontSize: 13 }}>Courier: {order.shipment.courier_name} {done.courier ? `· you rated ${done.courier}★` : ""}</div>
          <Stars value={done.courier || courierR} onPick={done.courier ? null : setCourierR} />
          {!done.courier && (
            <>
              <input placeholder="Comment (optional)" value={cc} onChange={(e) => setCc(e.target.value)} />
              <button style={{ marginTop: 8 }} disabled={!courierR} onClick={() => submit("courier", courierR, cc)}>Submit courier rating</button>
            </>
          )}
        </div>
      )}
      {msg && <div className="ok" style={{ marginTop: 10 }}>{msg}</div>}
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

function fmtWhen(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function fmtAgo(iso) {
  if (!iso) return "";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  return `${Math.round(s / 3600)}h ago`;
}

function osmEmbed(lat, lng) {
  const d = 0.012; // ~1.3 km half-window
  const bbox = [lng - d, lat - d, lng + d, lat + d].join(",");
  return `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${lat},${lng}`;
}

function TrackingTimeline({ orderId, isBuyer }) {
  const [tr, setTr] = useState(null);
  usePoll(() => { if (orderId) api(`/orders/${orderId}/tracking`).then(setTr).catch(() => {}); }, 12000, [orderId]);
  if (!tr || !tr.steps) return null;

  const delivered = tr.steps[tr.steps.length - 1].done;
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="between">
        <h3 style={{ margin: 0 }}>🚚 Delivery</h3>
        {tr.shipment?.courier_name && <span className="badge grey">{tr.shipment.status.replace(/_/g, " ")}</span>}
      </div>

      {(tr.to_label || tr.to_address_line || tr.to_place) && (
        <div style={{ fontSize: 13, marginTop: 4 }}>
          📦 <b>Deliver to:</b> {tr.to_label ? `${tr.to_label} — ` : ""}
          {tr.to_address_line ? `${tr.to_address_line}, ` : ""}{tr.to_place}
        </div>
      )}

      {tr.shipment?.courier_name && (
        <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
          {tr.shipment.courier_name}{tr.shipment.vehicle_class ? ` · ${tr.shipment.vehicle_class}` : ""}
          {tr.from_place ? ` · ${tr.from_place}` : ""}{tr.to_place ? ` → ${tr.to_place}` : ""}
        </div>
      )}

      {!delivered && tr.nav_url && (
        <div style={{ marginTop: 10 }}>
          <a className="btn" href={tr.nav_url} target="_blank" rel="noreferrer">🧭 Navigate the delivery route</a>
        </div>
      )}

      {tr.eta && (
        <div className={`eta ${delivered ? "ok" : ""}`} style={{ marginTop: 10 }}>
          {delivered ? "Delivered " : "Estimated delivery: "}<b>{fmtWhen(tr.eta)}</b>
          {!delivered && tr.eta_basis === "estimated" ? <span className="muted"> (estimate)</span> : null}
        </div>
      )}

      {/* Live courier position on a free OpenStreetMap embed (no API key). */}
      {!delivered && tr.courier_location && (
        <div style={{ marginTop: 12 }}>
          <div className="muted" style={{ fontSize: 13, marginBottom: 6 }}>
            📍 Courier is live{tr.courier_location.distance_km != null ? ` · ~${tr.courier_location.distance_km} km away` : ""}
            {tr.courier_location.eta_minutes != null ? ` · ~${tr.courier_location.eta_minutes} min away` : ""}
            {tr.courier_location.at ? ` · updated ${fmtAgo(tr.courier_location.at)}` : ""}
          </div>
          <iframe
            title="Courier live location"
            className="live-map"
            src={osmEmbed(tr.courier_location.lat, tr.courier_location.lng)}
          />
          <div style={{ marginTop: 4 }}>
            <a className="muted" style={{ fontSize: 12 }} target="_blank" rel="noreferrer"
               href={`https://www.openstreetmap.org/?mlat=${tr.courier_location.lat}&mlon=${tr.courier_location.lng}#map=14/${tr.courier_location.lat}/${tr.courier_location.lng}`}>
              Open full map ↗
            </a>
          </div>
        </div>
      )}

      {/* Buyer's delivery code — shown to the courier at handoff. */}
      {isBuyer && tr.delivery_code && (
        <div className="code-callout" style={{ marginTop: 12 }}>
          <div className="muted" style={{ fontSize: 12 }}>Give this code to the courier at delivery</div>
          <div className="code">{tr.delivery_code}</div>
        </div>
      )}

      <ol className="track" style={{ marginTop: 14 }}>
        {tr.steps.map((st) => (
          <li key={st.key} className={st.done ? "done" : st.current ? "current" : "pending"}>
            <span className="dot">{st.done ? "✓" : st.current ? "●" : "○"}</span>
            <span className="track-label">{st.label}</span>
            {st.at && <span className="track-at">{fmtWhen(st.at)}</span>}
          </li>
        ))}
      </ol>

      {tr.proof && (
        <div className="muted" style={{ fontSize: 13, marginTop: 10 }}>
          Proof of delivery:
          {tr.proof.otp_ok ? " code verified" : ""}
          {tr.proof.has_photo ? " · photo" : ""}
          {tr.proof.has_signature ? " · signature" : ""}
          {tr.proof.recipient_note ? ` · “${tr.proof.recipient_note}”` : ""}
          {!tr.proof.otp_ok && !tr.proof.has_photo && !tr.proof.has_signature && !tr.proof.recipient_note ? " recorded" : ""}
        </div>
      )}
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
  const [tare, setTare] = useState("");
  const [moisture, setMoisture] = useState("");
  const [clean, setClean] = useState(true);
  const [pestFree, setPestFree] = useState(true);
  const [inspKeys, setInspKeys] = useState([]);
  const [outcome, setOutcome] = useState("pass");
  const [carriers, setCarriers] = useState([]);
  const [courierId, setCourierId] = useState("");
  const [showDispute, setShowDispute] = useState(false);
  const [addresses, setAddresses] = useState([]);
  const [addrId, setAddrId] = useState("");
  const [deliveryPin, setDeliveryPin] = useState(null);

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
  usePoll(() => { if (id) load(); }, 12000, [id]);

  useEffect(() => {
    const role = me?.role;
    if (role && ["mandal_manager", "superadmin", "transport", "buyer_household", "buyer_business"].includes(role)) {
      api("/carriers?active_only=true").then((cs) => setCarriers(cs.filter((c) => c.kyc_status === "verified"))).catch(() => {});
    }
  }, [me]);

  // Buyer's saved delivery addresses, loaded when a quote is ready to confirm.
  useEffect(() => {
    if (me && order && me.id === order.buyer_id && order.status === "confirmed") {
      api("/auth/addresses").then((list) => {
        setAddresses(list);
        const def = list.find((a) => a.is_default) || list[0];
        if (def) setAddrId(String(def.id));
      }).catch(() => {});
    }
  }, [me, order?.status]);

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

  if (err && !order) return <div className="error">{err}</div>;
  if (!order || !me) return <p className="muted">{t("loading")}</p>;

  const s = order.status;
  const role = me.role;
  const isBuyer = me.id === order.buyer_id;
  const isStaff = ["superadmin", "field_manager", "field_leader"].includes(role);
  const isAgent = ["field_agent", "field_leader", "field_manager", "superadmin"].includes(role);
  const isTransport = ["transport", "field_leader", "field_manager", "superadmin"].includes(role);

  const Action = ({ children }) => (
    <div className="card" style={{ marginTop: 16, borderLeft: "4px solid var(--green-600)" }}>{children}</div>
  );

  return (
    <div style={{ maxWidth: 620 }}>
      <button className="ghost" onClick={() => router.push("/orders")}>← {t("my_orders")}</button>
      <h1 style={{ marginTop: 14 }}>{order.public_id}</h1>
      <span className="badge">{s.replace(/_/g, " ")}</span>

      {order.packing_video && (isBuyer || isStaff || isAgent) && (
        <div className="card" style={{ marginTop: 14, borderLeft: "4px solid var(--green-600)" }}>
          <b>🎥 Packing video</b>
          <p className="muted" style={{ fontSize: 13, margin: "4px 0 8px" }}>
            Recorded when your order was sealed for dispatch.
          </p>
          <video src={mediaUrl(order.packing_video)} controls preload="none"
                 style={{ width: "100%", borderRadius: 8, maxHeight: 260 }} />
        </div>
      )}

      <div className="card" style={{ marginTop: 16 }}>
        <div className="between">
          <div><b>₹{order.accepted_terms.price_per_unit}</b>/kg</div>
          <div>{order.accepted_terms.quantity} {order.accepted_terms.unit}</div>
        </div>
      </div>

      <Quote q={order.quote} />
      {order.quote && (
        <div style={{ marginTop: 12 }}>
          <button className="ghost" onClick={() =>
            downloadFile(`/orders/${id}/invoice.pdf`, `agrisetu-invoice-${order.public_id}.pdf`)
              .catch((e) => setErr(e.message))}>
            ⬇ {["paid", "packing", "ready_for_pickup", "picked_up", "in_transit",
                 "out_for_delivery", "delivered_pending_acceptance", "completed", "settled"].includes(s)
                 ? "Download receipt (PDF)" : "Download invoice (PDF)"}
          </button>
        </div>
      )}
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
              <label>Tare / bags (kg)</label>
              <input value={tare} onChange={(e) => setTare(e.target.value)} inputMode="decimal" placeholder="0" />
            </div>
            <div style={{ flex: 1 }}>
              <label>Moisture %</label>
              <input value={moisture} onChange={(e) => setMoisture(e.target.value)} inputMode="decimal" placeholder="e.g. 12" />
            </div>
          </div>
          <div className="row" style={{ marginTop: 6 }}>
            <label style={{ display: "flex", gap: 6, alignItems: "center", margin: 0 }}>
              <input type="checkbox" style={{ width: "auto" }} checked={clean} onChange={(e) => setClean(e.target.checked)} />
              Cleaned & sorted
            </label>
            <label style={{ display: "flex", gap: 6, alignItems: "center", margin: 0 }}>
              <input type="checkbox" style={{ width: "auto" }} checked={pestFree} onChange={(e) => setPestFree(e.target.checked)} />
              No pest / damage
            </label>
          </div>
          <label>Outcome</label>
          <select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            <option value="pass">Pass</option>
            <option value="pass_with_adjustment">Pass with adjustment</option>
            <option value="hold">Hold</option>
            <option value="fail">Fail</option>
          </select>
          <label>Inspection photos (optional)</label>
          <input type="file" accept="image/*" multiple
                 onChange={async (e) => {
                   const files = Array.from(e.target.files || []).slice(0, 5);
                   for (const f of files) {
                     try { const r = await uploadMedia(f); setInspKeys((k) => [...k, r.object_key]); }
                     catch (ex) { setErr(ex.message); }
                   }
                 }} />
          {inspKeys.length > 0 && (
            <div className="thumb-row" style={{ marginTop: 8 }}>
              {inspKeys.map((k) => (
                <img key={k} src={mediaUrl(k)} alt="inspection" style={{ width: 56, height: 56, objectFit: "cover" }} />
              ))}
            </div>
          )}
          <div style={{ marginTop: 12 }}>
            <button
              disabled={busy}
              onClick={() =>
                act(`/agent/orders/${id}/inspection`, {
                  gross_weight: gross ? Number(gross) : undefined,
                  tare_weight: tare ? Number(tare) : 0,
                  outcome,
                  checklist: {
                    moisture_pct: moisture ? Number(moisture) : undefined,
                    cleaned_sorted: clean,
                    pest_free: pestFree,
                  },
                  evidence: inspKeys.length ? inspKeys : undefined,
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

      {/* Buyer: choose delivery address + lock quote */}
      {isBuyer && s === "confirmed" && (
        <Action>
          <h3>Confirm quote</h3>
          <label>Deliver to</label>
          {addresses.length > 0 ? (
            <select value={addrId} onChange={(e) => setAddrId(e.target.value)}>
              {addresses.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}{a.is_default ? " (default)" : ""} — {a.address_line ? `${a.address_line}, ` : ""}{a.mandal}
                </option>
              ))}
            </select>
          ) : (
            <p className="muted" style={{ fontSize: 13 }}>
              No saved address yet. The order will deliver to the default mandal — add an address in{" "}
              <a href="/profile">your profile</a> for door-to-door delivery.
            </p>
          )}
          <details style={{ marginTop: 10 }}>
            <summary style={{ fontSize: 13, cursor: "pointer" }}>📍 Drop exact delivery point on map (optional)</summary>
            <div style={{ marginTop: 8 }}>
              <MapPicker value={deliveryPin} onChange={setDeliveryPin} />
            </div>
          </details>
          <details style={{ marginTop: 10 }}>
            <summary className="muted" style={{ fontSize: 13, cursor: "pointer" }}>Advanced: override route distance</summary>
            <label style={{ marginTop: 6 }}>Route distance (km) — leave blank to compute from location</label>
            <input value={routeKm} onChange={(e) => setRouteKm(e.target.value)} inputMode="decimal"
                   placeholder="auto" />
          </details>
          <div style={{ marginTop: 12 }}>
            <button
              disabled={busy}
              onClick={() =>
                act(`/orders/${id}/confirm-quote`, {
                  ...(addrId ? { address_id: Number(addrId) } : {}),
                  ...(deliveryPin ? { delivery_lat: deliveryPin.lat, delivery_lng: deliveryPin.lng } : {}),
                  ...(routeKm.trim() === "" ? {} : { route_km: Number(routeKm) }),
                })
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

      {/* Delivery timeline (all parties) once the order is packed or moving. */}
      {["ready_for_pickup", "picked_up", "in_transit", "out_for_delivery",
        "delivered_pending_acceptance", "completed", "settled"].includes(s) && (
        <TrackingTimeline orderId={id} isBuyer={isBuyer} />
      )}

      <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <Link href={`/bags/${id}`} className="btn ghost">🏷️ Bags &amp; labels</Link>
      </div>

      {/* Buyer: choose the courier (buyer-paid logistics) */}
      {isBuyer && !order.shipment?.courier_name &&
        ["payment_pending", "paid", "packing", "ready_for_pickup"].includes(s) && (
        <Action>
          <h3>Choose your delivery courier</h3>
          <p className="muted" style={{ fontSize: 13 }}>Transport is buyer-paid; pick a verified courier.</p>
          <select value={courierId} onChange={(e) => setCourierId(e.target.value)}>
            <option value="">— select courier —</option>
            {carriers.map((c) => (
              <option key={c.id} value={c.id}>{c.name} ({(c.service_areas || []).join(", ")})</option>
            ))}
          </select>
          <div style={{ marginTop: 12 }}>
            <button disabled={busy || !courierId}
                    onClick={() => act(`/orders/${id}/assign-courier`, { courier_id: Number(courierId) })}>
              Choose courier
            </button>
          </div>
        </Action>
      )}

      {/* Staff/transport: assign a courier */}
      {isTransport && !order.shipment?.courier_name &&
        ["paid", "packing", "ready_for_pickup"].includes(s) && (
        <Action>
          <h3>Assign transport courier</h3>
          <select value={courierId} onChange={(e) => setCourierId(e.target.value)}>
            <option value="">— select courier —</option>
            {carriers.map((c) => (
              <option key={c.id} value={c.id}>{c.name} ({(c.vehicle_classes || []).join("/")})</option>
            ))}
          </select>
          <div style={{ marginTop: 12 }}>
            <button disabled={busy || !courierId}
                    onClick={() => act(`/orders/${id}/assign-courier`, { courier_id: Number(courierId) })}>
              Assign courier
            </button>
          </div>
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

      {isBuyer && ["delivered_pending_acceptance", "completed", "settled", "partially_refunded", "refunded"].includes(s) && (
        <ReviewBox order={order} />
      )}

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
            <button className="ghost" disabled={busy} onClick={() => setShowDispute((v) => !v)}>
              {showDispute ? "Close" : "Report a problem"}
            </button>
          )}
      </div>

      {showDispute && (
        <DisputeBox orderId={id} onDone={() => { setShowDispute(false); load(); }} />
      )}
    </div>
  );
}
