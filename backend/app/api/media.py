import hashlib
import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.ids import public_id
from app.models.support import MediaObject
from app.services import audit, storage

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
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
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
    object_key = storage.save(raw, ctype, folder=f"agrisetu/{user.id}", filename=fname)
    if not object_key:
        key = f"{user.id}/{fname}"
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
        access_class="restricted",
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


@router.get("/file/{object_key:path}")
def serve_file(object_key: str):
    """Serve a stored media file (public listing images, dev). Demo listings use
    `sample/...` keys that render as a generated placeholder image, so the UI shows
    produce photos without bundled binaries.

    NOTE: pilot-only. Production must gate restricted evidence behind signed URLs.
    """
    if object_key.startswith("sample/"):
        return Response(content=_placeholder_svg(object_key), media_type="image/svg+xml")
    root = os.path.abspath(settings.media_dir)
    dest = os.path.abspath(os.path.join(root, object_key.replace("/", os.sep)))
    if not dest.startswith(root) or not os.path.isfile(dest):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return FileResponse(dest)
