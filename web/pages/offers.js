import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, getUser, mediaUrl } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

function fmtLeft(ms, t) {
  if (ms <= 0) return t("expired");
  const m = Math.floor(ms / 60000);
  const d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), mm = m % 60;
  const left = t("word_left");
  if (d > 0) return `${d}d ${h}h ${left}`;
  if (h > 0) return `${h}h ${mm}m ${left}`;
  return `${mm}m ${left}`;
}

function Countdown({ iso, now, t }) {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - now;
  const kind = ms <= 0 ? "danger" : ms < 3600000 ? "danger" : ms < 6 * 3600000 ? "amber" : "grey";
  return <span className={`badge ${kind}`}>⏳ {fmtLeft(ms, t)}</span>;
}

function round2(n) { return Math.round(n * 100) / 100; }

function OfferCard({ offer, me, now, onChange }) {
  const router = useRouter();
  const { t, lang } = useI18n();
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [showCounter, setShowCounter] = useState(false);
  const [price, setPrice] = useState("");
  const [qty, setQty] = useState("");

  const myRole = me.id === offer.buyer_id ? "buyer" : "seller";
  const latest = offer.latest || offer.versions[offer.versions.length - 1];
  const expired = offer.expired;
  const myTurn = offer.awaiting_role === myRole && !expired;

  // My most recent proposal (for the "meet in the middle" preset).
  const myLast = [...offer.versions].reverse().find((v) => v.proposer_role === myRole);
  const p = offer.product;
  const pname = p && (lang === "te" && p.commodity_te ? p.commodity_te : p.commodity);

  function openCounter() {
    setPrice(String(latest.price_per_unit));
    setQty(String(latest.quantity));
    setShowCounter((s) => !s);
  }

  // Counter-offer presets — quick, informed moves instead of blank fields.
  const theirPrice = Number(latest.price_per_unit);
  const presets = [];
  if (myLast) {
    const mid = round2((theirPrice + Number(myLast.price_per_unit)) / 2);
    if (mid !== theirPrice) presets.push({ label: `${t("meet_middle")} ₹${mid}`, price: mid });
  } else if (p && p.asking_price) {
    const mid = round2((theirPrice + Number(p.asking_price)) / 2);
    if (mid !== theirPrice) presets.push({ label: `${t("split_to")} ₹${mid}`, price: mid });
  }
  presets.push({ label: `${t("match_price")} ₹${theirPrice}`, price: theirPrice });

  async function call(path, body) {
    setErr(null); setBusy(true);
    try {
      const r = await api(path, { method: "POST", body });
      if (r.order) { router.push(`/order/${r.order.id}`); return; }
      onChange();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  const statusBadge = offer.status === "accepted" ? "" : offer.status === "expired" ? "amber" : "grey";

  return (
    <div className="card" style={{ marginBottom: 16, borderLeft: myTurn ? "4px solid var(--green-600)" : undefined }}>
      <div className="between" style={{ gap: 10 }}>
        <div className="row" style={{ gap: 10, alignItems: "center", flex: 1 }}>
          {p && p.image && (
            <img src={mediaUrl(p.image)} alt={pname} loading="lazy"
                 style={{ width: 46, height: 46, borderRadius: 8, objectFit: "cover" }} />
          )}
          <div>
            <h3 style={{ margin: 0 }}>
              {p && p.commodity_id ? (
                <Link href={`/product/${p.commodity_id}`} style={{ color: "inherit" }}>{pname}</Link>
              ) : (pname || `Listing #${offer.listing_id}`)}
            </h3>
            <div className="muted" style={{ fontSize: 13 }}>
              {p && p.place ? `${p.place} · ` : ""}{t("you_are")} {t("role_" + myRole)}
            </div>
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <span className={`badge ${statusBadge}`}>{t("ofs_" + offer.status)}</span>
          {(offer.status === "open" || offer.status === "countered") && (
            <div style={{ marginTop: 6 }}><Countdown iso={latest.expires_at} now={now} t={t} /></div>
          )}
        </div>
      </div>

      {/* Price gap: their current ask vs your last offer. */}
      <div className="row" style={{ gap: 18, marginTop: 12, flexWrap: "wrap" }}>
        <div>
          <div className="muted" style={{ fontSize: 12 }}>{latest.proposer_role === myRole ? t("your_terms") : t("their_terms")}</div>
          <div className="price" style={{ fontSize: 20 }}>₹{latest.price_per_unit}<small> /kg × {latest.quantity} kg</small></div>
        </div>
        {myLast && myLast.id !== latest.id && (
          <div>
            <div className="muted" style={{ fontSize: 12 }}>{t("your_last")}</div>
            <div style={{ fontSize: 16 }}>₹{myLast.price_per_unit} <small className="muted">/kg × {myLast.quantity}</small></div>
          </div>
        )}
        {p && p.asking_price && (
          <div>
            <div className="muted" style={{ fontSize: 12 }}>{t("listed_at")}</div>
            <div style={{ fontSize: 16 }}>₹{p.asking_price} <small className="muted">· {p.available_qty} {t("kg_left")}</small></div>
          </div>
        )}
      </div>

      <details style={{ marginTop: 10 }}>
        <summary className="muted" style={{ cursor: "pointer", fontSize: 13 }}>
          {t("history")} ({offer.versions.length} {offer.versions.length === 1 ? t("round") : t("rounds")})
        </summary>
        <ul className="timeline" style={{ marginTop: 8 }}>
          {offer.versions.map((v) => (
            <li key={v.id}>
              <b>v{v.version_no}</b> — {v.proposer_role} · ₹{v.price_per_unit}/kg × {v.quantity} kg
            </li>
          ))}
        </ul>
      </details>

      {err && <div className="error">{err}</div>}

      {offer.status === "accepted" ? (
        <div className="ok">{t("deal_agreed_see")}</div>
      ) : offer.status === "rejected" ? (
        <div className="muted" style={{ marginTop: 8 }}>{t("offer_rejected_msg")}</div>
      ) : expired || offer.status === "expired" ? (
        <div className="row" style={{ marginTop: 8, alignItems: "center" }}>
          <span className="muted">{t("offer_lapsed")}</span>
          {p && p.commodity_id && <Link href={`/product/${p.commodity_id}`} className="btn ghost">{t("make_fresh_offer")}</Link>}
        </div>
      ) : myTurn ? (
        <>
          <div className="row" style={{ marginTop: 8 }}>
            <button disabled={busy} onClick={() => call(`/offers/${offer.id}/accept`)}>
              {t("accept")} ₹{latest.price_per_unit}/kg
            </button>
            <button className="ghost" disabled={busy} onClick={openCounter}>{t("counter")}</button>
            <button className="danger" disabled={busy} onClick={() => call(`/offers/${offer.id}/reject`)}>{t("reject")}</button>
          </div>
          {showCounter && (
            <div style={{ marginTop: 12 }}>
              <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                {presets.map((pr) => (
                  <button key={pr.label} type="button" className="ghost" style={{ fontSize: 13 }}
                          onClick={() => setPrice(String(pr.price))}>
                    {pr.label}
                  </button>
                ))}
              </div>
              <div className="row" style={{ marginTop: 10, alignItems: "flex-end" }}>
                <div style={{ flex: 1 }}>
                  <label>{t("new_price")}</label>
                  <div className="row" style={{ gap: 6 }}>
                    <button type="button" className="ghost" onClick={() => setPrice((v) => String(round2(Math.max(0.01, (Number(v) || 0) - 0.5))))}>−</button>
                    <input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" style={{ flex: 1 }} />
                    <button type="button" className="ghost" onClick={() => setPrice((v) => String(round2((Number(v) || 0) + 0.5)))}>+</button>
                  </div>
                </div>
                <div style={{ flex: 1 }}>
                  <label>{t("qty_kg")}</label>
                  <input value={qty} onChange={(e) => setQty(e.target.value)} inputMode="decimal" />
                </div>
                <div>
                  <button disabled={busy || !price || !qty}
                          onClick={() => call(`/offers/${offer.id}/counter`, { price_per_unit: Number(price), quantity: Number(qty) })}>
                    {t("send_counter")}
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="muted" style={{ marginTop: 8 }}>{t("waiting_other")}</div>
      )}
    </div>
  );
}

export default function Offers() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [offers, setOffers] = useState([]);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(Date.now());

  async function load() {
    try { setOffers(await api("/offers")); }
    catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }

  useEffect(() => { setMe(getUser()); }, []);
  usePoll(load, 15000);
  // Tick the clock so countdowns stay live between polls.
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(id); }, []);

  const gate = roleGate(me, GROUPS.shopper, { label: "offers & negotiations" });
  if (gate) return gate;

  const actionable = offers.filter((o) => o.awaiting_role && me.id === (o.awaiting_role === "buyer" ? o.buyer_id : o.seller_id) && !o.expired).length;

  return (
    <div>
      <h1>{t("my_offers")}</h1>
      {actionable > 0 && (
        <p className="tagline">{actionable} {t("offers_awaiting")}</p>
      )}
      {err && <div className="error">{err}</div>}
      {loading ? (
        <p className="muted">{t("loading")}</p>
      ) : offers.length === 0 ? (
        <p className="muted">{t("no_negotiations")}</p>
      ) : (
        offers.map((o) => <OfferCard key={o.id} offer={o} me={me} now={now} onChange={load} />)
      )}
    </div>
  );
}
