import Link from "next/link";
import { useRouter } from "next/router";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

import { api, getToken, getUser, logout } from "../lib/api";
import { I18nProvider, useI18n } from "../lib/i18n";
import "../styles/globals.css";

// ---- Toasts -------------------------------------------------------------
const ToastCtx = createContext({ addToast: () => {} });
export const useToast = () => useContext(ToastCtx);

function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const addToast = useCallback((msg, kind = "info") => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, msg, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000);
  }, []);
  return (
    <ToastCtx.Provider value={{ addToast }}>
      {children}
      <div className="toast-wrap">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`} onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}>
            🔔 {t.msg}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

function Bell() {
  const router = useRouter();
  const { addToast } = useToast();
  const [count, setCount] = useState(0);
  const seen = useRef(null); // highest notification id already seen

  useEffect(() => {
    let alive = true;
    async function tick() {
      if (!getToken() || (typeof document !== "undefined" && document.hidden)) return;
      try {
        const rows = await api("/auth/notifications");
        if (!alive) return;
        setCount(rows.filter((n) => !n.read_at).length);
        const maxId = rows.length ? Math.max(...rows.map((n) => n.id)) : 0;
        if (seen.current === null) {
          seen.current = maxId; // first load: don't toast history
        } else if (maxId > seen.current) {
          rows.filter((n) => n.id > seen.current && !n.read_at)
            .forEach((n) => addToast(n.title));
          seen.current = maxId;
        }
      } catch {}
    }
    tick();
    const id = setInterval(tick, 15000);
    return () => { alive = false; clearInterval(id); };
  }, [addToast]);

  async function open() {
    try { await api("/auth/notifications/read", { method: "POST" }); } catch {}
    setCount(0);
    router.push("/support");
  }
  return (
    <button className="pill" aria-label="notifications" onClick={open}>
      🔔{count > 0 ? <span className="bell-badge">{count}</span> : null}
    </button>
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
  const carrier = user && ["transport", "mandal_manager", "superadmin"].includes(user.role);

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
      {seller && <Link href="/earnings">{t("earnings")}</Link>}
      {(buyer || seller) && <Link href="/requests">{t("requests")}</Link>}
      {(seller || advisor) && <Link href="/advisory">{t("advisory")}</Link>}
      {agent && <Link href="/agent">{t("agent_jobs")}</Link>}
      {carrier && <Link href="/transport">{t("transport")}</Link>}
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
      <ToastProvider>
        <Nav />
        <div className="container">
          <Component {...pageProps} />
        </div>
      </ToastProvider>
    </I18nProvider>
  );
}
