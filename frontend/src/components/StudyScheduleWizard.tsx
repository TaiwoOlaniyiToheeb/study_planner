import React, { useState } from "react";
import AvailabilityEditor from "./AvailabilityEditor";
import {
  AvailabilityPeriod, StudyGoal, StudyPreferences, SubjectSummary, StudySchedule,
} from "../types";
import { studyScheduleApi } from "../services/studyScheduleApi";

// NOTE: per the spec's own guidance to avoid dozens of near-duplicate files,
// StudyGoalStep, StudyPreferencesStep and SubjectPriorityStep are implemented
// as internal sub-components below rather than separate files — each is
// still a clearly separated, independently testable function component.

// Tertiary-education goal types (university/polytechnic-level), not
// secondary-school entrance exams (WAEC/NECO/JAMB lead INTO tertiary
// education, they aren't what a tertiary student is currently sitting for).
const EXAM_GOAL_OPTIONS = [
  "Semester / Course Examination", "Continuous Assessment (CA) / Test",
  "Professional Certification (e.g. ICAN, CFA, PMP)", "Project / Thesis Defense",
  "Postgraduate Qualifying Exam", "General Academic Improvement", "Other",
];
const SESSION_DURATIONS = [30, 45, 60, 90, 120] as const;
const BREAK_DURATIONS = [5, 10, 15, 20, 30] as const;

type Step = "goal" | "availability" | "preferences" | "subjects" | "review";
const STEP_ORDER: Step[] = ["goal", "availability", "preferences", "subjects", "review"];

interface Props {
  subjects: SubjectSummary[]; // fetched from the LMS separately and passed in
  onScheduleGenerated: (schedule: StudySchedule) => void;
  onCancel: () => void;
}

