// Mirrors backend/schemas/schemas.py — keep these in sync manually, or
// generate this file from the FastAPI OpenAPI spec (recommended) once the
// backend is wired up: `openapi-typescript http://localhost:8000/openapi.json`.

export type PreferredTime = "morning" | "afternoon" | "evening" | "no_preference";
export type ActivityType = "learning" | "practice" | "revision" | "assessment" | "review";
export type SessionStatus =
  | "scheduled" | "in_progress" | "completed" | "missed" | "skipped" | "rescheduled";
export type PeriodType = "busy" | "free";

export interface AvailabilityPeriod {
  id?: string;
  day_of_week: number; // 0=Monday .. 6=Sunday
  start_time: string;  // "HH:MM"
  end_time: string;
  period_type: PeriodType;
  label?: string;
}

export interface StudyGoal {
  exam_goal_type: string;
  exam_goal_other_text?: string;
  exam_date: string; // ISO date
  daily_study_minutes_goal: number;
}

export interface StudyPreferences {
  preferred_time: PreferredTime;
  session_duration_min: 30 | 45 | 60 | 90 | 120;
  break_duration_min: 5 | 10 | 15 | 20 | 30;
  max_sessions_per_day: number;
}

export interface SubjectSummary {
  subject_id: string;
  name: string;
  performance_percent?: number;
  completed_topics: number;
  incomplete_topics: number;
  manual_priority?: number;
}

export interface ScheduledSession {
  id: string;
  subject_id: string;
  subject_name: string;
  topic_id: string;
  topic_name: string;
  activity_type: ActivityType;
  scheduled_date: string;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  status: SessionStatus;
  priority: number;
  reason: string;
}

export interface UnscheduledTask {
  subject_id: string;
  topic_id: string;
  activity_type: ActivityType;
  estimated_minutes: number;
  reason_could_not_schedule: string;
}

export interface StudySchedule {
  id: string;
  student_id: string;
  status: string;
  exam_date: string;
  generated_at: string;
  sessions: ScheduledSession[];
  unscheduled: UnscheduledTask[];
  overall_reasoning?: string;
}

export const DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export const ACTIVITY_COLORS: Record<ActivityType, string> = {
  learning: "bg-blue-100 text-blue-800 border-blue-300",
  practice: "bg-amber-100 text-amber-800 border-amber-300",
  revision: "bg-purple-100 text-purple-800 border-purple-300",
  assessment: "bg-rose-100 text-rose-800 border-rose-300",
  review: "bg-emerald-100 text-emerald-800 border-emerald-300",
};
