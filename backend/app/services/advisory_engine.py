"""Crop-image / symptom triage against a reviewed knowledge base.

Returns likelihoods with uncertainty. Never invents pesticide doses or label claims.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.advisory import KnowledgeSource

LOW_CONFIDENCE_NOTE = (
    "This is decision-support, not a diagnosis. Low-confidence cases must be "
    "escalated to a qualified agronomist or agriculture officer."
)

NO_DOSE_NOTE = (
    "No pesticide dose is shown unless it is copied from a reviewed, "
    "crop-and-formulation-specific product label in the knowledge base. "
    "The model must not invent a dose."
)


def triage(db: Session, *, crop: str, notes: str | None, context: dict | None) -> dict:
    crop_key = (crop or "").strip().lower()
    blob = " ".join(
        [
            crop_key,
            (notes or "").lower(),
            " ".join(str(v).lower() for v in (context or {}).values()),
        ]
    )
    sources = list(
        db.scalars(
            select(KnowledgeSource).where(
                KnowledgeSource.status == "published",
            )
        )
    )
    scored: list[tuple[int, KnowledgeSource]] = []
    for src in sources:
        keys = [k.lower() for k in (src.keywords or [])]
        hits = sum(1 for k in keys if k and k in blob)
        if src.crop.lower() in crop_key or crop_key in src.crop.lower():
            hits += 2
        if hits:
            scored.append((hits, src))
    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        return {
            "likely_causes": [
                {
                    "label": "Uncertain — insufficient evidence",
                    "likelihood": "unknown",
                    "uncertainty": "high",
                    "category": "unknown",
                }
            ],
            "immediate_steps": [
                "Capture a whole-plant photo, a close-up of the damage, and a healthy comparison.",
                "Note crop stage, when symptoms began, recent weather and any spray/fertiliser used.",
                "Contact the local agriculture officer or platform agronomist if the crop is at risk.",
            ],
            "pesticide": None,
            "pesticide_note": NO_DOSE_NOTE,
            "confidence": "low",
            "escalate": True,
            "disclaimer": LOW_CONFIDENCE_NOTE,
            "knowledge_source_id": None,
            "knowledge_version": None,
        }

    src = scored[0][1]
    content = src.content or {}
    pesticide = content.get("pesticide")
    # Only pass through pesticide info that is explicitly label-sourced.
    if pesticide and not pesticide.get("label_sourced"):
        pesticide = None
    if pesticide and not pesticide.get("dose"):
        pesticide = {**pesticide, "dose": None, "dose_note": NO_DOSE_NOTE}

    confidence = content.get("confidence", "medium")
    escalate = bool(content.get("escalate", confidence == "low"))
    return {
        "likely_causes": content.get("likely_causes")
        or [
            {
                "label": src.title,
                "likelihood": "possible",
                "uncertainty": "medium",
                "category": content.get("category", "undifferentiated"),
            }
        ],
        "immediate_steps": content.get("immediate_steps")
        or [
            "Scout the field and compare affected vs healthy plants.",
            "Prefer cultural / IPM steps before any chemical option.",
        ],
        "ipm_order": content.get("ipm_order")
        or [
            "Confirm crop, pest/symptom and severity.",
            "Cultural controls first.",
            "Physical/biological options where evidence fits.",
            "Approved, label-consistent pesticide only if warranted — with expert escalation.",
        ],
        "pesticide": pesticide,
        "pesticide_note": NO_DOSE_NOTE,
        "confidence": confidence,
        "escalate": escalate,
        "disclaimer": LOW_CONFIDENCE_NOTE,
        "knowledge_source_id": src.id,
        "knowledge_version": src.version,
        "source_name": src.source_name,
        "reviewed_on": src.reviewed_on,
    }
