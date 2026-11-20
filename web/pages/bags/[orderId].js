import { useRouter } from "next/router";
import { useEffect, useRef, useState } from "react";

import { api, getUser } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { roleGate } from "../../lib/roles";

const STAFF = ["field_agent", "field_leader", "field_manager", "transport", "superadmin"];
const CAN_GENERATE = ["field_agent", "field_leader", "field_manager", "superadmin"];
const QRCODE_LIB = "https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js";

function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) return resolve();
    const s = document.createElement("script");
    s.src = src; s.onload = resolve; s.onerror = () => reject(new Error("load failed"));
    document.body.appendChild(s);
  });
}

export default function BagLabels() {
  const { t } = useI18n();
  const router = useRouter();
  const { orderId } = router.query;
  const [me, setMe] = useState(null);
  const [meta, setMeta] = useState(null);
  const [bags, setBags] = useState([]);
  const [count, setCount] = useState(1);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const qrRefs = useRef({});

  useEffect(() => { setMe(getUser()); }, []);

  async function load() {
    if (!orderId) return;
    try {
      const r = await api(`/orders/${orderId}/bags`);
      setMeta(r.meta); setBags(r.bags || []);
    } catch (e) { setErr(e.message); }
  }
  useEffect(() => { load(); }, [orderId]);

  // Render a QR (deep link to public tracking) for each bag once drawn.
  useEffect(() => {
    if (!bags.length) return;
    let alive = true;
    loadScript(QRCODE_LIB).then(() => {
      if (!alive || !window.QRCode) return;
      const origin = window.location.origin;
      bags.forEach((b) => {
        const el = qrRefs.current[b.bag_code];
        if (el && !el.hasChildNodes()) {
          // eslint-disable-next-line no-new
          new window.QRCode(el, { text: `${origin}/track?code=${b.bag_code}`, width: 90, height: 90 });
        }
      });
    }).catch(() => {});
    return () => { alive = false; };
  }, [bags]);

  async function generate() {
    setErr(null); setBusy(true);
    try {
      await api(`/orders/${orderId}/bags`, { method: "POST", body: { count: Number(count) } });
      await load();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  const gate = roleGate(me, STAFF, { label: "bag labels" });
  if (gate) return gate;

  const today = new Date().toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });

  return (
    <div style={{ maxWidth: 760, margin: "0 auto" }}>
      <style>{`@media print {
        nav.nav, .toast-wrap, .no-print { display: none !important; }
        .label-sheet { gap: 0 !important; }
        .bag-label { break-inside: avoid; page-break-inside: avoid; }
      }`}</style>

      <div className="no-print">
        <h1>{t("bg_title")}</h1>
        <p className="tagline">{t("bg_order")} #{orderId}{meta?.order_public_id ? ` · ${meta.order_public_id}` : ""}</p>
        {err && <div className="error">{err}</div>}
        {bags.length === 0 ? (
          CAN_GENERATE.includes(me.role) ? (
            <div className="card">
              <h3 style={{ marginTop: 0 }}>{t("bg_no_bags_gen")}</h3>
              <div className="row" style={{ gap: 6 }}>
                <label>{t("bg_how_many")}
                  <input type="number" min={1} max={200} value={count}
                         onChange={(e) => setCount(e.target.value)} style={{ width: 90 }} />
                </label>
                <button disabled={busy} onClick={generate} style={{ alignSelf: "flex-end" }}>{t("bg_generate")}</button>
              </div>
            </div>
          ) : <p className="muted">{t("bg_no_bags")}</p>
        ) : (
          <div className="row" style={{ gap: 8, marginBottom: 10 }}>
            <button onClick={() => window.print()}>{t("bg_print")}</button>
            <span className="muted" style={{ alignSelf: "center" }}>{bags.length} {t("bg_bags")}</span>
          </div>
        )}
      </div>

      <div className="label-sheet" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 12 }}>
        {bags.map((b) => (
          <div key={b.bag_code} className="bag-label card" style={{ border: "1px solid #000", padding: 12 }}>
            <div className="between">
              <b style={{ fontSize: 15 }}>{meta?.commodity || t("tk_produce")}{meta?.variety ? ` (${meta.variety})` : ""}</b>
              <span>{b.weight ? `${b.weight} kg` : ""}</span>
            </div>
            <div style={{ fontSize: 13, marginTop: 4 }}>
              <div><b>{t("bg_farmer")}</b> {meta?.farmer_name || "—"}{meta?.farmer_village ? `, ${meta.farmer_village}` : ""}</div>
              <div><b>{t("bg_order_label")}</b> {meta?.order_public_id || `#${orderId}`} · {t("bg_bag")} {b.bag_no}</div>
              {meta?.destination && <div><b>{t("bg_destination")}</b> {meta.destination}</div>}
              <div><b>{t("bg_date")}</b> {today}</div>
            </div>
            <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
              <div ref={(el) => { if (el) qrRefs.current[b.bag_code] = el; }} />
              <div style={{ textAlign: "right" }}>
                <div style={{ fontFamily: "monospace", fontWeight: 700, fontSize: 15 }}>{b.bag_code}</div>
                <div style={{ fontFamily: "monospace", letterSpacing: 2, fontSize: 22 }}>
                  *{b.bag_code}*
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
