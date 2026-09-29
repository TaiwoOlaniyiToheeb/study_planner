"""
Shared FastAPI dependencies.

`get_current_student_id` now verifies the JWT issued by `api/routes/auth.py`
(signup/login), so the app works standalone with no existing LMS. If you
later integrate into a real LMS with its own auth, replace the body of this
function with your token verification — every route in this feature depends
on it, so swapping this one function re-integrates the whole feature.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, Header, status
from jwt import PyJWTError
from sqlalchemy.orm import Session

from backend.db.session import SessionLocal  # your existing session factory


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_student_id(authorization: str | None = Header(default=None)) -> UUID:
    """
    Expects `Authorization: Bearer <token>` where <token> was issued by
    POST /api/auth/login or /api/auth/signup. Raises 401 on anything
    missing/invalid/expired. Never trusts a client-supplied student id from
    the request body/query string — ownership checks throughout the routers
    rely on this being tamper-proof.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or malformed credentials")

    token = authorization.split(" ", 1)[1].strip()
    # Imported here (not at module top) to avoid a circular import between
    # deps.py and auth.py, since auth.py's routes also depend on get_db above.
    from backend.api.routes.auth import decode_token

    try:
        student_id_str = decode_token(token)
    except PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    try:
        return UUID(student_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")


def ensure_owns_schedule(schedule_student_id: UUID, current_student_id: UUID) -> None:
    if schedule_student_id != current_student_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your schedule")

