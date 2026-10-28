import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { useI18n } from "../lib/i18n";

export default function Orders() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [orders, setOrders] = useState([]);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setMe(getUser());
    api("/orders")
      .then(setOrders)
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (!me) {
    return (
      <div>
        <p className="muted">Log in to see your orders.</p>
        <Link href="/login" className="btn">{t("login")}</Link>
      </div>
    );
  }

  return (
    <div>
      <h1>{t("my_orders")}</h1>
      {err && <div className="error">{err}</div>}
      {loading ? (
        <p className="muted">{t("loading")}</p>
      ) : orders.length === 0 ? (
        <p className="muted">No orders yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Order</th>
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
                <td><span className="badge grey">{o.status.replace(/_/g, " ")}</span></td>
                <td><Link href={`/order/${o.id}`}>Open →</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
