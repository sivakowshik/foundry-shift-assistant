"""Ask the shift assistant a question (needs Azure OpenAI settings in .env).

Usage:
    python ask.py "Who can cover the close on Saturday?"
    python ask.py --show-tools "What will labour cost this week?"
    python ask.py                 # interactive mode
"""
from __future__ import annotations

import argparse

from shift_assistant.agent import run_agent
from shift_assistant.config import get_settings, make_client
from shift_assistant.data import load_store


def main() -> None:
    parser = argparse.ArgumentParser(description="Hospitality shift assistant (Azure OpenAI tool calling)")
    parser.add_argument("question", nargs="*", help="Your question")
    parser.add_argument("--show-tools", action="store_true", help="Print each tool call and its result")
    args = parser.parse_args()

    s = get_settings()
    client = make_client(s)
    store = load_store(s.staff_csv, s.roster_csv)

    def answer(q: str) -> None:
        result = run_agent(q, client, s.deployment, store)
        if args.show_tools:
            for call in result.tool_calls:
                print(f"  -> {call.name}({call.arguments})\n     {call.result[:300]}")
        print(f"\n{result.answer}\n")

    if args.question:
        answer(" ".join(args.question))
        return
    print("Shift assistant. Type a question, or 'quit' to exit.")
    while True:
        q = input("> ").strip()
        if q.lower() in {"quit", "exit", "q"}:
            break
        if q:
            answer(q)


if __name__ == "__main__":
    main()
