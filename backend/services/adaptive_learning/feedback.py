"""
Adaptive scheduling feedback loop (spec sections 22-23).

Pure functions that translate a completed session's assessment score into
follow-up recommendations. These recommendations become ordinary
LearningTask-shaped inputs fed back through the SAME deterministic scheduler
(engine.py) on the next generation — no separate "adaptive" scheduling path
is needed, which keeps the system simple and testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from backend.schemas.schemas import ActivityType


@dataclass(frozen=True)
class ReinforcementRecommendation:
    subject_id: UUID
    topic_id: UUID
    activity_type: ActivityType
    priority: int
    estimated_minutes: int
    reason: str


def recommend_after_assessment(
    subject_id: UUID,
    topic_id: UUID,
    score_percent: float,
    already_completed_topic: bool,
    base_session_minutes: int,
) -> list[ReinforcementRecommendation]:
    """
    score < 50  -> schedule Practice AND Revision, high priority
    50 <= score < 75 -> schedule one Revision, medium priority
    score >= 75 -> no forced reinforcement (spaced_repetition's normal
                   schedule already covers it; avoids unnecessary repeats)
    """
    recs: list[ReinforcementRecommendation] = []
    if score_percent < 50:
        recs.append(ReinforcementRecommendation(
            subject_id=subject_id, topic_id=topic_id, activity_type=ActivityType.practice,
            priority=5, estimated_minutes=base_session_minutes,
            reason=f"Recent assessment score of {score_percent:.0f}% indicates this topic "
                   f"needs additional practice before moving on.",
        ))
        recs.append(ReinforcementRecommendation(
            subject_id=subject_id, topic_id=topic_id, activity_type=ActivityType.revision,
            priority=5, estimated_minutes=base_session_minutes,
            reason=f"Low score ({score_percent:.0f}%) — scheduling earlier revision than the "
                   f"standard interval.",
        ))
    elif score_percent < 75:
        recs.append(ReinforcementRecommendation(
            subject_id=subject_id, topic_id=topic_id, activity_type=ActivityType.revision,
            priority=4, estimated_minutes=base_session_minutes,
            reason=f"Moderate score ({score_percent:.0f}%) — one additional revision pass "
                   f"is recommended.",
        ))
    return recs


def recommend_after_missed_session(
    subject_id: UUID,
    topic_id: UUID,
    activity_type: ActivityType,
    original_priority: int,
    estimated_minutes: int,
) -> ReinforcementRecommendation:
    """
    A missed session is re-injected as a task with the SAME activity type and
    a slightly boosted priority (so it doesn't keep losing to newer content),
    to be placed by the normal scheduler run — never just "pushed to
    tomorrow" without re-running full constraint checking.
    """
    return ReinforcementRecommendation(
        subject_id=subject_id, topic_id=topic_id, activity_type=activity_type,
        priority=min(5, original_priority + 1),
        estimated_minutes=estimated_minutes,
        reason="Rescheduled after a missed session; priority increased slightly to ensure "
               "it is placed before newer, lower-priority tasks.",
    )
