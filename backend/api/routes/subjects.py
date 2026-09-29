"""
Minimal endpoints to get subjects/topics/preferences into the database when
there's no existing LMS supplying them. Not fancy — a real LMS would have
its own subject/curriculum management; this exists purely so the standalone
app is usable end-to-end.

GET/POST /api/subjects
POST     /api/subjects/{id}/topics
GET      /api/study-preferences
PUT      /api/study-preferences
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.deps import get_db, get_current_student_id
from backend.models.models import Subject, Topic, StudyPreference, PreferredTime as ORMPreferredTime
from backend.schemas.schemas import StudyGoalIn, StudyPreferencesIn, PreferredTime

router = APIRouter(tags=["subjects"])


class SubjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class SubjectOut(BaseModel):
    id: UUID
    name: str


class TopicIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    difficulty: int = Field(default=3, ge=1, le=5)
    sequence_index: int = 0
    prerequisite_topic_ids: list[UUID] = Field(default_factory=list)


class TopicOut(BaseModel):
    id: UUID
    subject_id: UUID
    name: str
    difficulty: int
    sequence_index: int


@router.get("/subjects", response_model=list[SubjectOut])
def list_subjects(db: Session = Depends(get_db)):
    # Subjects/topics are shared curriculum data, not per-student — no
    # ownership check needed here, only on schedules/sessions/availability.
    return db.query(Subject).all()


@router.post("/subjects", response_model=SubjectOut, status_code=status.HTTP_201_CREATED)
def create_subject(payload: SubjectIn, db: Session = Depends(get_db)):
    subject = Subject(name=payload.name)
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return subject


@router.get("/subjects/{subject_id}/topics", response_model=list[TopicOut])
def list_topics(subject_id: UUID, db: Session = Depends(get_db)):
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
    return db.query(Topic).filter(Topic.subject_id == subject_id).order_by(Topic.sequence_index).all()


@router.post("/subjects/{subject_id}/topics", response_model=TopicOut, status_code=status.HTTP_201_CREATED)
def create_topic(subject_id: UUID, payload: TopicIn, db: Session = Depends(get_db)):
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")

    topic = Topic(subject_id=subject_id, name=payload.name, difficulty=payload.difficulty,
                   sequence_index=payload.sequence_index)
    db.add(topic)
    db.flush()

    from backend.models.models import TopicPrerequisite
    for prereq_id in payload.prerequisite_topic_ids:
        db.add(TopicPrerequisite(topic_id=topic.id, prerequisite_id=prereq_id))

    db.commit()
    db.refresh(topic)
    return topic


# ---------------------------------------------------------------------------
# Study preferences (wizard steps 1 & 3 combined into one settings resource)
# ---------------------------------------------------------------------------

class StudyPreferencesFullIn(BaseModel):
    exam_goal_type: str
    exam_goal_other_text: str | None = None
    exam_date: date
    daily_study_minutes_goal: int = Field(gt=0, le=480)
    preferred_time: PreferredTime = PreferredTime.no_preference
    session_duration_min: int
    break_duration_min: int
    max_sessions_per_day: int = Field(ge=1, le=8)


class StudyPreferencesOut(StudyPreferencesFullIn):
    pass


@router.get("/study-preferences", response_model=StudyPreferencesOut)
def get_preferences(db: Session = Depends(get_db), student_id: UUID = Depends(get_current_student_id)):
    prefs = db.query(StudyPreference).filter(StudyPreference.student_id == student_id).first()
    if not prefs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No preferences set yet")
    return StudyPreferencesOut(
        exam_goal_type=prefs.exam_goal_type, exam_goal_other_text=prefs.exam_goal_other_text,
        exam_date=prefs.exam_date, daily_study_minutes_goal=prefs.daily_study_minutes_goal,
        preferred_time=PreferredTime(prefs.preferred_time.value),
        session_duration_min=prefs.session_duration_min, break_duration_min=prefs.break_duration_min,
        max_sessions_per_day=prefs.max_sessions_per_day,
    )


@router.put("/study-preferences", response_model=StudyPreferencesOut)
def upsert_preferences(
    payload: StudyPreferencesFullIn,
    db: Session = Depends(get_db),
    student_id: UUID = Depends(get_current_student_id),
):
    if payload.exam_date < date.today():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="exam_date cannot be in the past")
    if payload.session_duration_min not in (30, 45, 60, 90, 120):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_duration_min")
    if payload.break_duration_min not in (5, 10, 15, 20, 30):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid break_duration_min")

    prefs = db.query(StudyPreference).filter(StudyPreference.student_id == student_id).first()
    if not prefs:
        prefs = StudyPreference(student_id=student_id)
        db.add(prefs)

    prefs.exam_goal_type = payload.exam_goal_type
    prefs.exam_goal_other_text = payload.exam_goal_other_text
    prefs.exam_date = payload.exam_date
    prefs.daily_study_minutes_goal = payload.daily_study_minutes_goal
    prefs.preferred_time = ORMPreferredTime(payload.preferred_time.value)
    prefs.session_duration_min = payload.session_duration_min
    prefs.break_duration_min = payload.break_duration_min
    prefs.max_sessions_per_day = payload.max_sessions_per_day
    db.commit()
    db.refresh(prefs)

    return StudyPreferencesOut(
        exam_goal_type=prefs.exam_goal_type, exam_goal_other_text=prefs.exam_goal_other_text,
        exam_date=prefs.exam_date, daily_study_minutes_goal=prefs.daily_study_minutes_goal,
        preferred_time=payload.preferred_time, session_duration_min=prefs.session_duration_min,
        break_duration_min=prefs.break_duration_min, max_sessions_per_day=prefs.max_sessions_per_day,
    )
