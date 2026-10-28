import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rbac import Role
from app.core.security import check_otp, issue_token, set_otp
from app.core.serializers import self_user
from app.models.user import User

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


@router.post("/otp/request")
def request_otp(body: OtpRequest, db: Session = Depends(get_db)):
    phone = body.phone.strip()
    if not phone.isdigit() or len(phone) not in _PHONE_OK:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid phone number")
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
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        created = True

    return {
        "token": issue_token(user.id),
        "created": created,
        "user": self_user(user),
    }


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return self_user(user)
