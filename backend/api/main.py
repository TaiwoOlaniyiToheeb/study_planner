"""
Standalone FastAPI app. If integrating into an existing LMS backend, skip
this file and instead mount `study_schedule_router` / `study_session_router`
/ `availability_router` (and, if you don't already have auth or a
subject/topic catalog, `auth_router` / `subjects_router`) on your existing
app the same way this file does.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes.study_schedule import router as study_schedule_router
from backend.api.routes.study_session import router as study_session_router
from backend.api.routes.availability import router as availability_router
from backend.api.routes.auth import router as auth_router
from backend.api.routes.subjects import router as subjects_router
from backend.config import settings

app = FastAPI(title="AI Study Schedule API")

# CORS: the frontend (Vercel) and backend (Railway/Render/Fly) are different
# origins in a standalone deployment, so this must be enabled and scoped to
# your actual frontend URL(s) via the FRONTEND_ORIGINS env var — comma
# separated, e.g. "https://my-app.vercel.app,http://localhost:5173".
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(subjects_router, prefix="/api")
app.include_router(study_schedule_router, prefix="/api")
app.include_router(study_session_router, prefix="/api")
app.include_router(availability_router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
