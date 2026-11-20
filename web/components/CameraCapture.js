import { useEffect, useRef, useState } from "react";

import { useI18n } from "../lib/i18n";

// "Take photo" that uses the live webcam when possible (HTTPS or localhost),
// and otherwise falls back to a capture-enabled file input (phone camera on
// mobile, file picker on desktop over plain HTTP). Calls onCapture(File).
export default function CameraCapture({ onCapture, label, className = "btn ghost" }) {
  const { t } = useI18n();
  const [cam, setCam] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const fallbackRef = useRef(null);

  const [insecure, setInsecure] = useState(false);

  const webcamOk = typeof window !== "undefined" && window.isSecureContext
    && !!navigator.mediaDevices?.getUserMedia;

  // On a desktop over plain HTTP the live camera is blocked by the browser
  // (getUserMedia needs a secure context). Detect that so we can nudge the user
  // to the HTTPS URL instead of silently opening a file dialog.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const coarse = window.matchMedia?.("(pointer: coarse)")?.matches;
    setInsecure(!window.isSecureContext && !coarse); // desktop, not secure
  }, []);

  function open() {
    setErr(null);
    if (webcamOk) startCam();
    else fallbackRef.current?.click();
  }

  async function startCam() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
      });
      streamRef.current = stream;
      setCam(true);
      setTimeout(() => { if (videoRef.current) { videoRef.current.srcObject = stream; videoRef.current.play(); } }, 50);
    } catch {
      setErr(t("cc_cam_fail"));
      fallbackRef.current?.click();
    }
  }

  function stopCam() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCam(false);
  }

  function snap() {
    const v = videoRef.current;
    if (!v) return;
    const w = v.videoWidth || 960, h = v.videoHeight || 720;
    const canvas = document.createElement("canvas");
    canvas.width = w; canvas.height = h;
    canvas.getContext("2d").drawImage(v, 0, 0, w, h);
    stopCam(); setBusy(true);
    canvas.toBlob((blob) => {
      setBusy(false);
      if (blob) onCapture?.(new File([blob], `photo-${Date.now()}.jpg`, { type: "image/jpeg" }));
    }, "image/jpeg", 0.9);
  }

  function onFile(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) onCapture?.(file);
  }

  useEffect(() => () => stopCam(), []);

  return (
    <>
      <button type="button" className={className} onClick={open} disabled={busy} style={{ cursor: "pointer" }}>
        {label || t("sl_take_photo")}
      </button>
      <input ref={fallbackRef} type="file" accept="image/*" capture="environment"
             style={{ display: "none" }} onChange={onFile} />
      {err && <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{err}</div>}
      {insecure && !err && (
        <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
          {t("cc_insecure")}
        </div>
      )}
      {cam && (
        <div onClick={stopCam} style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,.85)", zIndex: 4000,
          display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12,
        }}>
          <video ref={videoRef} playsInline muted onClick={(e) => e.stopPropagation()}
                 style={{ maxWidth: "92vw", maxHeight: "70vh", borderRadius: 10, background: "#000" }} />
          <div className="row" style={{ gap: 10 }} onClick={(e) => e.stopPropagation()}>
            <button onClick={snap} disabled={busy}>{t("cc_capture")}</button>
            <button className="ghost" onClick={stopCam} style={{ color: "#fff", borderColor: "#fff" }}>{t("pf_cancel")}</button>
          </div>
        </div>
      )}
    </>
  );
}
