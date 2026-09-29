"""
GET/POST/PUT/DELETE /api/study-availability

CRUD for weekly availability periods (busy/free). Enforces:
  - start_time < end_time (schema-level, re-checked here defensively)
  - no overlap between periods of the SAME type on the SAME day for the
    SAME student (application-level check; see database migration comment
    for an optional DB-level EXCLUDE constraint).
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.deps import get_db, get_current_student_id
from backend.models.models import AvailabilityPeriod
from backend.schemas.schemas import AvailabilityPeriodIn, AvailabilityPeriodOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["availability"])


def _times_overlap(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end


@router.get("/study-availability", response_model=list[AvailabilityPeriodOut])
def list_availability(
    db: Session = Depends(get_db),
    student_id: UUID = Depends(get_current_student_id),
):
    rows = db.query(AvailabilityPeriod).filter(AvailabilityPeriod.student_id == student_id).all()
    return rows


@router.post("/study-availability", response_model=AvailabilityPeriodOut, status_code=status.HTTP_201_CREATED)
def create_availability(
    payload: AvailabilityPeriodIn,
    db: Session = Depends(get_db),
    student_id: UUID = Depends(get_current_student_id),
):
    existing = db.query(AvailabilityPeriod).filter(
        AvailabilityPeriod.student_id == student_id,
        AvailabilityPeriod.day_of_week == payload.day_of_week,
        AvailabilityPeriod.period_type == payload.period_type.value,
    ).all()
    for row in existing:
        if _times_overlap(payload.start_time, payload.end_time, row.start_time, row.end_time):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Overlaps an existing {payload.period_type.value} period "
                       f"({row.start_time}-{row.end_time}) on this day.",
            )

    row = AvailabilityPeriod(
        student_id=student_id,
        day_of_week=payload.day_of_week,
        start_time=payload.start_time,
        end_time=payload.end_time,
        period_type=payload.period_type.value,
        label=payload.label,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/study-availability/{period_id}", response_model=AvailabilityPeriodOut)
def update_availability(
    period_id: UUID,
    payload: AvailabilityPeriodIn,
    db: Session = Depends(get_db),
    student_id: UUID = Depends(get_current_student_id),
):
    row = db.query(AvailabilityPeriod).filter(
        AvailabilityPeriod.id == period_id, AvailabilityPeriod.student_id == student_id
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Availability period not found")

    conflicting = db.query(AvailabilityPeriod).filter(
        AvailabilityPeriod.student_id == student_id,
        AvailabilityPeriod.day_of_week == payload.day_of_week,
        AvailabilityPeriod.period_type == payload.period_type.value,
        AvailabilityPeriod.id != period_id,
    ).all()
    for other in conflicting:
        if _times_overlap(payload.start_time, payload.end_time, other.start_time, other.end_time):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Overlaps another period")

    row.day_of_week = payload.day_of_week
    row.start_time = payload.start_time
    row.end_time = payload.end_time
    row.period_type = payload.period_type.value
    row.label = payload.label
    db.commit()
    db.refresh(row)
    return row


@router.delete("/study-availability/{period_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_availability(
    period_id: UUID,
    db: Session = Depends(get_db),
    student_id: UUID = Depends(get_current_student_id),
):
    row = db.query(AvailabilityPeriod).filter(
        AvailabilityPeriod.id == period_id, AvailabilityPeriod.student_id == student_id
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Availability period not found")
    db.delete(row)
    db.commit()
