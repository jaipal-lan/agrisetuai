import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";

export default function Earnings() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => { setMe(getUser()); }, []);
  usePoll(() => {
    api("/auth/me/earnings").then(setData).catch((e) => setErr(e.message));
  }, 20000);

  if (!me) {
    return (
      <div>
        <p className="muted">Log in as a farmer to see earnings.</p>
        <Link href="/login" className="btn">{t("login")}</Link>
      </div>
    );
  }

  return (
    <div>
      <h1>Earnings</h1>
      {err && <div className="error">{err}</div>}
      {data && (
        <>
          <div className="grid" style={{ marginBottom: 16 }}>
            {[["Gross sales", data.totals.gross], ["Commission (0.7%)", data.totals.commission],
              ["Net proceeds", data.totals.net], ["Paid out", data.totals.paid]].map(([label, val]) => (
              <div className="card" key={label}>
                <div className="muted" style={{ fontSize: 13 }}>{label}</div>
                <div className="price" style={{ fontSize: 22 }}>₹{val}</div>
              </div>
            ))}
          </div>
          {data.orders.length === 0 ? (
            <p className="muted">No completed sales yet.</p>
          ) : (
            <table>
              <thead>
                <tr><th>Order</th><th>Gross</th><th>Commission</th><th>Net</th><th>Payout</th></tr>
              </thead>
              <tbody>
                {data.orders.map((o) => (
                  <tr key={o.order_public_id}>
                    <td><Link href={`/orders`}>{o.order_public_id}</Link></td>
                    <td>₹{o.gross}</td>
                    <td>−₹{o.commission}</td>
                    <td><b>₹{o.net}</b></td>
                    <td><span className={`badge ${o.payout_status === "processed" ? "" : "grey"}`}>{o.payout_status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
