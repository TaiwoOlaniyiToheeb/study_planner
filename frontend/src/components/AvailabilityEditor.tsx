import React, { useState } from "react";
import { AvailabilityPeriod, DAY_LABELS, PeriodType } from "../types";

const BUSY_LABELS = ["School", "Work", "Religious activity", "Family responsibility", "Sports", "Other"];

interface Props {
  periods: AvailabilityPeriod[];
  onChange: (periods: AvailabilityPeriod[]) => void;
}

function overlaps(a: AvailabilityPeriod, b: AvailabilityPeriod): boolean {
  return (
    a.day_of_week === b.day_of_week &&
    a.period_type === b.period_type &&
    a.start_time < b.end_time &&
    b.start_time < a.end_time
  );
}

export default function AvailabilityEditor({ periods, onChange }: Props) {
  const [draft, setDraft] = useState<AvailabilityPeriod>({
    day_of_week: 0, start_time: "17:00", end_time: "19:00", period_type: "free",
  });
  const [error, setError] = useState<string | null>(null);

  function addPeriod(type: PeriodType) {
    setError(null);
    const candidate = { ...draft, period_type: type };

    if (candidate.start_time >= candidate.end_time) {
      setError("Start time must be before end time.");
      return;
    }
    const conflict = periods.find((p) => overlaps(p, candidate));
    if (conflict) {
      setError(
        `This overlaps an existing ${conflict.period_type} period ` +
          `(${conflict.start_time}–${conflict.end_time}) on ${DAY_LABELS[conflict.day_of_week]}.`
      );
      return;
    }
    onChange([...periods, candidate]);
  }

  function removePeriod(index: number) {
    onChange(periods.filter((_, i) => i !== index));
  }

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-slate-200 p-4 space-y-3">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <select
            className="rounded border border-slate-300 px-2 py-1.5"
            value={draft.day_of_week}
            onChange={(e) => setDraft({ ...draft, day_of_week: Number(e.target.value) })}
          >
            {DAY_LABELS.map((label, i) => (
              <option key={label} value={i}>{label}</option>
            ))}
          </select>
          <input
            type="time"
            className="rounded border border-slate-300 px-2 py-1.5"
            value={draft.start_time}
            onChange={(e) => setDraft({ ...draft, start_time: e.target.value })}
          />
          <input
            type="time"
            className="rounded border border-slate-300 px-2 py-1.5"
            value={draft.end_time}
            onChange={(e) => setDraft({ ...draft, end_time: e.target.value })}
          />
          <select
            className="rounded border border-slate-300 px-2 py-1.5"
            value={draft.label ?? ""}
            onChange={(e) => setDraft({ ...draft, label: e.target.value || undefined })}
          >
            <option value="">Label (optional)</option>
            {BUSY_LABELS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>

        <div className="flex gap-3">
          <button
            className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
            onClick={() => addPeriod("free")}
          >
            + Add Available Period
          </button>
          <button
            className="rounded bg-slate-600 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
            onClick={() => addPeriod("busy")}
          >
            + Add Busy Period
          </button>
        </div>
        {error && <p className="text-sm text-rose-600">{error}</p>}
      </div>

      <div className="space-y-2">
        {DAY_LABELS.map((label, day) => {
          const dayPeriods = periods.filter((p) => p.day_of_week === day);
          if (dayPeriods.length === 0) return null;
          return (
            <div key={label} className="rounded-lg border border-slate-200 p-3">
              <p className="font-medium text-slate-700">{label}</p>
              <ul className="mt-1 space-y-1">
                {dayPeriods.map((p) => {
                  const globalIndex = periods.indexOf(p);
                  return (
                    <li key={globalIndex} className="flex items-center justify-between text-sm">
                      <span>
                        {p.start_time}–{p.end_time} →{" "}
                        <span className={p.period_type === "free" ? "text-emerald-700" : "text-slate-500"}>
                          {p.period_type === "free" ? "Free" : `Busy${p.label ? ` (${p.label})` : ""}`}
                        </span>
                      </span>
                      <button
                        className="text-xs text-rose-600 hover:underline"
                        onClick={() => removePeriod(globalIndex)}
                      >
                        Remove
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
    </div>
  );
}
