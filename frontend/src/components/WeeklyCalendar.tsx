import React, { useMemo, useState } from "react";
import { ScheduledSession, ActivityType, ACTIVITY_COLORS } from "../types";
import StudySessionCard from "./StudySessionCard";

interface Props {
  sessions: ScheduledSession[];
  onComplete?: (session: ScheduledSession) => void;
  onMiss?: (session: ScheduledSession) => void;
}

const ACTIVITY_FILTERS: (ActivityType | "all")[] = [
  "all", "learning", "practice", "revision", "assessment", "review",
];

export default function WeeklyCalendar({ sessions, onComplete, onMiss }: Props) {
  const [subjectFilter, setSubjectFilter] = useState<string>("all");
  const [activityFilter, setActivityFilter] = useState<ActivityType | "all">("all");
  const [view, setView] = useState<"weekly" | "daily">("weekly");
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const subjectNames = useMemo(
    () => Array.from(new Set(sessions.map((s) => s.subject_name))).sort(),
    [sessions]
  );

  const filtered = sessions.filter(
    (s) =>
      (subjectFilter === "all" || s.subject_name === subjectFilter) &&
      (activityFilter === "all" || s.activity_type === activityFilter)
  );

  const byDate = useMemo(() => {
    const grouped: Record<string, ScheduledSession[]> = {};
    for (const s of filtered) {
      grouped[s.scheduled_date] = grouped[s.scheduled_date] ?? [];
      grouped[s.scheduled_date].push(s);
    }
    for (const date of Object.keys(grouped)) {
      grouped[date].sort((a, b) => a.start_time.localeCompare(b.start_time));
    }
    return grouped;
  }, [filtered]);

  const sortedDates = Object.keys(byDate).sort();
  const datesToShow = view === "daily" && selectedDate ? [selectedDate] : sortedDates;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <select
          className="rounded border border-slate-300 px-2 py-1 text-sm"
          value={subjectFilter}
          onChange={(e) => setSubjectFilter(e.target.value)}
        >
          <option value="all">All subjects</option>
          {subjectNames.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>

        <select
          className="rounded border border-slate-300 px-2 py-1 text-sm"
          value={activityFilter}
          onChange={(e) => setActivityFilter(e.target.value as ActivityType | "all")}
        >
          {ACTIVITY_FILTERS.map((a) => (
            <option key={a} value={a}>{a === "all" ? "All activities" : a}</option>
          ))}
        </select>

        <div className="ml-auto flex gap-1 rounded border border-slate-300 p-0.5 text-sm">
          <button
            className={`rounded px-2 py-1 ${view === "weekly" ? "bg-slate-800 text-white" : ""}`}
            onClick={() => setView("weekly")}
          >
            Weekly
          </button>
          <button
            className={`rounded px-2 py-1 ${view === "daily" ? "bg-slate-800 text-white" : ""}`}
            onClick={() => setView("daily")}
          >
            Daily
          </button>
        </div>
      </div>

      {view === "daily" && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {sortedDates.map((d) => (
            <button
              key={d}
              className={`whitespace-nowrap rounded px-3 py-1 text-sm ${
                selectedDate === d ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-700"
              }`}
              onClick={() => setSelectedDate(d)}
            >
              {new Date(d).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
            </button>
          ))}
        </div>
      )}

      <div className={view === "weekly" ? "grid gap-4 sm:grid-cols-2 lg:grid-cols-3" : "space-y-3"}>
        {datesToShow.map((d) => (
          <div key={d} className="rounded-lg border border-slate-200 p-3">
            <p className="mb-2 font-semibold text-slate-800">
              {new Date(d).toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" })}
            </p>
            <div className="space-y-2">
              {byDate[d].map((session) => (
                <StudySessionCard
                  key={session.id}
                  session={session}
                  onComplete={onComplete}
                  onMiss={onMiss}
                />
              ))}
            </div>
          </div>
        ))}
        {datesToShow.length === 0 && (
          <p className="text-sm text-slate-500">No sessions match the current filters.</p>
        )}
      </div>
    </div>
  );
}
