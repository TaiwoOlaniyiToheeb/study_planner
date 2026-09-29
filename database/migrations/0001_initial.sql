-- 0001_initial.sql
-- AI Study Schedule feature — schema.
--
-- Tables marked "PLACEHOLDER (assumed existing)" should be DROPPED from this
-- migration if your LMS already has equivalent tables — keep only the
-- feature-specific tables below them and adjust foreign keys to point at
-- your real tables/columns.

-- ============================================================
-- PLACEHOLDER (assumed existing) — remove if your LMS already has these
-- ============================================================

CREATE TABLE IF NOT EXISTS students (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name       VARCHAR(255) NOT NULL,
    timezone        VARCHAR(64) NOT NULL DEFAULT 'UTC',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS subjects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS topics (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id      UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    difficulty      SMALLINT NOT NULL DEFAULT 3 CHECK (difficulty BETWEEN 1 AND 5),
    sequence_index  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_topics_subject ON topics(subject_id);

CREATE TABLE IF NOT EXISTS topic_prerequisites (
    topic_id            UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    prerequisite_id     UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    PRIMARY KEY (topic_id, prerequisite_id)
);

CREATE TABLE IF NOT EXISTS student_subjects (
    student_id      UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject_id      UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    PRIMARY KEY (student_id, subject_id)
);

CREATE TABLE IF NOT EXISTS completed_topics (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id      UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    topic_id        UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    completed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (student_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_completed_topics_student ON completed_topics(student_id);

CREATE TABLE IF NOT EXISTS assessment_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id      UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    topic_id        UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    score_percent   NUMERIC(5,2) NOT NULL CHECK (score_percent BETWEEN 0 AND 100),
    taken_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_assessment_student_topic ON assessment_results(student_id, topic_id);

-- ============================================================
-- FEATURE TABLES (new)
-- ============================================================

CREATE TABLE study_preferences (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id              UUID NOT NULL UNIQUE REFERENCES students(id) ON DELETE CASCADE,
    preferred_time          VARCHAR(20) NOT NULL DEFAULT 'no_preference'
                                CHECK (preferred_time IN ('morning','afternoon','evening','no_preference')),
    session_duration_min    INTEGER NOT NULL CHECK (session_duration_min IN (30,45,60,90,120)),
    break_duration_min      INTEGER NOT NULL CHECK (break_duration_min IN (5,10,15,20,30)),
    max_sessions_per_day    INTEGER NOT NULL CHECK (max_sessions_per_day BETWEEN 1 AND 8),
    daily_study_minutes_goal INTEGER NOT NULL CHECK (daily_study_minutes_goal > 0),
    exam_goal_type          VARCHAR(50) NOT NULL,
    exam_goal_other_text    VARCHAR(255),
    exam_date               DATE NOT NULL,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_exam_date_future CHECK (exam_date >= CURRENT_DATE)
);

CREATE TABLE availability_periods (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id      UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    day_of_week     SMALLINT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6), -- 0=Monday
    start_time      TIME NOT NULL,
    end_time        TIME NOT NULL,
    period_type     VARCHAR(10) NOT NULL CHECK (period_type IN ('busy','free')),
    label           VARCHAR(50),  -- School / Work / Religious / Family / Sports / Other
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_time_order CHECK (start_time < end_time)
);
CREATE INDEX IF NOT EXISTS idx_availability_student_day ON availability_periods(student_id, day_of_week);
-- Overlap prevention for periods of the same type is enforced at the application
-- layer (see services/scheduler/slots.py) because exclusion constraints on TIME
-- ranges without a date require the btree_gist extension; enable it if preferred:
-- CREATE EXTENSION IF NOT EXISTS btree_gist;
-- ALTER TABLE availability_periods ADD CONSTRAINT no_overlap
--   EXCLUDE USING gist (student_id WITH =, day_of_week WITH =, period_type WITH =,
--   tsrange(start_time::text, end_time::text) WITH &&);

CREATE TABLE study_schedules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id      UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    status          VARCHAR(20) NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft','active','archived')),
    exam_date       DATE NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    accepted_at     TIMESTAMPTZ,
    version         INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_schedules_student_status ON study_schedules(student_id, status);

CREATE TABLE study_sessions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    schedule_id         UUID NOT NULL REFERENCES study_schedules(id) ON DELETE CASCADE,
    student_id          UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject_id          UUID NOT NULL REFERENCES subjects(id),
    topic_id            UUID NOT NULL REFERENCES topics(id),
    activity_type       VARCHAR(20) NOT NULL
                            CHECK (activity_type IN ('learning','practice','revision','assessment','review')),
    scheduled_date      DATE NOT NULL,
    start_time          TIME NOT NULL,
    end_time            TIME NOT NULL,
    duration_minutes    INTEGER NOT NULL CHECK (duration_minutes > 0),
    status              VARCHAR(20) NOT NULL DEFAULT 'scheduled'
                            CHECK (status IN ('scheduled','in_progress','completed','missed','skipped','rescheduled')),
    priority            SMALLINT NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    reason              TEXT,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_session_time_order CHECK (start_time < end_time)
);
CREATE INDEX IF NOT EXISTS idx_sessions_schedule ON study_sessions(schedule_id);
CREATE INDEX IF NOT EXISTS idx_sessions_student_date ON study_sessions(student_id, scheduled_date);
-- Prevent overlapping sessions for the same student on the same day at the DB level:
CREATE EXTENSION IF NOT EXISTS btree_gist;
ALTER TABLE study_sessions ADD CONSTRAINT no_overlapping_sessions
    EXCLUDE USING gist (
        student_id WITH =,
        scheduled_date WITH =,
        tsrange(
            (scheduled_date + start_time)::timestamp,
            (scheduled_date + end_time)::timestamp
        ) WITH &&
    );

CREATE TABLE schedule_generation_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    schedule_id     UUID NOT NULL REFERENCES study_schedules(id) ON DELETE CASCADE,
    raw_ai_plan     JSONB NOT NULL,       -- validated structured plan from the LLM
    prompt_version  VARCHAR(50) NOT NULL,
    unscheduled     JSONB,                -- tasks the scheduler could not place
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE schedule_modifications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    schedule_id         UUID NOT NULL REFERENCES study_schedules(id) ON DELETE CASCADE,
    modification_type   VARCHAR(20) NOT NULL CHECK (modification_type IN ('manual','natural_language','adaptive')),
    instruction_text    TEXT,                 -- original NL instruction, if any
    structured_request  JSONB,                -- AI-interpreted / manual structured change
    applied_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_by          UUID REFERENCES students(id)
);

-- ============================================================
-- AUTH (new — only needed for standalone deployment; skip if your
-- existing LMS already handles login and issues its own tokens)
-- ============================================================

CREATE TABLE student_credentials (
    student_id      UUID PRIMARY KEY REFERENCES students(id) ON DELETE CASCADE,
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_student_credentials_email ON student_credentials(email);
