"""
Assembles the "learning profile" JSON that gets sent to the AI planner.

This is the single place that is LMS-schema-specific: if your existing LMS
stores subjects/topics/assessments differently, change the queries in here
only — everything downstream (prompt.py, service.py, the scheduler) consumes
the plain-dict shape returned by `build_student_data`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.models import (
    Subject, Topic, TopicPrerequisite, CompletedTopic, AssessmentResult,
)


def _recent_score_for_topic(db: Session, student_id: UUID, topic_id: UUID) -> float | None:
    row = (
        db.query(AssessmentResult)
        .filter(AssessmentResult.student_id == student_id, AssessmentResult.topic_id == topic_id)
        .order_by(AssessmentResult.taken_at.desc())
        .first()
    )
    return float(row.score_percent) if row else None


def _days_since_last_revision(db: Session, student_id: UUID, topic_id: UUID) -> int | None:
    row = (
        db.query(AssessmentResult)
        .filter(AssessmentResult.student_id == student_id, AssessmentResult.topic_id == topic_id)
        .order_by(AssessmentResult.taken_at.desc())
        .first()
    )
    if not row:
        return None
    return (datetime.now(timezone.utc).replace(tzinfo=None) - row.taken_at.replace(tzinfo=None)).days


def build_student_data(
    db: Session,
    student_id: UUID,
    subject_ids: list[UUID],
    exam_date: date,
    manual_priorities: dict[str, int] | None = None,
) -> dict[str, Any]:
    """
    Returns a plain-dict "learning profile" for the given student, restricted
    to the subjects they selected/are enrolled in. Only real, queried data
    goes in here — nothing is fabricated, satisfying the "do not invent"
    instruction given to the LLM.
    """
    manual_priorities = manual_priorities or {}
    completed_ids = {
        c.topic_id for c in db.query(CompletedTopic).filter(CompletedTopic.student_id == student_id)
    }

    subjects_payload = []
    for subject in db.query(Subject).filter(Subject.id.in_(subject_ids)):
        topics_payload = []
        for topic in db.query(Topic).filter(Topic.subject_id == subject.id):
            prereqs = [
                p.prerequisite_id
                for p in db.query(TopicPrerequisite).filter(TopicPrerequisite.topic_id == topic.id)
            ]
            prereqs_met = all(p in completed_ids for p in prereqs)
            topics_payload.append({
                "topic_id": str(topic.id),
                "name": topic.name,
                "difficulty": topic.difficulty,
                "sequence_index": topic.sequence_index,
                "is_completed": topic.id in completed_ids,
                "prerequisites_met": prereqs_met,
                "recent_score_percent": _recent_score_for_topic(db, student_id, topic.id),
                "days_since_last_activity": _days_since_last_revision(db, student_id, topic.id),
            })
        subjects_payload.append({
            "subject_id": str(subject.id),
            "name": subject.name,
            "manual_priority": manual_priorities.get(str(subject.id)),
            "topics": topics_payload,
        })

    return {
        "exam_date": exam_date.isoformat(),
        "days_to_exam": (exam_date - date.today()).days,
        "subjects": subjects_payload,
    }
