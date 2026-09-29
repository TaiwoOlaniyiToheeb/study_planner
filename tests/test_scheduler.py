"""
Unit tests for the deterministic scheduling engine. No DB, no LLM — pure
function tests, which is exactly why hard constraints live in engine.py
rather than being trusted to the AI.
"""
from datetime import date, time, timedelta
from uuid import uuid4

import pytest

from backend.schemas.schemas import LearningTask, ActivityType, PreferredTime
from backend.services.scheduler.slots import AvailabilityWindow
from backend.services.scheduler.engine import run_scheduler


def _monday_evening_availability():
    # Monday (0) 17:00-21:00 free, rest of week no free periods declared.
    return [AvailabilityWindow(day_of_week=0, start_time=time(17, 0), end_time=time(21, 0), period_type="free")]


def _make_task(subject_id, topic_id, activity=ActivityType.learning, priority=5, minutes=60):
    return LearningTask(
        subject_id=subject_id, topic_id=topic_id, activity_type=activity,
        priority=priority, estimated_minutes=minutes, reason="test task",
    )


def test_schedule_falls_inside_availability():
    subject_id, topic_id = uuid4(), uuid4()
    task = _make_task(subject_id, topic_id)
    exam = date.today() + timedelta(days=30)
    result = run_scheduler(
        tasks=[task], availability=_monday_evening_availability(),
        session_duration_min=60, break_duration_min=15, max_sessions_per_day=3,
        preferred_time=PreferredTime.no_preference, start_date=date.today(), exam_date=exam,
        topic_difficulty_lookup={str(topic_id): 3}, topic_recent_score_lookup={str(topic_id): None},
    )
    assert len(result.sessions) == 1
    s = result.sessions[0]
    assert time(17, 0) <= s.start_time
    assert s.end_time <= time(21, 0)


def test_no_scheduling_outside_availability():
    # No free periods declared at all -> nothing can be scheduled.
    subject_id, topic_id = uuid4(), uuid4()
    task = _make_task(subject_id, topic_id)
    exam = date.today() + timedelta(days=5)
    result = run_scheduler(
        tasks=[task], availability=[], session_duration_min=60, break_duration_min=15,
        max_sessions_per_day=3, preferred_time=PreferredTime.no_preference,
        start_date=date.today(), exam_date=exam,
        topic_difficulty_lookup={str(topic_id): 3}, topic_recent_score_lookup={str(topic_id): None},
    )
    assert len(result.sessions) == 0
    assert len(result.unscheduled) == 1


def test_no_overlapping_sessions():
    subject_id = uuid4()
    topics = [uuid4() for _ in range(6)]
    tasks = [_make_task(subject_id, t, priority=5, minutes=60) for t in topics]
    exam = date.today() + timedelta(days=10)
    availability = [AvailabilityWindow(day_of_week=d, start_time=time(17, 0), end_time=time(21, 0),
                                        period_type="free") for d in range(7)]
    result = run_scheduler(
        tasks=tasks, availability=availability, session_duration_min=60, break_duration_min=15,
        max_sessions_per_day=8, preferred_time=PreferredTime.no_preference,
        start_date=date.today(), exam_date=exam,
        topic_difficulty_lookup={str(t): 3 for t in topics},
        topic_recent_score_lookup={str(t): None for t in topics},
    )
    by_day: dict = {}
    for s in result.sessions:
        by_day.setdefault(s.scheduled_date, []).append((s.start_time, s.end_time))
    for day_sessions in by_day.values():
        day_sessions.sort()
        for i in range(len(day_sessions) - 1):
            assert day_sessions[i][1] <= day_sessions[i + 1][0], "sessions overlap"


def test_max_sessions_per_day_enforced():
    subject_id = uuid4()
    topics = [uuid4() for _ in range(10)]
    tasks = [_make_task(subject_id, t, minutes=30) for t in topics]
    exam = date.today() + timedelta(days=3)
    availability = [AvailabilityWindow(day_of_week=d, start_time=time(8, 0), end_time=time(22, 0),
                                        period_type="free") for d in range(7)]
    result = run_scheduler(
        tasks=tasks, availability=availability, session_duration_min=30, break_duration_min=5,
        max_sessions_per_day=2, preferred_time=PreferredTime.no_preference,
        start_date=date.today(), exam_date=exam,
        topic_difficulty_lookup={str(t): 3 for t in topics},
        topic_recent_score_lookup={str(t): None for t in topics},
    )
    by_day: dict = {}
    for s in result.sessions:
        by_day[s.scheduled_date] = by_day.get(s.scheduled_date, 0) + 1
    assert all(count <= 2 for count in by_day.values())


def test_never_schedules_after_exam_date():
    subject_id, topic_id = uuid4(), uuid4()
    task = _make_task(subject_id, topic_id)
    exam = date.today() + timedelta(days=2)
    availability = [AvailabilityWindow(day_of_week=d, start_time=time(0, 0), end_time=time(23, 59),
                                        period_type="free") for d in range(7)]
    result = run_scheduler(
        tasks=[task], availability=availability, session_duration_min=60, break_duration_min=10,
        max_sessions_per_day=5, preferred_time=PreferredTime.no_preference,
        start_date=date.today(), exam_date=exam,
        topic_difficulty_lookup={str(topic_id): 3}, topic_recent_score_lookup={str(topic_id): None},
    )
    for s in result.sessions:
        assert s.scheduled_date <= exam


def test_preferred_time_optimization():
    subject_id, topic_id = uuid4(), uuid4()
    task = _make_task(subject_id, topic_id)
    exam = date.today() + timedelta(days=10)
    # Free all day; preference should push the session into the evening window.
    availability = [AvailabilityWindow(day_of_week=0, start_time=time(6, 0), end_time=time(22, 0),
                                        period_type="free")]
    result = run_scheduler(
        tasks=[task], availability=availability, session_duration_min=60, break_duration_min=10,
        max_sessions_per_day=3, preferred_time=PreferredTime.evening,
        start_date=date.today(), exam_date=exam,
        topic_difficulty_lookup={str(topic_id): 3}, topic_recent_score_lookup={str(topic_id): None},
    )
    assert len(result.sessions) == 1
    assert result.sessions[0].start_time >= time(17, 0)


def test_unscheduled_tasks_reported_not_dropped():
    subject_id = uuid4()
    topics = [uuid4() for _ in range(5)]
    tasks = [_make_task(subject_id, t, minutes=90) for t in topics]
    exam = date.today() + timedelta(days=1)  # very tight horizon
    availability = [AvailabilityWindow(day_of_week=date.today().weekday(), start_time=time(9, 0),
                                        end_time=time(10, 30), period_type="free")]
    result = run_scheduler(
        tasks=tasks, availability=availability, session_duration_min=90, break_duration_min=10,
        max_sessions_per_day=1, preferred_time=PreferredTime.no_preference,
        start_date=date.today(), exam_date=exam,
        topic_difficulty_lookup={str(t): 3 for t in topics},
        topic_recent_score_lookup={str(t): None for t in topics},
    )
    assert len(result.sessions) + len(result.unscheduled) == 5
    assert len(result.unscheduled) >= 1
