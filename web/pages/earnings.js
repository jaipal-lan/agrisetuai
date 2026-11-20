import Link from "next/link";
import { useEffect, useState } from "react";

import { api, downloadCsv, getUser } from "../lib/api";
import { GROUPS, roleGate } from "../lib/roles";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";

// Farmer cash-out: shows withdrawable balance and lets them request a payout to
// their verified account; finance approves (disburses) or rejects.
function WithdrawCard() {
  const { t } = useI18n();
  const [bal, setBal] = useState(null);
  const [list, setList] = useState([]);
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  function load() {
    api("/auth/me/balance").then(setBal).catch(() => {});
    api("/auth/me/withdrawals").then(setList).catch(() => {});
  }
  useEffect(() => { load(); }, []);

  async function request() {
    setErr(null); setMsg(null); setBusy(true);
    try {
      await api("/auth/me/withdrawals", { method: "POST" });
      setMsg(t("wd_requested"));
      load();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  const WD_STATUS = { paid: "wd_paid", rejected: "wd_rejected", pending: "wd_pending_status" };
  if (!bal) return null;
  return (
    <>
      <h2>{t("wd_title")}</h2>
      <div className="card">
        <div className="between" style={{ flexWrap: "wrap", gap: 10 }}>
          <div>
            <div className="muted" style={{ fontSize: 13 }}>{t("wd_available")}</div>
            <div className="price" style={{ fontSize: 26 }}>₹{bal.available}</div>
            <div className="muted" style={{ fontSize: 12 }}>{t("wd_paid_so_far")} ₹{bal.paid_total}</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <button disabled={busy || !bal.can_request} onClick={request}>{t("wd_request")}</button>
            {!bal.account_verified && (
              <div className="muted" style={{ fontSize: 12, marginTop: 6, maxWidth: 220 }}>
                {bal.has_account ? t("wd_awaiting_verify")
                  : <>{t("wd_add_account_pre")} <Link href="/profile">{t("wd_your_profile")}</Link> {t("wd_add_account_post")}</>}
              </div>
            )}
            {bal.account_verified && bal.identity_verified === false && (
              <div className="muted" style={{ fontSize: 12, marginTop: 6, maxWidth: 220 }}>
                {t("wd_verify_id_pre")}{" "}
                <Link href="/profile">{t("wd_verify_id_link")}</Link> {t("wd_verify_id_post")}
              </div>
            )}
            {bal.account_verified && Number(bal.pending_withdrawal) > 0 && (
              <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
                {t("wd_pending_pre")} ₹{bal.pending_withdrawal} {t("wd_pending_post")}
              </div>
            )}
            {bal.account_verified && Number(bal.pending_withdrawal) === 0 && Number(bal.available) === 0 && (
              <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>{t("wd_no_balance")}</div>
            )}
          </div>
        </div>
        {err && <div className="error" style={{ marginTop: 8 }}>{err}</div>}
        {msg && <div className="ok" style={{ marginTop: 8 }}>{msg}</div>}
        {list.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div className="muted" style={{ fontSize: 13, marginBottom: 4 }}>{t("wd_recent")}</div>
            {list.map((w) => (
              <div key={w.id} className="between" style={{ padding: "6px 0", borderBottom: "1px solid var(--line)", fontSize: 14 }}>
                <span>₹{w.amount} <span className="muted">· {w.method || "—"} {w.account_masked || ""}</span></span>
                <span className={`badge ${w.status === "paid" ? "green" : w.status === "rejected" ? "amber" : "grey"}`}>{t(WD_STATUS[w.status] || w.status)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

export default function Earnings() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => { setMe(getUser()); }, []);
  usePoll(() => {
    api("/auth/me/earnings").then(setData).catch((e) => setErr(e.message));
  }, 20000);

  const gate = roleGate(me, GROUPS.seller, { label: "earnings" });
  if (gate) return gate;

  return (
    <div>
      <div className="between">
        <h1>{t("earnings")}</h1>
        {data && data.orders.length > 0 && (
          <button className="ghost" onClick={() =>
            downloadCsv("/auth/me/earnings.csv", "kissansetu-earnings.csv").catch((e) => setErr(e.message))}>
            {t("ea_download_csv")}
          </button>
        )}
      </div>
      {err && <div className="error">{err}</div>}
      {data && (
        <>
          <div className="grid" style={{ marginBottom: 16 }}>
            {[[t("ea_gross"), data.totals.gross], [t("ea_commission_pct"), data.totals.commission],
              [t("ea_net"), data.totals.net], [t("ea_paid"), data.totals.paid]].map(([label, val]) => (
              <div className="card" key={label}>
                <div className="muted" style={{ fontSize: 13 }}>{label}</div>
                <div className="price" style={{ fontSize: 22 }}>₹{val}</div>
              </div>
            ))}
          </div>
          <WithdrawCard />
          <h2>{t("ea_sales")}</h2>
          {data.orders.length === 0 ? (
            <p className="muted">{t("ea_no_sales")}</p>
          ) : (
            <table>
              <thead>
                <tr><th>{t("ea_col_order")}</th><th>{t("ea_col_gross")}</th><th>{t("ea_col_commission")}</th><th>{t("ea_col_net")}</th><th>{t("ea_col_payout")}</th></tr>
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
