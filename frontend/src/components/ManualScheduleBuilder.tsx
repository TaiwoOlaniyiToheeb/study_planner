import React, { useEffect, useState } from "react";
import { StudySchedule, ActivityType } from "../types";
import { studyScheduleApi } from "../services/studyScheduleApi";

interface SubjectOption { id: string; name: string }
interface TopicOption { id: string; name: string }

interface DraftSession {
  subject_id: string;
  topic_id: string;
  activity_type: ActivityType;
  scheduled_date: string;
  start_time: string;
  duration_minutes: number;
}

const ACTIVITY_OPTIONS: ActivityType[] = ["learning", "practice", "revision", "assessment", "review"];

interface Props {
  onScheduleCreated: (schedule: StudySchedule) => void;
  onCancel: () => void;
}

export default function ManualScheduleBuilder({ onScheduleCreated, onCancel }: Props) {
  const [subjects, setSubjects] = useState<SubjectOption[]>([]);
  const [topicsBySubject, setTopicsBySubject] = useState<Record<string, TopicOption[]>>({});
  const [examDate, setExamDate] = useState("");
  const [sessions, setSessions] = useState<DraftSession[]>([]);
  const [draft, setDraft] = useState<DraftSession>({
    subject_id: "", topic_id: "", activity_type: "learning",
    scheduled_date: "", start_time: "17:00", duration_minutes: 60,
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [showNewSubject, setShowNewSubject] = useState(false);
  const [newSubjectName, setNewSubjectName] = useState("");
  const [creatingSubject, setCreatingSubject] = useState(false);
  const [showNewTopic, setShowNewTopic] = useState(false);
  const [newTopicName, setNewTopicName] = useState("");
  const [creatingTopic, setCreatingTopic] = useState(false);

  useEffect(() => {
    studyScheduleApi.listSubjects().then(setSubjects).catch(() => setSubjects([]));
  }, []);

  useEffect(() => {
    if (!draft.subject_id || topicsBySubject[draft.subject_id]) return;
    studyScheduleApi.listTopics(draft.subject_id).then((topics) =>
      setTopicsBySubject((prev) => ({ ...prev, [draft.subject_id]: topics }))
    );
  }, [draft.subject_id, topicsBySubject]);

  async function handleCreateSubject() {
    if (!newSubjectName.trim()) return;
    setCreatingSubject(true);
    setError(null);
    try {
      const created = await studyScheduleApi.createSubject(newSubjectName.trim());
      setSubjects((prev) => [...prev, created]);
      setDraft({ ...draft, subject_id: created.id, topic_id: "" });
      setNewSubjectName("");
      setShowNewSubject(false);
    } catch (e: any) {
      setError(e.message ?? "Couldn't create that subject.");
    } finally {
      setCreatingSubject(false);
    }
  }

  async function handleCreateTopic() {
    if (!newTopicName.trim() || !draft.subject_id) return;
    setCreatingTopic(true);
    setError(null);
    try {
      const created = await studyScheduleApi.createTopic(draft.subject_id, { name: newTopicName.trim() });
      setTopicsBySubject((prev) => ({
        ...prev,
        [draft.subject_id]: [...(prev[draft.subject_id] ?? []), created],
      }));
      setDraft({ ...draft, topic_id: created.id });
      setNewTopicName("");
      setShowNewTopic(false);
    } catch (e: any) {
      setError(e.message ?? "Couldn't create that topic.");
    } finally {
      setCreatingTopic(false);
    }
  }

  function addSession() {
    setError(null);
    if (!draft.subject_id || !draft.topic_id || !draft.scheduled_date) {
      setError("Pick a subject, topic, and date before adding a session.");
      return;
    }
    setSessions([...sessions, draft]);
    setDraft({ ...draft, topic_id: "" });
  }

  function removeSession(index: number) {
    setSessions(sessions.filter((_, i) => i !== index));
  }

  async function handleSubmit() {
    if (!examDate) { setError("Set your exam date first."); return; }
    if (sessions.length === 0) { setError("Add at least one session."); return; }
    setSubmitting(true);
    setError(null);
    try {
      const schedule = await studyScheduleApi.createManualSchedule({ exam_date: examDate, sessions });
      onScheduleCreated(schedule);
    } catch (e: any) {
      setError(e.message ?? "Couldn't create that schedule.");
    } finally {
      setSubmitting(false);
    }
  }

  const subjectName = (id: string) => subjects.find((s) => s.id === id)?.name ?? "?";
  const topicName = (subjectId: string, topicId: string) =>
    topicsBySubject[subjectId]?.find((t) => t.id === topicId)?.name ?? "?";

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-4">
      <div>
        <h2 className="text-lg font-semibold">Build Your Own Schedule</h2>
        <p className="mt-1 text-sm text-slate-500">
          No AI involved here — you choose every subject, topic, date, and time yourself. We'll still
          stop you from double-booking a slot or scheduling past your exam date.
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium">Exam Date</label>
        <input
          type="date"
          className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
          value={examDate}
          min={new Date().toISOString().slice(0, 10)}
          onChange={(e) => setExamDate(e.target.value)}
        />
      </div>

      <div className="space-y-3 rounded-lg border border-slate-200 p-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div className="space-y-1">
            <select
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              value={draft.subject_id}
              onChange={(e) => setDraft({ ...draft, subject_id: e.target.value, topic_id: "" })}
            >
              <option value="">Subject...</option>
              {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            {!showNewSubject ? (
              <button
                type="button"
                className="text-xs text-slate-500 hover:underline"
                onClick={() => setShowNewSubject(true)}
              >
                + Don't see your subject? Add it
              </button>
            ) : (
              <div className="flex gap-1">
                <input
                  autoFocus
                  className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1 text-xs"
                  placeholder="e.g. Organic Chemistry"
                  value={newSubjectName}
                  onChange={(e) => setNewSubjectName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreateSubject()}
                />
                <button
                  type="button"
                  className="rounded bg-slate-800 px-2 py-1 text-xs text-white disabled:opacity-50"
                  onClick={handleCreateSubject}
                  disabled={creatingSubject}
                >
                  Add
                </button>
                <button
                  type="button"
                  className="text-xs text-slate-400 hover:underline"
                  onClick={() => { setShowNewSubject(false); setNewSubjectName(""); }}
                >
                  Cancel
                </button>
              </div>
            )}
          </div>

          <div className="space-y-1">
            <select
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
              value={draft.topic_id}
              onChange={(e) => setDraft({ ...draft, topic_id: e.target.value })}
              disabled={!draft.subject_id}
            >
              <option value="">Topic...</option>
              {(topicsBySubject[draft.subject_id] ?? []).map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
            {draft.subject_id && (
              !showNewTopic ? (
                <button
                  type="button"
                  className="text-xs text-slate-500 hover:underline"
                  onClick={() => setShowNewTopic(true)}
                >
                  + Add a topic
                </button>
              ) : (
                <div className="flex gap-1">
                  <input
                    autoFocus
                    className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1 text-xs"
                    placeholder="e.g. Thermodynamics"
                    value={newTopicName}
                    onChange={(e) => setNewTopicName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleCreateTopic()}
                  />
                  <button
                    type="button"
                    className="rounded bg-slate-800 px-2 py-1 text-xs text-white disabled:opacity-50"
                    onClick={handleCreateTopic}
                    disabled={creatingTopic}
                  >
                    Add
                  </button>
                  <button
                    type="button"
                    className="text-xs text-slate-400 hover:underline"
                    onClick={() => { setShowNewTopic(false); setNewTopicName(""); }}
                  >
                    Cancel
                  </button>
                </div>
              )
            )}
          </div>

          <select
            className="rounded border border-slate-300 px-2 py-1.5 text-sm"
            value={draft.activity_type}
            onChange={(e) => setDraft({ ...draft, activity_type: e.target.value as ActivityType })}
          >
            {ACTIVITY_OPTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>

          <input
            type="date"
            className="rounded border border-slate-300 px-2 py-1.5 text-sm"
            value={draft.scheduled_date}
            min={new Date().toISOString().slice(0, 10)}
            onChange={(e) => setDraft({ ...draft, scheduled_date: e.target.value })}
          />
          <input
            type="time"
            className="rounded border border-slate-300 px-2 py-1.5 text-sm"
            value={draft.start_time}
            onChange={(e) => setDraft({ ...draft, start_time: e.target.value })}
          />
          <input
            type="number"
            min={15} max={180} step={15}
            className="rounded border border-slate-300 px-2 py-1.5 text-sm"
            value={draft.duration_minutes}
            onChange={(e) => setDraft({ ...draft, duration_minutes: Number(e.target.value) })}
          />
        </div>
        <button
          className="rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white"
          onClick={addSession}
        >
          + Add Session
        </button>
      </div>

      {sessions.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium text-slate-700">{sessions.length} session(s) added</p>
          <ul className="space-y-1">
            {sessions.map((s, i) => (
              <li key={i} className="flex items-center justify-between rounded border border-slate-200 p-2 text-sm">
                <span>
                  {s.scheduled_date} {s.start_time} ({s.duration_minutes}m) &mdash;{" "}
                  <strong>{subjectName(s.subject_id)}</strong> / {topicName(s.subject_id, s.topic_id)} / {s.activity_type}
                </span>
                <button className="text-xs text-rose-600 hover:underline" onClick={() => removeSession(i)}>
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {error && <p className="text-sm text-rose-600">{error}</p>}

      <div className="flex justify-between border-t border-slate-200 pt-4">
        <button className="text-sm text-slate-500 hover:underline" onClick={onCancel}>Cancel</button>
        <button
          className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          onClick={handleSubmit}
          disabled={submitting}
        >
          {submitting ? "Saving..." : "Create Schedule"}
        </button>
      </div>
    </div>
  );
}
