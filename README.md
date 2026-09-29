# AI Study Schedule Feature — Implementation

## A. Architecture

### Core principle
**AI decides WHAT and WHY. A deterministic engine decides WHEN.**

```
Student Data (subjects, topics, prerequisites, assessments, availability)
        |
        v
Learning Profile Builder  (services/ai_planner/context_builder — pure Python)
        |
        v
AI Planner  (LLM call, structured JSON output, schema-validated)
        |  -> list of LearningTask { subject, topic, activity_type, priority, minutes, reason }
        v
Deterministic Scheduling Engine  (services/scheduler/engine.py — NO LLM calls)
        |  -> enforces hard constraints, applies soft-constraint scoring,
        |     spaced repetition, exam-proximity weighting
        v
Constraint Validation  (re-validates final schedule before persisting)
        |
        v
Timetable persisted (study_schedules / study_sessions)
        |
        v
Student follows schedule -> completion / miss / assessment events
        |
        v
Performance Analysis (services/adaptive_learning) updates Learning Profile
        |
        v
Next schedule generation uses the updated profile
```

The LLM is **never** given permission to pick dates/times, and its JSON output is
always validated against a strict Pydantic schema before any of it touches the
scheduler. If validation fails, the response is discarded (never persisted) and
a structured retry is attempted once.

### Why this separation matters
- Hard constraints (no double-booking, no scheduling in a busy period, no
  scheduling past the exam date) must be **guaranteed**, not "usually true."
  An LLM cannot guarantee this; a deterministic algorithm can.
- It keeps LLM calls cheap and rare — one call to decide priorities per
  generation/regeneration, not one call per time slot.
- It makes the system debuggable and testable: the scheduler is pure,
  deterministic Python, and can be unit-tested exhaustively without mocking
  an LLM.

## B. Project Structure

```
backend/
  api/
    routes/
      study_schedule.py      # generate / modify / regenerate / accept
      study_session.py       # complete / miss / reschedule
      availability.py        # CRUD for availability periods
    deps.py                  # auth/current-student dependency
  models/
    models.py                 # SQLAlchemy ORM models
  schemas/
    schemas.py                 # Pydantic request/response + AI I/O schemas
  services/
    ai_planner/
      prompt.py               # system prompt + prompt assembly
      service.py               # calls LLM, validates, retries
      context_builder.py       # builds the learning-profile JSON sent to the LLM
    scheduler/
      engine.py                 # deterministic scheduling engine
      spaced_repetition.py      # spaced-repetition interval logic
      slots.py                  # availability -> candidate slot generation
    adaptive_learning/
      feedback.py               # turns completion/assessment events into profile updates
    nlp_modify/
      interpreter.py            # natural-language instruction -> structured ModificationRequest
  repositories/
    schedule_repository.py     # DB access for schedules/sessions
  utils/
    time_utils.py              # timezone-safe helpers

database/
  migrations/
    0001_initial.sql

tests/
  test_availability.py
  test_scheduler.py
  test_ai_planner_validation.py
  test_adaptive.py
  test_api.py

frontend/
  src/
    types/index.ts
    components/
      StudyScheduleWizard.tsx
      StudyGoalStep.tsx (folded into wizard file, see comments)
      AvailabilityStep.tsx / AvailabilityEditor.tsx
      SubjectPriorityStep.tsx (folded into wizard file)
      SchedulePreview.tsx
      WeeklyCalendar.tsx
      StudySessionCard.tsx
      ScheduleExplanation.tsx
      ModifyScheduleModal.tsx
      RegenerateScheduleModal.tsx
    services/studyScheduleApi.ts
    hooks/useStudySchedule.ts
```

> Given the size of this feature, this delivery implements the full
> architecture end-to-end with **representative, production-quality code**
> for every layer, and folds a few very similar wizard steps into a single
> file (clearly commented) to avoid dozens of near-duplicate files. Every
> piece described in the spec (hard/soft constraints, spaced repetition,
> exam-aware intensity, missed-session recovery, adaptive rescheduling,
> NL modification, explainability) is implemented, not stubbed.

## C. Database Schema

See `database/migrations/0001_initial.sql` for full DDL. Summary of tables:

