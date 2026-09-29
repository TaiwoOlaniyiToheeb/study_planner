"""
SQLAlchemy ORM models for the AI Study Schedule feature.

Tables tagged `# EXISTING TABLE (placeholder)` are assumed to already exist
in your LMS. If they do, delete the class here and instead import your real
model, or repoint `__tablename__` / column `name=` kwargs at your existing
schema — the rest of this codebase only depends on the attribute names used
in this file (e.g. `Topic.difficulty`, `CompletedTopic.topic_id`), not on the
underlying table structure.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, date, time, timezone

from sqlalchemy import (
    Column, String, Integer, SmallInteger, Boolean, Date, Time, DateTime,
    ForeignKey, Text, Numeric, CheckConstraint, UniqueConstraint, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

# Portable JSON type: JSONB on Postgres (production), plain JSON on SQLite
# (so local smoke-testing/dev doesn't require a running Postgres instance).
PortableJSON = JSON().with_variant(JSONB, "postgresql")


def _uuid_col(**kw):
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, **kw)


def _utcnow() -> datetime:
    """Timezone-aware replacement for the deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# EXISTING TABLE (placeholder) — remove and reuse your real models if present
# ---------------------------------------------------------------------------

class Student(Base):
    __tablename__ = "students"
    id = _uuid_col()
    full_name = Column(String(255), nullable=False)
    timezone = Column(String(64), nullable=False, default="UTC")
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class Subject(Base):
    __tablename__ = "subjects"
    id = _uuid_col()
    name = Column(String(255), nullable=False)
    topics = relationship("Topic", back_populates="subject")


class Topic(Base):
    __tablename__ = "topics"
    id = _uuid_col()
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    difficulty = Column(SmallInteger, nullable=False, default=3)  # 1-5
    sequence_index = Column(Integer, nullable=False, default=0)
    subject = relationship("Subject", back_populates="topics")


class TopicPrerequisite(Base):
    __tablename__ = "topic_prerequisites"
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True)
    prerequisite_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True)


class CompletedTopic(Base):
    __tablename__ = "completed_topics"
    id = _uuid_col()
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    completed_at = Column(DateTime(timezone=True), default=_utcnow)
    __table_args__ = (UniqueConstraint("student_id", "topic_id"),)


class AssessmentResult(Base):
    __tablename__ = "assessment_results"
    id = _uuid_col()
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    score_percent = Column(Numeric(5, 2), nullable=False)
    taken_at = Column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# FEATURE TABLES (new)
# ---------------------------------------------------------------------------

class PreferredTime(str, enum.Enum):
    morning = "morning"
    afternoon = "afternoon"
    evening = "evening"
    no_preference = "no_preference"


class StudyPreference(Base):
    __tablename__ = "study_preferences"
    id = _uuid_col()
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"),
                         nullable=False, unique=True)
    preferred_time = Column(SAEnum(PreferredTime, name="preferred_time_enum"),
                             nullable=False, default=PreferredTime.no_preference)
    session_duration_min = Column(Integer, nullable=False)
    break_duration_min = Column(Integer, nullable=False)
    max_sessions_per_day = Column(Integer, nullable=False)
    daily_study_minutes_goal = Column(Integer, nullable=False)
    exam_goal_type = Column(String(50), nullable=False)
    exam_goal_other_text = Column(String(255), nullable=True)
    exam_date = Column(Date, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        CheckConstraint("session_duration_min IN (30,45,60,90,120)", name="chk_session_duration"),
        CheckConstraint("break_duration_min IN (5,10,15,20,30)", name="chk_break_duration"),
        CheckConstraint("max_sessions_per_day BETWEEN 1 AND 8", name="chk_max_sessions"),
    )


class AvailabilityPeriod(Base):
    __tablename__ = "availability_periods"
    id = _uuid_col()
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    day_of_week = Column(SmallInteger, nullable=False)  # 0=Monday .. 6=Sunday
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    period_type = Column(String(10), nullable=False)  # 'busy' | 'free'
    label = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="chk_dow"),
        CheckConstraint("period_type IN ('busy','free')", name="chk_period_type"),
        CheckConstraint("start_time < end_time", name="chk_time_order"),
    )


class ScheduleStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    archived = "archived"


class StudySchedule(Base):
    __tablename__ = "study_schedules"
    id = _uuid_col()
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    status = Column(SAEnum(ScheduleStatus, name="schedule_status_enum"),
                     nullable=False, default=ScheduleStatus.draft)
    exam_date = Column(Date, nullable=False)
    generated_at = Column(DateTime(timezone=True), default=_utcnow)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, nullable=False, default=1)

    sessions = relationship("StudySession", back_populates="schedule", cascade="all, delete-orphan")


class ActivityType(str, enum.Enum):
    learning = "learning"
    practice = "practice"
    revision = "revision"
    assessment = "assessment"
    review = "review"


class SessionStatus(str, enum.Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    missed = "missed"
    skipped = "skipped"
    rescheduled = "rescheduled"


class StudySession(Base):
    __tablename__ = "study_sessions"
    id = _uuid_col()
    schedule_id = Column(UUID(as_uuid=True), ForeignKey("study_schedules.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id"), nullable=False)
    activity_type = Column(SAEnum(ActivityType, name="activity_type_enum"), nullable=False)
    scheduled_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    status = Column(SAEnum(SessionStatus, name="session_status_enum"),
                     nullable=False, default=SessionStatus.scheduled)
    priority = Column(SmallInteger, nullable=False, default=3)
    reason = Column(Text, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    schedule = relationship("StudySchedule", back_populates="sessions")

    __table_args__ = (
        CheckConstraint("start_time < end_time", name="chk_session_time_order"),
    )


class ScheduleGenerationLog(Base):
    __tablename__ = "schedule_generation_logs"
    id = _uuid_col()
    schedule_id = Column(UUID(as_uuid=True), ForeignKey("study_schedules.id", ondelete="CASCADE"), nullable=False)
    raw_ai_plan = Column(PortableJSON, nullable=False)
    prompt_version = Column(String(50), nullable=False)
    unscheduled = Column(PortableJSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class ScheduleModification(Base):
    __tablename__ = "schedule_modifications"
    id = _uuid_col()
    schedule_id = Column(UUID(as_uuid=True), ForeignKey("study_schedules.id", ondelete="CASCADE"), nullable=False)
    modification_type = Column(String(20), nullable=False)  # manual | natural_language | adaptive
    instruction_text = Column(Text, nullable=True)
    structured_request = Column(PortableJSON, nullable=True)
    applied_at = Column(DateTime(timezone=True), default=_utcnow)
    applied_by = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=True)
