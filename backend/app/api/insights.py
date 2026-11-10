from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.rbac import Role
from app.models.advisory import (CropCalendarTask, CropCase, KnowledgeSource, MarketPrice,
                                 Reminder, Scheme, SchemeApplication, WeatherSnapshot)
from app.models.catalog import Commodity
from app.models.location import District, Mandal, State
from app.models.marketplace import CropInterest, Listing
from app.models.user import FarmerProfile, User

router = APIRouter(tags=["insights"])

_seller = require_roles(Role.FARMER, Role.FPO)


def _scheme_json(s: Scheme) -> dict:
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
        "crops": s.crops or [],
        "regions": s.regions or [],
        "disclaimer": "Do not treat this as a promise of eligibility.",
    }


def _scheme_matches(s: Scheme, crops: set[str], regions: set[str]) -> tuple[bool, str]:
    """Does a scheme target this farmer? crops/regions empty on the scheme = all.
    Returns (matched, human reason)."""
    s_crops = {c.lower() for c in (s.crops or [])}
    s_regions = set(s.regions or [])
    crop_hit = s_crops & crops
    region_hit = s_regions & regions
    crop_ok = (not s_crops) or bool(crop_hit)
    region_ok = (not s_regions) or bool(region_hit)
    if not (crop_ok and region_ok):
        return False, ""
    reasons = []
    if crop_hit:
        reasons.append("for " + "/".join(sorted(crop_hit)) + " growers")
    if region_hit:
        reasons.append("in " + "/".join(sorted(region_hit)))
    if not reasons:
        reasons.append("open to all farmers")
    return True, ", ".join(reasons)


def _farmer_context(db: Session, user: User) -> tuple[set[str], str | None, str | None, int | None]:
    """Derive a farmer's crops (from listings, crop interests and crop cases) and
    their district/state/mandal — the basis for personalised advice."""
    crops: set[str] = set()
    for cid in db.scalars(select(Listing.commodity_id).where(Listing.seller_id == user.id)):
        c = db.get(Commodity, cid)
        if c:
            crops.add(c.name.lower())
    for cid in db.scalars(select(CropInterest.commodity_id).where(CropInterest.user_id == user.id)):
        c = db.get(Commodity, cid)
        if c:
            crops.add(c.name.lower())
    for cr in db.scalars(select(CropCase.crop).where(CropCase.farmer_id == user.id)):
        if cr:
            crops.add(cr.lower())

    fp = db.scalar(select(FarmerProfile).where(FarmerProfile.user_id == user.id))
    district = state = None
    did = fp.district_id if fp else None
    mandal_id = fp.mandal_id if fp else None
    if not did and mandal_id:
        m = db.get(Mandal, mandal_id)
        did = m.district_id if m else None
    if did:
        d = db.get(District, did)
        if d:
            district = d.name
            st = db.get(State, d.state_id)
            state = st.name if st else None
    return crops, district, state, mandal_id


def _latest_snapshot(db: Session, mandal_id: int | None) -> WeatherSnapshot | None:
    """Latest weather for a mandal, falling back to any snapshot in its district
    (nearby weather is better than none in the pilot)."""
    if not mandal_id:
        return None
    snap = db.scalar(
        select(WeatherSnapshot).where(WeatherSnapshot.mandal_id == mandal_id)
        .order_by(WeatherSnapshot.id.desc())
    )
    if snap:
        return snap
    m = db.get(Mandal, mandal_id)
    if m:
        in_district = select(Mandal.id).where(Mandal.district_id == m.district_id)
        snap = db.scalar(
            select(WeatherSnapshot).where(WeatherSnapshot.mandal_id.in_(in_district))
            .order_by(WeatherSnapshot.id.desc())
        )
    return snap


def _weather_advice(payload: dict | None, current_tasks: list | None = None) -> list[dict]:
    """Plain, cautious weather guidance derived from a snapshot — never a command,
    just a heads-up. Ties into the farmer's current-season tasks when relevant."""
    p = payload or {}
    out: list[dict] = []
    if p.get("alert"):
        out.append({"level": "warning", "text": str(p["alert"])})
    rain = p.get("rain_prob_pct")
    if isinstance(rain, (int, float)):
        if rain >= 60:
            out.append({"level": "warning",
                        "text": "High chance of rain — avoid spraying and don't harvest or sun-dry grain in the open."})
        elif rain >= 35:
            out.append({"level": "info",
                        "text": "Some rain likely — plan spraying and drying for a dry window."})
    tmax = p.get("temp_max_c")
    if isinstance(tmax, (int, float)) and tmax >= 38:
        out.append({"level": "info",
                    "text": "High daytime heat — irrigate early morning or evening and watch for heat/water stress."})
    wind = p.get("wind_kmph")
    if isinstance(wind, (int, float)) and wind >= 25:
        out.append({"level": "info", "text": "Windy — postpone spraying to avoid spray drift."})
    # Flag weather-sensitive tasks the farmer has on right now.
    if current_tasks and isinstance(rain, (int, float)) and rain >= 35:
        for t in current_tasks:
            txt = (t.get("task") or "").lower()
            if any(w in txt for w in ("spray", "harvest", "dry", "dust")):
                out.append({"level": "info",
                            "text": f"Your {t['crop']} task “{t['task']}” is weather-sensitive — time it around the rain."})
                break
    return out


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
            "advice": [],
        }
    return {
        "mandal_id": mandal_id,
        "provider": snap.provider,
        "observed_at": snap.observed_at,
        "forecast_horizon": snap.forecast_horizon,
        "stale": snap.stale,
        "payload": snap.payload,
        "advice": _weather_advice(snap.payload),
        "source_note": "Pilot snapshot — not a live forecast feed.",
    }


