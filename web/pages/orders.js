import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

export default function Orders() {
  const { t } = useI18n();
  const router = useRouter();
  const [me, setMe] = useState(null);
  const [orders, setOrders] = useState([]);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState(null);

  // Farmers buy with the same login, so they reorder too.
  const isBuyer = me && ["farmer", "buyer_household", "buyer_business"].includes(me.role);

  async function reorder(id, commodityId) {
    setMsg(null);
    setErr(null);
    try {
      const r = await api(`/orders/${id}/reorder`, { method: "POST" });
      if (r.reorderable) {
        router.push(`/offers?focus=${r.offer_id}`);
      } else {
        setMsg(r.reason || "That lot is unavailable — showing other offerings.");
        if (r.commodity_id) setTimeout(() => router.push(`/product/${r.commodity_id}`), 1000);
      }
    } catch (e) {
      setErr(e.message);
    }
  }

  useEffect(() => { setMe(getUser()); }, []);
  usePoll(() => {
    api("/orders")
      .then(setOrders)
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, 15000);

  const gate = roleGate(me, GROUPS.shopper, { label: "orders" });
  if (gate) return gate;

  return (
    <div>
      <h1>{t("my_orders")}</h1>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok">{msg}</div>}
      {loading ? (
        <p className="muted">{t("loading")}</p>
      ) : orders.length === 0 ? (
        <div className="empty">
          <span className="emoji">📦</span>
          <p>{t("orders_empty")}</p>
          {isBuyer && <Link href="/" className="btn">{t("browse_market")}</Link>}
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>{t("col_order")}</th>
              <th>{t("price")}</th>
              <th>{t("quantity")}</th>
              <th>{t("status")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => (
              <tr key={o.id}>
                <td><Link href={`/order/${o.id}`}>{o.public_id}</Link></td>
                <td>₹{o.accepted_terms.price_per_unit}/kg</td>
                <td>{o.accepted_terms.quantity} {o.accepted_terms.unit}</td>
                <td><span className="badge grey">{t("st_" + o.status)}</span></td>
                <td>
                  <Link href={`/order/${o.id}`}>{t("open_arrow")}</Link>
                  {isBuyer && ["completed", "settled", "delivered_pending_acceptance"].includes(o.status) && (
                    <> · <a role="button" style={{ cursor: "pointer" }}
                           onClick={() => reorder(o.id, o.accepted_terms?.commodity_id)}>{t("reorder")}</a></>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
