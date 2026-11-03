import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, getUser, mediaUrl } from "../../lib/api";
import { useI18n } from "../../lib/i18n";

function WatchButton({ commodityId }) {
  const [state, setState] = useState(null); // {watching, target_price}
  const [target, setTarget] = useState("");
  const [msg, setMsg] = useState(null);

  async function load() {
    try {
      const s = await api(`/watchlist/${commodityId}`);
      setState(s);
      setTarget(s.target_price || "");
    } catch { setState({ watching: false }); }
  }
  useEffect(() => { if (commodityId) load(); /* eslint-disable-next-line */ }, [commodityId]);

  async function save() {
    setMsg(null);
    try {
      await api("/watchlist", { method: "POST", body: {
        commodity_id: Number(commodityId),
        target_price: target ? Number(target) : undefined,
      } });
      setMsg(target ? `We'll alert you at or below ₹${target}/kg.` : "Added to your favorites.");
      load();
    } catch (e) { setMsg(e.message); }
  }
  async function remove() {
    setMsg(null);
    try { await api(`/watchlist/${commodityId}`, { method: "DELETE" }); setMsg("Removed from favorites."); load(); }
    catch (e) { setMsg(e.message); }
  }

  if (!state) return null;
  return (
    <div className="card" style={{ marginBottom: 16, borderLeft: "4px solid var(--amber-600)" }}>
      <div className="between">
        <b>{state.watching ? "★ Watching this product" : "☆ Watch this product"}</b>
        {state.watching && <button className="ghost" onClick={remove}>Remove</button>}
      </div>
      <p className="muted" style={{ fontSize: 13, margin: "6px 0 0" }}>
        Get an alert when a new offering appears — or when the price drops to your target.
      </p>
      <div className="row" style={{ alignItems: "flex-end", marginTop: 8 }}>
        <div style={{ flex: "1 1 180px" }}>
          <label>Target price (₹/kg, optional)</label>
          <input value={target} onChange={(e) => setTarget(e.target.value)} inputMode="decimal" placeholder="e.g. 22" />
        </div>
        <button onClick={save}>{state.watching ? "Update alert" : "Watch"}</button>
      </div>
      {msg && <div className="ok" style={{ marginTop: 10 }}>{msg}</div>}
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

  useEffect(() => { setMe(getUser()); }, []);
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

      {me && ["buyer_household", "buyer_business"].includes(me.role) && (
        <WatchButton commodityId={id} />
      )}

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
