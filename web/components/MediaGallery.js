import { useEffect, useState, useCallback } from "react";
import { mediaUrl } from "../lib/api";

// Thumbnail strip + full-screen lightbox. Click a thumb to open; arrow keys /
// on-screen buttons move prev/next; click an image to zoom; videos play inline.
// `items`: [{ object_key, media_type }]. `video`: optional single video object_key.
export default function MediaGallery({ items = [], video = null, thumb = 64 }) {
  // Build a flat list of {type:'image'|'video', src}.
  const media = [
    ...items.map((m) => ({
      type: (m.media_type === "video" || /\.(mp4|webm|mov)(\?|$)/i.test(m.object_key || "")) ? "video" : "image",
      src: mediaUrl(m.object_key),
    })),
    ...(video ? [{ type: "video", src: mediaUrl(video) }] : []),
  ].filter((m) => m.src);

  const [open, setOpen] = useState(-1);
  const [zoom, setZoom] = useState(false);

  const close = useCallback(() => { setOpen(-1); setZoom(false); }, []);
  const go = useCallback((d) => { setZoom(false); setOpen((i) => (i + d + media.length) % media.length); }, [media.length]);

  useEffect(() => {
    if (open < 0) return;
    const onKey = (e) => {
      if (e.key === "Escape") close();
      else if (e.key === "ArrowRight") go(1);
      else if (e.key === "ArrowLeft") go(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, go, close]);

  if (media.length === 0) return null;
  const cur = open >= 0 ? media[open] : null;

  return (
    <>
      <div className="row" style={{ gap: 6, margin: "10px 0", flexWrap: "nowrap", overflowX: "auto" }}>
        {media.map((m, i) => (
          <div key={i} onClick={() => setOpen(i)} title="Click to view"
               style={{ position: "relative", flex: "0 0 auto", cursor: "pointer" }}>
            {m.type === "video" ? (
              <div style={{
                width: thumb, height: thumb * 0.78, borderRadius: 6, background: "#111",
                display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 20,
              }}>▶</div>
            ) : (
              <img src={m.src} alt="" loading="lazy"
                   style={{ width: thumb, height: thumb * 0.78, objectFit: "cover", borderRadius: 6, display: "block" }} />
            )}
          </div>
        ))}
      </div>

      {cur && (
        <div onClick={close} style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,.9)", zIndex: 5000,
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          {/* close */}
          <button onClick={close} aria-label="Close" style={{
            position: "absolute", top: 14, right: 16, zIndex: 2, fontSize: 22, lineHeight: 1,
            background: "rgba(255,255,255,.15)", color: "#fff", border: "none", borderRadius: 8, padding: "4px 12px", cursor: "pointer",
          }}>✕</button>

          {media.length > 1 && (
            <>
              <button onClick={(e) => { e.stopPropagation(); go(-1); }} aria-label="Previous" style={navBtn("left")}>‹</button>
              <button onClick={(e) => { e.stopPropagation(); go(1); }} aria-label="Next" style={navBtn("right")}>›</button>
            </>
          )}

          <div onClick={(e) => e.stopPropagation()} style={{ maxWidth: "94vw", maxHeight: "88vh", textAlign: "center" }}>
            {cur.type === "video" ? (
              <video src={cur.src} controls autoPlay playsInline
                     style={{ maxWidth: "94vw", maxHeight: "82vh", borderRadius: 8, background: "#000" }} />
            ) : (
              <img src={cur.src} alt="" onClick={() => setZoom((z) => !z)}
                   style={{
                     maxWidth: zoom ? "none" : "94vw", maxHeight: zoom ? "none" : "82vh",
                     width: zoom ? "auto" : undefined, cursor: zoom ? "zoom-out" : "zoom-in",
                     borderRadius: 8, transform: zoom ? "scale(1.8)" : "none", transition: "transform .15s",
                   }} />
            )}
            <div style={{ color: "#ddd", fontSize: 13, marginTop: 8 }}>
              {open + 1} / {media.length}{cur.type === "image" ? " · tap image to zoom" : ""}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function navBtn(side) {
  return {
    position: "absolute", [side]: 10, top: "50%", transform: "translateY(-50%)", zIndex: 2,
    fontSize: 40, lineHeight: 1, width: 52, height: 72, color: "#fff",
    background: "rgba(255,255,255,.12)", border: "none", borderRadius: 10, cursor: "pointer",
  };
}
