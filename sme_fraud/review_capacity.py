"""Shared limits and local working-day calendar for review admissions."""
from dataclasses import dataclass
from datetime import date


UI_BUDGET_MINUTES = {5: 120, 10: 240}
CAPACITY_VERSION = 'review-capacity-v1'


def positive_int(value, field):
    if type(value) is not int or value <= 0:
        raise ValueError(f'{field} must be a positive integer')
    return value


def local_date(value, field='date'):
    if type(value) is date:
        return value
    if not isinstance(value, str):
        raise ValueError(f'{field} must be an ISO local date')
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f'{field} must be an ISO local date') from exc
    if result.isoformat() != value:
        raise ValueError(f'{field} must be an ISO local date')
    return result


@dataclass(frozen=True)
class ReviewCapacity:
    slots: int
    minutes: int

    def __post_init__(self):
        positive_int(self.slots, 'Review slots')
        positive_int(self.minutes, 'Review minutes')

    @classmethod
    def ui(cls, slots):
        positive_int(slots, 'Review slots')
        if slots not in UI_BUDGET_MINUTES:
            raise ValueError('Daily review budget must be 5 or 10')
        return cls(slots, UI_BUDGET_MINUTES[slots])

    def fits(self, used_slots, used_minutes, work_minutes):
        positive_int(work_minutes, 'Work minutes')
        return used_slots < self.slots and used_minutes + work_minutes <= self.minutes


@dataclass(frozen=True)
class ReviewCalendar:
    # Weekdays use datetime's Monday=0 ... Sunday=6. No national holidays inferred.
    working_weekdays: tuple = tuple(range(7))
    non_working_dates: tuple = ()

    def __post_init__(self):
        days = tuple(self.working_weekdays)
        if not days or any(type(day) is not int or not 0 <= day <= 6 for day in days):
            raise ValueError('Working weekdays must be a nonempty subset of 0..6')
        holidays = tuple(local_date(value, 'Non-working date') for value in self.non_working_dates)
        object.__setattr__(self, 'working_weekdays', tuple(sorted(set(days))))
        object.__setattr__(self, 'non_working_dates', tuple(sorted(set(holidays))))

    def is_working_day(self, day):
        day = local_date(day)
        return day.weekday() in self.working_weekdays and day not in self.non_working_dates

    def as_dict(self):
        return dict(working_weekdays=list(self.working_weekdays),
                    non_working_dates=[day.isoformat() for day in self.non_working_dates])


def workload_scenarios():
    """Historical research scenarios are explicit and distinct from UI limits."""
    return tuple((f'research_{slots}_cases_{minutes}_minutes', 'research', ReviewCapacity(slots, minutes))
                 for slots, minutes in ((1, 45), (3, 135), (5, 225))) + tuple(
        (f'ui_{slots}_cases_{minutes}_minutes', 'ui', ReviewCapacity.ui(slots))
        for slots, minutes in sorted(UI_BUDGET_MINUTES.items()))
