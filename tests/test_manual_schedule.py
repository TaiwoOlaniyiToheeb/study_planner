"""
Integration tests for POST /api/study-schedule/manual — the fully
student-authored path (no AI, no scheduler). Exercises the real FastAPI
routes against an in-memory SQLite DB, since the overlap/exam-date/
subject-existence checks live directly in the route handler and are worth
covering with a real request/response round trip, not just unit tests of
helper functions.
"""
from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.deps import get_db, get_current_student_id
from backend.api.routes.study_schedule import router as study_schedule_router
from backend.api.routes.subjects import router as subjects_router
from backend.models.models import Base, Student


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    student_id = uuid4()
    seed_db = TestSessionLocal()
    seed_db.add(Student(id=student_id, full_name="Test Student", timezone="UTC"))
    seed_db.commit()
    seed_db.close()

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(subjects_router, prefix="/api")
    app.include_router(study_schedule_router, prefix="/api")
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_student_id] = lambda: student_id

    with TestClient(app) as c:
        yield c


def _make_subject_and_topic(client, subject_name="Financial Accounting", topic_name="Double Entry"):
    subj = client.post("/api/subjects", json={"name": subject_name}).json()
    topic = client.post(f"/api/subjects/{subj['id']}/topics", json={"name": topic_name}).json()
    return subj["id"], topic["id"]


def test_manual_schedule_happy_path(client):
    subject_id, topic_id = _make_subject_and_topic(client)
    exam_date = (date.today() + timedelta(days=30)).isoformat()
    session_date = (date.today() + timedelta(days=1)).isoformat()

    resp = client.post("/api/study-schedule/manual", json={
        "exam_date": exam_date,
        "sessions": [{
            "subject_id": subject_id, "topic_id": topic_id, "activity_type": "learning",
            "scheduled_date": session_date, "start_time": "17:00:00", "duration_minutes": 60,
        }],
    })
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["sessions"]) == 1
    assert body["sessions"][0]["subject_name"] == "Financial Accounting"
    assert body["status"] == "draft"


def test_manual_schedule_rejects_unknown_subject(client):
    exam_date = (date.today() + timedelta(days=30)).isoformat()
    session_date = (date.today() + timedelta(days=1)).isoformat()

    resp = client.post("/api/study-schedule/manual", json={
        "exam_date": exam_date,
        "sessions": [{
            "subject_id": str(uuid4()), "topic_id": str(uuid4()), "activity_type": "learning",
            "scheduled_date": session_date, "start_time": "17:00:00", "duration_minutes": 60,
        }],
    })
    assert resp.status_code == 400
    assert "Unknown subject" in resp.json()["detail"]


def test_manual_schedule_rejects_session_after_exam_date(client):
    subject_id, topic_id = _make_subject_and_topic(client)
    exam_date = (date.today() + timedelta(days=5)).isoformat()
    session_date = (date.today() + timedelta(days=10)).isoformat()  # after exam

    resp = client.post("/api/study-schedule/manual", json={
        "exam_date": exam_date,
        "sessions": [{
            "subject_id": subject_id, "topic_id": topic_id, "activity_type": "learning",
            "scheduled_date": session_date, "start_time": "17:00:00", "duration_minutes": 60,
        }],
    })
    assert resp.status_code == 400
    assert "after the exam date" in resp.json()["detail"]


def test_manual_schedule_rejects_overlap_within_batch(client):
    subject_id, topic_id = _make_subject_and_topic(client)
    exam_date = (date.today() + timedelta(days=30)).isoformat()
    session_date = (date.today() + timedelta(days=1)).isoformat()

    resp = client.post("/api/study-schedule/manual", json={
        "exam_date": exam_date,
        "sessions": [
            {"subject_id": subject_id, "topic_id": topic_id, "activity_type": "learning",
             "scheduled_date": session_date, "start_time": "17:00:00", "duration_minutes": 60},
            {"subject_id": subject_id, "topic_id": topic_id, "activity_type": "practice",
             "scheduled_date": session_date, "start_time": "17:30:00", "duration_minutes": 60},
        ],
    })
    assert resp.status_code == 400
    assert "overlap" in resp.json()["detail"]


def test_manual_schedule_rejects_overlap_with_existing_session(client):
    subject_id, topic_id = _make_subject_and_topic(client)
    exam_date = (date.today() + timedelta(days=30)).isoformat()
    session_date = (date.today() + timedelta(days=1)).isoformat()

    first = client.post("/api/study-schedule/manual", json={
        "exam_date": exam_date,
        "sessions": [{"subject_id": subject_id, "topic_id": topic_id, "activity_type": "learning",
                       "scheduled_date": session_date, "start_time": "17:00:00", "duration_minutes": 60}],
    })
    assert first.status_code == 201

    second = client.post("/api/study-schedule/manual", json={
        "exam_date": exam_date,
        "sessions": [{"subject_id": subject_id, "topic_id": topic_id, "activity_type": "practice",
                       "scheduled_date": session_date, "start_time": "17:15:00", "duration_minutes": 60}],
    })
    assert second.status_code == 400
    assert "Overlaps an already-scheduled session" in second.json()["detail"]
