import Link from "next/link";

import { useI18n } from "../lib/i18n";

const FEATURES = [
  { icon: "🤝",
    t: { en: "Two-way price negotiation", te: "రెండు వైపులా ధర బేరసారం", hi: "दोतरफ़ा मोल-भाव" },
    d: { en: "Buyers and farmers counter-offer with a full, tamper-proof version history.",
         te: "కొనుగోలుదారులు, రైతులు మార్పులేని చరిత్రతో బేరం చేస్తారు.",
         hi: "खरीदार और किसान छेड़छाड़-रहित इतिहास के साथ मोल-भाव करते हैं।" } },
  { icon: "🔬",
    t: { en: "Verified quality", te: "ధృవీకరించిన నాణ్యత", hi: "सत्यापित गुणवत्ता" },
    d: { en: "A field agent inspects and grades each lot before the buyer approves.",
         te: "ప్రతి లాట్‌ను ఫీల్డ్ ఏజెంట్ తనిఖీ చేసి గ్రేడ్ ఇస్తారు.",
         hi: "हर लॉट की जाँच और ग्रेडिंग फ़ील्ड एजेंट करता है, तब खरीदार स्वीकृति देता है।" } },
  { icon: "🌶️",
    t: { en: "Grains, pulses & spices", te: "ధాన్యాలు, పప్పులు & మసాలాలు", hi: "अनाज, दालें और मसाले" },
    d: { en: "Paddy, rice, dals, turmeric, chilli, pepper, coriander, cumin and more.",
         te: "వరి, బియ్యం, పప్పులు, పసుపు, మిర్చి, మిరియాలు, ధనియాలు, జీలకర్ర.",
         hi: "धान, चावल, दालें, हल्दी, मिर्च, काली मिर्च, धनिया, जीरा और भी।" } },
  { icon: "📦",
    t: { en: "Packing to delivery", te: "ప్యాకింగ్ నుండి డెలివరీ", hi: "पैकिंग से डिलीवरी तक" },
    d: { en: "QR-tracked lots, shipment milestones and buyer acceptance before payout.",
         te: "QR లాట్‌లు, షిప్‌మెంట్ దశలు, చెల్లింపుకు ముందు కొనుగోలుదారు అంగీకారం.",
         hi: "QR-ट्रैक लॉट, शिपमेंट चरण, और भुगतान से पहले खरीदार की स्वीकृति।" } },
  { icon: "🌱",
    t: { en: "AI crop advisory", te: "AI పంట సలహా", hi: "AI फसल सलाह" },
    d: { en: "Uncertainty-first triage sourced from reviewed advisories — never an invented dose.",
         te: "సమీక్షించిన సలహాల ఆధారంగా — ఊహించిన మందు మోతాదు ఎప్పుడూ ఇవ్వదు.",
         hi: "समीक्षित सलाह पर आधारित — कभी मनगढ़ंत दवा मात्रा नहीं।" } },
  { icon: "💳",
    t: { en: "Transparent fees", te: "పారదర్శక ఫీజులు", hi: "पारदर्शी शुल्क" },
    d: { en: "Every charge is itemised and posted to an auditable double-entry ledger.",
         te: "ప్రతి ఛార్జీ విడివిడిగా, ఆడిట్ చేయదగిన లెడ్జర్‌లో నమోదు.",
         hi: "हर शुल्क अलग से, ऑडिट-योग्य डबल-एंट्री लेज़र में दर्ज।" } },
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
  hi: [
    "किसान उपज सूचीबद्ध करता है; फ़ील्ड एजेंट गुणवत्ता सत्यापित करता है।",
    "खरीदार भाव तय करता है, या अनुरोध पोस्ट करता है जिसका किसान जवाब देते हैं।",
    "लॉट पैक, शिप और स्वीकार — फिर किसान को भुगतान।",
  ],
};

const HERO_SUB = {
  en: "AI advisory plus a verified farm-to-market for Andhra Pradesh & Telangana.",
  te: "ఆంధ్రప్రదేశ్ & తెలంగాణ రైతులకు AI సలహా + ధృవీకరించిన మార్కెట్.",
  hi: "आंध्र प्रदेश और तेलंगाना के किसानों के लिए AI सलाह + सत्यापित बाज़ार।",
};

const PLAN_SUB = {
  en: "Plans for farmers and buyers — start free and upgrade when you grow.",
  te: "రైతులకు, కొనుగోలుదారులకు — ఉచిత ప్లాన్‌తో మొదలుపెట్టండి.",
  hi: "किसानों और खरीदारों के लिए योजनाएँ — मुफ़्त से शुरू करें।",
};

export default function Welcome() {
  const { t, lang } = useI18n();
  const L = (o) => o[lang] || o.en; // fall back to English for any missing string

  return (
    <div>
      <section className="hero">
        <h1>{t("app_name")}</h1>
        <p>{t("tagline")} — {L(HERO_SUB)}</p>
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
            <h3>{L(f.t)}</h3>
            <div className="muted" style={{ fontSize: 14 }}>{L(f.d)}</div>
          </div>
        ))}
      </div>

      <h2 style={{ marginTop: 36 }}>{t("how_it_works")}</h2>
      <div className="grid steps">
        {L(STEPS).map((s, i) => (
          <div className="card" key={i}>
            <div style={{ fontSize: 15 }}>{s}</div>
          </div>
        ))}
      </div>

      <div className="card" style={{ marginTop: 32, textAlign: "center", padding: 32 }}>
        <h2 style={{ marginTop: 0 }}>{t("choose_plan")}</h2>
        <p className="muted" style={{ maxWidth: 520, margin: "0 auto 18px" }}>{L(PLAN_SUB)}</p>
        <Link href="/subscriptions" className="btn">{t("view_plans")}</Link>
      </div>
    </div>
  );
}
