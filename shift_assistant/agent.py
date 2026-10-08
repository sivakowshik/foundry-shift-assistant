"""The agent loop: send the question and tool schemas to the model, run any tools
it asks for, send the results back, and repeat until it gives a final answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .data import Store
from .tools import TOOL_SCHEMAS, run_tool

SYSTEM_PROMPT = """You are a shift assistant for a restaurant manager.
Use the tools to look up the roster, staff rules and costs. Never guess names,
hours or dollar amounts: every fact in your answer must come from a tool result.
Only close-trained staff may work a close shift. If a tool returns an error, fix
the arguments and try again, or explain what is missing. Keep answers short and
practical, and mention that labour costs are base-rate estimates when you give them."""


@dataclass
class ToolCallRecord:
    name: str
    arguments: str
    result: str


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    steps: int = 0


def _assistant_message(message: Any) -> dict[str, Any]:
    """Turn the SDK's message object into a plain dict we can send back next turn."""
    out: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    if getattr(message, "tool_calls", None):
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in message.tool_calls
        ]
    return out


def run_agent(question: str, client: Any, deployment: str, store: Store, max_steps: int = 6) -> AgentResult:
    """Answer a question with tool calling.

    `client` is an OpenAI-compatible client (Azure OpenAI v1 endpoint in production,
    a fake in the tests). `deployment` is the chat model deployment name.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    records: list[ToolCallRecord] = []
    for step in range(1, max_steps + 1):
        response = client.chat.completions.create(
            model=deployment,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0,
        )
        message = response.choices[0].message
        messages.append(_assistant_message(message))
        if not getattr(message, "tool_calls", None):
            return AgentResult(answer=(message.content or "").strip(), tool_calls=records, steps=step)
        for tc in message.tool_calls:
            result = run_tool(store, tc.function.name, tc.function.arguments)
            records.append(ToolCallRecord(tc.function.name, tc.function.arguments, result))
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    return AgentResult(
        answer="I couldn't finish that within the step limit. Try a more specific question.",
        tool_calls=records,
        steps=max_steps,
    )
