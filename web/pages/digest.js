import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { useI18n } from "../lib/i18n";

// Where a digest item points, when it points somewhere useful.
function hrefFor(it) {
  switch (it.object_type) {
    case "offer": return "/offers";
    case "rfq": return "/requests";
    case "saved_search": return "/saved";
    case "product": return it.object_id ? `/product/${it.object_id}` : "/";
    case "announcement": return "/inbox";
    case "crop_case": return "/advisory";
    default: return null;
  }
}

const EMOJI = {
  offers: "🤝", price_alerts: "🏷️", requests: "📋",
  announcements: "📢", advisory: "🌾",
};

export default function Digest() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try { setData(await api("/auth/notifications/digest")); }
    catch (e) { setErr(e.message); }
  }
  useEffect(() => { setMe(getUser()); load(); }, []);

  async function markRead() {
    setBusy(true);
    try {
      await api("/auth/notifications/digest/read", { method: "POST" });
      await load();
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  if (!me) {
    return (
      <div>
        <p className="muted">Log in to see your daily digest.</p>
        <Link href="/login" className="btn">{t("login")}</Link>
      </div>
    );
  }

  const noDigestCats = data && (!data.digest_categories || data.digest_categories.length === 0);

  return (
    <div style={{ maxWidth: 760 }}>
      <div className="between">
        <h1>📬 {t("daily_digest")} {data?.total > 0 && <span className="badge amber">{data.total}</span>}</h1>
        {data?.total > 0 && (
          <button className="ghost" onClick={markRead} disabled={busy}>
            {busy ? "…" : "Mark digest read"}
          </button>
        )}
      </div>
      {err && <div className="error">{err}</div>}

      {!data ? (
        <p className="muted">{t("loading")}</p>
      ) : noDigestCats ? (
        <div className="empty">
          <span className="emoji">📭</span>
          <p>No categories are set to daily digest yet.</p>
          <p className="muted" style={{ fontSize: 14 }}>
            On <Link href="/profile">your profile</Link>, set an alert type to
            <b> Daily</b> to batch it here instead of pinging the bell each time.
          </p>
        </div>
      ) : data.total === 0 ? (
        <div className="empty">
          <span className="emoji">✅</span>
          <p>You're all caught up — nothing waiting in today's digest.</p>
          <p className="muted" style={{ fontSize: 14 }}>
            Batched alerts for {data.digest_categories.join(", ")} will collect here.
          </p>
        </div>
      ) : (
        <>
          <p className="muted" style={{ marginTop: -6 }}>
            {data.total} batched alert{data.total === 1 ? "" : "s"} waiting — your once-a-day roll-up.
          </p>
          {data.groups.map((g) => (
            <section key={g.category} className="card" style={{ marginBottom: 16 }}>
              <div className="between" style={{ marginBottom: 6 }}>
                <h3 style={{ margin: 0 }}>{EMOJI[g.category] || "•"} {g.label}</h3>
                <span className="badge">{g.count}</span>
              </div>
              <ul className="timeline">
                {g.items.map((it) => {
                  const href = hrefFor(it);
                  return (
                    <li key={it.id}>
                      <b>{it.title}</b>
                      <div>{it.body}</div>
                      <small className="muted">
                        {it.created_at ? new Date(it.created_at).toLocaleString() : ""}
                      </small>
                      {href && <> · <Link href={href}>Open</Link></>}
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </>
      )}
    </div>
  );
}
