from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from datetime import date

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.ids import case_id
from app.core.rbac import Role
from app.models.advisory import AdvisoryLog, CropCase, KnowledgeSource
from app.models.user import User
from app.services import audit
from app.services.advisory_engine import triage

router = APIRouter(tags=["advisory"])

_reviewer = require_roles(Role.AGRONOMIST, Role.SUPERADMIN, Role.MANDAL_MANAGER)
_seller = require_roles(Role.FARMER, Role.FPO)


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


@router.get("/my-advisory")
def my_advisory(user=Depends(_seller), db: Session = Depends(get_db)):
    """A farmer's own advisory notes, logged by their field agent — with any
    upcoming follow-ups highlighted. The farmer's side of the advisory log."""
    from app.api.agents import _parse_follow_date

    today = date.today()
    rows = db.scalars(
        select(AdvisoryLog).where(AdvisoryLog.farmer_id == user.id)
        .order_by(AdvisoryLog.id.desc()).limit(100)
    )
    notes, upcoming = [], []
    for l in rows:
        agent = db.get(User, l.agent_id)
        item = {
            "id": l.id,
            "crop": l.crop,
            "topic": l.topic,
            "observation": l.observation,
            "recommendation": l.recommendation,
            "follow_up_on": l.follow_up_on,
            "follow_up_done": l.follow_up_done,
            "farmer_ack": l.farmer_ack,
            "farmer_ack_status": l.farmer_ack_status,
            "farmer_ack_note": l.farmer_ack_note,
            "farmer_ack_at": l.farmer_ack_at.isoformat() if l.farmer_ack_at else None,
            "agent_name": agent.name if agent else None,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        notes.append(item)
        d = _parse_follow_date(l.follow_up_on)
        if d is not None and not l.follow_up_done and d >= today:
            upcoming.append({**item, "follow_up_date": d.isoformat(), "days_until": (d - today).days})
    upcoming.sort(key=lambda x: x["follow_up_date"])
    return {"today": today.isoformat(), "notes": notes, "upcoming": upcoming}


class AdvisoryAck(BaseModel):
    status: str = "done"  # done | doing | question
    note: str | None = None


_ACK_LABEL = {
    "done": "has done this",
    "doing": "is working on this",
    "question": "has a question",
}


@router.post("/my-advisory/{log_id}/acknowledge")
def acknowledge_advisory(
    log_id: int, body: AdvisoryAck, user=Depends(_seller), db: Session = Depends(get_db)
):
    """The farmer replies to a piece of advice — 'done', 'working on it' or 'I have
    a question' (+ optional note). Notifies the agent so the loop is closed."""
    from datetime import datetime, timezone

    from app.services import notify

    log = db.get(AdvisoryLog, log_id)
    if not log or log.farmer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Advisory note not found")
    if body.status not in _ACK_LABEL:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "status must be done, doing or question")

    log.farmer_ack = True
    log.farmer_ack_status = body.status
    log.farmer_ack_note = (body.note or None)
    log.farmer_ack_at = datetime.now(timezone.utc)
    log.agent_ack_seen = False
    # When the farmer confirms it's done, clear the agent's follow-up to-do too.
    if body.status == "done":
        log.follow_up_done = True

    # Tell the agent who logged the advice.
    crop_txt = f" on {log.crop}" if log.crop else ""
    note_txt = f" — “{body.note}”" if body.note else ""
    notify.send(
        db, user_id=log.agent_id,
        title="Farmer responded to your advice",
        body=f"{user.name or 'The farmer'} {_ACK_LABEL[body.status]}{crop_txt}.{note_txt}",
        object_type="advisory_log", object_id=log.id,
    )
    db.commit()
    return {
        "id": log.id, "farmer_ack": True, "farmer_ack_status": log.farmer_ack_status,
        "farmer_ack_note": log.farmer_ack_note,
        "farmer_ack_at": log.farmer_ack_at.isoformat(),
        "follow_up_done": log.follow_up_done,
    }


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