export default function StudyScheduleWizard({ subjects, onScheduleGenerated, onCancel }: Props) {
  const [step, setStep] = useState<Step>("goal");
  const [goal, setGoal] = useState<StudyGoal>({
    exam_goal_type: EXAM_GOAL_OPTIONS[0], exam_date: "", daily_study_minutes_goal: 60,
  });
  const [availability, setAvailability] = useState<AvailabilityPeriod[]>([]);
  const [preferences, setPreferences] = useState<StudyPreferences>({
    preferred_time: "no_preference", session_duration_min: 60, break_duration_min: 15,
    max_sessions_per_day: 3,
  });
  const [priorities, setPriorities] = useState<Record<string, number>>({});
  // Local, appendable copy of the subjects list — lets the student add a
  // subject inline (e.g. their DB has none yet) without needing this wizard
  // to round-trip through the parent component. New subjects persist to the
  // backend immediately on creation, so they'll be there next time too.
  const [subjectList, setSubjectList] = useState<SubjectSummary[]>(subjects);
  const [selectedSubjectIds, setSelectedSubjectIds] = useState<string[]>(subjects.map((s) => s.subject_id));
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stepIndex = STEP_ORDER.indexOf(step);

  // "Desired study hours per day" and "preferred session duration" were two
  // separate questions asking essentially the same thing (how much time per
  // sitting) from two different angles. Collapsed into one control —
  // preferences.session_duration_min, set in the Preferences step — and the
  // daily total is derived from that times how many sessions/day the student
  // allows, rather than asked twice.
  const derivedDailyMinutes = preferences.session_duration_min * preferences.max_sessions_per_day;

  function goNext() {
    if (step === "goal" && !goal.exam_date) { setError("Please pick an examination date."); return; }
    setError(null);
    setStep(STEP_ORDER[Math.min(stepIndex + 1, STEP_ORDER.length - 1)]);
  }
  function goBack() {
    setError(null);
    setStep(STEP_ORDER[Math.max(stepIndex - 1, 0)]);
  }

  async function handleCreateSubject(name: string) {
    const created = await studyScheduleApi.createSubject(name);
    const newSubject: SubjectSummary = {
      subject_id: created.id, name: created.name, completed_topics: 0, incomplete_topics: 0,
    };
    setSubjectList((prev) => [...prev, newSubject]);
    setSelectedSubjectIds((prev) => [...prev, created.id]);
  }

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      // Only create availability periods that aren't already saved from a
      // previous Generate attempt — re-POSTing the exact same period twice
      // trips the backend's overlap check against itself and fails with a
      // confusing "Overlaps an existing free period" error.
      const existing = await studyScheduleApi.listAvailability();
      const alreadySaved = (p: AvailabilityPeriod) =>
        existing.some(
          (e) =>
            e.day_of_week === p.day_of_week &&
            e.start_time === p.start_time &&
            e.end_time === p.end_time &&
            e.period_type === p.period_type
        );
      for (const period of availability) {
        if (!alreadySaved(period)) {
          await studyScheduleApi.createAvailability(period);
        }
      }

      await studyScheduleApi.putStudyPreferences({
        exam_goal_type: goal.exam_goal_type,
        exam_goal_other_text: goal.exam_goal_other_text,
        exam_date: goal.exam_date,
        daily_study_minutes_goal: derivedDailyMinutes,
        preferred_time: preferences.preferred_time,
        session_duration_min: preferences.session_duration_min,
        break_duration_min: preferences.break_duration_min,
        max_sessions_per_day: preferences.max_sessions_per_day,
      });

      const schedule = await studyScheduleApi.generateSchedule(selectedSubjectIds);
      onScheduleGenerated(schedule);
    } catch (e: any) {
      setError(e.message ?? "AI schedule generation is temporarily unavailable. Please try again.");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-4">
      <ProgressBar currentIndex={stepIndex} total={STEP_ORDER.length} />

      {step === "goal" && <StudyGoalStep goal={goal} onChange={setGoal} />}
      {step === "availability" && (
        <div>
          <h2 className="mb-3 text-lg font-semibold">Weekly Availability</h2>
          <AvailabilityEditor periods={availability} onChange={setAvailability} />
        </div>
      )}
      {step === "preferences" && (
        <StudyPreferencesStep preferences={preferences} onChange={setPreferences} derivedDailyMinutes={derivedDailyMinutes} />
      )}
      {step === "subjects" && (
        <SubjectPriorityStep
          subjects={subjectList}
          selectedIds={selectedSubjectIds}
          onSelectedChange={setSelectedSubjectIds}
          priorities={priorities}
          onPrioritiesChange={setPriorities}
          onCreateSubject={handleCreateSubject}
        />
      )}
      {step === "review" && (
        <ReviewStep goal={goal} preferences={preferences} availability={availability}
                    subjectCount={selectedSubjectIds.length} derivedDailyMinutes={derivedDailyMinutes} />
      )}

      {error && <p className="text-sm text-rose-600">{error}</p>}

      <div className="flex justify-between border-t border-slate-200 pt-4">
        <button className="text-sm text-slate-500 hover:underline" onClick={onCancel}>Cancel</button>
        <div className="flex gap-2">
          {stepIndex > 0 && (
            <button className="rounded border border-slate-300 px-4 py-2 text-sm" onClick={goBack}>
              Back
            </button>
          )}
          {step !== "review" ? (
            <button className="rounded bg-slate-800 px-4 py-2 text-sm text-white" onClick={goNext}>
              Continue
            </button>
          ) : (
            <button
              className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              onClick={handleGenerate}
              disabled={generating}
            >
              {generating ? "Generating\u2026" : "Generate Schedule"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function ProgressBar({ currentIndex, total }: { currentIndex: number; total: number }) {
  return (
    <div className="flex gap-1">
      {Array.from({ length: total }).map((_, i) => (
        <div key={i} className={`h-1.5 flex-1 rounded ${i <= currentIndex ? "bg-slate-800" : "bg-slate-200"}`} />
      ))}
    </div>
  );
}

function StudyGoalStep({ goal, onChange }: { goal: StudyGoal; onChange: (g: StudyGoal) => void }) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Study Goal</h2>
      <label className="block text-sm font-medium">Examination / Study Goal</label>
      <select
        className="w-full rounded border border-slate-300 px-3 py-2"
        value={goal.exam_goal_type}
        onChange={(e) => onChange({ ...goal, exam_goal_type: e.target.value })}
      >
        {EXAM_GOAL_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
      {goal.exam_goal_type === "Other" && (
        <input
          className="w-full rounded border border-slate-300 px-3 py-2"
          placeholder="Describe your goal"
          value={goal.exam_goal_other_text ?? ""}
          onChange={(e) => onChange({ ...goal, exam_goal_other_text: e.target.value })}
        />
      )}

      <label className="block text-sm font-medium">Examination Date</label>
      <input
        type="date"
        className="w-full rounded border border-slate-300 px-3 py-2"
        value={goal.exam_date}
        min={new Date().toISOString().slice(0, 10)}
        onChange={(e) => onChange({ ...goal, exam_date: e.target.value })}
      />
      <p className="text-xs text-slate-500">
        You'll set how long each study session runs, and how many per day, in the next steps — your
        daily study time is calculated from those.
      </p>
    </div>
  );
}

function StudyPreferencesStep({
  preferences, onChange, derivedDailyMinutes,
}: { preferences: StudyPreferences; onChange: (p: StudyPreferences) => void; derivedDailyMinutes: number }) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Study Preferences</h2>

      <label className="block text-sm font-medium">Preferred Study Time</label>
      <div className="flex gap-2">
        {(["morning", "afternoon", "evening", "no_preference"] as const).map((t) => (
          <button
            key={t}
            className={`rounded border px-3 py-1.5 text-sm capitalize ${
              preferences.preferred_time === t ? "border-slate-800 bg-slate-800 text-white" : "border-slate-300"
            }`}
            onClick={() => onChange({ ...preferences, preferred_time: t })}
          >
            {t.replace("_", " ")}
          </button>
        ))}
      </div>

      <label className="block text-sm font-medium">Study Session Length</label>
      <div className="flex gap-2">
        {SESSION_DURATIONS.map((d) => (
          <button
            key={d}
            className={`rounded border px-3 py-1.5 text-sm ${
              preferences.session_duration_min === d ? "border-slate-800 bg-slate-800 text-white" : "border-slate-300"
            }`}
            onClick={() => onChange({ ...preferences, session_duration_min: d })}
          >
            {d}m
          </button>
        ))}
      </div>

      <label className="block text-sm font-medium">Break Duration</label>
      <div className="flex gap-2">
        {BREAK_DURATIONS.map((d) => (
          <button
            key={d}
            className={`rounded border px-3 py-1.5 text-sm ${
              preferences.break_duration_min === d ? "border-slate-800 bg-slate-800 text-white" : "border-slate-300"
            }`}
            onClick={() => onChange({ ...preferences, break_duration_min: d })}
          >
            {d}m
          </button>
        ))}
      </div>

      <label className="block text-sm font-medium">Maximum Study Sessions Per Day</label>
      <div className="flex gap-2">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            className={`h-9 w-9 rounded border text-sm ${
              preferences.max_sessions_per_day === n ? "border-slate-800 bg-slate-800 text-white" : "border-slate-300"
            }`}
            onClick={() => onChange({ ...preferences, max_sessions_per_day: n })}
          >
            {n}
          </button>
        ))}
      </div>

      <p className="rounded bg-slate-50 px-3 py-2 text-sm text-slate-600">
        That's up to <strong>{Math.round((derivedDailyMinutes / 60) * 10) / 10}h/day</strong> total
        ({preferences.max_sessions_per_day} × {preferences.session_duration_min}m sessions).
      </p>
    </div>
  );
}

