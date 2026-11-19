import Head from "next/head";
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
    router.push("/inbox");
  }
  return (
    <button className="pill" aria-label="notifications" onClick={open}>
      🔔{count > 0 ? <span className="bell-badge">{count}</span> : null}
    </button>
  );
}

// A compact top-level dropdown: a labelled button that reveals its links.
// Closes on outside click and on navigation. `items` are {href, label}; falsy
// entries are ignored so callers can inline role conditions.
function Menu({ label, items }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const list = (items || []).filter(Boolean);

  useEffect(() => { setOpen(false); }, [router.asPath]);
  useEffect(() => {
    function onDoc(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  if (!list.length) return null;
  const active = list.some((it) => router.pathname === it.href);
  return (
    <div className={`navmenu${open ? " open" : ""}`} ref={ref}>
      <button type="button" className={`navmenu-btn${active ? " active" : ""}`}
              aria-haspopup="true" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {label} <span className="caret" aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="navmenu-panel" role="menu">
          {list.map((it) => (
            <Link key={it.href} href={it.href} role="menuitem"
                  className={`navmenu-item${router.pathname === it.href ? " active" : ""}`}>
              {it.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function Nav() {
  const { t, lang, setLang } = useI18n();
  const router = useRouter();
  const [user, setUser] = useState(null);

  useEffect(() => {
    setUser(getUser());
  }, [router.pathname]);

  const staff = user && ["superadmin", "field_manager", "field_leader"].includes(user.role);
  const seller = user && user.role === "farmer";
  const buyer = user && ["buyer_household", "buyer_business"].includes(user.role);
  const shopper = buyer || seller; // the roles that browse/negotiate/trade
  const agent = user && ["field_agent", "field_leader", "field_manager", "superadmin"].includes(user.role);
  const lead = user && ["field_leader", "field_manager", "superadmin"].includes(user.role);
  const carrier = user && ["transport", "field_leader", "field_manager", "superadmin"].includes(user.role);
  const opsOnly = user && !shopper; // staff/agent/transport who don't browse/trade

  // A tiny helper so role conditions can be inlined inside the item lists.
  const it = (cond, href, label) => (cond ? { href, label } : null);

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
      <Link href={user ? "/dashboard" : "/"} className="brand">
        <span className="brand-mark">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 21c0-6 3-10 8-12-1 7-4 10-8 12z" fill="#86efac" />
            <path d="M12 21C7 18 4 12 4 5c6 1 9 6 9 12" fill="#22c55e" />
            <path d="M12 21v-9" stroke="#dcfce7" strokeWidth="1.4" strokeLinecap="round" />
          </svg>
          {t("app_name")}
        </span>
      </Link>

      {user && <Link href="/dashboard">{t("dashboard")}</Link>}

      {/* Guests: a few direct links. Logged-in users: grouped menus. */}
      {!user && <Link href="/">{t("marketplace")}</Link>}
      {!user && <Link href="/prices">{t("market_prices")}</Link>}
      {!user && <Link href="/track">Track</Link>}

      {shopper && <Menu label={t("buy")} items={[
        it(true, "/", t("marketplace")),
        it(true, "/prices", t("market_prices")),
        it(true, "/requests", t("requests")),
        it(true, "/offers", t("my_offers")),
      ]} />}

      {seller && <Menu label={t("sell")} items={[
        it(true, "/sell", t("sell")),
        it(true, "/earnings", t("earnings")),
      ]} />}

      {shopper && <Menu label={t("my_orders")} items={[
        it(true, "/orders", t("my_orders")),
        it(true, "/invoices", t("invoices")),
        it(true, "/track", "Track"),
      ]} />}

      {opsOnly && <Menu label={t("work")} items={[
        it(agent, "/agent", t("agent_jobs")),
        it(lead, "/team", t("team")),
        it(carrier, "/transport", t("transport")),
        it(agent || carrier, "/scan", "Scan"),
        it(staff, "/admin", t("admin")),
        it(true, "/requests", t("requests")),
        it(true, "/prices", t("market_prices")),
        it(true, "/track", "Track"),
      ]} />}

      {/* Staff who also need the admin console but are shoppers (rare) still get it. */}
      {staff && shopper && <Link href="/admin">{t("admin")}</Link>}

      {user && <Menu label={t("account")} items={[
        it(true, "/inbox", t("inbox")),
        it(true, "/support", t("support")),
        it(true, "/profile", t("profile")),
      ]} />}

      {user && user.onboarding_complete === false && (
        <Link href="/onboarding" className="pill" style={{ background: "var(--amber-600)", color: "#fff" }}>
          {t("complete_profile")}
        </Link>
      )}
      <span className="spacer" />
      {user && <Bell />}
      <ThemeToggle />
      <LangToggle lang={lang} setLang={setLang} />
      {user ? (
        <button className="pill" onClick={doLogout}>{t("logout")}</button>
      ) : (
        <>
          <Link href="/login" className="pill">{t("login")}</Link>
          <Link href="/register" className="pill" style={{ background: "var(--green-600, #16a34a)", color: "#fff" }}>
            {t("register")}
          </Link>
        </>
      )}
    </nav>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState("light");
  useEffect(() => {
    let t = "light";
    try { t = window.localStorage.getItem("agri_theme") || "light"; } catch {}
    setTheme(t);
    document.documentElement.dataset.theme = t;
  }, []);
  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try { window.localStorage.setItem("agri_theme", next); } catch {}
  }
  return (
    <button className="pill" aria-label="theme" onClick={toggle}>
      {theme === "dark" ? "☀️" : "🌙"}
    </button>
  );
}

function LangToggle({ lang, setLang }) {
  const order = ["te", "en", "hi"];
  const labels = { te: "తెలుగు", en: "English", hi: "हिन्दी" };
  const next = order[(order.indexOf(lang) + 1) % order.length];
  return (
    <button className="pill" aria-label="language" onClick={() => setLang(next)}>
      {labels[next]}
    </button>
  );
}

export default function App({ Component, pageProps }) {
  return (
    <I18nProvider>
      <ToastProvider>
        <Head>
          <title>AgriSetuAI — verified farm-to-market</title>
          <meta name="description" content="Door-to-door farm-to-market: farmers sell, buyers order, we verify, pack and deliver across Andhra Pradesh & Telangana." />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <meta name="theme-color" content="#14532d" />
          <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
          <link rel="apple-touch-icon" href="/favicon.svg" />
          <link rel="manifest" href="/manifest.webmanifest" />
        </Head>
        <Nav />
        <div className="container">
          <Component {...pageProps} />
        </div>
      </ToastProvider>
    </I18nProvider>
  );
}
