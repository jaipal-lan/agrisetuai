from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.ids import case_id
from app.core.rbac import Role
from app.models.advisory import CropCase, KnowledgeSource
from app.services import audit
from app.services.advisory_engine import triage

router = APIRouter(tags=["advisory"])

_reviewer = require_roles(Role.AGRONOMIST, Role.SUPERADMIN, Role.MANDAL_MANAGER)


class CropCaseCreate(BaseModel):
    crop: str
    commodity_id: int | None = None
    variety: str | None = None
    growth_stage: str | None = None
    mandal_id: int | None = None
    symptoms_began: str | None = None
    notes: str | None = None
    media_refs: list[str] | None = None
    context: dict | None = None


def _case_json(c: CropCase) -> dict:
    return {
        "id": c.id,
        "public_id": c.public_id,
        "crop": c.crop,
        "variety": c.variety,
        "growth_stage": c.growth_stage,
        "notes": c.notes,
        "ai_output": c.ai_output,
        "confidence": c.confidence,
        "escalated": c.escalated,
        "status": c.status,
        "expert_review": c.expert_review,
        "farmer_ack": c.farmer_ack,
        "knowledge_source_id": c.knowledge_source_id,
    }


@router.post("/ai/crop-cases", status_code=status.HTTP_201_CREATED)
def create_crop_case(
    body: CropCaseCreate, user=Depends(get_current_user), db: Session = Depends(get_db)
):
    result = triage(db, crop=body.crop, notes=body.notes, context=body.context,
                    media_refs=body.media_refs)
    c = CropCase(
        public_id=case_id(),
        farmer_id=user.id,
        commodity_id=body.commodity_id,
        crop=body.crop,
        variety=body.variety,
        growth_stage=body.growth_stage,
        mandal_id=body.mandal_id,
        symptoms_began=body.symptoms_began,
        notes=body.notes,
        media_refs={"refs": body.media_refs or []},
        context=body.context,
        ai_output=result,
        confidence=result["confidence"],
        knowledge_source_id=result.get("knowledge_source_id"),
        escalated=bool(result.get("escalate")),
        status="escalated" if result.get("escalate") else "triaged",
    )
    db.add(c)
    audit.record(
        db,
        actor_id=user.id,
        action="advisory.crop_case",
        object_type="crop_case",
        object_id=c.public_id,
        new_values={"confidence": result["confidence"], "escalate": result.get("escalate")},
    )
    db.commit()
    db.refresh(c)
    return _case_json(c)


@router.get("/ai/crop-cases")
def my_cases(user=Depends(get_current_user), db: Session = Depends(get_db)):
    staff = user.role in (Role.AGRONOMIST, Role.SUPERADMIN, Role.FIELD_AGENT, Role.MANDAL_MANAGER)
    stmt = select(CropCase).order_by(CropCase.id.desc())
    if not staff:
        stmt = stmt.where(CropCase.farmer_id == user.id)
    return [_case_json(c) for c in db.scalars(stmt.limit(50))]


@router.get("/ai/crop-cases/{case_id}")
def get_case(case_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.get(CropCase, case_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    staff = user.role in (Role.AGRONOMIST, Role.SUPERADMIN, Role.FIELD_AGENT, Role.MANDAL_MANAGER)
    if not staff and c.farmer_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your case")
    return _case_json(c)


class ExpertReview(BaseModel):
    note: str
    approved_advice: str | None = None
    harmful: bool = False


@router.post("/ai/crop-cases/{case_id}/expert-review")
def expert_review(
    case_id: int, body: ExpertReview, user=Depends(_reviewer), db: Session = Depends(get_db)
):
    c = db.get(CropCase, case_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    c.expert_id = user.id
    c.expert_review = {
        "note": body.note,
        "approved_advice": body.approved_advice,
        "harmful": body.harmful,
    }
    c.status = "reviewed"
    if body.harmful:
        c.status = "flagged"
    audit.record(
        db,
        actor_id=user.id,
        action="advisory.expert_review",
        object_type="crop_case",
        object_id=c.public_id,
        reason="harmful" if body.harmful else "reviewed",
    )
    db.commit()
    return _case_json(c)


@router.get("/advisories")
def advisories(crop: str | None = None, db: Session = Depends(get_db)):
    stmt = select(KnowledgeSource).where(KnowledgeSource.status == "published")
    if crop:
        stmt = stmt.where(KnowledgeSource.crop == crop)
    return [
        {
            "id": s.id,
            "slug": s.slug,
            "crop": s.crop,
            "title": s.title,
            "title_te": s.title_te,
            "source_name": s.source_name,
            "source_url": s.source_url,
            "reviewed_on": s.reviewed_on,
            "version": s.version,
            "content": s.content,
        }
        for s in db.scalars(stmt)
    ]
