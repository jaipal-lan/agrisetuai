// Localise a data value (commodity / market name that comes from the backend in
// English) into the viewer's language. Known names use an accurate native word;
// anything unknown is phonetically transliterated into the native script so it
// still reads in the viewer's language with the English pronunciation. Callers
// keep the English text as a subtitle so nothing is ever lost.

// ---- Curated, accurate native names for the common commodities -----------
const CURATED = {
  te: {
    tomato: "టమాటో", onion: "ఉల్లిపాయ", potato: "బంగాళాదుంప", paddy: "వరి", rice: "బియ్యం",
    wheat: "గోధుమ", maize: "మొక్కజొన్న", chilli: "మిరప", turmeric: "పసుపు", brinjal: "వంకాయ",
    banana: "అరటి", mango: "మామిడి", apple: "యాపిల్", coconut: "కొబ్బరి", groundnut: "వేరుశెనగ",
    cotton: "పత్తి", soybean: "సోయాబీన్", sugarcane: "చెరకు", garlic: "వెల్లుల్లి", ginger: "అల్లం",
    carrot: "క్యారెట్", cabbage: "క్యాబేజీ", cauliflower: "కాలీఫ్లవర్", grapes: "ద్రాక్ష",
    orange: "నారింజ", papaya: "బొప్పాయి", guava: "జామ", lemon: "నిమ్మ", cucumber: "దోసకాయ",
    pumpkin: "గుమ్మడికాయ", spinach: "పాలకూర", coriander: "కొత్తిమీర", barley: "బార్లీ",
    jowar: "జొన్న", bajra: "సజ్జ", millets: "చిరుధాన్యాలు", ragi: "రాగి", peas: "బటానీ",
    beans: "చిక్కుడు", okra: "బెండకాయ", ashgourd: "బూడిదగుమ్మడి", amaranthus: "తోటకూర",
    amla: "ఉసిరి", arecanut: "వక్క", gram: "శనగ", mustard: "ఆవాలు", sunflower: "ప్రొద్దుతిరుగుడు",
    pomegranate: "దానిమ్మ", watermelon: "పుచ్చకాయ", drumstick: "మునగకాయ", radish: "ముల్లంగి",
    beetroot: "బీట్‌రూట్", pineapple: "అనాస", jackfruit: "పనస",
  },
  hi: {
    tomato: "टमाटर", onion: "प्याज़", potato: "आलू", paddy: "धान", rice: "चावल", wheat: "गेहूँ",
    maize: "मक्का", chilli: "मिर्च", turmeric: "हल्दी", brinjal: "बैंगन", banana: "केला",
    mango: "आम", apple: "सेब", coconut: "नारियल", groundnut: "मूँगफली", cotton: "कपास",
    soybean: "सोयाबीन", sugarcane: "गन्ना", garlic: "लहसुन", ginger: "अदरक", carrot: "गाजर",
    cabbage: "पत्तागोभी", cauliflower: "फूलगोभी", grapes: "अंगूर", orange: "संतरा",
    papaya: "पपीता", guava: "अमरूद", lemon: "नींबू", cucumber: "खीरा", pumpkin: "कद्दू",
    spinach: "पालक", coriander: "धनिया", barley: "जौ", jowar: "ज्वार", bajra: "बाजरा",
    millets: "मोटा अनाज", ragi: "रागी", peas: "मटर", beans: "सेम", okra: "भिंडी",
    gram: "चना", mustard: "सरसों", sunflower: "सूरजमुखी", pomegranate: "अनार",
    watermelon: "तरबूज़", drumstick: "सहजन", radish: "मूली", pineapple: "अनानास",
  },
};

