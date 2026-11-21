import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import LiveTrackMap from "../../components/LiveTrackMap";
import AddressPicker from "../../components/AddressPicker";

import { api, downloadFile, getUser, mediaUrl, uploadMedia } from "../../lib/api";
import { usePoll } from "../../lib/hooks";
import { useI18n, tEnum } from "../../lib/i18n";

function DisputeBox({ orderId, onDone }) {
  const { t } = useI18n();
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
      <h3>{t("od_report_problem")}</h3>
      {err && <div className="error">{err}</div>}
      <label>{t("sp_issue_type")}</label>
      <select value={issueType} onChange={(e) => setIssueType(e.target.value)}>
        <option value="quality">{t("it_quality")}</option>
        <option value="quantity">{t("od_quantity_weight")}</option>
        <option value="delivery">{t("it_delivery")}</option>
        <option value="payment">{t("it_payment")}</option>
        <option value="other">{t("od_other")}</option>
      </select>
      <label>{t("od_what_wrong")}</label>
      <textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)}
                placeholder={t("od_describe_ph")} />
      <label>{t("od_evidence_photos")}</label>
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
          {t("od_submit_dispute")}
        </button>
      </div>
    </div>
  );
}

function Quote({ q }) {
  const { t } = useI18n();
  if (!q) return null;
  const line = (label, val) => (
    <div className="quote-line"><span>{label}</span><span>₹{val}</span></div>
  );
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3>{t("od_itemised")}{q.rule_version})</h3>
      {line(t("od_product_value"), q.product_value)}
      {line(t("od_packing"), q.packing_fee)}
      {line(t("od_inspection"), q.inspection_fee)}
      {line(q.route_km_source ? `${t("od_transport")} (${q.route_km_source} ${t("od_distance")})` : t("od_transport"), q.transport_charge)}
      {Number(q.service_fee) > 0 && line(`${t("od_service_fee")} (${tEnum(t, "role_", q.service_fee_payer)})`, q.service_fee)}
      {Number(q.tax) > 0 && line(t("od_tax"), q.tax)}
      <div className="quote-line total"><span>{t("od_buyer_pays")}</span><span>₹{q.buyer_total}</span></div>
      {q.seller_commission !== undefined && (
        <div className="quote-line">
          <span className="muted">{t("od_seller_commission")} ({q.seller_commission_pct}%)</span>
          <span className="muted">− ₹{q.seller_commission}</span>
        </div>
      )}
      <div className="quote-line"><span className="muted">{t("od_seller_receives")}</span><span className="muted">₹{q.seller_payable}</span></div>
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
  const { t } = useI18n();
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
      setMsg(t("od_thanks_rating"));
      loadDone();
    } catch (e) { setMsg(e.message); }
  }

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3>{t("od_rate_exp")}</h3>
      <div style={{ marginTop: 8 }}>
        <div className="muted" style={{ fontSize: 13 }}>{t("od_farmer")} {done.farmer ? `· ${t("od_you_rated")} ${done.farmer}★` : ""}</div>
        <Stars value={done.farmer || farmerR} onPick={done.farmer ? null : setFarmerR} />
        {!done.farmer && (
          <>
            <input placeholder={t("od_comment_opt")} value={fc} onChange={(e) => setFc(e.target.value)} />
            <button style={{ marginTop: 8 }} disabled={!farmerR} onClick={() => submit("farmer", farmerR, fc)}>{t("od_submit_farmer")}</button>
          </>
        )}
      </div>
      {hasCourier && (
        <div style={{ marginTop: 14 }}>
          <div className="muted" style={{ fontSize: 13 }}>{t("od_courier")} {order.shipment.courier_name} {done.courier ? `· ${t("od_you_rated")} ${done.courier}★` : ""}</div>
          <Stars value={done.courier || courierR} onPick={done.courier ? null : setCourierR} />
          {!done.courier && (
            <>
              <input placeholder={t("od_comment_opt")} value={cc} onChange={(e) => setCc(e.target.value)} />
              <button style={{ marginTop: 8 }} disabled={!courierR} onClick={() => submit("courier", courierR, cc)}>{t("od_submit_courier")}</button>
            </>
          )}
        </div>
      )}
      {msg && <div className="ok" style={{ marginTop: 10 }}>{msg}</div>}
    </div>
  );
}

