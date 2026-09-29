import {
  AvailabilityPeriod, StudySchedule, StudyPreferences, StudyGoal,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${localStorage.getItem("auth_token") ?? ""}`,
      ...(options.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

export const studyScheduleApi = {
  getActiveSchedule: () => request<StudySchedule>("/study-schedule"),

  generateSchedule: (subjectIds: string[]) =>
    request<StudySchedule>("/study-schedule/generate", {
      method: "POST",
      body: JSON.stringify(subjectIds),
    }),

  createManualSchedule: (payload: {
    exam_date: string;
    sessions: {
      subject_id: string; topic_id: string; activity_type: string;
      scheduled_date: string; start_time: string; duration_minutes: number;
    }[];
  }) =>
    request<StudySchedule>("/study-schedule/manual", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  regenerateWithInstruction: (scheduleId: string, instruction: string) =>
    request<StudySchedule>("/study-schedule/regenerate", {
      method: "POST",
      body: JSON.stringify({ schedule_id: scheduleId, instruction }),
    }),

  acceptSchedule: (scheduleId: string) =>
    request<StudySchedule>(`/study-schedule/${scheduleId}/accept`, { method: "POST" }),

  modifySession: (payload: {
    session_id: string; new_date?: string; new_start_time?: string;
    new_activity_type?: string; new_duration_minutes?: number;
  }) =>
    request(`/study-schedule/modify`, { method: "POST", body: JSON.stringify(payload) }),

  completeSession: (sessionId: string, assessmentScorePercent?: number) =>
    request(`/study-session/${sessionId}/complete`, {
      method: "POST",
      body: JSON.stringify({ assessment_score_percent: assessmentScorePercent ?? null }),
    }),

  missSession: (sessionId: string, action: "mark_completed" | "reschedule" | "skip") =>
    request(`/study-session/${sessionId}/miss`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),

  listAvailability: () => request<AvailabilityPeriod[]>("/study-availability"),

  createAvailability: (period: AvailabilityPeriod) =>
    request<AvailabilityPeriod>("/study-availability", {
      method: "POST",
      body: JSON.stringify(period),
    }),

  updateAvailability: (id: string, period: AvailabilityPeriod) =>
    request<AvailabilityPeriod>(`/study-availability/${id}`, {
      method: "PUT",
      body: JSON.stringify(period),
    }),

  deleteAvailability: (id: string) =>
    request<void>(`/study-availability/${id}`, { method: "DELETE" }),

  putStudyPreferences: (payload: {
    exam_goal_type: string; exam_goal_other_text?: string; exam_date: string;
    daily_study_minutes_goal: number; preferred_time: string;
    session_duration_min: number; break_duration_min: number; max_sessions_per_day: number;
  }) =>
    request("/study-preferences", { method: "PUT", body: JSON.stringify(payload) }),

  listSubjects: () => request<{ id: string; name: string }[]>("/subjects"),

  listTopics: (subjectId: string) =>
    request<{ id: string; subject_id: string; name: string; difficulty: number; sequence_index: number }[]>(
      `/subjects/${subjectId}/topics`
    ),

  createSubject: (name: string) =>
    request<{ id: string; name: string }>("/subjects", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  createTopic: (subjectId: string, payload: { name: string; difficulty?: number }) =>
    request<{ id: string; subject_id: string; name: string; difficulty: number; sequence_index: number }>(
      `/subjects/${subjectId}/topics`,
      { method: "POST", body: JSON.stringify(payload) }
    ),
};
