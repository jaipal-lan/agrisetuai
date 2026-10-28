import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, getUser } from "../../lib/api";
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
        <span className="badge">{listing.status}</span>
        <span className={`badge ${listing.claim_status === "organic" ? "" : "grey"}`}>
          {listing.claim_status}
        </span>
        {commodity && <span className="badge grey">{commodity.category}</span>}
      </div>

      <div className="card">
        <div className="between">
          <div className="price">₹{listing.asking_price}<small> {t("per_kg")}</small></div>
          <div className="muted">{t("available")}: <b>{listing.available_qty}</b> {listing.unit}</div>
        </div>
        <div className="muted" style={{ fontSize: 14, marginTop: 8 }}>
          Harvest year {listing.harvest_year || "—"} · Min order {listing.min_order_qty} {listing.unit}
        </div>
      </div>

      {err && <div className="error">{err}</div>}

      {isOwner ? (
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
