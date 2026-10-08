"""Offline tests for the business rules behind each tool (sample data, no Azure)."""
import json
from pathlib import Path

import pytest

from shift_assistant.data import hours_between, load_store, normalise_day
from shift_assistant.tools import check_assignment, estimate_labour_cost, find_cover, run_tool, staff_hours

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def store():
    return load_store(DATA / "staff.csv", DATA / "roster.csv")


def test_normalise_day_accepts_full_names():
    assert normalise_day("saturday") == "Sat"
    assert normalise_day("TUE") == "Tue"
    with pytest.raises(ValueError):
        normalise_day("Funday")


def test_hours_between_handles_midnight():
    assert hours_between("16:00", "23:00") == 7
    assert hours_between("18:00", "01:00") == 7


def test_close_rule_refuses_staff_who_cannot_close(store):
    result = check_assignment(store, "Sam", "Wed", "close")
    assert result["allowed"] is False
    assert any("cannot close" in r for r in result["reasons"])


def test_check_assignment_flags_double_booking_and_availability(store):
    result = check_assignment(store, "Mia", "Mon", "lunch")
    assert result["allowed"] is False
    assert any("not available" in r for r in result["reasons"])
    result = check_assignment(store, "Alex", "Mon", "close")
    assert any("already rostered" in r for r in result["reasons"])


def test_find_cover_only_returns_eligible_close_trained_staff(store):
    result = find_cover(store, "Saturday", "close")
    names = [c["name"] for c in result["candidates"]]
    assert result["currently_rostered"] == ["Jordan"]
    # Priya and Mia are already on Sat, Alex isn't available, Sam/Mia/Chloe can't close.
    # Leo fits exactly at his 30-hour max; Noah has the fewest hours so comes first.
    assert names == ["Noah", "Leo"]
    for c in result["candidates"]:
        assert store.person(c["name"]).can_close
    excluded = {e["name"]: e["reasons"] for e in result["excluded"]}
    assert any("cannot close" in r for r in excluded["Mia"])


def test_find_cover_sorts_by_fewest_hours(store):
    result = find_cover(store, "Thu", "lunch")
    hours = [c["hours_this_week"] for c in result["candidates"]]
    assert hours == sorted(hours)


def test_labour_cost_matches_manual_calculation(store):
    result = estimate_labour_cost(store, "Mon")
    # Alex 8h x 34.50 + Chloe 4h x 29.10 + Leo 7h x 28.20
    expected = 8 * 34.50 + 4 * 29.10 + 7 * 28.20
    assert result["total_cost"] == pytest.approx(expected)
    assert result["total_hours"] == 19


def test_labour_cost_on_cost_percent(store):
    base = estimate_labour_cost(store)["total_cost"]
    with_super = estimate_labour_cost(store, on_cost_percent=10)["total_cost"]
    assert with_super == pytest.approx(base * 1.10, rel=1e-4)


def test_staff_hours_remaining(store):
    rows = {r["name"]: r for r in staff_hours(store)["staff"]}
    assert rows["Sam"]["hours"] == 16
    assert rows["Sam"]["remaining"] == 14


def test_run_tool_returns_errors_as_json(store):
    assert "error" in json.loads(run_tool(store, "no_such_tool", "{}"))
    assert "error" in json.loads(run_tool(store, "find_cover", '{"day": "Funday"}'))
    assert "error" in json.loads(run_tool(store, "find_cover", "not json"))
    ok = json.loads(run_tool(store, "get_roster", '{"day": "Sun"}'))
    assert len(ok["shifts"]) == 3


def test_max_hours_rule(store):
    # Leo has 23h rostered with a 30h max: a 7h close fits, an 8h open doesn't.
    assert check_assignment(store, "Leo", "Sat", "close")["allowed"] is True
    result = check_assignment(store, "Leo", "Sat", "open")
    assert result["allowed"] is False
    assert any("max 30" in r for r in result["reasons"])