def _calendar_json(t: CropCalendarTask, month: int) -> dict:
    months = t.months or []
    return {
        "id": t.id,
        "crop": t.crop,
        "window": t.window,
        "task": t.task,
        "task_te": t.task_te,
        "kind": t.kind,
        "source": t.source,
        "version": t.version,
        "months": months,
        "current": month in months,
    }


@router.get("/crop-calendar")
def crop_calendar(crop: str | None = None, db: Session = Depends(get_db)):
    stmt = select(CropCalendarTask)
    if crop:
        stmt = stmt.where(CropCalendarTask.crop == crop)
    month = date.today().month
    return [_calendar_json(t, month) for t in db.scalars(stmt)]


class ReminderCreate(BaseModel):
    calendar_task_id: int | None = None
    due_on: str | None = None
    note: str | None = None


def _suggest_due(task: CropCalendarTask, today: date) -> str | None:
    """Pick a sensible due date for a calendar-task reminder: the 1st of the next
    occurrence of the task's earliest active month."""
    months = sorted(task.months or [])
    if not months:
        return None
    future = [m for m in months if m >= today.month]
    if future:
        return date(today.year, future[0], 1).isoformat()
    return date(today.year + 1, months[0], 1).isoformat()


def _reminder_json(r: Reminder, db: Session, lang_task: dict | None = None) -> dict:
    task = db.get(CropCalendarTask, r.calendar_task_id) if r.calendar_task_id else None
    return {
        "id": r.id,
        "status": r.status,
        "due_on": r.due_on,
        "note": r.note,
        "calendar_task_id": r.calendar_task_id,
        "crop": task.crop if task else None,
        "window": task.window if task else None,
        "task": task.task if task else None,
        "task_te": task.task_te if task else None,
    }


