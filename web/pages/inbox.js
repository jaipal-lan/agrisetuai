import Link from "next/link";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";

// Map a notification's object to a destination, when it points somewhere useful.
function hrefFor(n) {
  if (n.object_type === "order" && n.object_id) return `/orders`;
  return null;
}

export default function Inbox() {
  const { t } = useI18n();
  const [me, setMe] = useState(null);
  const [notes, setNotes] = useState([]);
  const [filter, setFilter] = useState("all"); // all | announcements | unread
  const [err, setErr] = useState(null);

  async function load() {
    try {
      setNotes(await api("/auth/notifications"));
    } catch (e) {
      setErr(e.message);
    }
  }
  useEffect(() => { setMe(getUser()); }, []);
  usePoll(load, 15000);

  async function markAllRead() {
    try {
      await api("/auth/notifications/read", { method: "POST" });
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  if (!me) {
    return (
      <div>
        <p className="muted">{t("ib_login")}</p>
        <Link href="/login" className="btn">{t("login")}</Link>
      </div>
    );
  }

  const unreadCount = notes.filter((n) => !n.read_at).length;
  const shown = notes.filter((n) =>
    filter === "announcements" ? n.object_type === "announcement"
    : filter === "unread" ? !n.read_at
    : true
  );

  return (
    <div style={{ maxWidth: 760 }}>
      <div className="between">
        <h1>{t("inbox")} {unreadCount > 0 && <span className="badge amber">{unreadCount}</span>}</h1>
        {unreadCount > 0 && <button className="ghost" onClick={markAllRead}>{t("ib_mark_all_read")}</button>}
      </div>
      {err && <div className="error">{err}</div>}

      <div className="row" style={{ gap: 8, marginBottom: 12 }}>
        {[["all", t("ib_all")], ["announcements", t("ib_announcements")], ["unread", t("ib_unread")]].map(([k, label]) => (
          <button key={k} className={filter === k ? "" : "ghost"} onClick={() => setFilter(k)}>{label}</button>
        ))}
      </div>

      {shown.length === 0 ? (
        <div className="empty">
          <span className="emoji">📭</span>
          <p>{filter === "all" ? t("ib_no_messages") : t("ib_nothing_filter")}</p>
        </div>
      ) : (
        <ul className="timeline">
          {shown.map((n) => {
            const href = hrefFor(n);
            const isAnn = n.object_type === "announcement";
            return (
              <li key={n.id} style={{
                borderLeft: isAnn ? "3px solid var(--amber-600)" : undefined,
                paddingLeft: isAnn ? 10 : undefined,
                opacity: n.read_at ? 0.7 : 1,
              }}>
                <div className="between">
                  <b>{isAnn ? "📢 " : ""}{n.title}</b>
                  {!n.read_at && <span className="badge amber" style={{ fontSize: 11 }}>{t("ib_new")}</span>}
                </div>
                <div>{n.body}</div>
                <small className="muted">{n.created_at ? new Date(n.created_at).toLocaleString() : ""}</small>
                {href && <> · <Link href={href}>{t("ib_open")}</Link></>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
