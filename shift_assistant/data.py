"""Load the staff list and weekly roster from CSV files.

Pure Python (standard library only), so it can be tested offline.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SLOTS = ["open", "lunch", "close"]
DEFAULT_SLOT_TIMES = {"open": ("07:00", "15:00"), "lunch": ("11:00", "15:00"), "close": ("16:00", "23:00")}


def normalise_day(value: str) -> str:
    """Accept 'saturday', 'Sat', 'SAT' etc. and return the 3-letter form used in the CSVs."""
    key = (value or "").strip()[:3].title()
    if key not in DAYS:
        raise ValueError(f"Unknown day '{value}'. Use one of: {', '.join(DAYS)}")
    return key


def normalise_slot(value: str) -> str:
    key = (value or "").strip().lower()
    if key not in SLOTS:
        raise ValueError(f"Unknown slot '{value}'. Use one of: {', '.join(SLOTS)}")
    return key


def _yes(value: str) -> bool:
    return (value or "").strip().lower() in {"yes", "y", "true", "1"}


def hours_between(start: str, end: str) -> float:
    sh, sm = (int(x) for x in start.split(":"))
    eh, em = (int(x) for x in end.split(":"))
    minutes = (eh * 60 + em) - (sh * 60 + sm)
    if minutes <= 0:  # shift finishes after midnight
        minutes += 24 * 60
    return round(minutes / 60, 2)


@dataclass(frozen=True)
class Staff:
    name: str
    role: str
    hourly_rate: float
    can_open: bool
    can_close: bool
    available_days: tuple[str, ...]
    max_hours: float


@dataclass(frozen=True)
class Shift:
    day: str
    slot: str
    name: str
    start: str
    end: str

    @property
    def hours(self) -> float:
        return hours_between(self.start, self.end)


@dataclass
class Store:
    staff: dict[str, Staff]
    roster: list[Shift]

    def person(self, name: str) -> Staff:
        for key, member in self.staff.items():
            if key.lower() == (name or "").strip().lower():
                return member
        raise KeyError(f"No staff member called '{name}'")

    def shifts_for(self, name: str) -> list[Shift]:
        return [s for s in self.roster if s.name.lower() == name.lower()]

    def weekly_hours(self, name: str) -> float:
        return round(sum(s.hours for s in self.shifts_for(name)), 2)


def load_staff(path: Path) -> dict[str, Staff]:
    with open(path, newline="", encoding="utf-8") as f:
        staff = {}
        for row in csv.DictReader(f):
            staff[row["name"].strip()] = Staff(
                name=row["name"].strip(),
                role=row["role"].strip(),
                hourly_rate=float(row["hourly_rate"]),
                can_open=_yes(row["can_open"]),
                can_close=_yes(row["can_close"]),
                available_days=tuple(normalise_day(d) for d in row["available_days"].split(";") if d.strip()),
                max_hours=float(row["max_hours"]),
            )
    return staff


def load_roster(path: Path) -> list[Shift]:
    with open(path, newline="", encoding="utf-8") as f:
        return [
            Shift(
                day=normalise_day(row["day"]),
                slot=normalise_slot(row["slot"]),
                name=row["name"].strip(),
                start=row["start"].strip(),
                end=row["end"].strip(),
            )
            for row in csv.DictReader(f)
        ]


def load_store(staff_csv: Path, roster_csv: Path) -> Store:
    return Store(staff=load_staff(Path(staff_csv)), roster=load_roster(Path(roster_csv)))
