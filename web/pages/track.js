import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";

// Public shipment tracking — no login. Enter a bag barcode (AGRI-...) to see its
// journey with no personal data (only crop + village).
export default function Track() {
  const { t } = useI18n();
  const router = useRouter();
  const [code, setCode] = useState("");
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  async function track(c) {
    const v = (c ?? code).trim();
    if (!v) return;
    setErr(null); setData(null); setBusy(true);
    try {
      setData(await api(`/track/${encodeURIComponent(v)}`));
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  // Deep-link support: /track?code=AGRI-1023-BAG-01
  useEffect(() => {
    const c = router.query.code;
    if (typeof c === "string" && c) { setCode(c); track(c); }
  }, [router.query.code]);

  return (
    <div style={{ maxWidth: 560, margin: "0 auto" }}>
      <h1>{t("tk_title")}</h1>
      <p className="tagline">{t("tk_intro")}</p>

      <div className="card">
        <div className="row" style={{ gap: 6 }}>
          <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="AGRI-1023-BAG-01"
                 style={{ flex: 1 }} onKeyDown={(e) => e.key === "Enter" && track()} />
          <button disabled={busy || !code.trim()} onClick={() => track()}>{t("track")}</button>
        </div>
        {err && <div className="error" style={{ marginTop: 10 }}>{err}</div>}
      </div>

      {data && (
        <div className="card">
          <div className="between">
            <h3 style={{ margin: 0 }}>{data.crop || t("tk_produce")}{data.village ? ` · ${data.village}` : ""}</h3>
            <span className="badge green">{data.status_label}</span>
          </div>
          <div className="muted" style={{ fontSize: 13, marginBottom: 10 }}>Bag {data.bag_code}</div>

          {/* Progress ladder */}
          <div style={{ display: "grid", gap: 0 }}>
            {data.ladder.map((s, i) => (
              <div key={s.status} className="row" style={{ gap: 10, alignItems: "flex-start" }}>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                  <div style={{
                    width: 18, height: 18, borderRadius: "50%",
                    background: s.reached ? "var(--green-600, #16a34a)" : "var(--line, #d1d5db)",
                    color: "#fff", fontSize: 11, display: "flex", alignItems: "center", justifyContent: "center",
                  }}>{s.reached ? "✓" : ""}</div>
                  {i < data.ladder.length - 1 && (
                    <div style={{ width: 2, height: 24, background: s.reached ? "var(--green-600, #16a34a)" : "var(--line, #d1d5db)" }} />
                  )}
                </div>
                <div style={{ paddingBottom: 14 }}>
                  <div style={{ fontWeight: s.reached ? 600 : 400, color: s.reached ? "var(--ink)" : "var(--muted, #6b7280)" }}>
                    {s.label}
                  </div>
                  {(() => {
                    const ev = data.timeline.find((t) => t.status === s.status);
                    return ev?.at ? <div className="muted" style={{ fontSize: 12 }}>{fmt(ev.at)}</div> : null;
                  })()}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function fmt(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}
