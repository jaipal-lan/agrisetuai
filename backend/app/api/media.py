import hashlib
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.ids import public_id
from app.core.security import verify_media_token
from app.models.support import MediaObject
from app.services import audit, storage

# Local on-disk prefix for PRIVATE files (KYC / ID docs). The public /media/file
# route refuses this prefix, so private files are only reachable via /media/secure
# with a valid signed token.
PRIVATE_PREFIX = "priv/"

router = APIRouter(prefix="/media", tags=["media"])

def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _placeholder_svg(label: str) -> str:
    """Neutral 'photo coming soon' placeholder shown until a seller uploads a
    real photo of their produce. Deliberately plain and photo-like (a muted
    frame + image glyph), NOT a cartoon emoji — a real upload replaces it."""
    text = (label.replace("sample/", "").replace(".svg", "").replace("-", " ")).strip()[:28]
    label_text = _xml_escape(text.title())
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" '
        'viewBox="0 0 400 300" font-family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif">'
        '<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#f1f3f4"/><stop offset="1" stop-color="#e3e6e8"/>'
        '</linearGradient></defs>'
        '<rect width="400" height="300" fill="url(#bg)"/>'
        # Simple framed-image glyph (no emoji), muted grey.
        '<g stroke="#b2b8bd" stroke-width="3" fill="none">'
        '<rect x="150" y="96" width="100" height="78" rx="10"/>'
        '</g>'
        '<circle cx="174" cy="120" r="8" fill="#b2b8bd"/>'
        '<path d="M154 170 L182 134 L202 156 L224 126 L248 170 Z" fill="#c4c9cd"/>'
        f'<text x="200" y="212" fill="#5f6368" font-size="22" font-weight="600" '
        f'text-anchor="middle">{label_text}</text>'
        '<text x="200" y="238" fill="#9aa0a6" font-size="13" '
        'text-anchor="middle">Photo coming soon</text></svg>'
    )

_ALLOWED = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
}


def _media_type(ctype: str) -> str:
    if ctype.startswith("video/"):
        return "video"
    if ctype == "application/pdf":
        return "document"
    return "image"


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    private: bool = Form(False),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Store an uploaded file. private=True (KYC / ID docs) keeps the file out of
    the public /media/file route: on Cloudinary it uploads as an authenticated
    asset (signed delivery URL); on local disk it lands under a `priv/` prefix
    that only the signed /media/secure route will serve."""
    ctype = (file.content_type or "").split(";")[0].strip().lower()
    if ctype not in _ALLOWED:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Only JPEG, PNG, WebP, PDF or MP4/WebM/MOV video uploads are allowed.",
        )
    raw = await file.read()
    limit = settings.media_video_max_bytes if ctype.startswith("video/") else settings.media_max_bytes
    if len(raw) > limit:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File too large")
    ext = _ALLOWED[ctype]
    fname = f"{public_id('MED', 10).lower()}.{ext}"
    # Prefer Cloudinary (permanent CDN URL); fall back to local disk for dev.
    object_key = storage.save(raw, ctype, folder=f"agrisetu/{user.id}",
                              filename=fname, private=private)
    if not object_key:
        key = f"{PRIVATE_PREFIX if private else ''}{user.id}/{fname}"
        root = os.path.abspath(settings.media_dir)
        dest = os.path.join(root, key.replace("/", os.sep))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(raw)
        object_key = key
    obj = MediaObject(
        object_key=object_key,
        owner_id=user.id,
        media_type=_media_type(ctype),
        content_type=ctype,
        size_bytes=len(raw),
        checksum=hashlib.sha256(raw).hexdigest(),
        access_class="private" if private else "restricted",
    )
    db.add(obj)
    audit.record(
        db,
        actor_id=user.id,
        action="media.upload",
        object_type="media",
        object_id=None,  # object_key can be a long Cloudinary URL; keep it in new_values
        new_values={"object_key": object_key, "size": len(raw), "content_type": ctype},
    )
    db.commit()
    return {
        "object_key": object_key,
        "checksum": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "content_type": ctype,
        "note": "Pilot stores files on local disk. Swap for signed object-storage URLs in production.",
    }


def _serve_local(object_key: str):
    root = os.path.abspath(settings.media_dir)
    dest = os.path.abspath(os.path.join(root, object_key.replace("/", os.sep)))
    if not dest.startswith(root) or not os.path.isfile(dest):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return FileResponse(dest)


@router.get("/file/{object_key:path}")
def serve_file(object_key: str):
    """Serve a PUBLIC stored media file (listing images, avatars, dev). Demo
    listings use `sample/...` keys that render as a generated placeholder image,
    so the UI shows produce photos without bundled binaries.

    Private files (KYC / ID docs, stored under the `priv/` prefix) are refused
    here — they are only reachable via /media/secure with a valid signed token.
    """
    if object_key.startswith("sample/"):
        return Response(content=_placeholder_svg(object_key), media_type="image/svg+xml")
    if object_key.startswith(PRIVATE_PREFIX):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This file is private.")
    return _serve_local(object_key)


@router.get("/secure/{object_key:path}")
def serve_secure(object_key: str, token: str = ""):
    """Serve a PRIVATE file (KYC / ID doc) only when presented with a valid,
    unexpired signed token bound to this exact object_key. The token is minted
    solely inside auth-gated responses (the owner's /auth/me and staff's
    /admin/kyc), so the file is never exposed at a guessable public URL."""
    if not token or not verify_media_token(token, object_key):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or expired link.")
    # Cloudinary-hosted private assets are stored as a full signed https URL.
    if object_key.startswith("http"):
        return RedirectResponse(object_key)
    return _serve_local(object_key)
