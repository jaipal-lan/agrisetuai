import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, getUser, mediaUrl } from "../lib/api";
import { useI18n } from "../lib/i18n";

// --- per-viewer "shopping area", remembered in localStorage -------------------
const AREA_KEY = "av_area";
const RECENT_KEY = "av_recent";

function readArea() {
  try { return JSON.parse(localStorage.getItem(AREA_KEY) || "null"); } catch { return null; }
}
function readRecent() {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); } catch { return []; }
}

// Seller rating as a compact star + review count, shown where a buyer decides.
function Rating({ value, count, size = 13 }) {
  if (value == null) return null;
  return (
    <span className="rating" style={{ fontSize: size }} title={`${value} from ${count} review${count === 1 ? "" : "s"}`}>
      <span className="rating-star">★</span> {value}
      {count > 0 && <span className="muted"> ({count})</span>}
    </span>
  );
}

// A reusable product-grid card (featured, near-you, full grid all share it).
function ProductCard({ p, lang, t }) {
  const name = lang === "te" && p.commodity_te ? p.commodity_te : p.commodity;
  const available = p.offering_count > 0;
  return (
    <Link href={`/product/${p.commodity_id}`} className="card product-card" style={{ color: "inherit" }}>
      {p.image && <img className="product-thumb" src={mediaUrl(p.image)} alt={name} loading="lazy" />}
      <div className="between">
        <h3>{name}</h3>
        {p.any_verified && <span className="badge">✓ verified</span>}
      </div>
      <div className="muted" style={{ fontSize: 13, marginBottom: 10 }}>
        {p.category} · MOQ {p.min_order_qty} kg
      </div>
      {available ? (
        <>
          <div className="price">
            ₹{p.price_min}{p.price_max !== p.price_min ? `–${p.price_max}` : ""}
            <small> {t("per_kg")}</small>
          </div>
          <div className="between" style={{ marginTop: 6 }}>
            <span className="muted" style={{ fontSize: 14 }}>
              {p.offering_count} farmer{p.offering_count > 1 ? "s" : ""} · {p.place_count} place{p.place_count > 1 ? "s" : ""}
            </span>
            <Rating value={p.seller_rating} count={p.seller_rating_count} />
          </div>
        </>
      ) : (
        <div className="badge grey" style={{ marginTop: 10 }}>Out of stock</div>
      )}
    </Link>
  );
}

// A compact "just listed" card for the fresh strip.
function FreshCard({ f, lang }) {
  const name = lang === "te" && f.commodity_te ? f.commodity_te : f.commodity;
  return (
    <Link href={`/product/${f.commodity_id}`} className="card fresh-card" style={{ color: "inherit" }}>
      {f.image && <img className="fresh-thumb" src={mediaUrl(f.image)} alt={name} loading="lazy" />}
      <div className="between">
        <b>{name}</b>
        {f.agent_verified && <span className="badge">✓</span>}
      </div>
      <div className="price" style={{ fontSize: 18, margin: "4px 0" }}>₹{f.price}<small> /kg</small></div>
      <div className="between">
        <span className="muted" style={{ fontSize: 12 }}>
          {[f.place, f.seller].filter(Boolean).join(" · ")}
        </span>
        <Rating value={f.seller_rating} count={f.seller_rating_count} size={12} />
      </div>
    </Link>
  );
}

