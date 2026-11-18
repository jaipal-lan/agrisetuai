"""Media storage: Cloudinary when configured, else local disk.

Cloudinary gives permanent CDN URLs — essential because the Render free tier's
disk is ephemeral (uploads vanish on restart). Signed server-side upload (no SDK
dependency; uses httpx). When Cloudinary isn't configured, save() returns None and
the caller writes to local disk (dev default).
"""
import base64
import hashlib
import logging
import time

import httpx

from app.core.config import settings

log = logging.getLogger("agrisetu.storage")


def configured() -> bool:
    return bool(settings.cloudinary_cloud_name and settings.cloudinary_api_key
               and settings.cloudinary_api_secret)


def _delivery_signature(to_sign: str, secret: str) -> str:
    """Cloudinary signed-delivery signature: s--<first 8 of urlsafe-b64(sha1(
    public_id + api_secret))>--. Used to deliver `type=authenticated` assets,
    which are NOT publicly accessible without this signature."""
    digest = hashlib.sha1((to_sign + secret).encode()).digest()
    sig8 = base64.urlsafe_b64encode(digest).decode().rstrip("=")[:8]
    return f"s--{sig8}--"


def _signed_authenticated_url(public_id: str, rtype: str, version) -> str:
    """Build a signed delivery URL for an authenticated (private) Cloudinary
    asset. We deliver with NO format extension (Cloudinary returns the original),
    so the signature is over the bare public_id — which sidesteps extension/format
    edge cases. `raw` public_ids already carry their extension."""
    secret = settings.cloudinary_api_secret
    cloud = settings.cloudinary_cloud_name
    sig = _delivery_signature(public_id, secret)
    ver = f"v{version}/" if version else ""
    return f"https://res.cloudinary.com/{cloud}/{rtype}/authenticated/{sig}/{ver}{public_id}"


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
         filename: str = "file", private: bool = False) -> str | None:
    """Upload to Cloudinary and return a permanent URL, or None when Cloudinary
    isn't configured / the upload fails (caller falls back to disk).

    private=True uploads as `type=authenticated` (KYC / ID docs): the asset is NOT
    publicly accessible and we return a *signed* delivery URL instead of the plain
    secure_url, so only holders of the signed link can view it."""
    if not configured():
        return None
    rtype = _resource_type(content_type)
    ts = str(int(time.time()))
    signed = {"folder": folder, "timestamp": ts}
    if private:
        signed["type"] = "authenticated"
    data = {
        "api_key": settings.cloudinary_api_key,
        "timestamp": ts,
        "folder": folder,
        "signature": _sign(signed, settings.cloudinary_api_secret),
    }
    if private:
        data["type"] = "authenticated"
    url = f"https://api.cloudinary.com/v1_1/{settings.cloudinary_cloud_name}/{rtype}/upload"
    try:
        r = httpx.post(url, data=data, files={"file": (filename, raw, content_type)}, timeout=60)
        if r.status_code in (200, 201):
            body = r.json()
            if private:
                # Authenticated assets have no usable secure_url; build a signed one.
                return _signed_authenticated_url(
                    body.get("public_id"), body.get("resource_type", rtype), body.get("version"))
            return body.get("secure_url")
        log.warning("cloudinary upload failed: %s %s", r.status_code, r.text[:200])
    except Exception:  # noqa: BLE001 - fall back to disk, never break the upload
        log.exception("cloudinary upload error")
    return None
