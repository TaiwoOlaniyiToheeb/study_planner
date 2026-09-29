"""
Spaced-repetition interval logic.

Base progression per spec: Learning (day 0) -> Practice (day +2) ->
Revision (day +6) -> Assessment (day +13), i.e. offsets [0, 2, 6, 13] from
the day a topic is first introduced.

Adjustments:
  - Higher topic difficulty (1-5) -> compress intervals (more frequent review).
  - Poor recent performance (<60%) -> pull revision earlier.
  - Very good performance (>=85%) -> skip/relax redundant repetitions.
  - Proximity to exam -> compress everything so all reinforcement lands
    before the exam date, and shift weight toward revision/assessment.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

BASE_OFFSETS_DAYS = {
    "learning": 0,
    "practice": 2,
    "revision": 6,
    "assessment": 13,
}


@dataclass(frozen=True)
class RepetitionPlan:
    activity_type: str
    target_date: date


def compute_repetition_schedule(
    introduced_on: date,
    difficulty: int,               # 1-5
    recent_score_percent: float | None,
    exam_date: date,
    activity_types: tuple[str, ...] = ("learning", "practice", "revision", "assessment"),
) -> list[RepetitionPlan]:
    """
    Returns target dates (before clamping to actual availability — the
    engine.py packer is responsible for finding the nearest valid slot)
    for each requested activity type, given the base offsets adjusted for
    difficulty/performance/exam proximity.
    """
    # Difficulty compresses intervals: difficulty 5 -> ~60% of base interval,
    # difficulty 1 -> ~120% of base interval.
    difficulty = max(1, min(5, difficulty))
    compression = 1.2 - (difficulty - 1) * 0.15  # 1->1.2, 5->0.6

    # Poor performance pulls revision/assessment earlier; good performance
    # relaxes it (but never later than the exam).
    if recent_score_percent is not None:
        if recent_score_percent < 60:
            compression *= 0.7
        elif recent_score_percent >= 85:
            compression *= 1.3

    days_to_exam = (exam_date - introduced_on).days
    plans: list[RepetitionPlan] = []
    for activity in activity_types:
        base_offset = BASE_OFFSETS_DAYS[activity]
        adjusted_offset = round(base_offset * compression)
        # Never schedule reinforcement after the exam date.
        adjusted_offset = min(adjusted_offset, max(days_to_exam, 0))
        target = introduced_on + timedelta(days=adjusted_offset)
        plans.append(RepetitionPlan(activity_type=activity, target_date=min(target, exam_date)))
    return plans


def should_skip_redundant_repetition(activity_type: str, recent_score_percent: float | None) -> bool:
    """
    Per spec: "If they perform very well, reduce unnecessary repetition."
    Skip a *revision* pass only (never skip the initial learning/practice or
    the final pre-exam assessment) when performance is already excellent.
    """
    return activity_type == "revision" and recent_score_percent is not None and recent_score_percent >= 90
