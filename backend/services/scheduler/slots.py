"""
Turns weekly availability (busy/free periods per day-of-week) into concrete
candidate time slots for a date range. Pure, deterministic, no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta, datetime
from typing import Iterable


@dataclass(frozen=True)
class AvailabilityWindow:
    day_of_week: int         # 0=Monday .. 6=Sunday
    start_time: time
    end_time: time
    period_type: str         # 'busy' | 'free'


@dataclass(frozen=True)
class Slot:
    the_date: date
    start_time: time
    end_time: time

    @property
    def minutes(self) -> int:
        start = datetime.combine(self.the_date, self.start_time)
        end = datetime.combine(self.the_date, self.end_time)
        return int((end - start).total_seconds() // 60)


def _subtract_busy(free_start: time, free_end: time, busy_periods: list[tuple[time, time]]) -> list[tuple[time, time]]:
    """Subtract overlapping busy windows from one free window; returns remaining sub-windows."""
    segments = [(free_start, free_end)]
    for b_start, b_end in busy_periods:
        new_segments = []
        for s, e in segments:
            if b_end <= s or b_start >= e:
                new_segments.append((s, e))  # no overlap
                continue
            if b_start > s:
                new_segments.append((s, b_start))
            if b_end < e:
                new_segments.append((b_end, e))
        segments = new_segments
    return segments


def generate_daily_free_windows(
    availability: list[AvailabilityWindow],
) -> dict[int, list[tuple[time, time]]]:
    """
    Returns, per day_of_week, the list of truly-free (start,end) windows after
    subtracting busy periods from declared free periods. If a day has no
    explicit 'free' periods, it is treated as fully unavailable (explicit
    opt-in model, per spec: students declare availability, not the inverse).
    """
    by_day_free: dict[int, list[tuple[time, time]]] = {}
    by_day_busy: dict[int, list[tuple[time, time]]] = {}
    for w in availability:
        target = by_day_free if w.period_type == "free" else by_day_busy
        target.setdefault(w.day_of_week, []).append((w.start_time, w.end_time))

    result: dict[int, list[tuple[time, time]]] = {}
    for day, free_windows in by_day_free.items():
        busy_windows = by_day_busy.get(day, [])
        merged: list[tuple[time, time]] = []
        for f_start, f_end in free_windows:
            merged.extend(_subtract_busy(f_start, f_end, busy_windows))
        # keep only windows with positive duration
        result[day] = [(s, e) for s, e in merged if s < e]
    return result


def candidate_slots_for_range(
    availability: list[AvailabilityWindow],
    start_date: date,
    end_date: date,
) -> list[Slot]:
    """
    Expands weekly free windows into a flat list of dated Slot objects
    covering [start_date, end_date] inclusive. These are raw free windows —
    the scheduling engine still needs to pack sessions (+breaks) into them
    and respect max-sessions-per-day.
    """
    free_by_day = generate_daily_free_windows(availability)
    slots: list[Slot] = []
    current = start_date
    while current <= end_date:
        dow = current.weekday()  # Monday=0
        for w_start, w_end in free_by_day.get(dow, []):
            slots.append(Slot(the_date=current, start_time=w_start, end_time=w_end))
        current += timedelta(days=1)
    return slots
