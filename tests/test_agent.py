"""Offline test of the agent loop with a fake (mocked) LLM client. No Azure calls are made."""
import json
from pathlib import Path
from types import SimpleNamespace

from shift_assistant.agent import run_agent
from shift_assistant.data import load_store
from shift_assistant.tools import TOOL_SCHEMAS

DATA = Path(__file__).resolve().parents[1] / "data"


def _tool_call(call_id, name, args):
    return SimpleNamespace(id=call_id, type="function", function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def _reply(content=None, tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))])


class FakeClient:
    """Replays scripted model replies and records every request."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs["messages"])))
        self.last_kwargs = kwargs
        return self.replies.pop(0)


def store():
    return load_store(DATA / "staff.csv", DATA / "roster.csv")


def test_agent_calls_tool_then_answers_from_result():
    client = FakeClient([
        _reply(tool_calls=[_tool_call("call_1", "find_cover", {"day": "Sat", "slot": "close"})]),
        _reply(content="Noah can cover Saturday's close."),
    ])
    result = run_agent("Who can cover the close on Saturday?", client, "gpt-4o-mini", store())

    assert result.answer == "Noah can cover Saturday's close."
    assert result.steps == 2
    assert [c.name for c in result.tool_calls] == ["find_cover"]
    assert client.last_kwargs["tools"] == TOOL_SCHEMAS
    assert client.last_kwargs["model"] == "gpt-4o-mini"

    # The second request must contain the assistant tool call and the real tool output.
    second = client.requests[1]
    assert second[2]["tool_calls"][0]["function"]["name"] == "find_cover"
    tool_msg = second[3]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "call_1"
    names = [c["name"] for c in json.loads(tool_msg["content"])["candidates"]]
    assert names == ["Noah", "Leo"]


def test_agent_handles_parallel_tool_calls():
    client = FakeClient([
        _reply(tool_calls=[
            _tool_call("a", "estimate_labour_cost", {"day": "Mon"}),
            _tool_call("b", "check_assignment", {"name": "Sam", "day": "Wed", "slot": "close"}),
        ]),
        _reply(content="Done."),
    ])
    result = run_agent("Monday cost, and can Sam close Wednesday?", client, "dep", store())
    assert len(result.tool_calls) == 2
    check = json.loads(result.tool_calls[1].result)
    assert check["allowed"] is False


def test_agent_passes_tool_errors_back_to_the_model():
    client = FakeClient([
        _reply(tool_calls=[_tool_call("x", "find_cover", {"day": "Funday"})]),
        _reply(content="Which day did you mean?"),
    ])
    result = run_agent("Who can close on Funday?", client, "dep", store())
    assert "error" in json.loads(result.tool_calls[0].result)
    assert result.answer == "Which day did you mean?"


def test_agent_stops_at_step_limit():
    looping = [_reply(tool_calls=[_tool_call(f"c{i}", "staff_hours", {})]) for i in range(3)]
    result = run_agent("loop", FakeClient(looping), "dep", store(), max_steps=3)
    assert result.steps == 3
    assert "step limit" in result.answer
