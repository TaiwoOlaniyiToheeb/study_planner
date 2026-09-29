from uuid import uuid4

from backend.schemas.schemas import ActivityType
from backend.services.adaptive_learning.feedback import (
    recommend_after_assessment, recommend_after_missed_session,
)
from backend.services.scheduler.spaced_repetition import (
    compute_repetition_schedule, should_skip_redundant_repetition,
)
from datetime import date, timedelta


def test_low_score_triggers_practice_and_revision():
    subj, topic = uuid4(), uuid4()
    recs = recommend_after_assessment(subj, topic, score_percent=35, already_completed_topic=True,
                                       base_session_minutes=60)
    activity_types = {r.activity_type for r in recs}
    assert ActivityType.practice in activity_types
    assert ActivityType.revision in activity_types
    assert all(r.priority == 5 for r in recs)


def test_moderate_score_triggers_single_revision():
    subj, topic = uuid4(), uuid4()
    recs = recommend_after_assessment(subj, topic, score_percent=65, already_completed_topic=True,
                                       base_session_minutes=60)
    assert len(recs) == 1
    assert recs[0].activity_type == ActivityType.revision


def test_high_score_triggers_no_reinforcement():
    subj, topic = uuid4(), uuid4()
    recs = recommend_after_assessment(subj, topic, score_percent=92, already_completed_topic=True,
                                       base_session_minutes=60)
    assert recs == []


def test_missed_session_reschedule_boosts_priority():
    subj, topic = uuid4(), uuid4()
    rec = recommend_after_missed_session(subj, topic, ActivityType.practice, original_priority=3,
                                          estimated_minutes=45)
    assert rec.priority == 4
    assert rec.activity_type == ActivityType.practice


def test_missed_session_priority_caps_at_five():
    subj, topic = uuid4(), uuid4()
    rec = recommend_after_missed_session(subj, topic, ActivityType.revision, original_priority=5,
                                          estimated_minutes=45)
    assert rec.priority == 5


def test_high_difficulty_compresses_repetition_interval():
    start = date.today()
    exam = start + timedelta(days=60)
    easy = compute_repetition_schedule(start, difficulty=1, recent_score_percent=None, exam_date=exam,
                                        activity_types=("revision",))
    hard = compute_repetition_schedule(start, difficulty=5, recent_score_percent=None, exam_date=exam,
                                        activity_types=("revision",))
    assert hard[0].target_date <= easy[0].target_date


def test_poor_performance_pulls_revision_earlier():
    start = date.today()
    exam = start + timedelta(days=60)
    poor = compute_repetition_schedule(start, difficulty=3, recent_score_percent=40, exam_date=exam,
                                        activity_types=("revision",))
    good = compute_repetition_schedule(start, difficulty=3, recent_score_percent=95, exam_date=exam,
                                        activity_types=("revision",))
    assert poor[0].target_date <= good[0].target_date


def test_never_targets_past_exam_date():
    start = date.today()
    exam = start + timedelta(days=3)
    plans = compute_repetition_schedule(start, difficulty=1, recent_score_percent=None, exam_date=exam,
                                         activity_types=("learning", "practice", "revision", "assessment"))
    assert all(p.target_date <= exam for p in plans)


def test_should_skip_redundant_revision_only_when_excellent():
    assert should_skip_redundant_repetition("revision", 95) is True
    assert should_skip_redundant_repetition("revision", 70) is False
    assert should_skip_redundant_repetition("assessment", 95) is False
