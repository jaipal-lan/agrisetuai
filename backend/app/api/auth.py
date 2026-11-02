import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rbac import Role
from app.core.security import check_otp, issue_token, otp_rate_ok, set_otp
from app.core.serializers import self_user
from app.models.common import utcnow
from app.models.support import ConsentRecord, Notification
from app.models.user import AgentProfile, BuyerProfile, FarmerProfile, User
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])

_PHONE_OK = {10, 11, 12}  # digit-length sanity (local or with country code)


class OtpRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=15)


class OtpVerify(BaseModel):
    phone: str
    code: str
    # Role is chosen at first sign-up; ignored for existing users.
    role: Role | None = None
    name: str | None = None
    preferred_language: str = "te"


class MePatch(BaseModel):
    name: str | None = None
    preferred_language: str | None = None
    village: str | None = None
    pickup_point: str | None = None
    skill_level: str | None = None
    languages: str | None = None


class ConsentBody(BaseModel):
    kind: str
    granted: bool = True
    version: str = "1"


@router.post("/otp/request")
def request_otp(body: OtpRequest, db: Session = Depends(get_db)):
    phone = body.phone.strip()
    if not phone.isdigit() or len(phone) not in _PHONE_OK:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid phone number")
    if not otp_rate_ok(phone):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many OTP requests. Wait a few minutes and try again.",
        )
    code = f"{secrets.randbelow(1_000_000):06d}"
    set_otp(phone, code)
    resp = {"sent": True}
    if settings.dev_mode:
        # Dev convenience only — never in production.
        resp["dev_code"] = code
    return resp


@router.post("/otp/verify")
def verify_otp(body: OtpVerify, db: Session = Depends(get_db)):
    phone = body.phone.strip()
    if not check_otp(phone, body.code.strip()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired code")

    user = db.scalar(select(User).where(User.phone == phone))
    created = False
    if user is None:
        if body.role is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "role is required for new accounts"
            )
        user = User(
            phone=phone,
            role=str(body.role),
            name=body.name,
            preferred_language=body.preferred_language,
            consent_at=utcnow().isoformat(),
        )
        db.add(user)
        db.flush()
        if user.role in (Role.FARMER, Role.FPO):
            db.add(FarmerProfile(user_id=user.id))
        elif user.role in (Role.BUYER_HOUSEHOLD, Role.BUYER_BUSINESS):
            kind = "household" if user.role == Role.BUYER_HOUSEHOLD else "business"
            db.add(BuyerProfile(user_id=user.id, buyer_type=kind))
        elif user.role == Role.FIELD_AGENT:
            db.add(AgentProfile(user_id=user.id))
        db.commit()
        db.refresh(user)
        created = True

    if user.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is not active")

    return {
        "token": issue_token(user.id, user.token_version or 0),
        "created": created,
        "user": self_user(user),
    }


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out = self_user(user)
    if user.farmer_profile:
        fp = user.farmer_profile
        out["farmer"] = {
            "village": fp.village,
            "pickup_point": fp.pickup_point,
            "mandal_id": fp.mandal_id,
            "verification_status": fp.verification_status,
        }
    if user.buyer_profile:
        out["buyer"] = {
            "buyer_type": user.buyer_profile.buyer_type,
            "verification_status": user.buyer_profile.verification_status,
        }
    if user.agent_profile:
        ap = user.agent_profile
        out["agent"] = {
            "skill_level": ap.skill_level,
            "languages": ap.languages,
            "available": ap.available,
            "service_mandals": ap.service_mandals,
        }
    return out


@router.patch("/me")
def patch_me(body: MePatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.name is not None:
        user.name = body.name
    if body.preferred_language is not None:
        user.preferred_language = body.preferred_language
    fp = user.farmer_profile
    if fp:
        if body.village is not None:
            fp.village = body.village
        if body.pickup_point is not None:
            fp.pickup_point = body.pickup_point
    ap = user.agent_profile
    if ap:
        if body.skill_level is not None:
            ap.skill_level = body.skill_level
        if body.languages is not None:
            ap.languages = body.languages
    user.onboarding_complete = True
    db.commit()
    db.refresh(user)
    return self_user(user)


@router.post("/consents")
def consents(body: ConsentBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rec = ConsentRecord(
        user_id=user.id, kind=body.kind, granted=body.granted, version=body.version
    )
    db.add(rec)
    if body.kind in ("terms", "privacy") and body.granted:
        user.consent_at = utcnow().isoformat()
    audit.record(
        db,
        actor_id=user.id,
        action="consent.record",
        object_type="user",
        object_id=user.id,
        new_values={"kind": body.kind, "granted": body.granted},
    )
    db.commit()
    return {"ok": True, "kind": body.kind, "granted": body.granted}


@router.post("/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.token_version = int(user.token_version or 0) + 1
    audit.record(db, actor_id=user.id, action="auth.logout", object_type="user", object_id=user.id)
    db.commit()
    return {"ok": True, "revoked": True}


@router.get("/notifications")
def notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.id.desc())
        .limit(50)
    )
    return [
        {
            "id": n.id,
            "title": n.title,
            "body": n.body,
            "object_type": n.object_type,
            "object_id": n.object_id,
            "read_at": n.read_at,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in rows
    ]


@router.post("/notifications/read")
def mark_notifications_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Mark all of the caller's notifications as read (clears the bell badge)."""
    now = utcnow().isoformat()
    rows = db.scalars(
        select(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    n = 0
    for row in rows:
        row.read_at = now
        n += 1
    db.commit()
    return {"ok": True, "marked": n}
