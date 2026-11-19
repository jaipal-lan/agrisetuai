import hashlib
import os
import secrets

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.ids import public_id
from app.core.rbac import Role
from app.core.security import (
    check_otp,
    hash_password,
    issue_phone_token,
    issue_token,
    otp_rate_ok,
    set_otp,
    verify_password,
    verify_phone_token,
)
from app.core.serializers import self_user
from app.models.common import utcnow
from app.models.support import ConsentRecord, MediaObject, Notification
from app.models.user import AgentProfile, BuyerProfile, FarmerProfile, Organisation, User
from app.services import audit, sms

router = APIRouter(prefix="/auth", tags=["auth"])

_PHONE_OK = {10, 11, 12}  # digit-length sanity (local or with country code)

# Roles a member of the public may self-register as. Staff roles (agents, leads,
# managers, transport, superadmin) are provisioned internally.
_SELF_SIGNUP_ROLES = {Role.FARMER, Role.BUYER_HOUSEHOLD, Role.BUYER_BUSINESS}


class OtpRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=15)


class OtpVerify(BaseModel):
    # OTP login (fallback for staff / accounts without a password). Account
    # creation now goes through POST /auth/register.
    phone: str
    code: str


class VerifyPhoneBody(BaseModel):
    phone: str
    code: str


class LoginBody(BaseModel):
    phone: str
    password: str


class PasswordResetBody(BaseModel):
    phone_token: str
    new_password: str = Field(min_length=1)


class PasswordChangeBody(BaseModel):
    current_password: str
    new_password: str = Field(min_length=1)


class MePatch(BaseModel):
    name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    avatar_object_key: str | None = None
    preferred_language: str | None = None
    district: str | None = None
    state: str | None = None
    pincode: str | None = None
    aadhaar: str | None = None
    pan: str | None = None
    village: str | None = None
    pickup_point: str | None = None
    mandal_id: int | None = None
    farm_size: float | None = None
    crops_grown: list[str] | None = None
    soil_type: str | None = None
    irrigation_type: str | None = None
    experience_years: int | None = None
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
    """OTP login — a fallback for staff accounts and any account without a
    password set, and for password recovery. New accounts are NOT created here;
    members of the public sign up via POST /auth/register."""
    phone = body.phone.strip()
    if not check_otp(phone, body.code.strip()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired code")

    user = db.scalar(select(User).where(User.phone == phone))
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No account found for this phone. Please register first.",
        )
    if user.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is not active")

    return {
        "token": issue_token(user.id, user.token_version or 0),
        "created": False,
        "user": self_user(user),
    }


