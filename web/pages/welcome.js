import Link from "next/link";

import { useI18n } from "../lib/i18n";

const FEATURES = [
  { icon: "🤝", en: "Two-way price negotiation", te: "రెండు వైపులా ధర బేరసారం",
    den: "Buyers and farmers counter-offer with a full, tamper-proof version history.",
    dte: "కొనుగోలుదారులు, రైతులు మార్పులేని చరిత్రతో బేరం చేస్తారు." },
  { icon: "🔬", en: "Verified quality", te: "ధృవీకరించిన నాణ్యత",
    den: "A field agent inspects and grades each lot before the buyer approves.",
    dte: "ప్రతి లాట్‌ను ఫీల్డ్ ఏజెంట్ తనిఖీ చేసి గ్రేడ్ ఇస్తారు." },
  { icon: "🌶️", en: "Grains, pulses & spices", te: "ధాన్యాలు, పప్పులు & మసాలాలు",
    den: "Paddy, rice, dals, turmeric, chilli, pepper, coriander, cumin and more.",
    dte: "వరి, బియ్యం, పప్పులు, పసుపు, మిర్చి, మిరియాలు, ధనియాలు, జీలకర్ర." },
  { icon: "📦", en: "Packing to delivery", te: "ప్యాకింగ్ నుండి డెలివరీ",
    den: "QR-tracked lots, shipment milestones and buyer acceptance before payout.",
    dte: "QR లాట్‌లు, షిప్‌మెంట్ దశలు, చెల్లింపుకు ముందు కొనుగోలుదారు అంగీకారం." },
  { icon: "🌱", en: "AI crop advisory", te: "AI పంట సలహా",
    den: "Uncertainty-first triage sourced from reviewed advisories — never an invented dose.",
    dte: "సమీక్షించిన సలహాల ఆధారంగా — ఊహించిన మందు మోతాదు ఎప్పుడూ ఇవ్వదు." },
  { icon: "💳", en: "Transparent fees", te: "పారదర్శక ఫీజులు",
    den: "Every charge is itemised and posted to an auditable double-entry ledger.",
    dte: "ప్రతి ఛార్జీ విడివిడిగా, ఆడిట్ చేయదగిన లెడ్జర్‌లో నమోదు." },
];

const STEPS = {
  en: [
    "Farmer lists produce; a field agent verifies quality.",
    "Buyer negotiates a price, or posts a request farmers answer.",
    "Lot is packed, shipped and accepted — then the farmer is paid.",
  ],
  te: [
    "రైతు పంటను జాబితా చేస్తారు; ఫీల్డ్ ఏజెంట్ నాణ్యత ధృవీకరిస్తారు.",
    "కొనుగోలుదారు ధర బేరం చేస్తారు లేదా అభ్యర్థన పోస్ట్ చేస్తారు.",
    "లాట్ ప్యాక్, రవాణా, అంగీకారం — తర్వాత రైతుకు చెల్లింపు.",
  ],
};

export default function Welcome() {
  const { t, lang } = useI18n();
  const d = (o) => (lang === "te" ? o.te : o.en);
  const dd = (o) => (lang === "te" ? o.dte : o.den);

  return (
    <div>
      <section className="hero">
        <h1>{t("app_name")}</h1>
        <p>{t("tagline")} — {lang === "te"
          ? "ఆంధ్రప్రదేశ్ & తెలంగాణ రైతులకు AI సలహా + ధృవీకరించిన మార్కెట్."
          : "AI advisory plus a verified farm-to-market for Andhra Pradesh & Telangana."}</p>
        <div className="row">
          <Link href="/" className="btn light">{t("browse_market")}</Link>
          <Link href="/subscriptions" className="btn">{t("view_plans")}</Link>
          <Link href="/login" className="btn">{t("get_started")}</Link>
        </div>
      </section>

      <div className="grid">
        {FEATURES.map((f, i) => (
          <div className="card" key={i}>
            <div className="feature-icon">{f.icon}</div>
            <h3>{d(f)}</h3>
            <div className="muted" style={{ fontSize: 14 }}>{dd(f)}</div>
          </div>
        ))}
      </div>

      <h2 style={{ marginTop: 36 }}>{t("how_it_works")}</h2>
      <div className="grid steps">
        {STEPS[lang === "te" ? "te" : "en"].map((s, i) => (
          <div className="card" key={i}>
            <div style={{ fontSize: 15 }}>{s}</div>
          </div>
        ))}
      </div>

      <div className="card" style={{ marginTop: 32, textAlign: "center", padding: 32 }}>
        <h2 style={{ marginTop: 0 }}>{t("choose_plan")}</h2>
        <p className="muted" style={{ maxWidth: 520, margin: "0 auto 18px" }}>
          {lang === "te"
            ? "రైతులకు, కొనుగోలుదారులకు — ఉచిత ప్లాన్‌తో మొదలుపెట్టండి."
            : "Plans for farmers and buyers — start free and upgrade when you grow."}
        </p>
        <Link href="/subscriptions" className="btn">{t("view_plans")}</Link>
      </div>
    </div>
  );
}
