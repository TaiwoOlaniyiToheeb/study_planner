"""
Loads configuration from environment variables. Adapt to your existing
LMS's config system if it already has one (e.g. pydantic-settings, django
settings, etc.) — nothing else in this codebase depends on this exact class.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _parse_origins(raw: str) -> list[str]:
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["http://localhost:5173"]


@dataclass(frozen=True)
class Settings:
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "")
    AI_PROVIDER_API_KEY: str = os.environ.get("AI_PROVIDER_API_KEY", "")
    AI_MODEL: str = os.environ.get("AI_MODEL", "claude-sonnet-5")
    JWT_SECRET: str = os.environ.get("JWT_SECRET", "")
    FRONTEND_ORIGINS: list[str] = field(
        default_factory=lambda: _parse_origins(os.environ.get("FRONTEND_ORIGINS", ""))
    )


settings = Settings()

