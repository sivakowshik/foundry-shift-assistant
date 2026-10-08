"""Run the agent's tools directly on the sample data. No Azure account or keys needed.

Usage:
    python offline_demo.py
"""
from __future__ import annotations

import json

from shift_assistant.config import data_paths
from shift_assistant.data import load_store
from shift_assistant.tools import run_tool


def show(title: str, tool: str, args: dict) -> None:
    print(f"\n=== {title} ===\n{tool}({json.dumps(args)})")
    print(json.dumps(json.loads(run_tool(STORE, tool, args)), indent=2))


STORE = load_store(*data_paths())

if __name__ == "__main__":
    show("Who can cover Saturday's close?", "find_cover", {"day": "Saturday", "slot": "close"})
    show("Can Sam close on Wednesday?", "check_assignment", {"name": "Sam", "day": "Wed", "slot": "close"})
    show("Labour cost estimate for the week", "estimate_labour_cost", {})
    show("Hours per person", "staff_hours", {})
