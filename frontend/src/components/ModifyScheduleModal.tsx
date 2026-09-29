import React, { useState } from "react";
import { ScheduledSession, ActivityType } from "../types";
import { studyScheduleApi } from "../services/studyScheduleApi";

interface Props {
  session: ScheduledSession;
  onClose: () => void;
  onModified: (updated: ScheduledSession) => void;
}

const ACTIVITY_OPTIONS: ActivityType[] = ["learning", "practice", "revision", "assessment", "review"];

export default function ModifyScheduleModal({ session, onClose, onModified }: Props) {
  const [date, setDate] = useState(session.scheduled_date);
  const [startTime, setStartTime] = useState(session.start_time);
  const [duration, setDuration] = useState(session.duration_minutes);
  const [activity, setActivity] = useState<ActivityType>(session.activity_type);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const updated = await studyScheduleApi.modifySession({
        session_id: session.id,
        new_date: date,
        new_start_time: startTime,
        new_activity_type: activity,
        new_duration_minutes: duration,
      });
      onModified(updated as ScheduledSession);
      onClose();
    } catch (e: any) {
      setError(e.message ?? "Couldn't save that change \u2014 it may overlap another session.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-sm space-y-3 rounded-lg bg-white p-5 shadow-xl">
        <h3 className="text-lg font-semibold">Modify Session</h3>
        <p className="text-sm text-slate-500">{session.subject_name} \u2014 {session.topic_name}</p>

        <label className="block text-sm font-medium">Date</label>
        <input type="date" className="w-full rounded border border-slate-300 px-2 py-1.5"
               value={date} onChange={(e) => setDate(e.target.value)} />

        <label className="block text-sm font-medium">Start time</label>
        <input type="time" className="w-full rounded border border-slate-300 px-2 py-1.5"
               value={startTime} onChange={(e) => setStartTime(e.target.value)} />

        <label className="block text-sm font-medium">Duration (minutes)</label>
        <input type="number" min={15} max={180} step={15}
               className="w-full rounded border border-slate-300 px-2 py-1.5"
               value={duration} onChange={(e) => setDuration(Number(e.target.value))} />

        <label className="block text-sm font-medium">Activity</label>
        <select className="w-full rounded border border-slate-300 px-2 py-1.5"
                value={activity} onChange={(e) => setActivity(e.target.value as ActivityType)}>
          {ACTIVITY_OPTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>

        {error && <p className="text-sm text-rose-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button className="rounded border border-slate-300 px-4 py-2 text-sm" onClick={onClose}>Cancel</button>
          <button
            className="rounded bg-slate-800 px-4 py-2 text-sm text-white disabled:opacity-50"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? "Saving\u2026" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