@router.post("/otp/verify-phone")
def verify_phone(body: VerifyPhoneBody, db: Session = Depends(get_db)):
    """Confirm phone ownership during registration / password reset. Consumes
    the OTP and returns a short-lived phone_token used to finish the flow, plus
    whether an account already exists for this phone (so the UI can redirect to
    login instead of registering a duplicate)."""
    phone = body.phone.strip()
    if not check_otp(phone, body.code.strip()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired code")
    exists = db.scalar(select(User.id).where(User.phone == phone)) is not None
    return {"phone_token": issue_phone_token(phone), "exists": exists}


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    """Phone + password login (the primary path)."""
    phone = body.phone.strip()
    user = db.scalar(select(User).where(User.phone == phone))
    # Constant-ish response whether or not the phone exists; never reveal which.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid phone or password")
    if user.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is not active")
    return {"token": issue_token(user.id, user.token_version or 0), "user": self_user(user)}


def _normalize_email(raw: str | None) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        from email_validator import EmailNotValidError, validate_email

        return validate_email(raw, check_deliverability=False).normalized
    except Exception as exc:  # noqa: BLE001 - map any validator error to 400
        if isinstance(exc, ImportError):
            return raw  # validator missing: accept as-is rather than block sign-up
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enter a valid email address")


async def _store_evidence(db: Session, owner_id: int, upload: UploadFile) -> str:
    """Persist a registration evidence file (reg doc / PAN) owned by the new
    user. Mirrors media.upload; kept here so it can run inside /register."""
    from app.api.media import _ALLOWED

    ctype = (upload.content_type or "").split(";")[0].strip().lower()
    if ctype not in _ALLOWED:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Evidence must be a JPEG, PNG, WebP or PDF file.",
        )
    raw = await upload.read()
    if len(raw) > settings.media_max_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Evidence file is too large.")
    ext = _ALLOWED[ctype]
    fname = f"{public_id('REG', 10).lower()}.{ext}"
    # Prefer Cloudinary (permanent); fall back to local disk for dev.
    from app.services import storage
    object_key = storage.save(raw, ctype, folder=f"agrisetu/kyc/{owner_id}", filename=fname)
    if not object_key:
        object_key = f"{owner_id}/{fname}"
        root = os.path.abspath(settings.media_dir)
        dest = os.path.join(root, object_key.replace("/", os.sep))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(raw)
    db.add(MediaObject(
        object_key=object_key,
        owner_id=owner_id,
        media_type="document" if ext == "pdf" else "image",
        content_type=ctype,
        size_bytes=len(raw),
        checksum=hashlib.sha256(raw).hexdigest(),
        access_class="restricted",
    ))
    return object_key


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    phone_token: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    first_name: str = Form(...),
    last_name: str | None = Form(None),
    email: str | None = Form(None),
    preferred_language: str = Form("te"),
    address_label: str = Form("Home"),
    address_mandal_id: int | None = Form(None),
    address_line: str | None = Form(None),
    address_lat: float | None = Form(None),
    address_lng: float | None = Form(None),
    # Business buyer extras
    biz_legal_name: str | None = Form(None),
    biz_registration_number: str | None = Form(None),
    biz_gst: str | None = Form(None),
    biz_address_line: str | None = Form(None),
    biz_mandal_id: int | None = Form(None),
    evidence: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    """Create a public account after phone verification. Multipart so business
    buyers can attach their registration document / org PAN as evidence in the
    same request (there is no session yet to upload against). Returns no auth
    token — the user is sent back to the login page to sign in."""
    from app.models.location import Mandal

    phone = verify_phone_token(phone_token)
    if not phone:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Phone verification expired. Please verify your number again.",
        )
    try:
        role_val = Role(role)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown role")
    if role_val not in _SELF_SIGNUP_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That role can't self-register")
    if len(password) < settings.password_min_length:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Password must be at least {settings.password_min_length} characters.",
        )
    first_name = (first_name or "").strip()
    if not first_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "First name is required")
    last_name = (last_name or "").strip() or None
    email_norm = _normalize_email(email)

    if db.scalar(select(User.id).where(User.phone == phone)) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An account already exists for this phone. Please log in.",
        )

    is_business = role_val == Role.BUYER_BUSINESS
    evidence = [f for f in (evidence or []) if f and f.filename]
    if is_business:
        if not (biz_legal_name or "").strip():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Business name is required")
        if not evidence:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Attach your business registration document or organisation PAN.",
            )

    # Validate the delivery mandal up front (if supplied).
    if address_mandal_id is not None and db.get(Mandal, address_mandal_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery mandal not found")

    full_name = " ".join(p for p in (first_name, last_name) if p)
    user = User(
        phone=phone,
        role=str(role_val),
        name=full_name,
        first_name=first_name,
        last_name=last_name,
        email=email_norm,
        password_hash=hash_password(password),
        preferred_language=preferred_language or "te",
        consent_at=utcnow().isoformat(),
    )
    db.add(user)
    db.flush()

    if role_val == Role.FARMER:
        db.add(FarmerProfile(user_id=user.id, mandal_id=address_mandal_id))
    else:
        kind = "business" if is_business else "household"
        db.add(BuyerProfile(user_id=user.id, buyer_type=kind))

    # Business organisation + evidence.
    if is_business:
        evidence_keys = [await _store_evidence(db, user.id, f) for f in evidence]
        org = Organisation(
            type="business",
            legal_name=biz_legal_name.strip(),
            verification_status="unverified",
            licence_refs={
                "registration_number": (biz_registration_number or "").strip() or None,
                "gst": (biz_gst or "").strip() or None,
                "address_line": (biz_address_line or "").strip() or None,
                "mandal_id": biz_mandal_id,
                "evidence_keys": evidence_keys,
            },
        )
        db.add(org)
        db.flush()
        user.organisation_id = org.id

    # Default delivery address (buyers + farmers who also buy).
    if address_mandal_id is not None:
        from app.models.account import SavedAddress

        db.add(SavedAddress(
            user_id=user.id,
            label=(address_label or "Home").strip() or "Home",
            mandal_id=address_mandal_id,
            address_line=(address_line or "").strip() or None,
            latitude=address_lat,
            longitude=address_lng,
            is_default=True,
        ))

    audit.record(db, actor_id=user.id, action="user.register", object_type="user",
                 object_id=user.id, new_values={"role": str(role_val), "business": is_business})
    db.commit()
    return {"created": True, "role": str(role_val), "phone": phone}


@router.post("/password/reset")
def reset_password(body: PasswordResetBody, db: Session = Depends(get_db)):
    """Set a new password after OTP phone verification (forgot-password flow).
    Revokes existing sessions."""
    phone = verify_phone_token(body.phone_token)
    if not phone:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Phone verification expired. Please verify your number again.",
        )
    user = db.scalar(select(User).where(User.phone == phone))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No account for this phone")
    if len(body.new_password) < settings.password_min_length:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Password must be at least {settings.password_min_length} characters.",
        )
    user.password_hash = hash_password(body.new_password)
    user.token_version = int(user.token_version or 0) + 1  # log out other sessions
    audit.record(db, actor_id=user.id, action="auth.password_reset", object_type="user",
                 object_id=user.id)
    db.commit()
    return {"ok": True}


