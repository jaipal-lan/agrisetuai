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
from app.services import audit

router = APIRouter(prefix="/media", tags=["media"])

_PLACEHOLDER_COLORS = [
    ("#2e7d32", "#60ad5e"), ("#558b2f", "#85bb5c"), ("#9e6d1f", "#ca9b52"),
    ("#8d6e63", "#be9c91"), ("#6a1b9a", "#9c4dcc"), ("#00838f", "#4fb3bf"),
]
_PLACEHOLDER_ICON = {
    "paddy": "🌾", "rice": "🍚", "milled": "🍚", "chilli": "🌶️", "turmeric": "🫚",
    "pepper": "⚫", "coriander": "🌿", "cumin": "🌿", "tamarind": "🫘", "ginger": "🫚",
    "mustard": "🌼", "groundnut": "🥜", "maize": "🌽", "gram": "🫘", "dal": "🫘",
}


def _placeholder_svg(label: str) -> str:
    text = (label.replace("sample/", "").replace(".svg", "").replace("-", " ")).strip()[:28]
    key = text.lower()
    icon = next((v for k, v in _PLACEHOLDER_ICON.items() if k in key), "🧺")
    c1, c2 = _PLACEHOLDER_COLORS[sum(ord(c) for c in label) % len(_PLACEHOLDER_COLORS)]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{c2}"/><stop offset="1" stop-color="{c1}"/>'
        f'</linearGradient></defs>'
        f'<rect width="400" height="300" fill="url(#g)"/>'
        f'<text x="200" y="130" font-size="80" text-anchor="middle" dominant-baseline="middle">{icon}</text>'
        f'<text x="200" y="210" fill="#ffffff" font-family="sans-serif" font-size="22" '
        f'text-anchor="middle" dominant-baseline="middle">{text}</text>'
        f'<text x="200" y="240" fill="#ffffff" font-family="sans-serif" font-size="12" '
        f'text-anchor="middle" opacity="0.85">sample photo</text></svg>'
    )

_ALLOWED = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}


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
            "Only JPEG, PNG, WebP or PDF uploads are allowed.",
        )
    raw = await file.read()
    if len(raw) > settings.media_max_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File too large")
    ext = _ALLOWED[ctype]
    key = f"{user.id}/{public_id('MED', 10).lower()}.{ext}"
    root = os.path.abspath(settings.media_dir)
    dest = os.path.join(root, key.replace("/", os.sep))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(raw)
    checksum = hashlib.sha256(raw).hexdigest()
    obj = MediaObject(
        object_key=key,
        owner_id=user.id,
        media_type="document" if ext == "pdf" else "image",
        content_type=ctype,
        size_bytes=len(raw),
        checksum=checksum,
        access_class="restricted",
    )
    db.add(obj)
    audit.record(
        db,
        actor_id=user.id,
        action="media.upload",
        object_type="media",
        object_id=key,
        new_values={"size": len(raw), "content_type": ctype},
    )
    db.commit()
    return {
        "object_key": key,
        "checksum": checksum,
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
