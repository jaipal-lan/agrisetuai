import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

function OfferCard({ offer, me, onChange }) {
  const router = useRouter();
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [showCounter, setShowCounter] = useState(false);
  const [price, setPrice] = useState("");
  const [qty, setQty] = useState("");

  const myRole = me.id === offer.buyer_id ? "buyer" : "seller";
  const latest = offer.versions[offer.versions.length - 1];
  const myTurn =
    ["open", "countered"].includes(offer.status) && latest.proposer_role !== myRole;

  async function call(path, body) {
    setErr(null);
    setBusy(true);
    try {
      const r = await api(path, { method: "POST", body });
      if (r.order) {
        router.push(`/order/${r.order.id}`);
        return;
      }
      onChange();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="between">
        <h3>Listing #{offer.listing_id} · you are the {myRole}</h3>
        <span className={`badge ${offer.status === "accepted" ? "" : "grey"}`}>{offer.status}</span>
      </div>

      <ul className="timeline" style={{ marginTop: 10 }}>
        {offer.versions.map((v) => (
          <li key={v.id}>
            <b>v{v.version_no}</b> — {v.proposer_role} offered ₹{v.price_per_unit}/kg × {v.quantity} kg
            <br />
            <small>expires {new Date(v.expires_at).toLocaleString()}</small>
          </li>
        ))}
      </ul>

      {err && <div className="error">{err}</div>}

      {offer.status === "accepted" ? (
        <div className="ok">Deal agreed. See it under My orders.</div>
      ) : myTurn ? (
        <>
          <div className="row" style={{ marginTop: 8 }}>
            <button disabled={busy} onClick={() => call(`/offers/${offer.id}/accept`)}>
              Accept ₹{latest.price_per_unit}/kg
            </button>
            <button className="ghost" disabled={busy} onClick={() => setShowCounter((s) => !s)}>
              Counter
            </button>
            <button className="danger" disabled={busy} onClick={() => call(`/offers/${offer.id}/reject`)}>
              Reject
            </button>
          </div>
          {showCounter && (
            <div className="row" style={{ marginTop: 12 }}>
              <div style={{ flex: 1 }}>
                <label>New price ₹/kg</label>
                <input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" />
              </div>
              <div style={{ flex: 1 }}>
                <label>Quantity kg</label>
                <input value={qty} onChange={(e) => setQty(e.target.value)} inputMode="decimal" />
              </div>
              <div style={{ alignSelf: "flex-end" }}>
                <button
                  disabled={busy || !price || !qty}
                  onClick={() =>
                    call(`/offers/${offer.id}/counter`, {
                      price_per_unit: Number(price),
                      quantity: Number(qty),
                    })
                  }
                >
                  Send counter
                </button>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="muted" style={{ marginTop: 8 }}>
          Waiting for the other party to respond.
        </div>
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

  async function load() {
    try {
      setOffers(await api("/offers"));
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { setMe(getUser()); }, []);
  usePoll(load, 15000);

  const gate = roleGate(me, GROUPS.shopper, { label: "offers & negotiations" });
  if (gate) return gate;

  return (
    <div>
      <h1>{t("my_offers")}</h1>
      {err && <div className="error">{err}</div>}
      {loading ? (
        <p className="muted">{t("loading")}</p>
      ) : offers.length === 0 ? (
        <p className="muted">No negotiations yet. Browse the {t("marketplace")} to make an offer.</p>
      ) : (
        offers.map((o) => <OfferCard key={o.id} offer={o} me={me} onChange={load} />)
      )}
    </div>
  );
}
