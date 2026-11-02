import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, getUser, logout } from "../lib/api";
import { I18nProvider, useI18n } from "../lib/i18n";
import "../styles/globals.css";

function Bell() {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let alive = true;
    async function tick() {
      try {
        const rows = await api("/auth/notifications");
        if (alive) setCount(rows.filter((n) => !n.read_at).length);
      } catch {}
    }
    tick();
    const id = setInterval(tick, 20000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);
  return (
    <Link href="/support" className="pill" aria-label="notifications">
      🔔{count > 0 ? <span className="bell-badge">{count}</span> : null}
    </Link>
  );
}

function Nav() {
  const { t, lang, setLang } = useI18n();
  const router = useRouter();
  const [user, setUser] = useState(null);

  useEffect(() => {
    setUser(getUser());
  }, [router.pathname]);

  const staff = user && ["superadmin", "finance", "mandal_manager", "support"].includes(user.role);
  const seller = user && ["farmer", "fpo"].includes(user.role);
  const buyer = user && ["buyer_household", "buyer_business"].includes(user.role);
  const advisor = user && ["agronomist", "superadmin", "mandal_manager", "field_agent"].includes(user.role);
  const agent = user && ["field_agent", "mandal_manager", "superadmin"].includes(user.role);

  async function doLogout() {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {}
    logout();
    setUser(null);
    router.push("/");
  }

  return (
    <nav className="nav">
      <Link href="/welcome" className="brand">{t("app_name")}</Link>
      <Link href="/">{t("marketplace")}</Link>
      {seller && <Link href="/sell">{t("sell")}</Link>}
      {(buyer || seller) && <Link href="/requests">{t("requests")}</Link>}
      {(seller || advisor) && <Link href="/advisory">{t("advisory")}</Link>}
      {agent && <Link href="/agent">{t("agent_jobs")}</Link>}
      <Link href="/insights">{t("insights")}</Link>
      {(!user || buyer || seller) && <Link href="/subscriptions">{t("plans")}</Link>}
      {user && <Link href="/offers">{t("my_offers")}</Link>}
      {user && <Link href="/orders">{t("my_orders")}</Link>}
      {user && <Link href="/support">{t("support")}</Link>}
      {staff && <Link href="/admin">{t("admin")}</Link>}
      <span className="spacer" />
      {user && <Bell />}
      <button
        className="pill"
        onClick={() => setLang(lang === "te" ? "en" : "te")}
        aria-label="language"
      >
        {lang === "te" ? "English" : "తెలుగు"}
      </button>
      {user ? (
        <button className="pill" onClick={doLogout}>{t("logout")}</button>
      ) : (
        <Link href="/login" className="pill">{t("login")}</Link>
      )}
    </nav>
  );
}

export default function App({ Component, pageProps }) {
  return (
    <I18nProvider>
      <Nav />
      <div className="container">
        <Component {...pageProps} />
      </div>
    </I18nProvider>
  );
}
