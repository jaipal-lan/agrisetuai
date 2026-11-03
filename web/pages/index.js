import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, getUser, mediaUrl } from "../lib/api";
import { useI18n } from "../lib/i18n";

export default function Marketplace() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const [products, setProducts] = useState([]);
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("name");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [me, setMe] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => { setMe(getUser()); }, []);
  const isBuyer = me && ["buyer_household", "buyer_business"].includes(me.role);

  async function saveSearch() {
    setSaving(true);
    setErr(null);
    try {
      const criteria = {};
      if (q.trim()) criteria.q = q.trim();
      if (category) criteria.category = category;
      await api("/saved-searches", { method: "POST", body: { criteria, alert: true } });
      router.push("/saved");
    } catch (e) { setErr(e.message); setSaving(false); }
  }

  async function load(search) {
    setLoading(true);
    setErr(null);
    try {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      if (search) params.set("q", search);
      if (sort) params.set("sort", sort);
      setProducts(await api(`/listings/products?${params.toString()}`));
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  // Debounce the search box so we don't fire a request per keystroke.
  useEffect(() => {
    const id = setTimeout(() => load(q.trim()), q ? 300 : 0);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, q, sort]);

  const pname = (p) => (lang === "te" && p.commodity_te ? p.commodity_te : p.commodity);
  const categories = [...new Set(products.map((p) => p.category))];

  return (
    <div>
      <h1>{t("marketplace")}</h1>
      <p className="tagline">{t("tagline")}</p>

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
              <option value="">All products</option>
              {categories.map((c) => <option key={c} value={c}>{c}</option>)}
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
            </select>
          </div>
        </div>
        {isBuyer && (
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
      {loading ? (
        <p className="muted">{t("loading")}</p>
      ) : products.length === 0 ? (
        <div className="empty">
          <span className="emoji">🔍</span>
          <p>No products match your search.</p>
        </div>
      ) : (
        <div className="grid">
          {products.map((p) => {
            const available = p.offering_count > 0;
            return (
              <Link key={p.commodity_id} href={`/product/${p.commodity_id}`} className="card product-card" style={{ color: "inherit" }}>
                {p.image && (
                  <img className="product-thumb" src={mediaUrl(p.image)} alt={pname(p)} loading="lazy" />
                )}
                <div className="between">
                  <h3>{pname(p)}</h3>
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
                    <div className="muted" style={{ fontSize: 14, marginTop: 6 }}>
                      {p.offering_count} farmer{p.offering_count > 1 ? "s" : ""} · {p.place_count} place{p.place_count > 1 ? "s" : ""}
                    </div>
                  </>
                ) : (
                  <div className="badge grey" style={{ marginTop: 10 }}>Out of stock</div>
                )}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
