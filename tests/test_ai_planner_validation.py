import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.schemas.schemas import AiLearningPlan, LearningTask, ActivityType
from backend.services.ai_planner.service import AiPlannerService


def _valid_payload():
    return {
        "tasks": [
            {
                "subject_id": str(uuid4()), "topic_id": str(uuid4()),
                "activity_type": "learning", "priority": 5,
                "estimated_minutes": 60, "reason": "prerequisite-valid next topic",
            }
        ],
        "overall_reasoning": "Prioritized Mathematics due to low recent scores.",
    }


def test_valid_plan_parses():
    plan = AiLearningPlan.model_validate(_valid_payload())
    assert len(plan.tasks) == 1
    assert plan.tasks[0].activity_type == ActivityType.learning


def test_invalid_json_raises():
    svc = AiPlannerService(api_key="x", model="m")
    with pytest.raises(json.JSONDecodeError):
        svc._parse_and_validate("not json at all {")


def test_missing_required_field_rejected():
    payload = _valid_payload()
    del payload["tasks"][0]["reason"]
    with pytest.raises(ValidationError):
        AiLearningPlan.model_validate(payload)


def test_invalid_activity_type_rejected():
    payload = _valid_payload()
    payload["tasks"][0]["activity_type"] = "cramming"  # not a real enum value
    with pytest.raises(ValidationError):
        AiLearningPlan.model_validate(payload)


def test_priority_out_of_range_rejected():
    payload = _valid_payload()
    payload["tasks"][0]["priority"] = 11
    with pytest.raises(ValidationError):
        AiLearningPlan.model_validate(payload)


def test_duplicate_subject_topic_activity_rejected():
    payload = _valid_payload()
    payload["tasks"].append(dict(payload["tasks"][0]))  # exact duplicate
    with pytest.raises(ValidationError):
        AiLearningPlan.model_validate(payload)


def test_empty_task_list_rejected():
    payload = _valid_payload()
    payload["tasks"] = []
    with pytest.raises(ValidationError):
        AiLearningPlan.model_validate(payload)


def test_code_fence_stripped_before_parsing():
    svc = AiPlannerService(api_key="x", model="m")
    fenced = "```json\n" + json.dumps(_valid_payload()) + "\n```"
    plan = svc._parse_and_validate(fenced)
    assert len(plan.tasks) == 1
