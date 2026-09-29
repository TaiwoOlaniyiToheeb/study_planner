import React from "react";
import { ScheduledSession, UnscheduledTask } from "../types";

interface Props {
  overallReasoning?: string;
  sessions: ScheduledSession[];
  unscheduled: UnscheduledTask[];
}

export default function ScheduleExplanation({ overallReasoning, sessions, unscheduled }: Props) {
  // Show a small, deduplicated set of per-task reasons rather than one line
  // per session (many sessions share the same underlying reason).
  const uniqueReasons = Array.from(new Set(sessions.map((s) => s.reason).filter(Boolean)));

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
      <h3 className="font-semibold text-slate-800">Why this schedule?</h3>
      {overallReasoning && <p className="text-sm text-slate-700">{overallReasoning}</p>}
      {uniqueReasons.length > 0 && (
        <ul className="list-inside list-disc space-y-1 text-sm text-slate-600">
          {uniqueReasons.slice(0, 8).map((reason, i) => <li key={i}>{reason}</li>)}
        </ul>
      )}

      {unscheduled.length > 0 && (
        <div className="mt-3 rounded border border-amber-300 bg-amber-50 p-3">
          <p className="text-sm font-medium text-amber-800">
            We couldn't fit all recommended study tasks into your available time.
          </p>
          <ul className="mt-1 list-inside list-disc text-sm text-amber-700">
            {unscheduled.map((t, i) => (
              <li key={i}>{t.activity_type} session ({t.estimated_minutes}m) \u2014 {t.reason_could_not_schedule}</li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-amber-700">
            Try adding more available time, increasing your max sessions/day, or extending your exam date.
          </p>
        </div>
      )}
    </div>
  );
}
