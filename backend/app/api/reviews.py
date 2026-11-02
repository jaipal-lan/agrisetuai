from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.money import D
from app.models.carrier import Carrier
from app.models.common import OrderStatus as S
from app.models.order import Order, Shipment
from app.models.review import Review
from app.models.user import User

router = APIRouter(prefix="/reviews", tags=["reviews"])

_REVIEWABLE = {S.DELIVERED_PENDING_ACCEPTANCE, S.COMPLETED, S.SETTLED,
               S.PARTIALLY_REFUNDED, S.REFUNDED}


def summary(db: Session, subject_type: str, subject_id: int) -> dict:
    avg, cnt = db.execute(
        select(func.avg(Review.rating), func.count(Review.id))
        .where(Review.subject_type == subject_type, Review.subject_id == subject_id)
    ).one()
    return {"avg": round(float(avg), 2) if avg is not None else None, "count": int(cnt or 0)}


class ReviewCreate(BaseModel):
    order_id: int
    subject_type: str  # farmer | courier
    rating: int = Field(ge=1, le=5)
    comment: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_review(body: ReviewCreate, user=Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.get(Order, body.order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if user.id != order.buyer_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the buyer can review this order")
    if S(order.status) not in _REVIEWABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, "You can review only after delivery")

    if body.subject_type == "farmer":
        subject_id = order.seller_id
    elif body.subject_type == "courier":
        shipment = db.scalar(select(Shipment).where(Shipment.order_id == order.id))
        if not shipment or not shipment.courier_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "No courier on this order to review")
        subject_id = shipment.courier_id
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "subject_type must be farmer or courier")

    existing = db.scalar(select(Review).where(
        Review.author_id == user.id, Review.order_id == order.id,
        Review.subject_type == body.subject_type,
    ))
    if existing:
        existing.rating = body.rating
        existing.comment = body.comment
        review = existing
    else:
        review = Review(author_id=user.id, order_id=order.id, subject_type=body.subject_type,
                        subject_id=subject_id, rating=body.rating, comment=body.comment)
        db.add(review)

    # Keep the carrier's cached rating in sync.
    if body.subject_type == "courier":
        db.flush()
        s = summary(db, "courier", subject_id)
        carrier = db.get(Carrier, subject_id)
        if carrier:
            carrier.rating = s["avg"]
    db.commit()
    return {"id": review.id, "subject_type": body.subject_type, "subject_id": subject_id,
            "rating": review.rating, "summary": summary(db, body.subject_type, subject_id)}


@router.get("")
def list_reviews(subject_type: str, subject_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Review).where(Review.subject_type == subject_type, Review.subject_id == subject_id)
        .order_by(Review.id.desc()).limit(50)
    )
    return {
        "summary": summary(db, subject_type, subject_id),
        "reviews": [
            {"id": r.id, "rating": r.rating, "comment": r.comment,
             "at": r.created_at.isoformat() if r.created_at else None}
            for r in rows
        ],
    }


@router.get("/for-order/{order_id}")
def reviews_for_order(order_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Which review subjects the buyer has already rated for this order."""
    rows = db.scalars(select(Review).where(Review.order_id == order_id, Review.author_id == user.id))
    done = {r.subject_type: r.rating for r in rows}
    return {"reviewed": done}