@router.post("/reminders")
def create_reminder(
    body: ReminderCreate, user=Depends(get_current_user), db: Session = Depends(get_db)
):
    due_on = body.due_on
    task = None
    if body.calendar_task_id:
        task = db.get(CropCalendarTask, body.calendar_task_id)
        if not task:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Calendar task not found")
        if not due_on:
            due_on = _suggest_due(task, date.today())
    r = Reminder(
        user_id=user.id,
        calendar_task_id=body.calendar_task_id,
        due_on=due_on,
        note=body.note or (task.task if task else None),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return _reminder_json(r, db)


@router.get("/reminders")
def my_reminders(status_filter: str | None = None,
                 user=Depends(get_current_user), db: Session = Depends(get_db)):
    """The logged-in user's reminders (open + snoozed first), enriched with the
    calendar task they came from."""
    stmt = select(Reminder).where(Reminder.user_id == user.id)
    if status_filter:
        stmt = stmt.where(Reminder.status == status_filter)
    rows = list(db.scalars(stmt.order_by(Reminder.id.desc())))
    rows.sort(key=lambda r: (r.status == "done", r.due_on or "9999"))
    return [_reminder_json(r, db) for r in rows]


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
    return _reminder_json(r, db)


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
def schemes(crop: str | None = None, state: str | None = None,
            district: str | None = None, db: Session = Depends(get_db)):
    """Published schemes. With a crop and/or state/district, returns only the
    schemes targeting that crop/region (each with a match reason)."""
    filtering = bool(crop or state or district)
    crops = {crop.lower()} if crop else set()
    regions = {x for x in (state, district) if x}
    out = []
    for s in db.scalars(select(Scheme).where(Scheme.status == "published")):
        if not filtering:
            out.append(_scheme_json(s))
            continue
        ok, reason = _scheme_matches(s, crops, regions)
        if ok:
            out.append({**_scheme_json(s), "match_reason": reason})
    return out


@router.get("/schemes/{scheme_id}")
def scheme_detail(scheme_id: int, db: Session = Depends(get_db)):
    s = db.get(Scheme, scheme_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scheme not found")
    return _scheme_json(s)


# --- Scheme application tracking ----------------------------------------------
_APP_STATUSES = ("interested", "applied", "received", "rejected")


class SchemeApp(BaseModel):
    status: str
    note: str | None = None


def _app_json(a: SchemeApplication, db: Session) -> dict:
    s = db.get(Scheme, a.scheme_id)
    return {
        "id": a.id,
        "scheme_id": a.scheme_id,
        "scheme_name": s.name if s else None,
        "scheme_name_te": s.name_te if s else None,
        "status": a.status,
        "note": a.note,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


@router.post("/schemes/{scheme_id}/application")
def set_scheme_application(
    scheme_id: int, body: SchemeApp, user=Depends(get_current_user), db: Session = Depends(get_db)
):
    """Farmer records (or updates) where they are on a scheme: interested →
    applied → received (or rejected). One row per farmer+scheme."""
    if body.status not in _APP_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"status must be one of {', '.join(_APP_STATUSES)}")
    if not db.get(Scheme, scheme_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scheme not found")
    app = db.scalar(select(SchemeApplication).where(
        SchemeApplication.user_id == user.id, SchemeApplication.scheme_id == scheme_id))
    if app:
        app.status = body.status
        app.note = body.note
    else:
        app = SchemeApplication(user_id=user.id, scheme_id=scheme_id,
                                status=body.status, note=body.note)
        db.add(app)
    db.commit()
    db.refresh(app)
    return _app_json(app, db)


@router.get("/my-scheme-applications")
def my_scheme_applications(user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(SchemeApplication)
                      .where(SchemeApplication.user_id == user.id)
                      .order_by(SchemeApplication.id.desc()))
    return [_app_json(r, db) for r in rows]


@router.delete("/schemes/{scheme_id}/application")
def clear_scheme_application(
    scheme_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)
):
    app = db.scalar(select(SchemeApplication).where(
        SchemeApplication.user_id == user.id, SchemeApplication.scheme_id == scheme_id))
    if app:
        db.delete(app)
        db.commit()
    return {"ok": True}


@router.get("/my-farm-plan")
def my_farm_plan(user: User = Depends(_seller), db: Session = Depends(get_db)):
    """A farmer's personalised plan: the crop-calendar tasks, government schemes
    and reviewed knowledge that match THEIR crops, district and the current season.
    """
    crops, district, state, mandal_id = _farmer_context(db, user)
    today = date.today()
    month = today.month

    # Calendar for the farmer's own crops, with the current season flagged.
    calendar = []
    for crop in sorted(crops):
        tasks = list(db.scalars(select(CropCalendarTask).where(CropCalendarTask.crop == crop)))
        if not tasks:
            continue
        items = sorted((_calendar_json(t, month) for t in tasks),
                       key=lambda x: (x["months"][0] if x["months"] else 99))
        calendar.append({"crop": crop, "tasks": items})
    # Mark which calendar tasks the farmer already has an active reminder for.
    active_reminders = list(db.scalars(
        select(Reminder).where(Reminder.user_id == user.id, Reminder.status != "done")
    ))
    reminded_task_ids = {r.calendar_task_id for r in active_reminders if r.calendar_task_id}
    for grp in calendar:
        for it in grp["tasks"]:
            it["reminder_set"] = it["id"] in reminded_task_ids
    reminders = sorted((_reminder_json(r, db) for r in active_reminders),
                       key=lambda x: x["due_on"] or "9999")

    current_tasks = [{**it, "crop": grp["crop"]}
                     for grp in calendar for it in grp["tasks"] if it["current"]]

    # Weather for the farmer's locality + plain cautions tied to their tasks.
    snap = _latest_snapshot(db, mandal_id)
    weather = None
    if snap:
        weather = {
            "mandal_id": snap.mandal_id,
            "provider": snap.provider,
            "observed_at": snap.observed_at,
            "forecast_horizon": snap.forecast_horizon,
            "stale": snap.stale,
            "payload": snap.payload,
            "advice": _weather_advice(snap.payload, current_tasks),
            "source_note": "Pilot snapshot — not a live forecast feed.",
        }

    # Schemes matched to the farmer's crops + region, with any tracked status.
    app_status = {a.scheme_id: a.status for a in db.scalars(
        select(SchemeApplication).where(SchemeApplication.user_id == user.id))}
    regions = {x for x in (state, district) if x}
    schemes_matched = []
    for s in db.scalars(select(Scheme).where(Scheme.status == "published")):
        ok, reason = _scheme_matches(s, crops, regions)
        if ok:
            schemes_matched.append({**_scheme_json(s), "match_reason": reason,
                                    "application_status": app_status.get(s.id)})

    # Reviewed knowledge for the farmer's crops.
    knowledge = []
    for crop in sorted(crops):
        for k in db.scalars(select(KnowledgeSource).where(
            KnowledgeSource.status == "published", KnowledgeSource.crop == crop
        )):
            knowledge.append({"id": k.id, "crop": k.crop, "title": k.title,
                              "title_te": k.title_te, "source_name": k.source_name,
                              "source_url": k.source_url})

    return {
        "today": today.isoformat(),
        "month": month,
        "crops": sorted(crops),
        "district": district,
        "state": state,
        "has_profile": bool(crops) or bool(district),
        "weather": weather,
        "current_tasks": current_tasks,
        "calendar": calendar,
        "reminders": reminders,
        "schemes": schemes_matched,
        "knowledge": knowledge,
    }