export default function Marketplace() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const [me, setMe] = useState(null);

  // Full-grid browse state (active when searching / filtering).
  const [products, setProducts] = useState([]);
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("name");
  const [minRating, setMinRating] = useState(0);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);

  // Curated landing state (shown when not actively searching).
  const [disc, setDisc] = useState(null);
  const [area, setArea] = useState(null);         // {id, name}
  const [mandals, setMandals] = useState([]);
  const [recent, setRecent] = useState([]);

  // Any active search, filter or non-default sort switches to the full grid.
  const browsing = !!(q.trim() || category || minRating || sort !== "name");
  const isBuyer = me && ["buyer_household", "buyer_business"].includes(me.role);

  useEffect(() => {
    setMe(getUser());
    setArea(readArea());
    setRecent(readRecent());
  }, []);

  // Mandals for the "shopping near" picker (buyers only — it's their lens).
  useEffect(() => {
    if (!isBuyer) return;
    api("/locations/mandals").then(setMandals).catch(() => {});
  }, [isBuyer]);

  // Curated discovery feed; refetches when the chosen area changes.
  useEffect(() => {
    if (browsing) return;
    const qs = area?.id ? `?mandal_id=${area.id}` : "";
    api(`/listings/discovery${qs}`).then(setDisc).catch((e) => setErr(e.message));
  }, [browsing, area]);

  // Full product grid (debounced) — only while browsing.
  useEffect(() => {
    if (!browsing) return;
    const run = async () => {
      setLoading(true); setErr(null);
      try {
        const params = new URLSearchParams();
        if (category) params.set("category", category);
        if (q.trim()) params.set("q", q.trim());
        if (sort) params.set("sort", sort);
        if (minRating) params.set("min_rating", String(minRating));
        setProducts(await api(`/listings/products?${params.toString()}`));
      } catch (e) { setErr(e.message); } finally { setLoading(false); }
    };
    const id = setTimeout(run, q ? 300 : 0);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [browsing, category, q, sort, minRating]);

  function chooseArea(id) {
    const m = mandals.find((x) => String(x.id) === String(id));
    const next = m ? { id: m.id, name: m.name } : null;
    setArea(next);
    try {
      if (next) localStorage.setItem(AREA_KEY, JSON.stringify(next));
      else localStorage.removeItem(AREA_KEY);
    } catch { /* storage may be unavailable */ }
  }

  async function saveSearch() {
    setSaving(true); setErr(null);
    try {
      const criteria = {};
      if (q.trim()) criteria.q = q.trim();
      if (category) criteria.category = category;
      await api("/saved-searches", { method: "POST", body: { criteria, alert: true } });
      router.push("/saved");
    } catch (e) { setErr(e.message); setSaving(false); }
  }

  const gridCategories = [...new Set(products.map((p) => p.category))];

  return (
    <div>
      <h1>{t("marketplace")}</h1>
      <p className="tagline">{t("tagline")}</p>

      {/* Search / filter bar */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ flex: "2 1 220px" }}>
            <label>{t("search")}</label>
            <input value={q} onChange={(e) => setQ(e.target.value)}
                   placeholder="Search produce (e.g. paddy, turmeric)…" />
          </div>
          <div style={{ flex: "1 1 160px" }}>
            <label>Category</label>
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">{t("all_products")}</option>
              {(browsing ? gridCategories : (disc?.categories || []).map((c) => c.category))
                .map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div style={{ flex: "1 1 160px" }}>
            <label>Sort</label>
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="name">Name</option>
              <option value="price_asc">Price: low to high</option>
              <option value="price_desc">Price: high to low</option>
              <option value="verified">Verified first</option>
              <option value="availability">Most offerings</option>
              <option value="rating">{t("sort_top_rated")}</option>
            </select>
          </div>
          <div style={{ flex: "0 1 auto", alignSelf: "center" }}>
            <label className="rating-filter" style={{ cursor: "pointer", userSelect: "none" }}>
              <input type="checkbox" checked={minRating >= 4}
                     onChange={(e) => setMinRating(e.target.checked ? 4 : 0)} />
              {" "}<span className="rating-star">★</span> {t("rated_4_plus")}
            </label>
          </div>
        </div>
        {isBuyer && browsing && (
          <div className="row" style={{ marginTop: 12 }}>
            <button className="ghost" onClick={saveSearch} disabled={saving}>
              🔖 {saving ? "…" : t("save_search")}
            </button>
            <span className="muted" style={{ fontSize: 13 }}>
              Get alerted when a new matching listing is published.
            </span>
          </div>
        )}
      </div>

      {err && <div className="error">{err}</div>}

      {/* ---------------- Browsing: the flat results grid ---------------- */}
      {browsing ? (
        loading ? (
          <p className="muted">{t("loading")}</p>
        ) : products.length === 0 ? (
          <div className="empty"><span className="emoji">🔍</span><p>No products match your search.</p></div>
        ) : (
          <div className="grid">
            {products.map((p) => <ProductCard key={p.commodity_id} p={p} lang={lang} t={t} />)}
          </div>
        )
      ) : !disc ? (
        <p className="muted">{t("loading")}</p>
      ) : (
        /* ---------------- Curated landing ---------------- */
        <>
          {/* Headline stats */}
          {disc.stats?.live_products > 0 && (
            <div className="stat-strip">
              <div><b>{disc.stats.live_products}</b> {t("live_products")}</div>
              <div><b>{disc.stats.farmers}</b> {t("farmers_selling")}</div>
              <div><b>{disc.stats.places}</b> {t("places")}</div>
            </div>
          )}

          {/* Shopping-near picker (buyers) */}
          {isBuyer && (
            <div className="card area-bar">
              <label style={{ marginRight: 8 }}>📍 {t("shopping_near")}</label>
              <select value={area?.id || ""} onChange={(e) => chooseArea(e.target.value)}>
                <option value="">{t("set_location")}…</option>
                {mandals.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </div>
          )}

          {/* Near you */}
          {area && disc.near_you && (
            <section className="disc-section">
              <div className="section-head">
                <h2>{t("near_you")}{disc.near_you.district ? ` · ${disc.near_you.district}` : ""}</h2>
              </div>
              {disc.near_you.products.length === 0 ? (
                <p className="muted">{t("nothing_near")}</p>
              ) : (
                <div className="grid">
                  {disc.near_you.products.map((p) => <ProductCard key={p.commodity_id} p={p} lang={lang} t={t} />)}
                </div>
              )}
            </section>
          )}

          {/* Recently viewed (compact pills) */}
          {recent.length > 0 && (
            <section className="disc-section">
              <div className="section-head"><h2>{t("recently_viewed")}</h2></div>
              <div className="pill-row">
                {recent.map((r) => (
                  <Link key={r.commodity_id} href={`/product/${r.commodity_id}`} className="pill">
                    {lang === "te" && r.commodity_te ? r.commodity_te : r.commodity}
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* Featured */}
          {disc.featured?.length > 0 && (
            <section className="disc-section">
              <div className="section-head"><h2>⭐ {t("featured")}</h2></div>
              <div className="grid">
                {disc.featured.map((p) => <ProductCard key={p.commodity_id} p={p} lang={lang} t={t} />)}
              </div>
            </section>
          )}

          {/* Browse by category */}
          {disc.categories?.length > 0 && (
            <section className="disc-section">
              <div className="section-head"><h2>{t("browse_by_category")}</h2></div>
              <div className="pill-row">
                {disc.categories.map((c) => (
                  <button key={c.category} className="pill" onClick={() => setCategory(c.category)}>
                    {c.category} <span className="muted">· {c.offering_count}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          {/* Just listed */}
          {disc.fresh?.length > 0 && (
            <section className="disc-section">
              <div className="section-head"><h2>🌱 {t("just_listed")}</h2></div>
              <div className="fresh-strip">
                {disc.fresh.map((f) => <FreshCard key={f.listing_id} f={f} lang={lang} />)}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
