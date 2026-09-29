"""
GET  /api/study-schedule
POST /api/study-schedule/generate
POST /api/study-schedule/modify           (manual, single-session)
POST /api/study-schedule/regenerate       (natural language, whole schedule)
POST /api/study-schedule/{id}/accept

Ties together: context_builder -> AiPlannerService -> scheduler.engine, with
schema validation and student-ownership checks at every step. A student can
only ever read/write schedules where `schedule.student_id == current student`.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.deps import get_db, get_current_student_id, ensure_owns_schedule
from backend.models.models import (
    StudySchedule, StudySession, StudyPreference, ScheduleGenerationLog,
    ScheduleModification, Subject, Topic, ScheduleStatus, SessionStatus as ORMSessionStatus,
    AvailabilityPeriod,
)
from backend.schemas.schemas import (
    StudyScheduleOut, ScheduledSessionOut, UnscheduledTaskOut,
    ManualModificationIn, NaturalLanguageModifyIn, ActivityType, PreferredTime,
    ManualScheduleIn,
)
from backend.services.ai_planner.context_builder import build_student_data
from backend.services.ai_planner.service import AiPlannerService, AiPlannerError
from backend.services.scheduler.engine import run_scheduler
from backend.services.scheduler.slots import AvailabilityWindow
from backend.services.nlp_modify.interpreter import NlModificationInterpreter, NlModificationError
from backend.config import settings  # AI_PROVIDER_API_KEY, AI_MODEL, etc.

logger = logging.getLogger(__name__)
router = APIRouter(tags=["study-schedule"])

ai_planner = AiPlannerService(api_key=settings.AI_PROVIDER_API_KEY, model=settings.AI_MODEL)
nl_interpreter = NlModificationInterpreter(api_key=settings.AI_PROVIDER_API_KEY, model=settings.AI_MODEL)


def _serialize_schedule(db: Session, schedule: StudySchedule) -> StudyScheduleOut:
    sessions_out = []
    for s in schedule.sessions:
        subject = db.get(Subject, s.subject_id)
        topic = db.get(Topic, s.topic_id)
        sessions_out.append(ScheduledSessionOut(
            id=s.id, subject_id=s.subject_id, subject_name=subject.name if subject else "Unknown",
            topic_id=s.topic_id, topic_name=topic.name if topic else "Unknown",
            activity_type=s.activity_type, scheduled_date=s.scheduled_date,
            start_time=s.start_time, end_time=s.end_time, duration_minutes=s.duration_minutes,
            status=s.status, priority=s.priority, reason=s.reason or "",
        ))
    log = db.query(ScheduleGenerationLog).filter(
        ScheduleGenerationLog.schedule_id == schedule.id
    ).order_by(ScheduleGenerationLog.created_at.desc()).first()
    unscheduled_out = []
    if log and log.unscheduled:
        unscheduled_out = [UnscheduledTaskOut(**u) for u in log.unscheduled]
    return StudyScheduleOut(
        id=schedule.id, student_id=schedule.student_id, status=schedule.status.value,
        exam_date=schedule.exam_date, generated_at=schedule.generated_at.isoformat(),
        sessions=sessions_out, unscheduled=unscheduled_out,
        overall_reasoning=(log.raw_ai_plan or {}).get("overall_reasoning") if log else None,
    )


@router.get("/study-schedule", response_model=StudyScheduleOut)
def get_active_schedule(
    db: Session = Depends(get_db),
    student_id: UUID = Depends(get_current_student_id),
):
    schedule = db.query(StudySchedule).filter(
        StudySchedule.student_id == student_id, StudySchedule.status == ScheduleStatus.active
    ).order_by(StudySchedule.generated_at.desc()).first()
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active schedule")
    return _serialize_schedule(db, schedule)


async def _generate_and_persist(
    db: Session,
    student_id: UUID,
    subject_ids: list[UUID],
    manual_priorities: dict[str, int] | None = None,
) -> StudySchedule:
    prefs = db.query(StudyPreference).filter(StudyPreference.student_id == student_id).first()
    if not prefs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Complete the study-preferences step before generating a schedule.")
    if prefs.exam_date < date.today():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="exam_date is in the past")

    student_data = build_student_data(db, student_id, subject_ids, prefs.exam_date, manual_priorities)

    try:
        plan = await ai_planner.generate_plan(student_data)
    except AiPlannerError as e:
        # Failure handling per spec section 29 — never crash, never persist partial output.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    # Build lookups the scheduler needs, from the SAME queried data (no re-invention).
    difficulty_lookup: dict[str, int] = {}
    score_lookup: dict[str, float | None] = {}
    for subj in student_data["subjects"]:
        for t in subj["topics"]:
            difficulty_lookup[t["topic_id"]] = t["difficulty"]
            score_lookup[t["topic_id"]] = t["recent_score_percent"]

    availability_rows = db.query(AvailabilityPeriod).filter_by(student_id=student_id).all()
    availability = [
        AvailabilityWindow(day_of_week=a.day_of_week, start_time=a.start_time,
                            end_time=a.end_time, period_type=a.period_type)
        for a in availability_rows
    ]

    result = run_scheduler(
        tasks=plan.tasks,
        availability=availability,
        session_duration_min=prefs.session_duration_min,
        break_duration_min=prefs.break_duration_min,
        max_sessions_per_day=prefs.max_sessions_per_day,
        preferred_time=PreferredTime(prefs.preferred_time.value),
        start_date=date.today(),
        exam_date=prefs.exam_date,
        topic_difficulty_lookup=difficulty_lookup,
        topic_recent_score_lookup=score_lookup,
    )

    schedule = StudySchedule(student_id=student_id, status=ScheduleStatus.draft, exam_date=prefs.exam_date)
    db.add(schedule)
    db.flush()  # get schedule.id

    for s in result.sessions:
        db.add(StudySession(
            schedule_id=schedule.id, student_id=student_id, subject_id=s.subject_id,
            topic_id=s.topic_id, activity_type=s.activity_type, scheduled_date=s.scheduled_date,
            start_time=s.start_time, end_time=s.end_time, duration_minutes=s.duration_minutes,
            status=ORMSessionStatus.scheduled, priority=s.priority, reason=s.reason,
        ))

    db.add(ScheduleGenerationLog(
        schedule_id=schedule.id,
        raw_ai_plan=plan.model_dump(mode="json"),
        prompt_version="study-planner-v1",
        unscheduled=[u.__dict__ | {"subject_id": str(u.subject_id), "topic_id": str(u.topic_id),
                                    "activity_type": u.activity_type.value}
                     for u in result.unscheduled],
    ))
    db.commit()
    db.refresh(schedule)
    return schedule


@router.post("/study-schedule/generate", response_model=StudyScheduleOut, status_code=status.HTTP_201_CREATED)
async def generate_schedule(
    subject_ids: list[UUID],
    db: Session = Depends(get_db),
    student_id: UUID = Depends(get_current_student_id),
):
    schedule = await _generate_and_persist(db, student_id, subject_ids)
    return _serialize_schedule(db, schedule)


@router.post("/study-schedule/manual", response_model=StudyScheduleOut, status_code=status.HTTP_201_CREATED)
def create_manual_schedule(
    payload: ManualScheduleIn,
    db: Session = Depends(get_db),
    student_id: UUID = Depends(get_current_student_id),
):
    """
    Fully student-authored schedule — no AI planner call, no spaced-repetition
    engine. The student picks every subject/topic/activity/date/time
    themselves. Hard constraints are still enforced here (no double-booking,
    nothing past the exam date, valid subject/topic references) because
    those aren't planning judgment calls, they're data-integrity rules that
    apply regardless of who built the schedule.
    """
    if payload.exam_date < date.today():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="exam_date cannot be in the past")

    # Validate every subject/topic reference exists before writing anything.
    subject_ids = {s.subject_id for s in payload.sessions}
    topic_ids = {s.topic_id for s in payload.sessions}
    found_subjects = {row.id for row in db.query(Subject).filter(Subject.id.in_(subject_ids)).all()}
    found_topics = {row.id for row in db.query(Topic).filter(Topic.id.in_(topic_ids)).all()}
    missing_subjects = subject_ids - found_subjects
    missing_topics = topic_ids - found_topics
    if missing_subjects or missing_topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown subject id(s): {list(missing_subjects)}, unknown topic id(s): {list(missing_topics)}",
        )

    # Check for overlaps and after-exam-date sessions within the submitted
    # batch itself, and against the student's other already-scheduled
    # sessions — the same hard constraints an AI-generated schedule must
    # satisfy, just checked directly instead of via the packing algorithm.
    sorted_sessions = sorted(payload.sessions, key=lambda s: (s.scheduled_date, s.start_time))
    for i, s in enumerate(sorted_sessions):
        if s.scheduled_date > payload.exam_date:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                 detail=f"Session on {s.scheduled_date} is after the exam date")
        end_time = (datetime.combine(s.scheduled_date, s.start_time) +
                    timedelta(minutes=s.duration_minutes)).time()
        for other in sorted_sessions[i + 1:]:
            if other.scheduled_date != s.scheduled_date:
                break
            other_end = (datetime.combine(other.scheduled_date, other.start_time) +
                         timedelta(minutes=other.duration_minutes)).time()
            if s.start_time < other_end and other.start_time < end_time:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Two sessions overlap on {s.scheduled_date}: "
                           f"{s.start_time}-{end_time} and {other.start_time}-{other_end}",
                )

    existing_sessions = db.query(StudySession).filter(
        StudySession.student_id == student_id,
        StudySession.status.in_([ORMSessionStatus.scheduled, ORMSessionStatus.rescheduled]),
    ).all()
    for s in sorted_sessions:
        end_time = (datetime.combine(s.scheduled_date, s.start_time) +
                    timedelta(minutes=s.duration_minutes)).time()
        for existing in existing_sessions:
            if existing.scheduled_date != s.scheduled_date:
                continue
            if s.start_time < existing.end_time and existing.start_time < end_time:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Overlaps an already-scheduled session on {s.scheduled_date} "
                           f"({existing.start_time}-{existing.end_time})",
                )

    schedule = StudySchedule(student_id=student_id, status=ScheduleStatus.draft, exam_date=payload.exam_date)
    db.add(schedule)
    db.flush()

    for s in sorted_sessions:
        end_time = (datetime.combine(s.scheduled_date, s.start_time) +
                    timedelta(minutes=s.duration_minutes)).time()
        db.add(StudySession(
            schedule_id=schedule.id, student_id=student_id, subject_id=s.subject_id,
            topic_id=s.topic_id, activity_type=s.activity_type, scheduled_date=s.scheduled_date,
            start_time=s.start_time, end_time=end_time, duration_minutes=s.duration_minutes,
            status=ORMSessionStatus.scheduled, priority=3, reason="Manually scheduled by student.",
        ))

    db.commit()
    db.refresh(schedule)
    return _serialize_schedule(db, schedule)


@router.post("/study-schedule/regenerate", response_model=StudyScheduleOut)
async def regenerate_schedule(
    payload: NaturalLanguageModifyIn,
    db: Session = Depends(get_db),
    student_id: UUID = Depends(get_current_student_id),
):
    schedule = db.query(StudySchedule).filter(StudySchedule.id == payload.schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    ensure_owns_schedule(schedule.student_id, student_id)

    subject_ids = list({s.subject_id for s in schedule.sessions})
    subjects = db.query(Subject).filter(Subject.id.in_(subject_ids)).all()
    name_to_id = {s.name: str(s.id) for s in subjects}

    try:
        structured = await nl_interpreter.interpret(payload.instruction, name_to_id)
    except NlModificationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    db.add(ScheduleModification(
        schedule_id=schedule.id, modification_type="natural_language",
        instruction_text=payload.instruction, structured_request=structured.model_dump(mode="json"),
        applied_by=student_id,
    ))
    db.commit()

    # NOTE: a full implementation would fold `structured` into run_scheduler's
    # constraints (e.g. filter candidate slots by exclude_time_after/before,
    # bias subject placement toward move_subject_id_to_days). The
    # StructuredModificationRequest -> scheduler wiring point is
    # `run_scheduler`'s `availability`/`preferred_time` args; extend
    # `engine.run_scheduler` with an optional `modification` parameter that
    # filters `free_by_dow` and re-weights `task.priority` accordingly before
    # the greedy placement loop.
    manual_priorities = structured.increase_subject_priority or {}
    new_schedule = await _generate_and_persist(db, student_id, subject_ids, manual_priorities)
    return _serialize_schedule(db, new_schedule)


@router.post("/study-schedule/modify", response_model=ScheduledSessionOut)
def modify_session(
    payload: ManualModificationIn,
    db: Session = Depends(get_db),
    student_id: UUID = Depends(get_current_student_id),
):
    session_row = db.query(StudySession).filter(StudySession.id == payload.session_id).first()
    if not session_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    ensure_owns_schedule(session_row.student_id, student_id)

    schedule = db.get(StudySchedule, session_row.schedule_id)

    new_date = payload.new_date or session_row.scheduled_date
    new_start = payload.new_start_time or session_row.start_time
    new_duration = payload.new_duration_minutes or session_row.duration_minutes

    if new_date > schedule.exam_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Cannot move a session after the exam date")

    from datetime import datetime as dt, timedelta as td
    new_end = (dt.combine(new_date, new_start) + td(minutes=new_duration)).time()

    conflict = db.query(StudySession).filter(
        StudySession.student_id == student_id,
        StudySession.scheduled_date == new_date,
        StudySession.id != session_row.id,
        StudySession.start_time < new_end,
        new_start < StudySession.end_time,
    ).first()
    if conflict:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Requested time overlaps another scheduled session")

    session_row.scheduled_date = new_date
    session_row.start_time = new_start
    session_row.end_time = new_end
    session_row.duration_minutes = new_duration
    if payload.new_activity_type:
        session_row.activity_type = payload.new_activity_type
    session_row.status = ORMSessionStatus.rescheduled

    db.add(ScheduleModification(
        schedule_id=session_row.schedule_id, modification_type="manual",
        structured_request=payload.model_dump(mode="json"), applied_by=student_id,
    ))
    db.commit()
    db.refresh(session_row)

    subject = db.get(Subject, session_row.subject_id)
    topic = db.get(Topic, session_row.topic_id)
    return ScheduledSessionOut(
        id=session_row.id, subject_id=session_row.subject_id,
        subject_name=subject.name if subject else "Unknown",
        topic_id=session_row.topic_id, topic_name=topic.name if topic else "Unknown",
        activity_type=session_row.activity_type, scheduled_date=session_row.scheduled_date,
        start_time=session_row.start_time, end_time=session_row.end_time,
        duration_minutes=session_row.duration_minutes, status=session_row.status,
        priority=session_row.priority, reason=session_row.reason or "",
    )


@router.post("/study-schedule/{schedule_id}/accept", response_model=StudyScheduleOut)
def accept_schedule(
    schedule_id: UUID,
    db: Session = Depends(get_db),
    student_id: UUID = Depends(get_current_student_id),
):
    schedule = db.query(StudySchedule).filter(StudySchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    ensure_owns_schedule(schedule.student_id, student_id)

    # Archive any previously-active schedule for this student.
    db.query(StudySchedule).filter(
        StudySchedule.student_id == student_id, StudySchedule.status == ScheduleStatus.active
    ).update({StudySchedule.status: ScheduleStatus.archived})

    schedule.status = ScheduleStatus.active
    schedule.accepted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(schedule)
    return _serialize_schedule(db, schedule)
