import Link from "next/link";
import { useEffect, useState } from "react";

import { api, downloadCsv, getUser } from "../lib/api";
import { GROUPS, roleGate } from "../lib/roles";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";

// Farmer cash-out: shows withdrawable balance and lets them request a payout to
// their verified account; finance approves (disburses) or rejects.
function WithdrawCard() {
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
      setMsg("Withdrawal requested — finance will process it to your payout account.");
      load();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  if (!bal) return null;
  return (
    <>
      <h2>Withdraw</h2>
      <div className="card">
        <div className="between" style={{ flexWrap: "wrap", gap: 10 }}>
          <div>
            <div className="muted" style={{ fontSize: 13 }}>Available to withdraw</div>
            <div className="price" style={{ fontSize: 26 }}>₹{bal.available}</div>
            <div className="muted" style={{ fontSize: 12 }}>Paid out so far: ₹{bal.paid_total}</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <button disabled={busy || !bal.can_request} onClick={request}>Request withdrawal</button>
            {!bal.account_verified && (
              <div className="muted" style={{ fontSize: 12, marginTop: 6, maxWidth: 220 }}>
                {bal.has_account ? "Your payout account is awaiting verification."
                  : <>Add a payout account in <Link href="/profile">your profile</Link> first.</>}
              </div>
            )}
            {bal.account_verified && bal.identity_verified === false && (
              <div className="muted" style={{ fontSize: 12, marginTop: 6, maxWidth: 220 }}>
                Verify your identity before withdrawing — upload a government photo ID under{" "}
                <Link href="/profile">Identity verification</Link> and wait for approval.
              </div>
            )}
            {bal.account_verified && Number(bal.pending_withdrawal) > 0 && (
              <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
                A withdrawal of ₹{bal.pending_withdrawal} is already pending.
              </div>
            )}
            {bal.account_verified && Number(bal.pending_withdrawal) === 0 && Number(bal.available) === 0 && (
              <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>No balance to withdraw yet.</div>
            )}
          </div>
        </div>
        {err && <div className="error" style={{ marginTop: 8 }}>{err}</div>}
        {msg && <div className="ok" style={{ marginTop: 8 }}>{msg}</div>}
        {list.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div className="muted" style={{ fontSize: 13, marginBottom: 4 }}>Recent withdrawals</div>
            {list.map((w) => (
              <div key={w.id} className="between" style={{ padding: "6px 0", borderBottom: "1px solid var(--line)", fontSize: 14 }}>
                <span>₹{w.amount} <span className="muted">· {w.method || "—"} {w.account_masked || ""}</span></span>
                <span className={`badge ${w.status === "paid" ? "green" : w.status === "rejected" ? "amber" : "grey"}`}>{w.status}</span>
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
        <h1>Earnings</h1>
        {data && data.orders.length > 0 && (
          <button className="ghost" onClick={() =>
            downloadCsv("/auth/me/earnings.csv", "kissansetu-earnings.csv").catch((e) => setErr(e.message))}>
            ⬇ Download CSV
          </button>
        )}
      </div>
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
          <WithdrawCard />
          <h2>Sales</h2>
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
