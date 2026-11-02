import hashlib
import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.ids import public_id
from app.models.support import MediaObject
from app.services import audit

router = APIRouter(prefix="/media", tags=["media"])

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
