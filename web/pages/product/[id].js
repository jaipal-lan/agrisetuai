import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, mediaUrl } from "../../lib/api";
import { useI18n } from "../../lib/i18n";

export default function ProductOfferings() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const { id } = router.query;
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!id) return;
    api(`/listings/products/${id}`).then(setData).catch((e) => setErr(e.message));
  }, [id]);

  if (err) return <div className="error">{err}</div>;
  if (!data) return <p className="muted">{t("loading")}</p>;

  const title = lang === "te" && data.commodity_te ? data.commodity_te : data.commodity;

  return (
    <div>
      <button className="ghost" onClick={() => router.push("/")}>← {t("marketplace")}</button>
      <h1 style={{ marginTop: 12 }}>{title}</h1>
      <p className="tagline">
        {data.offering_count} farmer offering{data.offering_count === 1 ? "" : "s"}
        {data.places.length > 0 && <> · from {data.places.join(", ")}</>}
        {" "}· minimum order {data.min_order_qty} kg
      </p>

      <div className="grid">
        {data.offerings.map((o) => {
          const img = o.media[0] ? mediaUrl(o.media[0].object_key) : null;
          return (
            <div key={o.id} className="card" style={{ opacity: o.out_of_stock ? 0.65 : 1 }}>
              {img && (
                <img src={img} alt={o.commodity} loading="lazy"
                     style={{ width: "100%", height: 130, objectFit: "cover", borderRadius: 8, marginBottom: 10 }} />
              )}
              <div className="between">
                <h3 style={{ fontSize: 16 }}>{o.place?.label || "—"}</h3>
                {o.agent_verified && <span className="badge">✓ verified</span>}
              </div>
              {o.seller_rating != null && (
                <div style={{ fontSize: 13 }}><span style={{ color: "#f59e0b" }}>★ {o.seller_rating}</span> <span className="muted">({o.seller_rating_count})</span></div>
              )}
              <div className="muted" style={{ fontSize: 13 }}>
                {o.variety ? `${o.variety} · ` : ""}{o.is_organic ? "organic" : "non-organic"}
                {o.grade ? ` · ${o.grade.label}` : ""}{o.harvest_year ? ` · HY ${o.harvest_year}` : ""}
              </div>
              {o.agent_verified && o.verification_note && (
                <div className="ok" style={{ fontSize: 12, marginTop: 6 }}>✓ {o.verification_note}</div>
              )}
              {o.specifications && <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>{o.specifications}</div>}
              <div className="price" style={{ marginTop: 8 }}>₹{o.asking_price}<small> {t("per_kg")}</small></div>
              {o.out_of_stock ? (
                <div className="badge grey" style={{ marginTop: 10 }}>Out of stock</div>
              ) : (
                <>
                  <div className="muted" style={{ fontSize: 14, marginTop: 6 }}>
                    {t("available")}: {o.available_qty} {o.unit} · min {o.min_order_qty}
                  </div>
                  <div style={{ marginTop: 12 }}>
                    <Link href={`/listing/${o.id}`} className="btn">View & offer</Link>
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
