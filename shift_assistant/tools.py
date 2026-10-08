"""Tools the agent can call. Each tool is a plain Python function that returns JSON-friendly data.

The model never touches the CSVs directly: it asks for a tool, the code runs the
business rules, and the model explains the result. That keeps the numbers exact
and the rules (like "only close-trained staff can close") enforced in code.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from .data import DAYS, DEFAULT_SLOT_TIMES, Store, hours_between, normalise_day, normalise_slot


def get_roster(store: Store, day: str | None = None) -> dict[str, Any]:
    """Return the rostered shifts, for one day or the whole week."""
    days = [normalise_day(day)] if day else DAYS
    shifts = [
        {"day": s.day, "slot": s.slot, "name": s.name, "start": s.start, "end": s.end, "hours": s.hours}
        for s in store.roster
        if s.day in days
    ]
    return {"days": days, "shifts": shifts}


def check_assignment(store: Store, name: str, day: str, slot: str) -> dict[str, Any]:
    """Check whether a person can be rostered on a slot, using the same rules a manager checks."""
    day, slot = normalise_day(day), normalise_slot(slot)
    try:
        person = store.person(name)
    except KeyError as exc:
        return {"allowed": False, "reasons": [str(exc)]}
    start, end = DEFAULT_SLOT_TIMES[slot]
    reasons = []
    if slot == "close" and not person.can_close:
        reasons.append(f"{person.name} cannot close (not close-trained)")
    if slot == "open" and not person.can_open:
        reasons.append(f"{person.name} cannot open (not open-trained)")
    if day not in person.available_days:
        reasons.append(f"{person.name} is not available on {day}")
    if any(s.day == day for s in store.shifts_for(person.name)):
        reasons.append(f"{person.name} is already rostered on {day}")
    new_total = store.weekly_hours(person.name) + hours_between(start, end)
    if new_total > person.max_hours:
        reasons.append(
            f"{person.name} would reach {new_total:g} hours this week (max {person.max_hours:g})"
        )
    return {"name": person.name, "day": day, "slot": slot, "allowed": not reasons, "reasons": reasons}


def find_cover(store: Store, day: str, slot: str = "close") -> dict[str, Any]:
    """Find who could cover a slot on a day, best options first (fewest hours this week)."""
    day, slot = normalise_day(day), normalise_slot(slot)
    candidates, excluded = [], []
    for person in store.staff.values():
        result = check_assignment(store, person.name, day, slot)
        if result["allowed"]:
            candidates.append(
                {"name": person.name, "role": person.role, "hours_this_week": store.weekly_hours(person.name)}
            )
        else:
            excluded.append({"name": person.name, "reasons": result["reasons"]})
    candidates.sort(key=lambda c: c["hours_this_week"])
    current = [s.name for s in store.roster if s.day == day and s.slot == slot]
    return {"day": day, "slot": slot, "currently_rostered": current, "candidates": candidates, "excluded": excluded}


def estimate_labour_cost(store: Store, day: str | None = None, on_cost_percent: float = 0.0) -> dict[str, Any]:
    """Estimate labour cost from rostered hours x each person's base hourly rate.

    on_cost_percent lets a manager add a flat percentage (e.g. super). Penalty rates
    and award rules are NOT modelled; this is a base-rate estimate only.
    """
    days = [normalise_day(day)] if day else DAYS
    by_day: dict[str, float] = {d: 0.0 for d in days}
    hours_by_day: dict[str, float] = {d: 0.0 for d in days}
    for s in store.roster:
        if s.day in by_day:
            rate = store.person(s.name).hourly_rate
            by_day[s.day] += s.hours * rate
            hours_by_day[s.day] += s.hours
    multiplier = 1 + max(on_cost_percent, 0.0) / 100
    per_day = [
        {"day": d, "hours": round(hours_by_day[d], 2), "cost": round(by_day[d] * multiplier, 2)} for d in days
    ]
    return {
        "per_day": per_day,
        "total_hours": round(sum(hours_by_day.values()), 2),
        "total_cost": round(sum(by_day.values()) * multiplier, 2),
        "on_cost_percent": on_cost_percent,
        "note": "Base hourly rates from the staff CSV only; penalty rates and award rules are not included.",
    }


def staff_hours(store: Store) -> dict[str, Any]:
    """Weekly rostered hours for each person against their maximum."""
    rows = []
    for person in store.staff.values():
        hours = store.weekly_hours(person.name)
        rows.append(
            {"name": person.name, "hours": hours, "max_hours": person.max_hours, "remaining": round(person.max_hours - hours, 2)}
        )
    return {"staff": rows}


# --- Tool schemas sent to the model (OpenAI / Azure OpenAI function-calling format) ---

_DAY = {"type": "string", "description": "Day of the week, e.g. 'Sat' or 'Saturday'"}
_SLOT = {"type": "string", "enum": ["open", "lunch", "close"], "description": "Shift slot"}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_roster",
            "description": "Get the rostered shifts for one day, or the whole week if no day is given.",
            "parameters": {"type": "object", "properties": {"day": _DAY}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_cover",
            "description": "Find staff who can cover a slot on a given day. Applies training, availability, double-booking and max-hours rules.",
            "parameters": {"type": "object", "properties": {"day": _DAY, "slot": _SLOT}, "required": ["day"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_assignment",
            "description": "Check whether a named person can be rostered on a slot, and why not if they can't.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "day": _DAY, "slot": _SLOT},
                "required": ["name", "day", "slot"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_labour_cost",
            "description": "Estimate labour cost (base hourly rates x rostered hours) for a day or the whole week.",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": _DAY,
                    "on_cost_percent": {"type": "number", "description": "Optional flat on-cost percentage, e.g. 12 for super"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "staff_hours",
            "description": "Weekly rostered hours for every staff member compared with their maximum hours.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

_REGISTRY: dict[str, Callable[..., dict[str, Any]]] = {
    "get_roster": get_roster,
    "find_cover": find_cover,
    "check_assignment": check_assignment,
    "estimate_labour_cost": estimate_labour_cost,
    "staff_hours": staff_hours,
}


def run_tool(store: Store, name: str, arguments: str | dict | None) -> str:
    """Run a tool by name with JSON arguments from the model. Always returns a JSON string.

    Errors are returned to the model as {"error": ...} instead of crashing the agent,
    so it can correct itself (e.g. a misspelt day).
    """
    func = _REGISTRY.get(name)
    if func is None:
        return json.dumps({"error": f"Unknown tool '{name}'"})
    try:
        args = json.loads(arguments) if isinstance(arguments, str) and arguments.strip() else (arguments or {})
        if not isinstance(args, dict):
            raise ValueError("Tool arguments must be a JSON object")
        return json.dumps(func(store, **args))
    except (ValueError, TypeError, KeyError) as exc:
        return json.dumps({"error": str(exc)})