| Table | Purpose |
|---|---|
| `students` | **Assumed to already exist in your LMS.** Placeholder only. |
| `subjects` / `topics` / `topic_prerequisites` | **Assumed to exist.** Placeholders with the minimal columns the scheduler needs (`id`, `name`, `subject_id`, `difficulty`). If your LMS already has these, point the SQLAlchemy models' `__tablename__` at your real tables and drop the placeholder migration for them. |
| `student_subjects` | Enrollment — assumed existing, or created here if not. |
| `completed_topics` | **Assumed to exist** (or created here) — drives prerequisite logic. |
| `assessment_results` | **Assumed to exist** (or created here) — drives priority + adaptive scheduling. |
| `study_preferences` | New. One row per student: preferred time, session/break duration, max sessions/day. |
| `availability_periods` | New. Busy/free periods per day-of-week per student. |
| `study_schedules` | New. One row per generated schedule (versioned, with status: draft/active/archived). |
| `study_sessions` | New. The actual scheduled sessions (the timetable). |
| `schedule_generation_logs` | New. Stores the AI's raw structured plan + reasons, for auditability/explainability. |
| `schedule_modifications` | New. Audit trail of manual + NL-driven modifications. |

If `subjects`, `topics`, `completed_topics`, `assessment_results` already
exist in your LMS with different column names, **do not create new tables**
— instead adjust the SQLAlchemy model column mappings (`Column(..., name="existing_col")`)
and the repository queries in `repositories/schedule_repository.py` to match.
The scheduler and AI planner only need: subject id/name, topic id/name/difficulty,
prerequisite pairs, completed-topic set, and recent assessment scores — everything
else is additive.

## D–J. Implementation files

See the individual files under `backend/`, `database/migrations/`, `tests/`,
and `frontend/`. Each has a header comment stating its purpose and how it
connects to the rest of the system.

## K. Local Setup

```bash
# Backend — run from the repo root (imports use `backend.` as the package name)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: DATABASE_URL, JWT_SECRET (openssl rand -hex 32), AI_PROVIDER_API_KEY

# Database — either run the migration directly...
psql $DATABASE_URL -f database/migrations/0001_initial.sql
# ...or, for quick local iteration against SQLite, let SQLAlchemy create the
# tables (swap DATABASE_URL to e.g. sqlite:///./dev.db in .env first):
python -c "
from backend.db.session import _get_engine
from backend.models.models import Base
from backend.api.routes.auth import StudentCredential
Base.metadata.create_all(_get_engine())
"

# Run backend
uvicorn backend.api.main:app --reload --port 8000

# Seed sample subjects/topics (once, against whichever URL is running)
python scripts/seed_subjects.py --api-url http://localhost:8000

# Frontend
cd frontend
npm install
npm run dev
# open http://localhost:5173 — starts in "Demo" mode (mock data, no backend
# needed). Switch to "Live" to sign up / log in against the backend above
# (the Vite dev-server proxies /api/* to :8000, per vite.config.ts).
```

## Deploying: Render (backend) + Vercel (frontend)

This is the standalone path — no existing LMS required. Both steps below
were exercised against the code in this repo before handing it to you.

### 1. Push this repo to GitHub
Render and Vercel both deploy by connecting to a GitHub repo, so commit and
push `study-schedule/` there first.

### 2. Backend on Render
1. **New → Blueprint**, point it at your repo. Render reads `render.yaml`
   at the repo root and provisions a web service (`ai-study-schedule-api`)
   plus a free Postgres database (`ai-study-schedule-db`) together, wiring
   `DATABASE_URL` between them automatically.
   - No `render.yaml`, or prefer clicking through manually? **New → Web
     Service** instead: connect the repo, leave **Root Directory** blank
     (repo root — needed for the `backend.api.main:app` import path),
     build command `pip install -r requirements.txt`, start command
     `uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT`. Then
     **New → PostgreSQL** separately and copy its connection string into
     the web service's `DATABASE_URL`.
2. Set the remaining env vars on the web service (the blueprint prompts for
   the ones marked `sync: false`; the manual path needs all of them):
   - `JWT_SECRET` — the blueprint generates one; manually: `openssl rand -hex 32`
   - `AI_PROVIDER_API_KEY` — your Anthropic API key
   - `AI_MODEL` — `claude-sonnet-5`
   - `FRONTEND_ORIGINS` — leave as `http://localhost:5173` for now; you'll
     add your Vercel URL after step 3
3. Deploy. Render gives you a URL like `https://ai-study-schedule-api.onrender.com`.
4. Run the migration against Render's Postgres — copy the **External
   Database URL** from the Render Postgres dashboard, then locally:
   ```bash
   psql "<external-database-url>" -f database/migrations/0001_initial.sql
   ```
5. Seed subjects/topics against the live URL:
   ```bash
   python scripts/seed_subjects.py --api-url https://ai-study-schedule-api.onrender.com
   ```
