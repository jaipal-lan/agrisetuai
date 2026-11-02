import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { useI18n } from "../lib/i18n";

// Human-readable benefit lines, built from the benefits JSON snapshot.
function benefitLines(b, audience) {
  if (!b) return [];
  const out = [];
  if (audience === "farmer") {
    out.push(
      b.max_active_listings >= 100
        ? "Unlimited active listings"
        : `${b.max_active_listings} active listings`
    );
  } else {
    out.push(
      b.max_active_rfqs >= 200
        ? "Unlimited open requests"
        : `${b.max_active_rfqs} open requests`
    );
  }
  if (b.fee_discount_pct > 0) out.push(`${b.fee_discount_pct}% off service fees`);
  if (b.featured_listings > 0) out.push(`${b.featured_listings} featured listings`);
  if (b.rfq_boost) out.push(audience === "farmer" ? "Priority in buyer search" : "Priority matching");
  if (b.advisory_full) out.push("Full AI crop advisory");
  if (b.priority_support) out.push("Priority support");
  return out;
}

export default function Subscriptions() {
  const { t, lang } = useI18n();
  const [user, setUser] = useState(null);
  const [plans, setPlans] = useState([]);
  const [me, setMe] = useState(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  // Which audience's plans to show. Default to the logged-in user's audience.
  const [tab, setTab] = useState("farmer");

  async function load() {
    try {
      const all = await api("/subscriptions/plans");
      setPlans(all);
    } catch (e) {
      setErr(e.message);
    }
    const u = getUser();
    setUser(u);
    if (u) {
      try {
        const m = await api("/subscriptions/me");
        setMe(m);
        if (m.audience) setTab(m.audience);
      } catch {}
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function subscribe(code) {
    setErr(null);
    setMsg(null);
    setBusy(code);
    try {
      await api("/subscriptions/subscribe", { method: "POST", body: { plan_code: code } });
      const m = await api("/subscriptions/me");
      setMe(m);
      setMsg(t("subscribed"));
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy("");
    }
  }

  const shown = plans.filter((p) => p.audience === tab);
  const activeCode = me && me.subscription ? me.subscription.plan_code : null;

  function pname(p) {
    return lang === "te" && p.name_te ? p.name_te : p.name;
  }

  return (
    <div>
      <h1>{t("plans")}</h1>
      <p className="tagline">{t("choose_plan")}</p>

      {me && me.subscription && (
        <div className="ok" style={{ marginBottom: 16 }}>
          {t("current_plan")}: <b>{me.subscription.plan_name}</b> · {t("active_until")}{" "}
          {new Date(me.subscription.expires_at).toLocaleDateString()}
        </div>
      )}
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok">{msg}</div>}

      <div className="row" style={{ marginBottom: 20 }}>
        <button
          className={tab === "farmer" ? "" : "ghost"}
          onClick={() => setTab("farmer")}
        >
          {t("for_farmers")}
        </button>
        <button
          className={tab === "buyer" ? "" : "ghost"}
          onClick={() => setTab("buyer")}
        >
          {t("for_buyers")}
        </button>
      </div>

      <div className="grid">
        {shown.map((p) => {
          const isActive = p.code === activeCode;
          const canBuy = user && me && me.audience === p.audience;
          return (
            <div className="card" key={p.code} style={isActive ? { borderColor: "var(--green-600)", borderWidth: 2 } : {}}>
              <div className="between">
                <h3>{pname(p)}</h3>
                {isActive && <span className="badge">{t("subscribed")}</span>}
              </div>
              <div className="price" style={{ margin: "6px 0 14px" }}>
                {p.price > 0 ? (
                  <>₹{p.price}<small> /{t("month")}</small></>
                ) : (
                  <>{t("free")}</>
                )}
              </div>
              <ul style={{ paddingLeft: 18, margin: "0 0 16px", fontSize: 14, lineHeight: 1.9 }}>
                {benefitLines(p.benefits, p.audience).map((line, i) => (
                  <li key={i}>{line}</li>
                ))}
              </ul>
              {!user ? (
                <Link href="/login" className="btn">{t("login_to_subscribe")}</Link>
              ) : !canBuy ? (
                <button className="ghost" disabled title="This plan is for a different account type">
                  {p.audience === "farmer" ? t("for_farmers") : t("for_buyers")}
                </button>
              ) : isActive ? (
                <button disabled>{t("subscribed")}</button>
              ) : (
                <button onClick={() => subscribe(p.code)} disabled={busy === p.code}>
                  {busy === p.code ? t("loading") : t("subscribe")}
                </button>
              )}
            </div>
          );
        })}
      </div>

      <p className="disclaimer" style={{ marginTop: 20 }}>
        Payments are mock in this pilot. Benefits are snapshotted when you subscribe, so later
        plan changes won't alter an active membership.
      </p>
    </div>
  );
}
