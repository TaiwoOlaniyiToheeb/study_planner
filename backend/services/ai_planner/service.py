"""
AiPlannerService — the only piece of the system that talks to the LLM.

Contract:
  - Input: a plain-dict learning profile (see context_builder.build_student_data).
  - Output: a validated `AiLearningPlan` (schemas.py), or an `AiPlannerError`.
  - Never persists anything itself. Never returns unvalidated data to callers.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import ValidationError

from backend.schemas.schemas import AiLearningPlan
from backend.services.ai_planner.prompt import (
    SYSTEM_PROMPT, build_user_prompt, PROMPT_VERSION, exam_phase,
)

logger = logging.getLogger(__name__)


class AiPlannerError(Exception):
    """Raised when the AI is unavailable or never returns valid output."""


class AiPlannerService:
    def __init__(self, api_key: str, model: str, base_url: str = "https://api.anthropic.com/v1/messages",
                 timeout_seconds: float = 30.0):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._timeout = timeout_seconds

    async def _call_llm(self, user_prompt: str) -> str:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": self._model,
            "max_tokens": 4000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._base_url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            # Concatenate any text blocks; ignore other block types defensively.
            text_blocks = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
            return "".join(text_blocks)

    @staticmethod
    def _strip_code_fences(raw: str) -> str:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
        return raw.strip()

    def _parse_and_validate(self, raw_text: str) -> AiLearningPlan:
        cleaned = self._strip_code_fences(raw_text)
        payload: dict[str, Any] = json.loads(cleaned)  # raises json.JSONDecodeError
        return AiLearningPlan.model_validate(payload)   # raises pydantic.ValidationError

    async def generate_plan(self, student_data: dict[str, Any]) -> AiLearningPlan:
        """
        Calls the LLM once, and if the response is not valid JSON matching
        `AiLearningPlan`, retries exactly once with an explicit correction
        instruction. If the retry also fails validation, raises
        AiPlannerError — callers must fail safely (never persist partial or
        malformed output).
        """
        days_to_exam = student_data.get("days_to_exam", 0)
        user_prompt = build_user_prompt(student_data, days_to_exam)

        try:
            raw = await self._call_llm(user_prompt)
        except httpx.HTTPError as e:
            logger.error("AI planner HTTP error: %s", e)
            raise AiPlannerError("AI schedule generation is temporarily unavailable. Please try again.") from e

        try:
            return self._parse_and_validate(raw)
        except (json.JSONDecodeError, ValidationError) as first_error:
            logger.warning("AI planner returned invalid output, retrying once: %s", first_error)

        # Structured retry: tell the model exactly what was wrong.
        retry_prompt = (
            user_prompt
            + "\n\nYour previous response was invalid or did not match the required "
              "schema exactly. Return ONLY a single valid JSON object matching the "
              "schema, with no extra text, no markdown fences, and no trailing commas."
        )
        try:
            raw_retry = await self._call_llm(retry_prompt)
            return self._parse_and_validate(raw_retry)
        except httpx.HTTPError as e:
            logger.error("AI planner HTTP error on retry: %s", e)
            raise AiPlannerError("AI schedule generation is temporarily unavailable. Please try again.") from e
        except (json.JSONDecodeError, ValidationError) as second_error:
            logger.error("AI planner returned invalid output twice, giving up: %s", second_error)
            raise AiPlannerError(
                "AI schedule generation failed to produce a valid plan. Nothing was saved; "
                "please try again."
            ) from second_error
