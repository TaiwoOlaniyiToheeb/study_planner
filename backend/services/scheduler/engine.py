"""
Deterministic Scheduling Engine.

Takes the AI's prioritized learning tasks (schemas.AiLearningPlan) plus the
student's availability/preferences and produces a concrete timetable. This
module makes NO network calls and has NO dependency on the AI planner — it
is pure, testable Python, which is exactly why hard constraints are
enforced here rather than trusted to the LLM.

Algorithm (matches spec section 13):
  1. Expand each LearningTask into a spaced-repetition series of dated
     targets (learning/practice/revision/assessment) via spaced_repetition.py.
  2. Generate candidate free slots per day from availability (slots.py).
  3. Rank candidate slots per day by soft-constraint fit (preferred time).
  4. Greedily place highest-priority tasks first into the best-fitting slot
     on or near their target date, enforcing hard constraints throughout.
  5. Enforce max-sessions-per-day and break spacing between consecutive
     sessions.
  6. If a task can't be placed near its target date, search forward day by
     day up to the exam date before giving up on it.
  7. Anything still unplaced is reported back, never silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time, timedelta, datetime
from typing import Optional
from uuid import UUID

from backend.schemas.schemas import LearningTask, ActivityType, PreferredTime
from backend.services.scheduler.slots import AvailabilityWindow, candidate_slots_for_range, Slot
from backend.services.scheduler.spaced_repetition import compute_repetition_schedule, should_skip_redundant_repetition


@dataclass
class PlacedSession:
    subject_id: UUID
    topic_id: UUID
    activity_type: ActivityType
    scheduled_date: date
    start_time: time
    end_time: time
    duration_minutes: int
    priority: int
    reason: str


@dataclass
class UnscheduledTask:
    subject_id: UUID
    topic_id: UUID
    activity_type: ActivityType
    estimated_minutes: int
    reason_could_not_schedule: str


@dataclass
class SchedulingResult:
    sessions: list[PlacedSession] = field(default_factory=list)
    unscheduled: list[UnscheduledTask] = field(default_factory=list)


TIME_WINDOWS = {
    PreferredTime.morning: (time(5, 0), time(12, 0)),
    PreferredTime.afternoon: (time(12, 0), time(17, 0)),
    PreferredTime.evening: (time(17, 0), time(23, 0)),
}


def _preference_score(slot_start: time, preferred: PreferredTime) -> int:
    """Lower is better. 0 = inside preferred window, 1 = adjacent, 2 = elsewhere."""
    if preferred == PreferredTime.no_preference:
        return 0
    window = TIME_WINDOWS[preferred]
    if window[0] <= slot_start < window[1]:
        return 0
    return 1


def _add_minutes(t: time, minutes: int) -> time:
    """
    Add minutes to a time-of-day, clamping at 23:59:59.999999 instead of
    wrapping to the next day. `time` objects have no notion of "day", so
    silently wrapping past midnight (via datetime + timedelta) previously
    caused candidate_end to come back *smaller* than the window end,
    breaking the "candidate_end > w_end" termination check and hanging in
    an infinite loop near midnight. Clamping means any arithmetic that
    would cross midnight simply lands past the end of any realistic
    availability window, which correctly fails the fit check instead.
    """
    total_minutes = t.hour * 60 + t.minute + minutes
    if total_minutes >= 24 * 60:
        return time(23, 59, 59, 999999)
    return time(total_minutes // 60, total_minutes % 60)


class DayBook:
    """Tracks committed sessions per day to enforce hard constraints while packing."""

    def __init__(self, max_sessions_per_day: int):
        self.max_sessions_per_day = max_sessions_per_day
        self._by_day: dict[date, list[tuple[time, time]]] = {}

    def sessions_on(self, d: date) -> list[tuple[time, time]]:
        return self._by_day.get(d, [])

    def count_on(self, d: date) -> int:
        return len(self.sessions_on(d))

    def has_room(self, d: date) -> bool:
        return self.count_on(d) < self.max_sessions_per_day

    def overlaps(self, d: date, start: time, end: time) -> bool:
        for s, e in self.sessions_on(d):
            if start < e and s < end:
                return True
        return False

    def commit(self, d: date, start: time, end: time) -> None:
        self._by_day.setdefault(d, []).append((start, end))


def _find_slot_on_day(
    day_windows: list[tuple[time, time]],
    day_book: DayBook,
    the_date: date,
    duration_minutes: int,
    break_minutes: int,
    preferred_time: PreferredTime,
) -> Optional[tuple[time, time]]:
    """
    Among the free windows for this day (after subtracting busy periods),
    find the best-fitting gap of >= duration_minutes that does not overlap
    already-committed sessions, leaving `break_minutes` after any adjacent
    prior session. Returns (start, end) or None.
    """
    candidates: list[tuple[int, time, time]] = []  # (pref_score, start, end)

    for w_start, w_end in day_windows:
        cursor = w_start
        while True:
            candidate_end = _add_minutes(cursor, duration_minutes)
            if candidate_end > w_end:
                break
            if not day_book.overlaps(the_date, cursor, candidate_end):
                # Ensure break spacing from any existing session ending right before.
                gap_ok = True
                for s, e in day_book.sessions_on(the_date):
                    if e <= cursor and (datetime.combine(the_date, cursor) -
                                        datetime.combine(the_date, e)).total_seconds() / 60 < break_minutes:
                        gap_ok = False
                    if cursor <= s and (datetime.combine(the_date, s) -
                                        datetime.combine(the_date, candidate_end)).total_seconds() / 60 < break_minutes:
                        gap_ok = False
                if gap_ok:
                    score = _preference_score(cursor, preferred_time)
                    candidates.append((score, cursor, candidate_end))
            # advance in 15-minute increments to search the window
            cursor = _add_minutes(cursor, 15)
            if cursor >= w_end:
                break

    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[0], c[1]))  # best preference score, then earliest
    return candidates[0][1], candidates[0][2]


def run_scheduler(
    tasks: list[LearningTask],
    availability: list[AvailabilityWindow],
    session_duration_min: int,
    break_duration_min: int,
    max_sessions_per_day: int,
    preferred_time: PreferredTime,
    start_date: date,
    exam_date: date,
    topic_difficulty_lookup: dict[str, int],
    topic_recent_score_lookup: dict[str, float | None],
) -> SchedulingResult:
    """
    Main entry point. `topic_difficulty_lookup` / `topic_recent_score_lookup`
    are keyed by str(topic_id) and come from the same data used to build the
    AI's learning profile (context_builder), NOT invented here.
    """
    if start_date > exam_date:
        return SchedulingResult(
            sessions=[],
            unscheduled=[
                UnscheduledTask(
                    subject_id=t.subject_id, topic_id=t.topic_id, activity_type=t.activity_type,
                    estimated_minutes=t.estimated_minutes,
                    reason_could_not_schedule="start_date is after exam_date",
                )
                for t in tasks
            ],
        )

    day_book = DayBook(max_sessions_per_day=max_sessions_per_day)
    result = SchedulingResult()

    # Pre-compute per-day free windows once for the whole horizon.
    from backend.services.scheduler.slots import generate_daily_free_windows
    free_by_dow = generate_daily_free_windows(availability)

    # Sort tasks by priority desc (5 = most important), so high-priority
    # topics claim the best slots first — a soft-constraint optimization.
    tasks_sorted = sorted(tasks, key=lambda t: t.priority, reverse=True)

    for task in tasks_sorted:
        difficulty = topic_difficulty_lookup.get(str(task.topic_id), 3)
        recent_score = topic_recent_score_lookup.get(str(task.topic_id))

        if should_skip_redundant_repetition(task.activity_type.value, recent_score):
            continue  # excellent performance -> skip this redundant revision task

        repetition_plans = compute_repetition_schedule(
            introduced_on=start_date,
            difficulty=difficulty,
            recent_score_percent=recent_score,
            exam_date=exam_date,
            activity_types=(task.activity_type.value,),
        )
        target_date = repetition_plans[0].target_date

        placed = False
        # Search forward from the target date up to the exam date (hard
        # constraint: never schedule after exam_date) for a valid slot.
        search_date = max(target_date, start_date)
        while search_date <= exam_date:
            if day_book.has_room(search_date):
                windows = free_by_dow.get(search_date.weekday(), [])
                found = _find_slot_on_day(
                    windows, day_book, search_date,
                    duration_minutes=min(task.estimated_minutes, session_duration_min),
                    break_minutes=break_duration_min,
                    preferred_time=preferred_time,
                )
                if found:
                    s, e = found
                    day_book.commit(search_date, s, e)
                    result.sessions.append(PlacedSession(
                        subject_id=task.subject_id,
                        topic_id=task.topic_id,
                        activity_type=task.activity_type,
                        scheduled_date=search_date,
                        start_time=s,
                        end_time=e,
                        duration_minutes=min(task.estimated_minutes, session_duration_min),
                        priority=task.priority,
                        reason=task.reason,
                    ))
                    placed = True
                    break
            search_date += timedelta(days=1)

        if not placed:
            result.unscheduled.append(UnscheduledTask(
                subject_id=task.subject_id,
                topic_id=task.topic_id,
                activity_type=task.activity_type,
                estimated_minutes=task.estimated_minutes,
                reason_could_not_schedule=(
                    "No available slot (respecting availability, daily session limit, "
                    "and break spacing) between target date and exam date."
                ),
            ))

    return result
