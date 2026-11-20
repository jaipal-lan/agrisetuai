import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, getUser, mediaUrl, productImage } from "../../lib/api";
import { useI18n } from "../../lib/i18n";

// Record this product in the per-viewer "recently viewed" list (newest first,
// deduped, capped) so the home page can surface it.
function rememberRecent(d) {
  try {
    const entry = { commodity_id: d.commodity_id, commodity: d.commodity, commodity_te: d.commodity_te };
    const prev = JSON.parse(localStorage.getItem("av_recent") || "[]");
    const next = [entry, ...prev.filter((r) => r.commodity_id !== entry.commodity_id)].slice(0, 8);
    localStorage.setItem("av_recent", JSON.stringify(next));
  } catch { /* storage may be unavailable */ }
}

// Collapsible list of a farmer's buyer reviews, loaded on demand from the
// existing public /reviews endpoint.
function SellerReviews({ sellerId, count, t }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && !data) {
      setLoading(true);
      try {
        setData(await api(`/reviews?subject_type=farmer&subject_id=${sellerId}`));
      } catch { setData({ reviews: [] }); } finally { setLoading(false); }
    }
  }
  if (!count) return null;
  return (
    <div style={{ marginTop: 8 }}>
      <button className="ghost" style={{ padding: "2px 8px", fontSize: 13 }} onClick={toggle}>
        {open ? "▾" : "▸"} {t("see_reviews")} ({count})
      </button>
      {open && (
        <div className="review-list">
          {loading ? (
            <p className="muted" style={{ fontSize: 13 }}>{t("loading")}</p>
          ) : (data?.reviews || []).length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>{t("no_reviews_yet")}</p>
          ) : (
            data.reviews.map((r) => (
              <div key={r.id} className="review-item">
                <span className="rating-star">{"★".repeat(r.rating)}</span>
                <span className="muted rating-star">{"★".repeat(5 - r.rating)}</span>
                {r.comment && <div style={{ fontSize: 13, marginTop: 2 }}>{r.comment}</div>}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

export default function ProductOfferings() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const { id } = router.query;
  const [data, setData] = useState(null);
  const [me, setMe] = useState(null);
  const [err, setErr] = useState(null);
  const [sortBy, setSortBy] = useState("rating");

  useEffect(() => { setMe(getUser()); }, []);
  useEffect(() => {
    if (!id) return;
    api(`/listings/products/${id}`).then((d) => {
      setData(d);
      rememberRecent(d);
    }).catch((e) => setErr(e.message));
  }, [id]);

  if (err) return <div className="error">{err}</div>;
  if (!data) return <p className="muted">{t("loading")}</p>;

  const title = lang === "te" && data.commodity_te ? data.commodity_te : data.commodity;

  // Sort offerings for the buyer: sold-out always last, then by the chosen key.
  const offerings = [...(data.offerings || [])].sort((a, b) => {
    if (a.out_of_stock !== b.out_of_stock) return a.out_of_stock ? 1 : -1;
    if (sortBy === "price") return Number(a.asking_price) - Number(b.asking_price);
    const ar = a.seller_rating == null ? -1 : a.seller_rating;
    const br = b.seller_rating == null ? -1 : b.seller_rating;
    return br - ar || Number(a.asking_price) - Number(b.asking_price);
  });

  return (
    <div>
      <button className="ghost" onClick={() => router.push("/")}>← {t("marketplace")}</button>
      <h1 style={{ marginTop: 12 }}>{title}</h1>
      <p className="tagline">
        {data.offering_count} {data.offering_count === 1 ? t("pr_offering") : t("pr_offerings")}
        {data.places.length > 0 && <> · {t("pr_from")} {data.places.join(", ")}</>}
        {" "}· {t("pr_min_order")} {data.min_order_qty} kg
      </p>
      {data.seller_rating != null && (
        <div className="trust-line">
          <span className="rating-star">★</span> <b>{data.seller_rating}</b>
          <span className="muted">
            {" "}· {t("rated_by")} {data.seller_rating_count} {data.seller_rating_count === 1 ? t("pr_buyer") : t("pr_buyers")}
            {data.offering_count > 1 ? ` ${t("across_sellers")}` : ""}
          </span>
        </div>
      )}

      {offerings.length > 1 && (
        <div className="row" style={{ alignItems: "center", margin: "4px 0 14px" }}>
          <label style={{ margin: 0 }}>{t("sort_sellers")}</label>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} style={{ maxWidth: 220 }}>
            <option value="rating">{t("sort_top_rated")}</option>
            <option value="price">{t("sort_lowest_price")}</option>
          </select>
        </div>
      )}

      <div className="grid">
        {offerings.map((o) => {
          const img = o.media[0] ? productImage(o.media[0].object_key) : null;
          return (
            <div key={o.id} className="card" style={{ opacity: o.out_of_stock ? 0.65 : 1 }}>
              {img && (
                <img src={img} alt={o.commodity} loading="lazy"
                     style={{ width: "100%", height: 130, objectFit: "cover", borderRadius: 8, marginBottom: 10 }} />
              )}
              <div className="between">
                <h3 style={{ fontSize: 16 }}>{o.place?.label || "—"}</h3>
                {o.agent_verified && <span className="badge">{t("sl_verified_tag")}</span>}
              </div>
              <div style={{ fontSize: 13, marginTop: 2 }}>
                {o.seller_rating != null ? (
                  <span className="rating" title={`${o.seller_rating} from ${o.seller_rating_count} review${o.seller_rating_count === 1 ? "" : "s"}`}>
                    <span className="rating-star">★</span> {o.seller_rating}
                    <span className="muted"> ({o.seller_rating_count})</span>
                  </span>
                ) : (
                  <span className="muted">{t("new_seller")}</span>
                )}
              </div>
              {o.top_review?.comment && (
                <div className="top-review">“{o.top_review.comment}”</div>
              )}
              {o.seller?.id && (
                <SellerReviews sellerId={o.seller.id} count={o.seller_rating_count} t={t} />
              )}
              <div className="muted" style={{ fontSize: 13 }}>
                {o.variety ? `${o.variety} · ` : ""}{o.is_organic ? t("sl_organic_tag") : t("pr_non_organic")}
                {o.quality_grade ? ` · ${t("sl_grade_short")} ${o.quality_grade}` : ""}
                {o.defect_pct != null ? ` · ${o.defect_pct}% ${t("sl_defects_suffix")}` : ""}
                {o.harvest_year ? ` · ${t("pr_hy")} ${o.harvest_year}` : ""}
              </div>
              {o.defect_notes && <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>⚠ {o.defect_notes}</div>}
              {o.video && (
                <video src={mediaUrl(o.video)} controls preload="none"
                       style={{ width: "100%", borderRadius: 8, marginTop: 8, maxHeight: 180 }} />
              )}
              {o.agent_verified && o.verification_note && (
                <div className="ok" style={{ fontSize: 12, marginTop: 6 }}>✓ {o.verification_note}</div>
              )}
              {o.specifications && <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>{o.specifications}</div>}
              <div className="price" style={{ marginTop: 8 }}>₹{o.asking_price}<small> /{o.unit || "kg"}</small></div>
              {o.out_of_stock ? (
                <div className="badge grey" style={{ marginTop: 10 }}>{t("out_of_stock")}</div>
              ) : (
                <>
                  <div className="muted" style={{ fontSize: 14, marginTop: 6 }}>
                    {t("available")}: {o.available_qty} {o.unit} · {t("pr_min")} {o.min_order_qty}
                  </div>
                  <div style={{ marginTop: 12 }}>
                    <Link href={`/listing/${o.id}`} className="btn">{t("pr_view_offer")}</Link>
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
