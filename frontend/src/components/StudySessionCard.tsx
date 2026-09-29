import React from "react";
import { ScheduledSession, ACTIVITY_COLORS } from "../types";

interface Props {
  session: ScheduledSession;
  onComplete?: (session: ScheduledSession) => void;
  onMiss?: (session: ScheduledSession) => void;
}

export default function StudySessionCard({ session, onComplete, onMiss }: Props) {
  const isPast = session.status === "scheduled" && new Date(`${session.scheduled_date}T${session.end_time}`) < new Date();

  return (
    <div className={`rounded-md border p-2 text-sm ${ACTIVITY_COLORS[session.activity_type]}`}>
      <div className="flex items-center justify-between">
        <span className="font-medium">{session.start_time}–{session.end_time}</span>
        <span className="rounded-full bg-white/60 px-2 py-0.5 text-xs capitalize">
          {session.activity_type}
        </span>
      </div>
      <p className="mt-1 font-semibold">{session.subject_name}</p>
      <p className="text-xs opacity-80">{session.topic_name}</p>

      {session.status !== "completed" && session.status !== "skipped" && (
        <div className="mt-2 flex gap-2">
          {onComplete && (
            <button
              className="rounded bg-white/70 px-2 py-1 text-xs font-medium hover:bg-white"
              onClick={() => onComplete(session)}
            >
              Mark complete
            </button>
          )}
          {isPast && onMiss && (
            <button
              className="rounded bg-white/70 px-2 py-1 text-xs font-medium text-rose-700 hover:bg-white"
              onClick={() => onMiss(session)}
            >
              ⚠️ Missed
            </button>
          )}
        </div>
      )}
      {session.status === "completed" && (
        <p className="mt-1 text-xs font-medium">✓ Completed</p>
      )}
    </div>
  );
}