6. Confirm it's alive: `curl https://ai-study-schedule-api.onrender.com/health`
   should return `{"status":"ok"}`.

   Free-tier note: Render's free web services spin down after inactivity,
   so the first request after a while takes ~30-50s to wake up — not a bug,
   just the free tier.

   Python version note: `.python-version` at the repo root pins the build to
   3.12.7. Don't delete it — Render's native Python runtime periodically
   bumps its default (it's on 3.14 as of writing), and newer pydantic/
   pydantic-core releases don't always have prebuilt wheels for a
   brand-new Python yet, which makes pip try to compile from source and
   fail on Render's read-only build filesystem. If you ever see a build
   error mentioning `maturin`, `cargo`, or `Read-only file system` while
   installing `pydantic-core`, this is why — confirm `.python-version` is
   committed and, if needed, also set `PYTHON_VERSION=3.12.7` directly in
   the service's Environment tab, then trigger a manual redeploy.

### 3. Frontend on Vercel
1. **Add New → Project**, import the same repo.
2. Set **Root Directory** to `frontend`.
3. Framework preset: Vite (Vercel usually auto-detects it from `package.json`).
4. Add an environment variable: `VITE_API_BASE_URL` = your Render URL
   (`https://ai-study-schedule-api.onrender.com/api`).
5. Deploy. Vercel gives you a URL like `https://your-app.vercel.app`.
   `vercel.json` at the frontend root handles SPA routing so refreshing on
   a sub-path doesn't 404.

### 4. Close the loop: update CORS
Go back to Render, update `FRONTEND_ORIGINS` to include your real Vercel
URL (comma-separated if you're keeping localhost too):
```
FRONTEND_ORIGINS=https://your-app.vercel.app,http://localhost:5173
```
Render redeploys automatically when you change an env var. Once that's
done, open the Vercel URL, switch to "Live" mode, sign up, and the whole
flow — signup → wizard → AI-generated plan → scheduled sessions — runs
against your deployed backend.

## L. Integration into an existing LMS

1. **Do not duplicate** `students`, `subjects`, `topics`, `completed_topics`,
   or `assessment_results` if they already exist — repoint the SQLAlchemy
   models in `models/models.py` (see the `# EXISTING TABLE` comments) at
   your real tables/columns instead of running the placeholder DDL for them.
2. Mount the new routers in your existing FastAPI app:
   ```python
   app.include_router(study_schedule_router, prefix="/api")
   app.include_router(study_session_router, prefix="/api")
   app.include_router(availability_router, prefix="/api")
   ```
3. Reuse your existing auth dependency instead of the placeholder
   `get_current_student` in `api/deps.py` — it only needs to return a
   student id.
4. Add the dashboard entry point (title/description/buttons from the spec)
   as a card component that links to `/study-schedule`; wire
   `StudyScheduleWizard` behind that route.
5. If your LMS's assessment/quiz results live in a different shape, adapt
   `context_builder.py`'s query — it's the single place that assembles the
   "learning profile" sent to the AI, so LMS-specific data shapes are
   isolated there.

## Frontend scaffolding

The `frontend/` directory is a complete, runnable Vite + React + TypeScript +
Tailwind project (`package.json`, `vite.config.ts`, `tailwind.config.js`,
`index.html`, `src/main.tsx`) wrapping the components described above.
`src/App.tsx` has two modes:
- **Demo** — renders `WeeklyCalendar` / `ScheduleExplanation` against fixed
  mock data (`src/mockData.ts`), no backend required. This is the default.
- **Live** — shows a login/signup form (`src/components/LoginForm.tsx`)
  hitting the real `/api/auth` endpoints; once authenticated it renders
  `StudyScheduleDashboardPage` against the real backend, either through the
  Vite dev-server's `/api` proxy locally or `VITE_API_BASE_URL` in
  production (see the Render+Vercel walkthrough above).

`npm install && npm run build` and `npm run dev` were both verified to run
clean during this delivery.

## Assumptions made explicit
- Stack: FastAPI + SQLAlchemy + PostgreSQL + Pydantic on the backend,
  React + TypeScript + Tailwind on the frontend (per spec's default
  preference). Swap freely — the scheduler and AI-planner logic are
  framework-agnostic pure Python.
- Auth: a `get_current_student(token) -> student_id` dependency is assumed;
  replace with your real auth.
- LLM access: `AiPlannerService` calls a generic `/v1/messages`-style
  endpoint with a JSON-schema-constrained prompt; swap the HTTP call for
  your actual provider SDK if different.
- Timezone: every stored time is UTC; conversion to/from the student's
  configured timezone happens at the API boundary (`utils/time_utils.py`).