function Certificate({ orderId }) {
  const { t } = useI18n();
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
        <h3>{t("od_verified_lot")}</h3>
        <span className="pill-tag">{cert.certificate_id}</span>
      </div>
      <div style={{ fontSize: 14 }}>
        <b>{cert.product?.commodity}</b>
        {cert.product?.grade ? ` · ${cert.product.grade}` : ""}
        {cert.product?.claim_status ? ` · ${cert.product.claim_status}` : ""}
      </div>
      <div className="quote-line"><span>{t("od_observed_outcome")}</span><span>{tEnum(t, "oc_", cert.observed?.outcome)}</span></div>
      {m.net_qty_kg && <div className="quote-line"><span>{t("od_measured_net")}</span><span>{m.net_qty_kg} kg</span></div>}
      {m.gross_weight_kg && <div className="quote-line"><span>{t("od_gross_tare")}</span><span>{m.gross_weight_kg} / {m.tare_weight_kg || 0} kg</span></div>}
      {m.moisture_pct != null && <div className="quote-line"><span>{t("od_moisture")}</span><span>{m.moisture_pct}%</span></div>}
      {cert.lot && <div className="quote-line"><span>{t("od_lot_seal")}</span><span>{cert.lot.public_id}</span></div>}
      <div className="quote-line"><span className="muted">{t("od_inspected")}</span><span className="muted">{cert.inspected_at ? new Date(cert.inspected_at).toLocaleString() : ""}</span></div>
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
  const { t } = useI18n();
  const [tr, setTr] = useState(null);
  usePoll(() => { if (orderId) api(`/orders/${orderId}/tracking`).then(setTr).catch(() => {}); }, 12000, [orderId]);
  if (!tr || !tr.steps) return null;

  const delivered = tr.steps[tr.steps.length - 1].done;
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="between">
        <h3 style={{ margin: 0 }}>{t("od_delivery")}</h3>
        {tr.shipment?.courier_name && <span className="badge grey">{tEnum(t, "st_", tr.shipment.status)}</span>}
      </div>

      {(tr.to_label || tr.to_address_line || tr.to_place) && (
        <div style={{ fontSize: 13, marginTop: 4 }}>
          📦 <b>{t("od_deliver_to")}</b> {tr.to_label ? `${tr.to_label} — ` : ""}
          {tr.to_address_line ? `${tr.to_address_line}, ` : ""}{tr.to_place}
        </div>
      )}

      {tr.shipment?.courier_name && (
        <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
          {tr.shipment.courier_name}{tr.shipment.vehicle_class ? ` · ${tEnum(t, "vc_", tr.shipment.vehicle_class)}` : ""}
          {tr.from_place ? ` · ${tr.from_place}` : ""}{tr.to_place ? ` → ${tr.to_place}` : ""}
        </div>
      )}

      {!delivered && tr.nav_url && (
        <div style={{ marginTop: 10 }}>
          <a className="btn" href={tr.nav_url} target="_blank" rel="noreferrer">{t("od_navigate")}</a>
        </div>
      )}

      {tr.eta && (
        <div className={`eta ${delivered ? "ok" : ""}`} style={{ marginTop: 10 }}>
          {delivered ? t("od_delivered_word") : t("od_est_delivery")}<b>{fmtWhen(tr.eta)}</b>
          {!delivered && tr.eta_basis === "estimated" ? <span className="muted"> {t("od_estimate")}</span> : null}
        </div>
      )}

      {/* Live delivery map: pickup, drop + courier's moving position (OSM, no key). */}
      {!delivered && (tr.from_coord || tr.to_coord || tr.courier_location) && (
        <div style={{ marginTop: 12 }}>
          <div className="muted" style={{ fontSize: 13, marginBottom: 6 }}>
            {tr.courier_location ? (
              <>{t("od_courier_live")}{tr.courier_location.distance_km != null ? ` · ~${tr.courier_location.distance_km} ${t("od_km_away")}` : ""}
                {tr.courier_location.eta_minutes != null ? ` · ~${tr.courier_location.eta_minutes} ${t("od_min_away")}` : ""}
                {tr.courier_location.at ? ` · ${t("od_updated")} ${fmtAgo(tr.courier_location.at)}` : ""}</>
            ) : t("od_route_preview")}
          </div>
          <LiveTrackMap from={tr.from_coord} to={tr.to_coord} courier={tr.courier_location}
            labels={{ pickup: t("map_pickup"), delivery: t("map_delivery"), courier: t("map_courier"),
                      km_away: t("od_km_away"), min: t("od_min_away") }} />
        </div>
      )}

      {/* Buyer's delivery code — shown to the courier at handoff. */}
      {isBuyer && tr.delivery_code && (
        <div className="code-callout" style={{ marginTop: 12 }}>
          <div className="muted" style={{ fontSize: 12 }}>{t("od_give_code")}</div>
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
          {t("od_proof")}
          {tr.proof.otp_ok ? ` ${t("od_code_verified")}` : ""}
          {tr.proof.has_photo ? ` · ${t("od_photo")}` : ""}
          {tr.proof.has_signature ? ` · ${t("od_signature")}` : ""}
          {tr.proof.recipient_note ? ` · “${tr.proof.recipient_note}”` : ""}
          {!tr.proof.otp_ok && !tr.proof.has_photo && !tr.proof.has_signature && !tr.proof.recipient_note ? ` ${t("od_recorded")}` : ""}
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
  const [newAddr, setNewAddr] = useState(null);     // from AddressPicker ("deliver elsewhere")
  const [addingAddr, setAddingAddr] = useState(false);
  const [payMethod, setPayMethod] = useState("online");  // "online" | "cod"
  const [rescheduleAddr, setRescheduleAddr] = useState(false);  // failed-delivery re-address

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
      <span className="badge">{t("st_" + s)}</span>

      {order.packing_video && (isBuyer || isStaff || isAgent) && (
        <div className="card" style={{ marginTop: 14, borderLeft: "4px solid var(--green-600)" }}>
          <b>{t("od_packing_video")}</b>
          <p className="muted" style={{ fontSize: 13, margin: "4px 0 8px" }}>
            {t("od_packing_video_sub")}
          </p>
          <video src={mediaUrl(order.packing_video)} controls preload="none"
                 style={{ width: "100%", borderRadius: 8, maxHeight: 260 }} />
        </div>
      )}

      <div className="card" style={{ marginTop: 16 }}>
        <div className="between">
          <div><b>₹{order.accepted_terms.price_per_unit}</b>/{order.accepted_terms.unit || "kg"}</div>
          <div>{order.accepted_terms.quantity} {order.accepted_terms.unit}</div>
        </div>
      </div>

      <Quote q={order.quote} />
      {order.quote && (
        <div style={{ marginTop: 12 }}>
          <button className="ghost" onClick={() =>
            downloadFile(`/orders/${id}/invoice.pdf`, `kissansetu-invoice-${order.public_id}.pdf`)
              .catch((e) => setErr(e.message))}>
            ⬇ {["paid", "packing", "ready_for_pickup", "picked_up", "in_transit",
                 "out_for_delivery", "delivered_pending_acceptance", "completed", "settled"].includes(s)
                 ? t("od_download_receipt") : t("od_download_invoice")}
          </button>
        </div>
      )}
      <Certificate orderId={id} />

      {err && <div className="error">{err}</div>}

      {/* Staff: assign inspection */}
      {isStaff && s === "provisional_agreement" && (
        <Action>
          <h3>{t("od_assign_inspection")}</h3>
          <label>{t("od_field_agent_id")}</label>
          <input value={agentId} onChange={(e) => setAgentId(e.target.value)} inputMode="numeric" />
          <div style={{ marginTop: 12 }}>
            <button disabled={busy} onClick={() => act(`/orders/${id}/assign-inspection`, { agent_id: Number(agentId) })}>
              {t("od_assign")}
            </button>
          </div>
        </Action>
      )}

      {/* Agent: submit inspection */}
      {isAgent && ["inspection_assigned", "inspection_in_progress", "inspection_hold"].includes(s) && (
        <Action>
          <h3>{t("od_inspection_h")}</h3>
          <div className="row">
            <div style={{ flex: 1 }}>
              <label>{t("ag_gross_weight")}</label>
              <input value={gross} onChange={(e) => setGross(e.target.value)} inputMode="decimal" />
            </div>
            <div style={{ flex: 1 }}>
              <label>{t("od_tare_bags")}</label>
              <input value={tare} onChange={(e) => setTare(e.target.value)} inputMode="decimal" placeholder="0" />
            </div>
            <div style={{ flex: 1 }}>
              <label>{t("ag_moisture")}</label>
              <input value={moisture} onChange={(e) => setMoisture(e.target.value)} inputMode="decimal" placeholder="e.g. 12" />
            </div>
          </div>
          <div className="row" style={{ marginTop: 6 }}>
            <label style={{ display: "flex", gap: 6, alignItems: "center", margin: 0 }}>
              <input type="checkbox" style={{ width: "auto" }} checked={clean} onChange={(e) => setClean(e.target.checked)} />
              {t("od_cleaned_sorted")}
            </label>
            <label style={{ display: "flex", gap: 6, alignItems: "center", margin: 0 }}>
              <input type="checkbox" style={{ width: "auto" }} checked={pestFree} onChange={(e) => setPestFree(e.target.checked)} />
              {t("od_no_pest")}
            </label>
          </div>
          <label>{t("ag_outcome")}</label>
          <select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            <option value="pass">{t("od_pass")}</option>
            <option value="pass_with_adjustment">{t("od_pass_adj")}</option>
            <option value="hold">{t("od_hold")}</option>
            <option value="fail">{t("od_fail")}</option>
          </select>
          <label>{t("od_insp_photos")}</label>
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
              {t("ag_submit_insp")}
            </button>
          </div>
        </Action>
      )}

      {/* Buyer: approve inspection */}
      {isBuyer && s === "buyer_approval_pending" && (
        <Action>
          <h3>{t("od_review_approve")}</h3>
          <button disabled={busy} onClick={() => act(`/orders/${id}/buyer-approve`)}>{t("od_approve")}</button>
        </Action>
      )}

      {/* Buyer: choose delivery address + lock quote (Zepto/Rapido-style) */}
      {isBuyer && s === "confirmed" && (
        <Action>
          <h3>{t("od_deliver_to_h")}</h3>
          {/* Saved addresses as selectable cards */}
          {!addingAddr && addresses.length > 0 && (
            <div style={{ display: "grid", gap: 8 }}>
              {addresses.map((a) => {
                const sel = String(a.id) === String(addrId);
                return (
                  <label key={a.id} className="card" style={{
                    display: "flex", gap: 10, alignItems: "flex-start", cursor: "pointer", margin: 0,
                    borderColor: sel ? "var(--green-600)" : "var(--line)",
                    borderWidth: sel ? 2 : 1, padding: "10px 12px",
                  }}>
                    <input type="radio" name="addr" checked={sel} onChange={() => setAddrId(String(a.id))}
                           style={{ marginTop: 3 }} />
                    <div>
                      <b>{a.label === "Home" ? "🏠" : a.label === "Work" ? "💼" : "📍"} {a.label}</b>
                      {a.is_default && <span className="badge green" style={{ marginLeft: 6 }}>{t("pf_default")}</span>}
                      <div className="muted" style={{ fontSize: 13 }}>
                        {a.address_line ? `${a.address_line} · ` : ""}{a.mandal}
                      </div>
                    </div>
                  </label>
                );
              })}
            </div>
          )}

          {/* Add / deliver elsewhere */}
          {!addingAddr ? (
            <button className="ghost" style={{ marginTop: 10 }} onClick={() => setAddingAddr(true)}>
              {t("od_deliver_diff")}
            </button>
          ) : (
            <div style={{ marginTop: 6 }}>
              <AddressPicker autoLocate onChange={setNewAddr} />
              <button className="ghost" style={{ marginTop: 8 }}
                      onClick={() => { setAddingAddr(false); setNewAddr(null); }}>
                {t("od_use_saved")}
              </button>
            </div>
          )}

          {addresses.length === 0 && !addingAddr && (
            <p className="muted" style={{ fontSize: 13 }}>
              {t("od_no_saved_addr")}
            </p>
          )}

          <details style={{ marginTop: 10 }}>
            <summary className="muted" style={{ fontSize: 13, cursor: "pointer" }}>{t("od_advanced_override")}</summary>
            <label style={{ marginTop: 6 }}>{t("od_route_dist_label")}</label>
            <input value={routeKm} onChange={(e) => setRouteKm(e.target.value)} inputMode="decimal"
                   placeholder={t("od_auto")} />
          </details>

          {/* Payment method choice carried into the quote */}
          <label style={{ marginTop: 12 }}>{t("pay_method")}</label>
          <div className="seg" role="group" style={{ marginTop: 2 }}>
            <button type="button" className={payMethod === "online" ? "seg-on" : ""}
                    onClick={() => setPayMethod("online")}>💳 {t("pay_online")}</button>
            <button type="button" className={payMethod === "cod" ? "seg-on" : ""}
                    onClick={() => setPayMethod("cod")}>💵 {t("pay_cod")}</button>
          </div>
          {payMethod === "cod" && (
            <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>{t("cod_note")}</div>
          )}

          <div style={{ marginTop: 12 }}>
            <button
              disabled={busy || (addingAddr && !newAddr?.lat) || (!addingAddr && addresses.length === 0)}
              onClick={async () => {
                let useAddrId = addrId;
                // "Deliver elsewhere": save the picked address first, then use it.
                if (addingAddr && newAddr?.lat) {
                  try {
                    const saved = await api("/auth/addresses", { method: "POST", body: {
                      label: newAddr.label || "Home",
                      mandal_id: newAddr.mandal_id ? Number(newAddr.mandal_id) : undefined,
                      address_line: newAddr.address_line || null,
                      latitude: newAddr.lat, longitude: newAddr.lng,
                    } });
                    useAddrId = String(saved.id);
                  } catch { /* fall back to raw pin below */ }
                }
                act(`/orders/${id}/confirm-quote`, {
                  ...(useAddrId ? { address_id: Number(useAddrId) } : {}),
                  ...(!useAddrId && newAddr?.lat ? { delivery_lat: newAddr.lat, delivery_lng: newAddr.lng } : {}),
                  ...(routeKm.trim() === "" ? {} : { route_km: Number(routeKm) }),
                  payment_method: payMethod,
                });
              }}
            >
              {t("od_confirm_lock")}
            </button>
          </div>
        </Action>
      )}

      {/* Buyer: pay — online (provider/mock) or confirm a cash-on-delivery order */}
      {isBuyer && s === "payment_pending" && (
        order.quote?.payment_method === "cod" ? (
          <Action>
            <h3>💵 {t("pay_cod")} — ₹{order.buyer_total}</h3>
            <p className="muted" style={{ fontSize: 13 }}>{t("cod_note")}.</p>
            <button disabled={busy}
                    onClick={() => act(`/orders/${id}/cod-confirm`, undefined, { "Idempotency-Key": order.public_id })}>
              {t("cod_confirm")}
            </button>
          </Action>
        ) : (
          <Action>
            <h3>{t("od_pay")} ₹{order.buyer_total}</h3>
            <p className="muted" style={{ fontSize: 13 }}>{t("od_mock_pay")}</p>
            <button disabled={busy} onClick={() => act(`/orders/${id}/pay`, undefined, { "Idempotency-Key": order.public_id })}>
              {t("od_pay_now")}
            </button>
          </Action>
        )
      )}

      {/* Agent/staff: packing */}
      {isAgent && s === "paid" && (
        <Action>
          <h3>{t("od_packing_h")}</h3>
          <button disabled={busy} onClick={() => act(`/orders/${id}/packing-complete`)}>{t("od_seal_complete")}</button>
        </Action>
      )}

      {/* Delivery timeline (all parties) once the order is packed or moving. */}
      {["ready_for_pickup", "picked_up", "in_transit", "out_for_delivery", "delivery_failed",
        "delivered_pending_acceptance", "completed", "settled"].includes(s) && (
        <TrackingTimeline orderId={id} isBuyer={isBuyer} />
      )}

      {/* Failed delivery: goods are held at the warehouse (Zepto/Swiggi style). */}
      {s === "delivery_failed" && (
        <Action>
          <h3 style={{ borderLeft: "4px solid var(--amber-600)", paddingLeft: 10 }}>{t("od_warehouse_held")}</h3>
          <p className="muted" style={{ fontSize: 13 }}>
            {t("od_warehouse_msg")}
          </p>

          {isBuyer && (
            <>
              {!rescheduleAddr ? (
                <button className="ghost" onClick={() => setRescheduleAddr(true)}>
                  {t("od_deliver_diff2")}
                </button>
              ) : (
                <div style={{ marginTop: 6 }}>
                  <AddressPicker autoLocate onChange={setNewAddr} />
                  <button className="ghost" style={{ marginTop: 8 }}
                          onClick={() => { setRescheduleAddr(false); setNewAddr(null); }}>
                    {t("od_keep_original")}
                  </button>
                </div>
              )}
              <div style={{ marginTop: 12 }}>
                <button disabled={busy || (rescheduleAddr && !newAddr?.lat)}
                        onClick={async () => {
                          const body = (rescheduleAddr && newAddr?.lat)
                            ? { delivery_lat: newAddr.lat, delivery_lng: newAddr.lng } : {};
                          await act(`/orders/${id}/redeliver`, body);
                          setRescheduleAddr(false); setNewAddr(null);
                        }}>
                  {t("od_reschedule")}
                </button>
              </div>
            </>
          )}

          {(isTransport || isStaff || isAgent) && (
            <div className="row" style={{ marginTop: 14, gap: 8 }}>
              <button className="ghost" disabled={busy} onClick={() => act(`/orders/${id}/redeliver`, {})}>
                {t("od_send_back_out")}
              </button>
              <button disabled={busy} onClick={() => act(`/orders/${id}/warehouse-pickup`)}>
                {t("od_buyer_collected")}
              </button>
            </div>
          )}
        </Action>
      )}

      <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <Link href={`/bags/${id}`} className="btn ghost">{t("od_bags_labels")}</Link>
      </div>

      {/* Buyer: choose the courier (buyer-paid logistics) */}
      {isBuyer && !order.shipment?.courier_name &&
        ["payment_pending", "paid", "packing", "ready_for_pickup"].includes(s) && (
        <Action>
          <h3>{t("od_choose_courier")}</h3>
          <p className="muted" style={{ fontSize: 13 }}>{t("od_transport_buyer_paid")}</p>
          <select value={courierId} onChange={(e) => setCourierId(e.target.value)}>
            <option value="">{t("od_select_courier")}</option>
            {carriers.map((c) => (
              <option key={c.id} value={c.id}>{c.name} ({(c.service_areas || []).join(", ")})</option>
            ))}
          </select>
          <div style={{ marginTop: 12 }}>
            <button disabled={busy || !courierId}
                    onClick={() => act(`/orders/${id}/assign-courier`, { courier_id: Number(courierId) })}>
              {t("od_choose_courier_btn")}
            </button>
          </div>
        </Action>
      )}

      {/* Staff/transport: assign a courier */}
      {isTransport && !order.shipment?.courier_name &&
        ["paid", "packing", "ready_for_pickup"].includes(s) && (
        <Action>
          <h3>{t("od_assign_courier")}</h3>
          <select value={courierId} onChange={(e) => setCourierId(e.target.value)}>
            <option value="">{t("od_select_courier")}</option>
            {carriers.map((c) => (
              <option key={c.id} value={c.id}>{c.name} ({(c.vehicle_classes || []).map((v) => tEnum(t, "vc_", v)).join("/")})</option>
            ))}
          </select>
          <div style={{ marginTop: 12 }}>
            <button disabled={busy || !courierId}
                    onClick={() => act(`/orders/${id}/assign-courier`, { courier_id: Number(courierId) })}>
              {t("od_assign_courier_btn")}
            </button>
          </div>
        </Action>
      )}

      {/* Transport: shipment milestones */}
      {isTransport && ["ready_for_pickup", "picked_up", "in_transit", "out_for_delivery"].includes(s) && (
        <Action>
          <h3>{t("od_shipment")}</h3>
          <div className="row">
            {[
              ["ready_for_pickup", "picked_up", "tr_mark_picked_up"],
              ["picked_up", "in_transit", "tr_mark_in_transit"],
              ["in_transit", "out_for_delivery", "tr_out_for_delivery"],
              ["out_for_delivery", "delivered", "tr_mark_delivered"],
            ]
              .filter(([from]) => from === s)
              .map(([, ev, label]) => (
                <button key={ev} disabled={busy} onClick={() => act(`/orders/${id}/shipment/event`, { event: ev })}>
                  {t(label)}
                </button>
              ))}
            {s === "out_for_delivery" && (
              <button className="amber" disabled={busy}
                      onClick={() => act(`/orders/${id}/shipment/event`, { event: "failed_delivery" })}>
                {t("od_delivery_failed_wh")}
              </button>
            )}
          </div>
        </Action>
      )}

      {/* Buyer: acceptance */}
      {isBuyer && s === "delivered_pending_acceptance" && (
        <Action>
          <h3>{t("od_confirm_delivery")}</h3>
          <button disabled={busy} onClick={() => act(`/orders/${id}/acceptance`)}>{t("od_accept_delivery")}</button>
        </Action>
      )}

      {s === "settled" && <div className="ok" style={{ marginTop: 16 }}>{t("od_order_complete")}</div>}

      {isBuyer && ["delivered_pending_acceptance", "completed", "settled", "partially_refunded", "refunded"].includes(s) && (
        <ReviewBox order={order} />
      )}

      <h2>{t("history")}</h2>
      <ul className="timeline">
        {order.history.map((h, i) => (
          <li key={i}>
            {t("st_" + h.to)}
            {h.reason_code ? <span className="muted"> · {h.reason_code}</span> : null}
            <br />
            <small>{new Date(h.at).toLocaleString()}</small>
          </li>
        ))}
      </ul>

      <div className="row" style={{ marginTop: 20 }}>
        {(isBuyer || isStaff) && !["settled", "cancelled", "refunded"].includes(s) && (
          <button className="danger" disabled={busy} onClick={() => act(`/orders/${id}/cancel`, { reason_code: "user_cancelled" })}>
            {t("od_cancel_order")}
          </button>
        )}
        {(isBuyer || me.id === order.seller_id) &&
          ["paid", "packing", "ready_for_pickup", "picked_up", "in_transit", "out_for_delivery", "delivered_pending_acceptance"].includes(s) && (
            <button className="ghost" disabled={busy} onClick={() => setShowDispute((v) => !v)}>
              {showDispute ? t("od_close") : t("od_report_problem")}
            </button>
          )}
      </div>

      {showDispute && (
        <DisputeBox orderId={id} onDone={() => { setShowDispute(false); load(); }} />
      )}
    </div>
  );
}