@router.post("/password/change")
def change_password(body: PasswordChangeBody, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Change password while logged in. If the account has no password yet
    (OTP-only), the current password check is skipped so it can set one."""
    if user.password_hash and not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect")
    if len(body.new_password) < settings.password_min_length:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Password must be at least {settings.password_min_length} characters.",
        )
    user.password_hash = hash_password(body.new_password)
    audit.record(db, actor_id=user.id, action="auth.password_change", object_type="user",
                 object_id=user.id)
    db.commit()
    return {"ok": True}


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
            "farm_size": None if fp.farm_size is None else str(fp.farm_size),
            "crops_grown": fp.crops_grown or [],
            "soil_type": fp.soil_type,
            "irrigation_type": fp.irrigation_type,
            "experience_years": fp.experience_years,
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
    if user.organisation_id:
        org = db.get(Organisation, user.organisation_id)
        if org:
            refs = org.licence_refs or {}
            out["organisation"] = {
                "id": org.id,
                "type": org.type,
                "legal_name": org.legal_name,
                "verification_status": org.verification_status,
                "registration_number": refs.get("registration_number"),
                "gst": refs.get("gst"),
            }
    return out


@router.patch("/me")
def patch_me(body: MePatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.first_name is not None:
        user.first_name = body.first_name.strip() or None
    if body.last_name is not None:
        user.last_name = body.last_name.strip() or None
    if body.email is not None:
        user.email = _normalize_email(body.email)
    if body.avatar_object_key is not None:
        user.avatar_object_key = body.avatar_object_key.strip() or None
    if body.name is not None:
        user.name = body.name
    elif body.first_name is not None or body.last_name is not None:
        # Keep the display name in sync with the structured name.
        user.name = " ".join(p for p in (user.first_name, user.last_name) if p) or user.name
    if body.preferred_language is not None:
        user.preferred_language = body.preferred_language
    for attr in ("district", "state", "pincode", "aadhaar", "pan"):
        val = getattr(body, attr)
        if val is not None:
            setattr(user, attr, (val.strip() or None))
    fp = user.farmer_profile
    if fp:
        if body.village is not None:
            fp.village = body.village
        if body.pickup_point is not None:
            fp.pickup_point = body.pickup_point
        if body.mandal_id is not None:
            fp.mandal_id = body.mandal_id
        if body.farm_size is not None:
            fp.farm_size = body.farm_size
        if body.crops_grown is not None:
            fp.crops_grown = [c.strip() for c in body.crops_grown if c and c.strip()]
        if body.soil_type is not None:
            fp.soil_type = body.soil_type.strip() or None
        if body.irrigation_type is not None:
            fp.irrigation_type = body.irrigation_type.strip() or None
        if body.experience_years is not None:
            fp.experience_years = body.experience_years
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


class IdProofBody(BaseModel):
    object_key: str          # from /media/upload
    doc_type: str = "aadhaar"  # aadhaar | pan | voter_id | driving_licence | passport | other


@router.post("/me/id-proof")
def add_id_proof(body: IdProofBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Attach a government photo-ID proof for identity verification. The file is
    uploaded first via /media/upload; this records its key and marks the user's
    profile verification pending for staff review."""
    from app.models.common import utcnow

    key = (body.object_key or "").strip()
    if not key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No document uploaded.")
    docs = list(user.id_documents or [])
    docs.append({"object_key": key, "doc_type": (body.doc_type or "other").strip(),
                 "uploaded_at": utcnow().isoformat()})
    user.id_documents = docs
    # Belt-and-braces: mark the underlying media object private (the upload should
    # already have, but never leave a KYC doc classed as public).
    from app.models.support import MediaObject
    mo = db.scalar(select(MediaObject).where(MediaObject.object_key == key))
    if mo is not None:
        mo.access_class = "private"
    # Submitting an ID moves the relevant profile into the review queue.
    for prof in (user.farmer_profile, user.buyer_profile):
        if prof and prof.verification_status in (None, "unverified", "rejected"):
            prof.verification_status = "pending"
    audit.record(db, actor_id=user.id, action="user.id_proof.add", object_type="user",
                 object_id=user.id, new_values={"doc_type": body.doc_type})
    db.commit()
    db.refresh(user)
    return self_user(user)


class IdProofDelete(BaseModel):
    object_key: str


@router.delete("/me/id-proof")
def remove_id_proof(body: IdProofDelete, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Remove one of the caller's uploaded ID proofs (by object_key)."""
    key = (body.object_key or "").strip()
    docs = [d for d in (user.id_documents or []) if (d or {}).get("object_key") != key]
    user.id_documents = docs
    audit.record(db, actor_id=user.id, action="user.id_proof.remove", object_type="user",
                 object_id=user.id)
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


# --- Payout account (seller / transport partner) --------------------------

class PayoutAccountBody(BaseModel):
    method: str = "upi"  # upi | bank
    upi_id: str | None = None
    account_name: str | None = None
    account_number: str | None = None
    ifsc: str | None = None


def _payout_json(a) -> dict | None:
    if a is None:
        return None
    # Mask the account number; never return it in full.
    acct = a.account_number
    masked = f"****{acct[-4:]}" if acct and len(acct) >= 4 else acct
    return {"method": a.method, "upi_id": a.upi_id, "account_name": a.account_name,
            "account_number_masked": masked, "ifsc": a.ifsc, "verified": a.verified}


@router.get("/payout-account")
def get_payout_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.account import PayoutAccount
    a = db.scalar(select(PayoutAccount).where(PayoutAccount.user_id == user.id))
    return {"account": _payout_json(a)}


@router.put("/payout-account")
def put_payout_account(body: PayoutAccountBody, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    from app.models.account import PayoutAccount

    if body.method not in ("upi", "bank"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "method must be upi or bank")
    if body.method == "upi":
        if not body.upi_id or "@" not in body.upi_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A valid UPI id (name@bank) is required")
    else:
        if not (body.account_name and body.account_number and body.ifsc):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bank name, account number and IFSC are required")
        if len(body.ifsc) != 11:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "IFSC must be 11 characters")
    a = db.scalar(select(PayoutAccount).where(PayoutAccount.user_id == user.id))
    if a is None:
        a = PayoutAccount(user_id=user.id)
        db.add(a)
    a.method = body.method
    a.upi_id = body.upi_id if body.method == "upi" else None
    a.account_name = body.account_name if body.method == "bank" else None
    a.account_number = body.account_number if body.method == "bank" else None
    a.ifsc = body.ifsc if body.method == "bank" else None
    a.verified = False  # re-verify whenever details change
    audit.record(db, actor_id=user.id, action="payout_account.update", object_type="user",
                 object_id=user.id, new_values={"method": body.method})
    db.commit()
    return {"account": _payout_json(a), "ok": True}


# --- Saved delivery addresses (buyers / farmers who buy) -------------------

class AddressBody(BaseModel):
    label: str = "Home"
    mandal_id: int
    address_line: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    is_default: bool = False


def _addr_json(a, mandals: dict) -> dict:
    return {"id": a.id, "label": a.label, "mandal_id": a.mandal_id,
            "mandal": mandals.get(a.mandal_id), "address_line": a.address_line,
            "latitude": float(a.latitude) if a.latitude is not None else None,
            "longitude": float(a.longitude) if a.longitude is not None else None,
            "is_default": a.is_default}


@router.get("/addresses")
def list_addresses(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.account import SavedAddress
    from app.models.location import Mandal
    mandals = {m.id: m.name for m in db.scalars(select(Mandal))}
    rows = db.scalars(select(SavedAddress).where(SavedAddress.user_id == user.id)
                      .order_by(SavedAddress.is_default.desc(), SavedAddress.id.desc()))
    return [_addr_json(a, mandals) for a in rows]


@router.post("/addresses", status_code=status.HTTP_201_CREATED)
def add_address(body: AddressBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.account import SavedAddress
    from app.models.location import Mandal
    if db.get(Mandal, body.mandal_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mandal not found")
    a = SavedAddress(user_id=user.id, label=body.label.strip() or "Home",
                     mandal_id=body.mandal_id, address_line=body.address_line,
                     latitude=body.latitude, longitude=body.longitude,
                     is_default=body.is_default)
    db.add(a)
    db.flush()
    if body.is_default:
        for other in db.scalars(select(SavedAddress).where(
                SavedAddress.user_id == user.id, SavedAddress.id != a.id)):
            other.is_default = False
    db.commit()
    mandals = {m.id: m.name for m in db.scalars(select(Mandal))}
    return _addr_json(a, mandals)


# --- Farmer withdrawals (cash out accrued payout balance) ------------------

def _pending_payout_total(db: Session, user_id: int):
    from app.core.money import money
    from app.models.finance import Payout
    rows = db.scalars(select(Payout).where(Payout.seller_id == user_id, Payout.status == "pending"))
    return money(sum(float(p.amount) for p in rows))


def _wd_json(w) -> dict:
    return {
        "id": w.id, "amount": str(w.amount), "currency": w.currency,
        "method": w.method, "account_masked": w.account_masked, "status": w.status,
        "note": w.note, "decided_at": w.decided_at,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


@router.get("/me/balance")
def my_balance(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Withdrawable balance = accrued payouts awaiting disbursement."""
    from app.core.money import money
    from app.models.account import PayoutAccount
    from app.models.finance import Payout, WithdrawalRequest

    available = _pending_payout_total(db, user.id)
    paid = money(sum(float(p.amount) for p in db.scalars(
        select(Payout).where(Payout.seller_id == user.id, Payout.status == "processed"))))
    req = db.scalar(select(WithdrawalRequest).where(
        WithdrawalRequest.farmer_id == user.id, WithdrawalRequest.status == "requested"))
    acct = db.scalar(select(PayoutAccount).where(PayoutAccount.user_id == user.id))
    from app.services import kyc
    id_ok = kyc.identity_verified(user)
    return {
        "currency": "INR",
        "available": str(available),
        "paid_total": str(paid),
        "pending_withdrawal": str(req.amount) if req else "0.00",
        "has_account": acct is not None,
        "account_verified": bool(acct and acct.verified),
        "identity_verified": id_ok,
        "can_request": bool(acct and acct.verified) and id_ok and available > money(0) and req is None,
    }


@router.get("/me/withdrawals")
def my_withdrawals(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.finance import WithdrawalRequest
    rows = db.scalars(select(WithdrawalRequest).where(WithdrawalRequest.farmer_id == user.id)
                      .order_by(WithdrawalRequest.id.desc()))
    return [_wd_json(w) for w in rows]


@router.post("/me/withdrawals", status_code=status.HTTP_201_CREATED)
def request_withdrawal(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Request a cash-out of the full accrued balance to the verified payout
    account. Finance approves (disburses) or rejects."""
    from app.core.money import money
    from app.models.account import PayoutAccount
    from app.models.finance import WithdrawalRequest

    acct = db.scalar(select(PayoutAccount).where(PayoutAccount.user_id == user.id))
    if acct is None or not acct.verified:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Add and get your payout account verified before withdrawing.")
    from app.services import kyc
    if not kyc.identity_verified(user):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Verify your identity first — upload a government photo ID in your "
                            "profile and wait for approval before withdrawing.")
    if db.scalar(select(WithdrawalRequest).where(
            WithdrawalRequest.farmer_id == user.id, WithdrawalRequest.status == "requested")):
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a withdrawal request pending.")
    available = _pending_payout_total(db, user.id)
    if available <= money(0):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No balance available to withdraw yet.")
    masked = acct.upi_id if acct.method == "upi" else (
        f"****{acct.account_number[-4:]}" if acct.account_number and len(acct.account_number) >= 4
        else acct.account_number)
    w = WithdrawalRequest(farmer_id=user.id, amount=available, method=acct.method,
                          account_masked=masked, status="requested")
    db.add(w)
    # Alert finance (managers + superadmins).
    from app.services import notify
    for f in db.scalars(select(User).where(
            User.role.in_([str(Role.FIELD_MANAGER), str(Role.SUPERADMIN)]), User.status == "active")):
        notify.send(db, user_id=f.id, title="Withdrawal requested",
                    body=f"{user.name or 'A partner'} requested a withdrawal of Rs. {available}.",
                    object_type="payout", object_id=user.id)
    audit.record(db, actor_id=user.id, action="withdrawal.request", object_type="user",
                 object_id=user.id, new_values={"amount": str(available)})
    db.commit()
    db.refresh(w)
    return _wd_json(w)


@router.delete("/addresses/{address_id}")
def delete_address(address_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.account import SavedAddress
    a = db.get(SavedAddress, address_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Address not found")
    db.delete(a)
    db.commit()
    return {"deleted": address_id}


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
