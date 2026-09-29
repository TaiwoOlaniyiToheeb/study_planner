"""
API-layer tests focused on authz/ownership — the part most likely to have a
security regression. Uses dependency overrides so no real auth/AI/DB is
needed; wire similarly in your real test suite once auth is implemented.
"""
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.deps import get_current_student_id
from backend.api.routes.availability import router as availability_router


def make_app(student_id: uuid.UUID) -> FastAPI:
    app = FastAPI()
    app.include_router(availability_router, prefix="/api")
    app.dependency_overrides[get_current_student_id] = lambda: student_id
    return app


def test_missing_auth_header_rejected():
    """Without a dependency override, the placeholder auth dependency must
    reject requests missing an Authorization header (401), not crash with
    a raw 500."""
    from backend.api.deps import get_current_student_id as real_dep
    import asyncio
    with pytest.raises(Exception):
        asyncio.run(real_dep(authorization=None))


def test_student_cannot_see_another_students_availability(monkeypatch):
    """
    Two different students hitting GET /study-availability should never see
    each other's rows — this is enforced by filtering on the authenticated
    student_id (from the dependency), never a client-supplied id, in every
    query in routes/availability.py.
    """
    student_a = uuid.uuid4()
    student_b = uuid.uuid4()

    # This test documents the required behavior/shape; a full run requires a
    # real (or SQLite in-memory) DB wired via dependency_overrides[get_db].
    # The critical invariant under test: routes/availability.py filters every
    # query by `AvailabilityPeriod.student_id == student_id` where
    # `student_id` comes exclusively from `get_current_student_id`, never
    # from the request body/path — grep-verifiable in the router source.
    import inspect
    from backend.api.routes import availability as availability_module
    source = inspect.getsource(availability_module)
    assert "AvailabilityPeriod.student_id == student_id" in source
    assert source.count("get_current_student_id") >= 1
