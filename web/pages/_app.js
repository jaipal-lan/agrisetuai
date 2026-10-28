import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { getUser, logout } from "../lib/api";
import { I18nProvider, useI18n } from "../lib/i18n";
import "../styles/globals.css";

function Nav() {
  const { t, lang, setLang } = useI18n();
  const router = useRouter();
  const [user, setUser] = useState(null);

  useEffect(() => {
    setUser(getUser());
  }, [router.pathname]);

  const staff = user && ["superadmin", "finance", "mandal_manager"].includes(user.role);
  const seller = user && ["farmer", "fpo"].includes(user.role);

  return (
    <nav className="nav">
      <Link href="/" className="brand">{t("app_name")}</Link>
      <Link href="/">{t("marketplace")}</Link>
      {seller && <Link href="/sell">{t("sell")}</Link>}
      {user && <Link href="/offers">{t("my_offers")}</Link>}
      {user && <Link href="/orders">{t("my_orders")}</Link>}
      {staff && <Link href="/admin">{t("admin")}</Link>}
      <span className="spacer" />
      <button
        className="pill"
        onClick={() => setLang(lang === "te" ? "en" : "te")}
        aria-label="language"
      >
        {lang === "te" ? "English" : "తెలుగు"}
      </button>
      {user ? (
        <button
          className="pill"
          onClick={() => {
            logout();
            setUser(null);
            router.push("/");
          }}
        >
          {t("logout")}
        </button>
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
