import Link from "next/link";
import { useEffect, useState } from "react";

import { api, downloadFile, getUser } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

export default function Invoices() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [orders, setOrders] = useState([]);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { setMe(getUser()); }, []);
  usePoll(() => {
    api("/orders")
      .then(setOrders)
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, 20000);

  const gate = roleGate(me, GROUPS.shopper, { label: "invoices" });
  if (gate) return gate;

  const PAID = ["paid", "packing", "ready_for_pickup", "picked_up", "in_transit",
    "out_for_delivery", "delivered_pending_acceptance", "completed", "settled"];
  // Only orders with a locked quote have an invoice/receipt.
  const billable = orders.filter((o) => o.quote);

  return (
    <div>
      <h1>{t("invoices")}</h1>
      <p className="muted" style={{ fontSize: 14 }}>
        {t("iv_intro")}
      </p>
      {err && <div className="error">{err}</div>}
      {loading ? (
        <p className="muted">{t("loading")}</p>
      ) : billable.length === 0 ? (
        <div className="empty">
          <span className="emoji">🧾</span>
          <p>{t("iv_empty")}</p>
          <Link href="/" className="btn">{t("browse_market")}</Link>
        </div>
      ) : (
        <table>
          <thead>
            <tr><th>{t("iv_col_order")}</th><th>{t("iv_col_number")}</th><th>{t("iv_col_amount")}</th><th>{t("status")}</th><th>{t("iv_col_document")}</th></tr>
          </thead>
          <tbody>
            {billable.map((o) => {
              const paid = PAID.includes(o.status);
              const fname = `kissansetu-invoice-${(o.invoice_number || o.public_id).replace(/\//g, "-")}.pdf`;
              return (
                <tr key={o.id}>
                  <td><Link href={`/order/${o.id}`}>{o.public_id}</Link></td>
                  <td style={{ whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>{o.invoice_number || "—"}</td>
                  <td>₹{o.buyer_total || o.quote.buyer_total}</td>
                  <td><span className="badge grey">{t("st_" + o.status)}</span></td>
                  <td>
                    <button className="ghost" onClick={() =>
                      downloadFile(`/orders/${o.id}/invoice.pdf`, fname)
                        .catch((e) => setErr(e.message))}>
                      ⬇ {paid ? t("iv_receipt") : t("iv_invoice")} (PDF)
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
