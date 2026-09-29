from datetime import time, date

import pytest
from pydantic import ValidationError

from backend.schemas.schemas import AvailabilityPeriodIn, PeriodType
from backend.services.scheduler.slots import (
    AvailabilityWindow, generate_daily_free_windows, candidate_slots_for_range,
)


def test_valid_availability_period():
    p = AvailabilityPeriodIn(day_of_week=0, start_time=time(17, 0), end_time=time(21, 0),
                              period_type=PeriodType.free)
    assert p.start_time < p.end_time


def test_invalid_time_order_rejected():
    with pytest.raises(ValidationError):
        AvailabilityPeriodIn(day_of_week=0, start_time=time(21, 0), end_time=time(17, 0),
                              period_type=PeriodType.free)


def test_busy_subtracted_from_free():
    windows = [
        AvailabilityWindow(day_of_week=0, start_time=time(8, 0), end_time=time(16, 0), period_type="busy"),
        AvailabilityWindow(day_of_week=0, start_time=time(5, 0), end_time=time(21, 0), period_type="free"),
    ]
    result = generate_daily_free_windows(windows)
    # Free 05:00-21:00 minus busy 08:00-16:00 -> [05:00-08:00, 16:00-21:00]
    assert (time(5, 0), time(8, 0)) in result[0]
    assert (time(16, 0), time(21, 0)) in result[0]


def test_multiple_periods_per_day():
    windows = [
        AvailabilityWindow(day_of_week=1, start_time=time(4, 0), end_time=time(8, 0), period_type="free"),
        AvailabilityWindow(day_of_week=1, start_time=time(16, 0), end_time=time(20, 0), period_type="free"),
    ]
    result = generate_daily_free_windows(windows)
    assert len(result[1]) == 2


def test_day_with_no_free_periods_is_unavailable():
    windows = [AvailabilityWindow(day_of_week=2, start_time=time(8, 0), end_time=time(16, 0), period_type="busy")]
    result = generate_daily_free_windows(windows)
    assert result.get(2, []) == []


def test_candidate_slots_expand_over_date_range():
    windows = [AvailabilityWindow(day_of_week=0, start_time=time(17, 0), end_time=time(19, 0), period_type="free")]
    slots = candidate_slots_for_range(windows, date(2026, 1, 5), date(2026, 1, 18))  # two Mondays
    mondays = [s for s in slots if s.the_date.weekday() == 0]
    assert len(mondays) == 2
