import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";

// Dashboard cards/actions/role come from the backend in English; map the known
// labels to i18n keys so they follow the language switch (unknown → shown as-is).
const DASH_KEY = {
  "Active listings": "dl_active_listings", "Open negotiations": "dl_open_neg", "Orders selling": "dl_orders_selling",
  "Awaiting payout": "dl_awaiting_payout", "Orders buying": "dl_orders_buying", "Open offers": "dl_open_offers",
  "Orders in progress": "dl_orders_progress", "Open requests (RFQ)": "dl_open_rfq", "Inspections to do": "dl_inspections_todo",
  "My targets": "dl_my_targets", "Upcoming meetings": "dl_upcoming_meetings", "Unassigned inspections": "dl_unassigned_insp",
  "In inspection": "dl_in_inspection", "Field agents": "dl_field_agents", "Active targets": "dl_active_targets",
  "Held at warehouse": "dl_at_warehouse", "GMV (settled)": "dl_gmv", "Open disputes": "dl_open_disputes",
  "Pending payouts": "dl_pending_payouts", "Active deliveries": "dl_active_deliveries", "Earnings (paid)": "dl_earnings_paid",
  "Total orders": "dl_total_orders", "Open listings": "dl_open_listings", "Pending KYC": "dl_pending_kyc", "Unread alerts": "dl_unread_alerts",
  "List produce": "da_list_produce", "Buy produce": "da_buy_produce", "My offers": "my_offers", "My orders": "my_orders",
  "Earnings": "da_earnings", "Invoices": "da_invoices", "Market prices": "market_prices", "Browse market": "browse_market",
  "Post a requirement": "da_post_req", "Inspection jobs": "da_inspection_jobs", "Team console": "da_team_console",
  "Admin console": "da_admin_console", "Disputes & refunds": "da_disputes", "Delivery jobs": "da_delivery_jobs", "My earnings": "da_my_earnings",
  "Farmer": "role_farmer", "Household buyer": "role_household", "Business buyer": "role_business",
  "Field agent": "role_field_agent", "Field leader": "role_field_leader", "Field manager": "role_field_manager",
  "Transport partner": "role_transport", "Superadmin": "role_superadmin",
};

export default function Dashboard() {
  const { t } = useI18n();
  const dl = (label) => (DASH_KEY[label] ? t(DASH_KEY[label]) : label);
  const router = useRouter();
  const [me, setMe] = useState(null);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => { setMe(getUser()); }, []);
  usePoll(() => {
    api("/dashboard").then(setData).catch((e) => setErr(e.message));
  }, 15000);

  if (!me) {
    return (
      <div>
        <h1>{t("app_name")}</h1>
        <p className="muted">{t("login_see_dashboard")}</p>
        <Link href="/login" className="btn">{t("login")}</Link>
      </div>
    );
  }

  return (
    <div>
      <div className="between">
        <div>
          <h1 style={{ marginBottom: 2 }}>{t("welcome_back")}{data?.name ? `, ${data.name}` : ""}</h1>
          {data && <span className="badge">{dl(data.role_label)}</span>}
        </div>
      </div>
      {err && <div className="error">{err}</div>}

      {data?.onboarding_complete === false && (
        <div className="card" style={{ borderLeft: "4px solid var(--amber-600)", marginTop: 12 }}>
          <b>{t("finish_profile")}</b>
          <div className="muted" style={{ fontSize: 13 }}>{t("finish_profile_sub")}</div>
          <div style={{ marginTop: 10 }}>
            <button onClick={() => router.push("/onboarding")}>{t("complete_profile")}</button>
          </div>
        </div>
      )}

      {data && (
        <>
          <div className="grid" style={{ marginTop: 16 }}>
            {data.cards.map((c) => (
              <div
                key={c.label}
                className={`card stat-card${c.alert ? " alert" : ""}`}
                style={{
                  cursor: c.href ? "pointer" : "default",
                  borderLeft: c.alert ? "4px solid var(--amber-600)" : "4px solid var(--green-600)",
                }}
                onClick={() => c.href && router.push(c.href)}
              >
                <div className="stat-icon" aria-hidden="true">{c.icon || "•"}</div>
                <div className="muted" style={{ fontSize: 13 }}>{dl(c.label)}</div>
                <div className="price" style={{ fontSize: 26 }}>{c.value}</div>
                {c.alert && <span className="stat-dot" title="Needs attention" />}
              </div>
            ))}
          </div>

          <h2 style={{ marginTop: 24 }}>{t("quick_actions")}</h2>
          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            {data.actions.map((a) => (
              <button
                key={a.href + a.label}
                className={a.primary ? "" : "ghost"}
                onClick={() => router.push(a.href)}
              >
                {dl(a.label)}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