// ---- Phonetic transliteration (approximate) ------------------------------
const TE_MAPS = {
  vinit: { a: "అ", aa: "ఆ", i: "ఇ", ii: "ఈ", u: "ఉ", uu: "ఊ", e: "ఎ", ee: "ఈ", ai: "ఐ",
           o: "ఒ", oo: "ఊ", au: "ఔ", ea: "ఈ", ay: "ఐ", ou: "ఔ" },
  vmatra: { a: "", aa: "ా", i: "ి", ii: "ీ", u: "ు", uu: "ూ", e: "ె", ee: "ీ", ai: "ై",
            o: "ొ", oo: "ూ", au: "ౌ", ea: "ీ", ay: "ై", ou: "ౌ" },
  cons: { k: "క", kh: "ఖ", g: "గ", gh: "ఘ", ch: "చ", j: "జ", jh: "ఝ", t: "ట", th: "థ",
          d: "డ", dh: "ధ", n: "న", p: "ప", ph: "ఫ", f: "ఫ", b: "బ", bh: "భ", m: "మ",
          y: "య", r: "ర", l: "ల", v: "వ", w: "వ", s: "స", sh: "శ", h: "హ", c: "క",
          q: "క", x: "క్స", z: "జ" },
  virama: "్",
};
const HI_MAPS = {
  vinit: { a: "अ", aa: "आ", i: "इ", ii: "ई", u: "उ", uu: "ऊ", e: "ए", ee: "ई", ai: "ऐ",
           o: "ओ", oo: "ऊ", au: "औ", ea: "ई", ay: "ऐ", ou: "औ" },
  vmatra: { a: "", aa: "ा", i: "ि", ii: "ी", u: "ु", uu: "ू", e: "े", ee: "ी", ai: "ै",
            o: "ो", oo: "ू", au: "ौ", ea: "ी", ay: "ै", ou: "ौ" },
  cons: { k: "क", kh: "ख", g: "ग", gh: "घ", ch: "च", j: "ज", jh: "झ", t: "ट", th: "थ",
          d: "ड", dh: "ध", n: "न", p: "प", ph: "फ", f: "फ", b: "ब", bh: "भ", m: "म",
          y: "य", r: "र", l: "ल", v: "व", w: "व", s: "स", sh: "श", h: "ह", c: "क",
          q: "क", x: "क्स", z: "ज़" },
  virama: "्",
};

const TWO_CONS = { ch: 1, sh: 1, th: 1, ph: 1, gh: 1, kh: 1, bh: 1, dh: 1, jh: 1 };
const TWO_VOWEL = { aa: 1, ee: 1, oo: 1, ai: 1, au: 1, ay: 1, ou: 1, ea: 1 };
const isVowel = (c) => "aeiou".includes(c);

function transliterate(word, maps) {
  const { cons, vinit, vmatra, virama } = maps;
  let out = "";
  let i = 0;
  while (i < word.length) {
    const two = word.substr(i, 2);
    if (!isVowel(word[i])) {
      let glyph, len;
      if (TWO_CONS[two] && cons[two]) { glyph = cons[two]; len = 2; }
      else if (cons[word[i]]) { glyph = cons[word[i]]; len = 1; }
      else { i += 1; continue; }        // unknown char — skip
      let j = i + len;
      const vtwo = word.substr(j, 2);
      let vk = null, vlen = 0;
      if (TWO_VOWEL[vtwo] && vmatra[vtwo] != null) { vk = vtwo; vlen = 2; }
      else if (isVowel(word[j])) { vk = word[j]; vlen = 1; }
      if (vk) { out += glyph + vmatra[vk]; i = j + vlen; }
      else { out += glyph + virama; i = j; }   // consonant cluster / word end
    } else {
      let vk, vlen;
      if (TWO_VOWEL[two] && vinit[two]) { vk = two; vlen = 2; }
      else { vk = word[i]; vlen = 1; }
      out += (vinit[vk] || "");
      i += vlen;
    }
  }
  return out || word;
}

// Localise a backend-supplied name. English is returned unchanged; other
// languages return an accurate curated name where known, else a per-word
// phonetic transliteration (punctuation/brackets/digits are preserved).
export function localizeName(name, lang) {
  if (!name || lang === "en") return name;
  const maps = lang === "hi" ? HI_MAPS : lang === "te" ? TE_MAPS : null;
  if (!maps) return name;
  const curated = CURATED[lang] || {};
  const whole = name.trim().toLowerCase();
  if (curated[whole]) return curated[whole];
  return name.replace(/[A-Za-z]+/g, (w) => curated[w.toLowerCase()] || transliterate(w.toLowerCase(), maps));
}
