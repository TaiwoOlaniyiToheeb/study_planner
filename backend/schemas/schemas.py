"""
Pydantic schemas.

Two families live here:
1. API request/response models (validation for the REST layer).
2. AI planner I/O schemas — the exact contract the LLM must satisfy.
   `AiLearningPlan` is what we validate every LLM response against before
   it is allowed anywhere near the scheduler or the database.
"""
from __future__ import annotations

from datetime import date, time
from enum import Enum
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------

class PreferredTime(str, Enum):
    morning = "morning"
    afternoon = "afternoon"
    evening = "evening"
    no_preference = "no_preference"


class ActivityType(str, Enum):
    learning = "learning"
    practice = "practice"
    revision = "revision"
    assessment = "assessment"
    review = "review"


class SessionStatus(str, Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    missed = "missed"
    skipped = "skipped"
    rescheduled = "rescheduled"


class PeriodType(str, Enum):
    busy = "busy"
    free = "free"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

class AvailabilityPeriodIn(BaseModel):
    day_of_week: int = Field(ge=0, le=6, description="0=Monday .. 6=Sunday")
    start_time: time
    end_time: time
    period_type: PeriodType
    label: Optional[str] = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def check_time_order(self):
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class AvailabilityPeriodOut(AvailabilityPeriodIn):
    id: UUID


# ---------------------------------------------------------------------------
# Study preferences / goal (wizard steps 1 & 3)
# ---------------------------------------------------------------------------

class StudyGoalIn(BaseModel):
    exam_goal_type: str
    exam_goal_other_text: Optional[str] = None
    exam_date: date
    daily_study_minutes_goal: int = Field(gt=0, le=480, description="Hard ceiling: 8h/day")

    @field_validator("exam_date")
    @classmethod
    def exam_date_future(cls, v: date):
        if v < date.today():
            raise ValueError("exam_date cannot be in the past")
        return v


class StudyPreferencesIn(BaseModel):
    preferred_time: PreferredTime = PreferredTime.no_preference
    session_duration_min: int = Field(description="one of 30/45/60/90/120")
    break_duration_min: int = Field(description="one of 5/10/15/20/30")
    max_sessions_per_day: int = Field(ge=1, le=8)

    @field_validator("session_duration_min")
    @classmethod
    def valid_session_duration(cls, v):
        if v not in (30, 45, 60, 90, 120):
            raise ValueError("session_duration_min must be one of 30,45,60,90,120")
        return v

    @field_validator("break_duration_min")
    @classmethod
    def valid_break_duration(cls, v):
        if v not in (5, 10, 15, 20, 30):
            raise ValueError("break_duration_min must be one of 5,10,15,20,30")
        return v


# ---------------------------------------------------------------------------
# Subject priority (wizard step 4)
# ---------------------------------------------------------------------------

class SubjectPriorityIn(BaseModel):
    subject_id: UUID
    manual_priority: Optional[int] = Field(default=None, ge=1, le=5)


# ---------------------------------------------------------------------------
# AI Planner contract — the ONLY thing the LLM is allowed to return
# ---------------------------------------------------------------------------

class LearningTask(BaseModel):
    """One structured recommendation from the AI. No dates/times — ever."""
    subject_id: UUID
    topic_id: UUID
    activity_type: ActivityType
    priority: int = Field(ge=1, le=5)
    estimated_minutes: int = Field(gt=0, le=180)
    reason: str = Field(max_length=280)

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v: str):
        if not v.strip():
            raise ValueError("reason must not be empty")
        return v


class AiLearningPlan(BaseModel):
    """
    The complete, validated response expected from the LLM for a single
    generation/regeneration call. Anything that fails this schema is
    discarded (see services/ai_planner/service.py) — never persisted,
    never passed to the scheduler.
    """
    tasks: List[LearningTask] = Field(min_length=1, max_length=200)
    overall_reasoning: str = Field(max_length=1000)

    @model_validator(mode="after")
    def no_duplicate_subject_topic_activity(self):
        seen = set()
        for t in self.tasks:
            key = (t.subject_id, t.topic_id, t.activity_type)
            if key in seen:
                raise ValueError(f"duplicate task for subject/topic/activity: {key}")
            seen.add(key)
        return self


# ---------------------------------------------------------------------------
# Scheduler output
# ---------------------------------------------------------------------------

class ScheduledSessionOut(BaseModel):
    id: UUID
    subject_id: UUID
    subject_name: str
    topic_id: UUID
    topic_name: str
    activity_type: ActivityType
    scheduled_date: date
    start_time: time
    end_time: time
    duration_minutes: int
    status: SessionStatus
    priority: int
    reason: str


class UnscheduledTaskOut(BaseModel):
    subject_id: UUID
    topic_id: UUID
    activity_type: ActivityType
    estimated_minutes: int
    reason_could_not_schedule: str


class StudyScheduleOut(BaseModel):
    id: UUID
    student_id: UUID
    status: str
    exam_date: date
    generated_at: str
    sessions: List[ScheduledSessionOut]
    unscheduled: List[UnscheduledTaskOut] = []
    overall_reasoning: Optional[str] = None


# ---------------------------------------------------------------------------
# Fully manual scheduling (student builds every session themselves — no AI,
# no spaced-repetition engine). Hard constraints (no overlap, not past the
# exam date, inside declared availability) are still enforced server-side;
# only the AI's prioritization/spaced-repetition layer is skipped.
# ---------------------------------------------------------------------------

class ManualSessionIn(BaseModel):
    subject_id: UUID
    topic_id: UUID
    activity_type: ActivityType
    scheduled_date: date
    start_time: time
    duration_minutes: int = Field(gt=0, le=180)

    @field_validator("scheduled_date")
    @classmethod
    def not_in_the_past(cls, v: date):
        if v < date.today():
            raise ValueError("scheduled_date cannot be in the past")
        return v


class ManualScheduleIn(BaseModel):
    exam_date: date
    sessions: List[ManualSessionIn] = Field(min_length=1, max_length=200)

    @field_validator("exam_date")
    @classmethod
    def exam_date_future(cls, v: date):
        if v < date.today():
            raise ValueError("exam_date cannot be in the past")
        return v


# ---------------------------------------------------------------------------
# Modification requests
# ---------------------------------------------------------------------------

class ManualModificationIn(BaseModel):
    session_id: UUID
    new_date: Optional[date] = None
    new_start_time: Optional[time] = None
    new_activity_type: Optional[ActivityType] = None
    new_duration_minutes: Optional[int] = Field(default=None, gt=0, le=180)


class NaturalLanguageModifyIn(BaseModel):
    schedule_id: UUID
    instruction: str = Field(min_length=1, max_length=500)


class StructuredModificationRequest(BaseModel):
    """
    What the AI is allowed to produce when interpreting a natural-language
    instruction. This is a constraint-adjustment request, NOT a set of
    database writes — the scheduler re-runs with these adjustments and the
    same hard-constraint validation as a normal generation.
    """
    reduce_sessions_on_days: List[int] = Field(default_factory=list)  # 0=Mon..6=Sun
    increase_sessions_on_days: List[int] = Field(default_factory=list)
    move_subject_id_to_days: Optional[dict[str, list[int]]] = None  # {subject_id: [days]}
    exclude_time_after: Optional[time] = None
    exclude_time_before: Optional[time] = None
    increase_subject_priority: Optional[dict[str, int]] = None  # {subject_id: delta}
    notes: str = Field(default="", max_length=280)


class SessionMissedActionIn(BaseModel):
    action: str = Field(pattern="^(mark_completed|reschedule|skip)$")
