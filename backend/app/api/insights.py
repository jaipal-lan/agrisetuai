from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.advisory import CropCalendarTask, MarketPrice, Reminder, Scheme, WeatherSnapshot
from app.models.location import Mandal

router = APIRouter(tags=["insights"])


@router.get("/weather")
def weather(mandal_id: int, db: Session = Depends(get_db)):
    m = db.get(Mandal, mandal_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mandal not found")
    snap = db.scalar(
        select(WeatherSnapshot)
        .where(WeatherSnapshot.mandal_id == mandal_id)
        .order_by(WeatherSnapshot.id.desc())
    )
    if not snap:
        return {
            "mandal_id": mandal_id,
            "stale": True,
            "provider": None,
            "message": "No weather snapshot for this locality yet.",
        }
    return {
        "mandal_id": mandal_id,
        "provider": snap.provider,
        "observed_at": snap.observed_at,
        "forecast_horizon": snap.forecast_horizon,
        "stale": snap.stale,
        "payload": snap.payload,
        "source_note": "Pilot snapshot — not a live forecast feed.",
    }


@router.get("/crop-calendar")
def crop_calendar(crop: str | None = None, db: Session = Depends(get_db)):
    stmt = select(CropCalendarTask)
    if crop:
        stmt = stmt.where(CropCalendarTask.crop == crop)
    return [
        {
            "id": t.id,
            "crop": t.crop,
            "window": t.window,
            "task": t.task,
            "task_te": t.task_te,
            "kind": t.kind,
            "source": t.source,
            "version": t.version,
        }
        for t in db.scalars(stmt)
    ]


class ReminderCreate(BaseModel):
    calendar_task_id: int | None = None
    due_on: str | None = None
    note: str | None = None


@router.post("/reminders")
def create_reminder(
    body: ReminderCreate, user=Depends(get_current_user), db: Session = Depends(get_db)
):
    r = Reminder(
        user_id=user.id,
        calendar_task_id=body.calendar_task_id,
        due_on=body.due_on,
        note=body.note,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "status": r.status, "due_on": r.due_on}


@router.patch("/reminders/{reminder_id}")
def patch_reminder(
    reminder_id: int,
    status_value: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = db.get(Reminder, reminder_id)
    if not r or r.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reminder not found")
    if status_value not in ("open", "snoozed", "done"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid status")
    r.status = status_value
    db.commit()
    return {"id": r.id, "status": r.status}


@router.get("/market-prices")
def market_prices(commodity: str | None = None, db: Session = Depends(get_db)):
    stmt = select(MarketPrice).order_by(MarketPrice.id.desc())
    if commodity:
        stmt = stmt.where(MarketPrice.commodity == commodity)
    return [
        {
            "id": p.id,
            "market": p.market,
            "commodity": p.commodity,
            "variety": p.variety,
            "min_price": str(p.min_price),
            "max_price": str(p.max_price),
            "modal_price": str(p.modal_price),
            "unit": p.unit,
            "arrivals": p.arrivals,
            "as_of": p.as_of,
            "source_name": p.source_name,
            "source_url": p.source_url,
            "stale": p.stale,
            "disclaimer": "Official market observation, not a guaranteed sale price on this platform.",
        }
        for p in db.scalars(stmt.limit(50))
    ]


@router.get("/schemes")
def schemes(db: Session = Depends(get_db)):
    return [
        {
            "id": s.id,
            "name": s.name,
            "name_te": s.name_te,
            "department": s.department,
            "eligibility": s.eligibility,
            "documents": s.documents,
            "apply_route": s.apply_route,
            "deadline": s.deadline,
            "source_url": s.source_url,
            "last_checked": s.last_checked,
            "disclaimer": "Do not treat this as a promise of eligibility.",
        }
        for s in db.scalars(select(Scheme).where(Scheme.status == "published"))
    ]


@router.get("/schemes/{scheme_id}")
def scheme_detail(scheme_id: int, db: Session = Depends(get_db)):
    s = db.get(Scheme, scheme_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scheme not found")
    return {
        "id": s.id,
        "name": s.name,
        "name_te": s.name_te,
        "department": s.department,
        "eligibility": s.eligibility,
        "documents": s.documents,
        "apply_route": s.apply_route,
        "deadline": s.deadline,
        "source_url": s.source_url,
        "last_checked": s.last_checked,
        "disclaimer": "Do not treat this as a promise of eligibility.",
    }