function SubjectPriorityStep({
  subjects, selectedIds, onSelectedChange, priorities, onPrioritiesChange, onCreateSubject,
}: {
  subjects: SubjectSummary[]; selectedIds: string[]; onSelectedChange: (ids: string[]) => void;
  priorities: Record<string, number>; onPrioritiesChange: (p: Record<string, number>) => void;
  onCreateSubject: (name: string) => Promise<void>;
}) {
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  function toggle(id: string) {
    onSelectedChange(
      selectedIds.includes(id) ? selectedIds.filter((s) => s !== id) : [...selectedIds, id]
    );
  }

  async function handleAdd() {
    if (!newName.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      await onCreateSubject(newName.trim());
      setNewName("");
      setShowAdd(false);
    } catch (e: any) {
      setCreateError(e.message ?? "Couldn't add that subject.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold">Subject Priorities</h2>
      <p className="text-sm text-slate-500">
        Star ratings below reflect your recent performance data. You can override the priority manually,
        but the AI will still weigh objective performance data alongside your input.
      </p>

      {subjects.length === 0 && (
        <p className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
          No subjects yet — add at least one below before generating a schedule.
        </p>
      )}

      {subjects.map((s) => (
        <div key={s.subject_id} className="flex items-center justify-between rounded border border-slate-200 p-3">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={selectedIds.includes(s.subject_id)} onChange={() => toggle(s.subject_id)} />
            <span className="font-medium">{s.name}</span>
            <span className="text-xs text-slate-500">
              {s.completed_topics} completed \u00b7 {s.incomplete_topics} remaining
              {s.performance_percent != null ? ` \u00b7 ${s.performance_percent}%` : ""}
            </span>
          </label>
          <select
            className="rounded border border-slate-300 px-2 py-1 text-sm"
            value={priorities[s.subject_id] ?? ""}
            onChange={(e) =>
              onPrioritiesChange({ ...priorities, [s.subject_id]: Number(e.target.value) })
            }
          >
            <option value="">AI-decided</option>
            {[1, 2, 3, 4, 5].map((p) => <option key={p} value={p}>Manual: {p}</option>)}
          </select>
        </div>
      ))}

      {!showAdd ? (
        <button
          type="button"
          className="rounded border border-dashed border-slate-300 px-4 py-2 text-sm text-slate-600 hover:border-slate-400"
          onClick={() => setShowAdd(true)}
        >
          + Add a subject
        </button>
      ) : (
        <div className="flex items-center gap-2 rounded border border-slate-200 p-3">
          <input
            autoFocus
            className="flex-1 rounded border border-slate-300 px-2 py-1.5 text-sm"
            placeholder="e.g. Financial Accounting"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          />
          <button
            type="button"
            className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            onClick={handleAdd}
            disabled={creating}
          >
            {creating ? "Adding\u2026" : "Add"}
          </button>
          <button
            type="button"
            className="text-sm text-slate-400 hover:underline"
            onClick={() => { setShowAdd(false); setNewName(""); }}
          >
            Cancel
          </button>
        </div>
      )}
      {createError && <p className="text-sm text-rose-600">{createError}</p>}
    </div>
  );
}

function ReviewStep({
  goal, preferences, availability, subjectCount, derivedDailyMinutes,
}: {
  goal: StudyGoal; preferences: StudyPreferences; availability: AvailabilityPeriod[];
  subjectCount: number; derivedDailyMinutes: number;
}) {
  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold">Review & Generate</h2>
      <ul className="space-y-1 text-sm text-slate-700">
        <li><strong>Goal:</strong> {goal.exam_goal_type} on {goal.exam_date || "\u2014"}</li>
        <li><strong>Session length:</strong> {preferences.session_duration_min}m × {preferences.max_sessions_per_day}/day
          {" "}(≈{Math.round((derivedDailyMinutes / 60) * 10) / 10}h/day)</li>
        <li><strong>Preferred time:</strong> {preferences.preferred_time.replace("_", " ")}</li>
        <li><strong>Break:</strong> {preferences.break_duration_min}m</li>
        <li><strong>Availability periods defined:</strong> {availability.length}</li>
        <li><strong>Subjects included:</strong> {subjectCount}</li>
      </ul>
      <p className="text-xs text-slate-500">
        Click "Generate Schedule" to have the AI build a prioritized learning plan, which a
        deterministic scheduler will then fit into your available time.
      </p>
    </div>
  );
}
