"""
DB engine/session factory. Replace with your existing LMS's engine/session
if one already exists — `SessionLocal` is the only symbol other modules
import from here.

The engine is created lazily so importing this module (e.g. for routing or
testing with dependency_overrides) never fails just because DATABASE_URL
isn't set yet. Falls back to an in-memory SQLite URL only when nothing is
configured, purely so imports/tests don't explode — real deployments must
set DATABASE_URL.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config import settings

_engine = None
_SessionFactory = None


def _get_engine():
    global _engine
    if _engine is None:
        url = settings.DATABASE_URL or "sqlite:///:memory:"
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


class _LazySessionLocal:
    """Callable that behaves like sessionmaker(), but defers engine creation."""

    def __call__(self, *args, **kwargs):
        global _SessionFactory
        if _SessionFactory is None:
            _SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=_get_engine())
        return _SessionFactory(*args, **kwargs)


SessionLocal = _LazySessionLocal()
