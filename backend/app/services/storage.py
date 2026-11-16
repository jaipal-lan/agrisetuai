"""Media storage: Cloudinary when configured, else local disk.

Cloudinary gives permanent CDN URLs — essential because the Render free tier's
disk is ephemeral (uploads vanish on restart). Signed server-side upload (no SDK
dependency; uses httpx). When Cloudinary isn't configured, save() returns None and
the caller writes to local disk (dev default).
"""
import hashlib
import logging
import time

import httpx

from app.core.config import settings

log = logging.getLogger("agrisetu.storage")


def configured() -> bool:
    return bool(settings.cloudinary_cloud_name and settings.cloudinary_api_key
               and settings.cloudinary_api_secret)


def _resource_type(content_type: str) -> str:
    ct = (content_type or "").lower()
    if ct.startswith("image/"):
        return "image"
    if ct.startswith("video/"):
        return "video"
    return "raw"  # PDFs / docs — stored and delivered as-is


def _sign(params: dict, secret: str) -> str:
    to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return hashlib.sha1((to_sign + secret).encode()).hexdigest()


def save(raw: bytes, content_type: str, *, folder: str = "agrisetu",
         filename: str = "file") -> str | None:
    """Upload to Cloudinary and return the permanent secure URL, or None when
    Cloudinary isn't configured / the upload fails (caller falls back to disk)."""
    if not configured():
        return None
    rtype = _resource_type(content_type)
    ts = str(int(time.time()))
    signed = {"folder": folder, "timestamp": ts}
    data = {
        "api_key": settings.cloudinary_api_key,
        "timestamp": ts,
        "folder": folder,
        "signature": _sign(signed, settings.cloudinary_api_secret),
    }
    url = f"https://api.cloudinary.com/v1_1/{settings.cloudinary_cloud_name}/{rtype}/upload"
    try:
        r = httpx.post(url, data=data, files={"file": (filename, raw, content_type)}, timeout=60)
        if r.status_code in (200, 201):
            return r.json().get("secure_url")
        log.warning("cloudinary upload failed: %s %s", r.status_code, r.text[:200])
    except Exception:  # noqa: BLE001 - fall back to disk, never break the upload
        log.exception("cloudinary upload error")
    return None
