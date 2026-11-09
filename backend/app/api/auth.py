import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rbac import Role
from app.core.security import check_otp, issue_token, otp_rate_ok, set_otp
from app.core.serializers import self_user
from app.models.common import utcnow
from app.models.support import ConsentRecord, Notification
from app.models.user import AgentProfile, BuyerProfile, FarmerProfile, Organisation, User
from app.services import audit, sms

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
    mandal_id: int | None = None
    skill_level: str | None = None
    languages: str | None = None
    service_mandals: list[int] | None = None
    buyer_type: str | None = None
    submit_kyc: bool = False


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
    sms.send_otp(phone, code)  # console provider in dev/sandbox; real gateway in prod
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
            if user.role == Role.FPO:
                # An FPO is a group; give it an Organisation it leads from day one.
                org = Organisation(type="fpo", legal_name=(user.name or "Farmer group"))
                db.add(org)
                db.flush()
                user.organisation_id = org.id
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
        if body.mandal_id is not None:
            fp.mandal_id = body.mandal_id
        if body.submit_kyc:
            fp.verification_status = "pending"
    bp = user.buyer_profile
    if bp:
        if body.buyer_type is not None:
            bp.buyer_type = body.buyer_type
        if body.submit_kyc:
            bp.verification_status = "pending"
    ap = user.agent_profile
    if ap:
        if body.skill_level is not None:
            ap.skill_level = body.skill_level
        if body.languages is not None:
            ap.languages = body.languages
        if body.service_mandals is not None:
            ap.service_mandals = body.service_mandals
    user.onboarding_complete = True
    audit.record(db, actor_id=user.id, action="user.onboard", object_type="user",
                 object_id=user.id, new_values={"submit_kyc": body.submit_kyc})
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
    # Digest-deferred alerts stay out of the instant feed until they've been
    # read (via the digest), then they join the normal history.
    rows = db.scalars(
        select(Notification)
        .where(
            Notification.user_id == user.id,
            or_(Notification.deferred.is_(False), Notification.read_at.isnot(None)),
        )
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


def _earnings_data(db: Session, user: User) -> dict:
    """Farmer/FPO earnings statement: per-order gross, commission, net, payout."""
    from app.core.money import money
    from app.models.common import OrderStatus as OS
    from app.models.finance import Payout
    from app.models.order import Order

    rows = db.scalars(
        select(Order).where(
            Order.seller_id == user.id,
            Order.status.in_([OS.COMPLETED, OS.SETTLED, OS.PARTIALLY_REFUNDED, OS.REFUNDED]),
        ).order_by(Order.id.desc())
    )
    payouts = {p.order_id: p for p in db.scalars(select(Payout).where(Payout.seller_id == user.id))}
    lines = []
    tot_gross = tot_comm = tot_net = tot_paid = money(0)
    for o in rows:
        q = o.quote or {}
        t = o.accepted_terms or {}
        gross = money(q.get("product_value") or (float(t.get("price_per_unit", 0)) * float(t.get("quantity", 0))))
        comm = money(q.get("seller_commission", 0))
        net = money(o.seller_payable or (gross - comm))
        payout = payouts.get(o.id)
        paid = money(payout.amount) if payout else money(0)
        tot_gross += gross; tot_comm += comm; tot_net += net; tot_paid += paid
        lines.append({
            "order_public_id": o.public_id,
            "status": o.status,
            "gross": str(gross),
            "commission": str(comm),
            "net": str(net),
            "payout_status": payout.status if payout else ("pending" if o.status != OS.SETTLED else "—"),
            "paid": str(paid),
        })
    return {
        "currency": "INR",
        "totals": {"gross": str(tot_gross), "commission": str(tot_comm),
                   "net": str(tot_net), "paid": str(tot_paid)},
        "orders": lines,
    }


@router.get("/me/earnings")
def my_earnings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _earnings_data(db, user)


@router.get("/me/earnings.csv")
def my_earnings_csv(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Earnings statement as a downloadable CSV."""
    import csv
    import io

    from fastapi.responses import Response

    data = _earnings_data(db, user)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["order", "status", "gross_inr", "commission_inr", "net_inr", "payout_status", "paid_inr"])
    for o in data["orders"]:
        w.writerow([o["order_public_id"], o["status"], o["gross"], o["commission"],
                    o["net"], o["payout_status"], o["paid"]])
    tot = data["totals"]
    w.writerow(["TOTAL", "", tot["gross"], tot["commission"], tot["net"], "", tot["paid"]])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="agrisetu-earnings.csv"'},
    )


class NotifPrefs(BaseModel):
    # Legacy binary field (kept for back-compat) and the newer per-category
    # digest list. A category in `muted` wins over the same key in `digest`.
    muted: list[str] | None = None
    digest: list[str] | None = None


def _pref_categories(user: User) -> dict:
    """Each muteable category with the recipient's delivery mode:
    instant (default) | digest (daily roll-up) | off (muted)."""
    from app.services.notify import MUTEABLE_CATEGORIES

    muted = set(user.muted_notifications or [])
    digest = set(user.digest_notifications or [])
    cats = []
    for k, label in MUTEABLE_CATEGORIES:
        mode = "off" if k in muted else ("digest" if k in digest else "instant")
        cats.append({"key": k, "label": label, "mode": mode, "muted": mode == "off"})
    return {"categories": cats}


@router.get("/notification-preferences")
def get_notification_preferences(user: User = Depends(get_current_user)):
    """The muteable notification categories and each one's delivery mode."""
    return _pref_categories(user)


@router.put("/notification-preferences")
def set_notification_preferences(
    body: NotifPrefs, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Update delivery modes. `muted` and `digest` are each a full replacement of
    that list when provided (omit a list to leave it unchanged). Unknown keys are
    ignored; a category present in both lists is treated as muted."""
    from app.services.notify import MUTEABLE_CATEGORIES

    valid = {k for k, _ in MUTEABLE_CATEGORIES}
    if body.muted is not None:
        user.muted_notifications = sorted(valid.intersection(body.muted))
    if body.digest is not None:
        user.digest_notifications = sorted(valid.intersection(body.digest))
    # Mute wins: a category can't be both muted and digest.
    muted = set(user.muted_notifications or [])
    user.digest_notifications = sorted(set(user.digest_notifications or []) - muted)
    db.commit()
    return _pref_categories(user)


@router.post("/notifications/read")
def mark_notifications_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Mark the caller's instant notifications as read (clears the bell badge).
    Digest-deferred alerts have their own read action so they aren't cleared
    before the user has seen the roll-up."""
    now = utcnow().isoformat()
    rows = db.scalars(
        select(Notification).where(
            Notification.user_id == user.id,
            Notification.read_at.is_(None),
            Notification.deferred.is_(False),
        )
    )
    n = 0
    for row in rows:
        row.read_at = now
        n += 1
    db.commit()
    return {"ok": True, "marked": n}


@router.get("/notifications/digest")
def notifications_digest(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The daily roll-up: pending digest-deferred alerts grouped by category.

    Returns everything the user has chosen to batch and not yet read, newest
    first within each group, plus which categories are on digest delivery."""
    from app.services.notify import MUTEABLE_CATEGORIES, category_for

    labels = dict(MUTEABLE_CATEGORIES)
    rows = list(db.scalars(
        select(Notification)
        .where(
            Notification.user_id == user.id,
            Notification.deferred.is_(True),
            Notification.read_at.is_(None),
        )
        .order_by(Notification.id.desc())
    ))
    groups: dict[str, dict] = {}
    for n in rows:
        cat = category_for(n.object_type) or "other"
        g = groups.setdefault(cat, {
            "category": cat,
            "label": labels.get(cat, "Other updates"),
            "count": 0,
            "items": [],
        })
        g["count"] += 1
        g["items"].append({
            "id": n.id,
            "title": n.title,
            "body": n.body,
            "object_type": n.object_type,
            "object_id": n.object_id,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        })
    # Preserve the MUTEABLE_CATEGORIES order, with any stragglers last.
    order = {k: i for i, (k, _) in enumerate(MUTEABLE_CATEGORIES)}
    ordered = sorted(groups.values(), key=lambda g: order.get(g["category"], 99))
    return {
        "generated_at": utcnow().isoformat(),
        "total": len(rows),
        "groups": ordered,
        "digest_categories": sorted(user.digest_notifications or []),
    }


@router.post("/notifications/digest/read")
def mark_digest_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Mark the pending digest-deferred alerts as read; they then move into the
    normal notification history."""
    now = utcnow().isoformat()
    rows = db.scalars(
        select(Notification).where(
            Notification.user_id == user.id,
            Notification.deferred.is_(True),
            Notification.read_at.is_(None),
        )
    )
    n = 0
    for row in rows:
        row.read_at = now
        n += 1
    db.commit()
    return {"ok": True, "marked": n}
