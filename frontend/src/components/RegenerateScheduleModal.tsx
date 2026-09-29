import React, { useState } from "react";
import { StudySchedule } from "../types";
import { studyScheduleApi } from "../services/studyScheduleApi";

interface Props {
  scheduleId: string;
  onClose: () => void;
  onRegenerated: (schedule: StudySchedule) => void;
}

const EXAMPLES = [
  "I want fewer sessions on weekdays.",
  "Move Mathematics to Saturday.",
  "I don't want to study after 8 PM.",
  "Give me more Physics.",
];

export default function RegenerateScheduleModal({ scheduleId, onClose, onRegenerated }: Props) {
  const [instruction, setInstruction] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    if (!instruction.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const schedule = await studyScheduleApi.regenerateWithInstruction(scheduleId, instruction.trim());
      onRegenerated(schedule);
      onClose();
    } catch (e: any) {
      setError(e.message ?? "Couldn't apply that change. Please try rephrasing it.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md space-y-4 rounded-lg bg-white p-5 shadow-xl">
        <h3 className="text-lg font-semibold">Regenerate Schedule</h3>
        <p className="text-sm text-slate-500">Describe the change you'd like in plain language.</p>
        <textarea
          className="w-full rounded border border-slate-300 p-2 text-sm"
          rows={3}
          placeholder={EXAMPLES[0]}
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
        />
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600 hover:bg-slate-200"
              onClick={() => setInstruction(ex)}
            >
              {ex}
            </button>
          ))}
        </div>
        {error && <p className="text-sm text-rose-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button className="rounded border border-slate-300 px-4 py-2 text-sm" onClick={onClose}>Cancel</button>
          <button
            className="rounded bg-slate-800 px-4 py-2 text-sm text-white disabled:opacity-50"
            onClick={handleSubmit}
            disabled={loading}
          >
            {loading ? "Applying\u2026" : "Apply"}
          </button>
        </div>
      </div>
    </div>
  );
}
