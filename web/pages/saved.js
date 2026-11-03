import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getUser, mediaUrl } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { GROUPS, roleGate } from "../lib/roles";

export default function Saved() {
  const { t, lang } = useI18n();
  const [me, setMe] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [results, setResults] = useState(null);

  useEffect(() => { setMe(getUser()); }, []);
  usePoll(() => {
    api("/saved-searches").then(setRows).catch((e) => setErr(e.message)).finally(() => setLoading(false));
  }, 20000);

  const gate = roleGate(me, GROUPS.buyer, { label: "saved searches" });
  if (gate) return gate;

  function refresh() {
    api("/saved-searches").then(setRows).catch((e) => setErr(e.message));
  }

  async function viewResults(id) {
    if (openId === id) { setOpenId(null); setResults(null); return; }
    setErr(null);
    try {
      const r = await api(`/saved-searches/${id}/results`);
      setResults(r); setOpenId(id);
      refresh(); // viewing marks matches seen -> clears the "new" badge
    } catch (e) { setErr(e.message); }
  }
  async function toggleAlert(s) {
    try { await api(`/saved-searches/${s.id}`, { method: "PATCH", body: { alert: !s.alert } }); refresh(); }
    catch (e) { setErr(e.message); }
  }
  async function remove(id) {
    if (!confirm("Delete this saved search?")) return;
    try { await api(`/saved-searches/${id}`, { method: "DELETE" }); setRows((r) => r.filter((x) => x.id !== id)); if (openId === id) { setOpenId(null); setResults(null); } }
    catch (e) { setErr(e.message); }
  }

  const pname = (o) => (lang === "te" && o.commodity_te ? o.commodity_te : o.commodity);

  return (
    <div>
      <h1>{t("saved_searches")}</h1>
      <p className="tagline">Save a market search and we’ll alert you when a new matching listing appears.</p>
      {err && <div className="error">{err}</div>}

      {loading ? (
        <p className="muted">{t("loading")}</p>
      ) : rows.length === 0 ? (
        <div className="empty">
          <span className="emoji">🔖</span>
          <p>No saved searches yet. On the marketplace, set a search and tap “{t("save_search")}”.</p>
          <Link href="/" className="btn">Browse the market</Link>
        </div>
      ) : (
        <div className="grid">
          {rows.map((s) => (
            <div key={s.id} className="card" style={{ borderLeft: s.new_count > 0 ? "4px solid var(--green-600)" : undefined }}>
              <div className="between">
                <h3 style={{ margin: 0 }}>{s.label}</h3>
                <button className="ghost" onClick={() => remove(s.id)} aria-label="delete">✕</button>
              </div>
              {s.label !== s.description && (
                <div className="muted" style={{ fontSize: 13 }}>{s.description}</div>
              )}
              <div className="row" style={{ gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                <span className="badge grey">{s.match_count} match{s.match_count === 1 ? "" : "es"}</span>
                {s.new_count > 0 && <span className="badge">{s.new_count} new</span>}
                {s.best_price != null && <span className="badge grey">from ₹{s.best_price}{t("per_kg")}</span>}
              </div>
              <div className="row" style={{ marginTop: 12, alignItems: "center" }}>
                <button className="ghost" onClick={() => viewResults(s.id)}>
                  {openId === s.id ? "Hide results" : "View results"}
                </button>
                <label style={{ display: "flex", alignItems: "center", gap: 6, margin: 0, fontSize: 14 }}>
                  <input type="checkbox" checked={s.alert} onChange={() => toggleAlert(s)} style={{ width: "auto" }} />
                  Alerts
                </label>
              </div>

              {openId === s.id && results && (
                <div style={{ marginTop: 14, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
                  {results.offerings.length === 0 ? (
                    <p className="muted" style={{ fontSize: 14 }}>No live listings match right now.</p>
                  ) : (
                    <div className="thumb-row" style={{ display: "grid", gap: 10 }}>
                      {results.offerings.map((o) => (
                        <Link key={o.id} href={`/product/${o.commodity_id}`} className="row"
                              style={{ gap: 10, alignItems: "center", color: "inherit", textDecoration: "none" }}>
                          {o.media && o.media[0] && (
                            <img src={mediaUrl(o.media[0].object_key)} alt={pname(o)}
                                 style={{ width: 46, height: 46, borderRadius: 8, objectFit: "cover" }} loading="lazy" />
                          )}
                          <div style={{ flex: 1 }}>
                            <div style={{ fontWeight: 600 }}>{pname(o)} {o.agent_verified && <span className="badge" style={{ fontSize: 10 }}>✓</span>}</div>
                            <div className="muted" style={{ fontSize: 12 }}>{o.place?.label || "—"}</div>
                          </div>
                          <div className="price" style={{ fontSize: 16 }}>₹{o.asking_price}</div>
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
