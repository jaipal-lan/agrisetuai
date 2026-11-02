import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, getUser, mediaUrl } from "../../lib/api";
import { useI18n } from "../../lib/i18n";

export default function ListingDetail() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const { id } = router.query;
  const [listing, setListing] = useState(null);
  const [commodity, setCommodity] = useState(null);
  const [user, setUser] = useState(null);
  const [price, setPrice] = useState("");
  const [qty, setQty] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setUser(getUser());
  }, []);

  useEffect(() => {
    if (!id) return;
    api(`/listings/${id}`)
      .then((l) => {
        setListing(l);
        setPrice(l.asking_price);
      })
      .catch((e) => setErr(e.message));
  }, [id]);

  useEffect(() => {
    if (!listing) return;
    api("/catalog/commodities")
      .then((cs) => setCommodity(cs.find((c) => c.id === listing.commodity_id)))
      .catch(() => {});
  }, [listing]);

  async function makeOffer() {
    setErr(null);
    setBusy(true);
    try {
      const offer = await api("/offers", {
        method: "POST",
        body: {
          listing_id: Number(id),
          price_per_unit: Number(price),
          quantity: Number(qty),
        },
      });
      router.push(`/offers?focus=${offer.id}`);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (err && !listing) return <div className="error">{err}</div>;
  if (!listing) return <p className="muted">{t("loading")}</p>;

  const cname =
    commodity && lang === "te" && commodity.name_te ? commodity.name_te : commodity && commodity.name;
  const isBuyer = user && ["buyer_household", "buyer_business"].includes(user.role);
  const isOwner = user && user.id === (listing.seller && listing.seller.id);

  return (
    <div style={{ maxWidth: 560 }}>
      <button className="ghost" onClick={() => router.push("/")}>← {t("marketplace")}</button>
      <h1 style={{ marginTop: 16 }}>{cname || "Listing"}</h1>
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="badge">{listing.status.replace(/_/g, " ")}</span>
        <span className={`badge ${listing.is_organic ? "" : "grey"}`}>
          {listing.is_organic ? "organic" : listing.claim_status}
        </span>
        {commodity && <span className="badge grey">{commodity.category}</span>}
        {listing.agent_verified && <span className="badge">✓ agent verified</span>}
        {listing.out_of_stock && <span className="badge amber">out of stock</span>}
      </div>

      {listing.media && listing.media.length > 0 && (
        <div className="row" style={{ gap: 8, marginBottom: 14, flexWrap: "nowrap", overflowX: "auto" }}>
          {listing.media.map((m, i) => (
            <img key={i} src={mediaUrl(m.object_key)} alt={`sample ${i + 1}`} loading="lazy"
                 style={{ width: 150, height: 110, objectFit: "cover", borderRadius: 8, flex: "0 0 auto" }} />
          ))}
        </div>
      )}

      <div className="card">
        <div className="between">
          <div className="price">₹{listing.asking_price}<small> {t("per_kg")}</small></div>
          <div className="muted">{t("available")}: <b>{listing.available_qty}</b> {listing.unit}</div>
        </div>
        <div className="muted" style={{ fontSize: 14, marginTop: 8 }}>
          {listing.place?.label && <>📍 {listing.place.label} · </>}
          {listing.variety ? `${listing.variety} · ` : ""}
          Harvest {listing.harvest_year || "—"} · Min order {listing.min_order_qty} {listing.unit}
        </div>
        {listing.pickup_terms && (
          <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>{listing.pickup_terms}</div>
        )}
      </div>

      {/* Specifications (farmer-declared + grade spec) */}
      {(listing.specifications || (listing.grade && listing.grade.attributes)) && (
        <div className="card" style={{ marginTop: 14 }}>
          <h3 style={{ fontSize: 16 }}>Specifications</h3>
          <div className="row" style={{ gap: 8, marginBottom: 8 }}>
            <span className="pill-tag">{listing.is_organic ? "Organic" : "Non-organic"}</span>
            {listing.grade && <span className="pill-tag">Grade: {listing.grade.label}</span>}
            {listing.variety && <span className="pill-tag">Variety: {listing.variety}</span>}
          </div>
          {listing.specifications && <div style={{ fontSize: 14 }}>{listing.specifications}</div>}
          {listing.grade && listing.grade.attributes && (
            <table style={{ marginTop: 8 }}>
              <tbody>
                {Object.entries(listing.grade.attributes).filter(([, v]) => v != null).map(([k, v]) => (
                  <tr key={k}><td className="muted">{k.replace(/_/g, " ")}</td><td>{String(v)}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Agent verification comment */}
      {listing.agent_verified && (
        <div className="card" style={{ marginTop: 14, borderLeft: "4px solid var(--green-600)" }}>
          <div className="between">
            <b>✓ Agent verified</b>
            {listing.verified_by_name && <span className="muted" style={{ fontSize: 13 }}>by {listing.verified_by_name}</span>}
          </div>
          {listing.verification_note && (
            <div style={{ fontSize: 14, marginTop: 6 }}>“{listing.verification_note}”</div>
          )}
          {listing.verified_at && (
            <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{new Date(listing.verified_at).toLocaleString()}</div>
          )}
        </div>
      )}

      {err && <div className="error">{err}</div>}

      {listing.out_of_stock ? (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="badge grey">Out of stock</div>
          <p className="muted" style={{ marginTop: 8 }}>This lot is sold out. See other farmers offering this product.</p>
          <button className="ghost" onClick={() => router.push(`/product/${listing.commodity_id}`)}>
            Other offerings
          </button>
        </div>
      ) : isOwner ? (
        <div className="ok" style={{ marginTop: 16 }}>This is your listing. Manage it under {t("sell")}.</div>
      ) : isBuyer ? (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>{t("make_offer")}</h3>
          <div className="row">
            <div style={{ flex: 1 }}>
              <label>{t("price")} ({t("per_kg")})</label>
              <input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" />
            </div>
            <div style={{ flex: 1 }}>
              <label>{t("quantity")} ({listing.unit})</label>
              <input value={qty} onChange={(e) => setQty(e.target.value)} inputMode="decimal" />
            </div>
          </div>
          <div style={{ marginTop: 16 }}>
            <button onClick={makeOffer} disabled={busy || !price || !qty}>{t("make_offer")}</button>
          </div>
        </div>
      ) : (
        <div className="card" style={{ marginTop: 16 }}>
          <p className="muted">Log in as a buyer to negotiate.</p>
          <button onClick={() => router.push("/login")}>{t("login")}</button>
        </div>
      )}
    </div>
  );
}
