import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api, getUser } from "../lib/api";
import { usePoll } from "../lib/hooks";
import { useI18n } from "../lib/i18n";

export default function Dashboard() {
  const { t } = useI18n();
  const router = useRouter();
  const [me, setMe] = useState(null);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => { setMe(getUser()); }, []);
  usePoll(() => {
    api("/dashboard").then(setData).catch((e) => setErr(e.message));
  }, 15000);

  if (!me) {
    return (
      <div>
        <h1>{t("app_name")}</h1>
        <p className="muted">Log in to see your dashboard.</p>
        <Link href="/login" className="btn">{t("login")}</Link>
      </div>
    );
  }

  return (
    <div>
      <div className="between">
        <div>
          <h1 style={{ marginBottom: 2 }}>{t("welcome_back")}{data?.name ? `, ${data.name}` : ""}</h1>
          {data && <span className="badge">{data.role_label}</span>}
        </div>
      </div>
      {err && <div className="error">{err}</div>}

      {data?.onboarding_complete === false && (
        <div className="card" style={{ borderLeft: "4px solid var(--amber-600)", marginTop: 12 }}>
          <b>Finish setting up your profile</b>
          <div className="muted" style={{ fontSize: 13 }}>Add your details so we can match you better.</div>
          <div style={{ marginTop: 10 }}>
            <button onClick={() => router.push("/onboarding")}>Complete profile</button>
          </div>
        </div>
      )}

      {data && (
        <>
          <div className="grid" style={{ marginTop: 16 }}>
            {data.cards.map((c) => (
              <div
                key={c.label}
                className="card stat-card"
                style={{
                  cursor: c.href ? "pointer" : "default",
                  borderLeft: c.alert ? "4px solid var(--amber-600)" : "4px solid var(--green-600)",
                }}
                onClick={() => c.href && router.push(c.href)}
              >
                <div className="muted" style={{ fontSize: 13 }}>{c.label}</div>
                <div className="price" style={{ fontSize: 26 }}>{c.value}</div>
              </div>
            ))}
          </div>

          <h2 style={{ marginTop: 24 }}>Quick actions</h2>
          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            {data.actions.map((a) => (
              <button
                key={a.href + a.label}
                className={a.primary ? "" : "ghost"}
                onClick={() => router.push(a.href)}
              >
                {a.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
