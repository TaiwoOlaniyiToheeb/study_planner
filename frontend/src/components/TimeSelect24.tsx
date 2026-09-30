import React from "react";

interface Props {
  value: string; // "HH:MM"
  onChange: (value: string) => void;
  /** Exclude 00 from the hour options — use for end-time pickers so a
   * period can never be set to end at midnight (00:00), which is always
   * numerically "before" any same-day start time and produces a confusing
   * "start time must be before end time" error. For an overnight period,
   * users add a second period starting at 00:00 the next day instead. */
  excludeMidnightHour?: boolean;
  className?: string;
}

const MINUTES = ["00", "15", "30", "45"];

/**
 * Two plain <select> dropdowns (hour 00–23, minute :00/:15/:30/:45) instead
 * of a native <input type="time">. Native time inputs render in 12-hour
 * AM/PM or 24-hour format depending on the browser's OS locale settings —
 * not something we can reliably control from code — which is what was
 * causing the confusing "9pm to 12am" entry to misbehave. This component
 * is always unambiguous 24-hour time, on every browser and OS.
 */
export default function TimeSelect24({ value, onChange, excludeMidnightHour, className }: Props) {
  const [hh, mm] = value.split(":");
  const hourOptions = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, "0")).filter(
    (h) => !(excludeMidnightHour && h === "00")
  );

  return (
    <div className={`flex items-center gap-1 ${className ?? ""}`}>
      <select
        className="rounded border border-slate-300 px-1.5 py-1.5 text-sm"
        value={hh}
        onChange={(e) => onChange(`${e.target.value}:${mm}`)}
        aria-label="Hour (24-hour)"
      >
        {hourOptions.map((h) => <option key={h} value={h}>{h}</option>)}
      </select>
      <span className="text-slate-400">:</span>
      <select
        className="rounded border border-slate-300 px-1.5 py-1.5 text-sm"
        value={mm}
        onChange={(e) => onChange(`${hh}:${e.target.value}`)}
        aria-label="Minute"
      >
        {MINUTES.map((m) => <option key={m} value={m}>{m}</option>)}
      </select>
    </div>
  );
}
