import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";

export default function Marketplace() {
  const { t, lang } = useI18n();
  const [products, setProducts] = useState([]);
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      setProducts(await api(`/listings/products?${params.toString()}`));
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category]);

  const pname = (p) => (lang === "te" && p.commodity_te ? p.commodity_te : p.commodity);
  const categories = [...new Set(products.map((p) => p.category))];

  return (
    <div>
      <h1>{t("marketplace")}</h1>
      <p className="tagline">{t("tagline")}</p>

      <div className="card" style={{ marginBottom: 20 }}>
        <label>Category</label>
        <select value={category} onChange={(e) => setCategory(e.target.value)} style={{ maxWidth: 240 }}>
          <option value="">All products</option>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      {err && <div className="error">{err}</div>}
      {loading ? (
        <p className="muted">{t("loading")}</p>
      ) : (
        <div className="grid">
          {products.map((p) => {
            const available = p.offering_count > 0;
            return (
              <Link key={p.commodity_id} href={`/product/${p.commodity_id}`} className="card" style={{ color: "inherit" }}>
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
