import React, { useEffect, useState } from "react";
import StudyScheduleWizard from "../components/StudyScheduleWizard";
import ManualScheduleBuilder from "../components/ManualScheduleBuilder";
import WeeklyCalendar from "../components/WeeklyCalendar";
import ScheduleExplanation from "../components/ScheduleExplanation";
import RegenerateScheduleModal from "../components/RegenerateScheduleModal";
import ModifyScheduleModal from "../components/ModifyScheduleModal";
import { StudySchedule, ScheduledSession, SubjectSummary } from "../types";
import { studyScheduleApi } from "../services/studyScheduleApi";

// Dashboard entry-point card (spec section 3). Drop this into your existing
// student dashboard grid.
export function AiStudyScheduleCard({ hasSchedule, onOpen }: { hasSchedule: boolean; onOpen: () => void }) {
  return (
    <div className="rounded-lg border border-slate-200 p-5">
      <h3 className="text-base font-semibold">{"\u{1F916}"} AI Study Schedule</h3>
      <p className="mt-1 text-sm text-slate-600">
        Not sure when or what to study? Let AI create a personalized reading timetable based on your
        available time, subjects, learning progress, and goals — or build your own from scratch if
        you'd rather stay fully in control.
      </p>
      <button
        className="mt-4 rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white"
        onClick={onOpen}
      >
        {hasSchedule ? "View My Schedule" : "Create My Schedule"}
      </button>
    </div>
  );
}

type CreationMode = "choose" | "ai" | "manual";

interface Props {
  subjects: SubjectSummary[]; // fetched from the LMS's own subject/progress endpoints
}

export default function StudyScheduleDashboardPage({ subjects }: Props) {
  const [schedule, setSchedule] = useState<StudySchedule | null>(null);
  const [creationMode, setCreationMode] = useState<CreationMode | null>(null);
  const [showRegenerate, setShowRegenerate] = useState(false);
  const [modifyingSession, setModifyingSession] = useState<ScheduledSession | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    studyScheduleApi.getActiveSchedule().then(setSchedule).catch(() => setLoadError(null));
    // A 404 (no active schedule yet) is expected for first-time users — not
    // surfaced as an error.
  }, []);

  async function handleAccept() {
    if (!schedule) return;
    const accepted = await studyScheduleApi.acceptSchedule(schedule.id);
    setSchedule(accepted);
  }

  async function handleComplete(session: ScheduledSession) {
    await studyScheduleApi.completeSession(session.id);
    setSchedule((prev) =>
      prev ? { ...prev, sessions: prev.sessions.map((s) => s.id === session.id ? { ...s, status: "completed" } : s) } : prev
    );
  }

  async function handleMiss(session: ScheduledSession) {
    const result: any = await studyScheduleApi.missSession(session.id, "reschedule");
    if (result.status === "rescheduled") {
      const refreshed = await studyScheduleApi.getActiveSchedule();
      setSchedule(refreshed);
    }
  }

  // Step 1 of creation: let the student choose AI-generated vs fully manual.
  if (creationMode === "choose") {
    return (
      <div className="mx-auto max-w-2xl space-y-4 p-6">
        <h2 className="text-lg font-semibold">How would you like to build your schedule?</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <button
            className="rounded-lg border border-slate-200 p-5 text-left hover:border-slate-400"
            onClick={() => setCreationMode("ai")}
          >
            <p className="font-semibold">{"\u{1F916}"} Let AI build it</p>
            <p className="mt-1 text-sm text-slate-600">
              Answer a few questions about your goal, availability, and preferences — AI prioritizes
              what to study and a scheduler fits it into your time.
            </p>
          </button>
          <button
            className="rounded-lg border border-slate-200 p-5 text-left hover:border-slate-400"
            onClick={() => setCreationMode("manual")}
          >
            <p className="font-semibold">{"\u{1F4DD}"} Build it myself</p>
            <p className="mt-1 text-sm text-slate-600">
              Pick every subject, topic, date, and time yourself. No AI involved — you're fully in
              control, we just stop double-booking and scheduling past your exam date.
            </p>
          </button>
        </div>
        <button className="text-sm text-slate-500 hover:underline" onClick={() => setCreationMode(null)}>
          Cancel
        </button>
      </div>
    );
  }

  if (creationMode === "ai") {
    return (
      <StudyScheduleWizard
        subjects={subjects}
        onCancel={() => setCreationMode(null)}
        onScheduleGenerated={(s) => { setSchedule(s); setCreationMode(null); }}
      />
    );
  }

  if (creationMode === "manual") {
    return (
      <ManualScheduleBuilder
        onCancel={() => setCreationMode(null)}
        onScheduleCreated={(s) => { setSchedule(s); setCreationMode(null); }}
      />
    );
  }

  if (!schedule) {
    return (
      <div className="mx-auto max-w-lg p-6">
        <AiStudyScheduleCard hasSchedule={false} onOpen={() => setCreationMode("choose")} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Your Study Plan</h1>
        <div className="flex gap-2">
          {schedule.status === "draft" && (
            <button className="rounded bg-emerald-600 px-4 py-2 text-sm text-white" onClick={handleAccept}>
              Accept Schedule
            </button>
          )}
          <button
            className="rounded border border-slate-300 px-4 py-2 text-sm"
            onClick={() => setShowRegenerate(true)}
          >
            Regenerate Schedule
          </button>
          <button className="rounded border border-slate-300 px-4 py-2 text-sm" onClick={() => setCreationMode("choose")}>
            New Schedule
          </button>
        </div>
      </div>

      <ScheduleExplanation
        overallReasoning={schedule.overall_reasoning}
        sessions={schedule.sessions}
        unscheduled={schedule.unscheduled}
      />

      <WeeklyCalendar sessions={schedule.sessions} onComplete={handleComplete} onMiss={handleMiss} />

      {showRegenerate && (
        <RegenerateScheduleModal
          scheduleId={schedule.id}
          onClose={() => setShowRegenerate(false)}
          onRegenerated={setSchedule}
        />
      )}
      {modifyingSession && (
        <ModifyScheduleModal
          session={modifyingSession}
          onClose={() => setModifyingSession(null)}
          onModified={(updated) =>
            setSchedule((prev) =>
              prev ? { ...prev, sessions: prev.sessions.map((s) => s.id === updated.id ? updated : s) } : prev
            )
          }
        />
      )}
    </div>
  );
}
