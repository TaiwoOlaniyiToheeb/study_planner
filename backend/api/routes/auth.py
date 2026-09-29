"""
Minimal but real JWT auth so the app can run standalone without an existing
LMS. Replace this whole module with your real LMS's auth once you have one
— `get_current_student_id` in `deps.py` is the only integration point the
rest of the codebase depends on.

Endpoints:
  POST /api/auth/signup  { full_name, email, password, timezone? } -> token
  POST /api/auth/login   { email, password }                       -> token
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.config import settings
from backend.models.models import Base, Student

router = APIRouter(prefix="/auth", tags=["auth"])

ALGORITHM = "HS256"
TOKEN_EXPIRES_HOURS = 24 * 7  # 1 week


class StudentCredential(Base):
    """
    Separate table for login credentials rather than bolting email/password
    onto the placeholder `students` table — keeps auth swappable without
    touching the `Student` model your real LMS will likely already have.
    """
    __tablename__ = "student_credentials"
    student_id = Column(UUID(as_uuid=True), primary_key=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)


class SignupIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    timezone: str = Field(default="UTC", max_length=64)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    student_id: str


def _hash_password(password: str) -> str:
    # bcrypt has a hard 72-byte input limit; truncate defensively.
    password_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    password_bytes = password.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))
    except ValueError:
        return False


def _create_token(student_id: str) -> str:
    secret = settings.JWT_SECRET
    if not secret:
        raise RuntimeError("JWT_SECRET is not set — cannot issue tokens.")
    payload = {
        "sub": student_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRES_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(token: str) -> str:
    """Returns the student_id encoded in the token, or raises."""
    secret = settings.JWT_SECRET
    payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    return payload["sub"]


@router.post("/signup", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupIn, db: Session = Depends(get_db)):
    existing = db.query(StudentCredential).filter(StudentCredential.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    student = Student(id=uuid4(), full_name=payload.full_name, timezone=payload.timezone)
    db.add(student)
    db.flush()  # get student.id

    credential = StudentCredential(
        student_id=student.id, email=payload.email,
        password_hash=_hash_password(payload.password),
    )
    db.add(credential)
    db.commit()

    token = _create_token(str(student.id))
    return TokenOut(access_token=token, student_id=str(student.id))


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    credential = db.query(StudentCredential).filter(StudentCredential.email == payload.email).first()
    if not credential or not _verify_password(payload.password, credential.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = _create_token(str(credential.student_id))
    return TokenOut(access_token=token, student_id=str(credential.student_id))
