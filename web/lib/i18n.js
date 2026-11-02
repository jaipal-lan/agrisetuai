// Minimal Telugu-first / English dictionary. Language is stored per-viewer.
import { createContext, useContext, useEffect, useState } from "react";

const STRINGS = {
  te: {
    app_name: "అగ్రిసేతు AI",
    tagline: "రైతు నుండి కొనుగోలుదారు వరకు — ధృవీకరించిన మార్కెట్",
    marketplace: "మార్కెట్",
    sell: "అమ్మకం",
    requests: "అభ్యర్థనలు",
    advisory: "పంట సలహా",
    insights: "ధరలు & పథకాలు",
    support: "సహాయం",
    my_offers: "నా ఆఫర్‌లు",
    my_orders: "నా ఆర్డర్‌లు",
    admin: "అడ్మిన్",
    login: "లాగిన్",
    logout: "లాగ్ అవుట్",
    phone: "ఫోన్ నంబర్",
    send_otp: "OTP పంపండి",
    enter_otp: "OTP నమోదు చేయండి",
    verify: "ధృవీకరించండి",
    role: "పాత్ర",
    name: "పేరు",
    search: "వెతకండి",
    commodity: "పంట",
    price: "ధర",
    quantity: "పరిమాణం",
    available: "అందుబాటులో",
    make_offer: "ఆఫర్ ఇవ్వండి",
    asking_price: "అడిగే ధర",
    create_listing: "కొత్త లిస్టింగ్",
    publish: "ప్రచురించు",
    status: "స్థితి",
    per_kg: "/కేజీ",
    loading: "లోడ్ అవుతోంది…",
  },
  en: {
    app_name: "AgriSetuAI",
    tagline: "Farmer to buyer — a verified marketplace",
    marketplace: "Marketplace",
    sell: "Sell",
    requests: "Requests",
    advisory: "Crop advice",
    insights: "Prices & schemes",
    support: "Support",
    my_offers: "My offers",
    my_orders: "My orders",
    admin: "Admin",
    login: "Login",
    logout: "Logout",
    phone: "Phone number",
    send_otp: "Send OTP",
    enter_otp: "Enter OTP",
    verify: "Verify",
    role: "Role",
    name: "Name",
    search: "Search",
    commodity: "Commodity",
    price: "Price",
    quantity: "Quantity",
    available: "Available",
    make_offer: "Make an offer",
    asking_price: "Asking price",
    create_listing: "New listing",
    publish: "Publish",
    status: "Status",
    per_kg: "/kg",
    loading: "Loading…",
  },
};

const I18nContext = createContext({ lang: "te", t: (k) => k, setLang: () => {} });

export function I18nProvider({ children }) {
  const [lang, setLangState] = useState("te");
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("agri_lang");
      if (saved) setLangState(saved);
    } catch {}
  }, []);
  const setLang = (l) => {
    setLangState(l);
    try {
      window.localStorage.setItem("agri_lang", l);
    } catch {}
  };
  const t = (key) => (STRINGS[lang] && STRINGS[lang][key]) || STRINGS.en[key] || key;
  return (
    <I18nContext.Provider value={{ lang, t, setLang }}>
      {children}
    </I18nContext.Provider>
  );
}

export const useI18n = () => useContext(I18nContext);
