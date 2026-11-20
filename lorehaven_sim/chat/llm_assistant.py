"""Anthropic assistant. Numbers come from simulate(); this module does not compute them."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from chat.limits import AiSettings
from chat.policy import promo_grid_sentence
from chat.prompt import build_messages, build_system_prompt
from chat.status import log_api_error
from sim.constants import LIST_GROUP_TYPES
from sim.model import Scenario, promo_bounds, simulate

MAX_TOOL_ROUNDS = 2
_ASSUMPTION = "Untested straight-line assumption, not a finding."
_NOT_SCORED = "That promo was not scored."

SIMULATE_TOOL = {
    "name": "simulate",
    "description": (
        "Score one list price or one promo with the simulator and return its saved result. "
        "Omit promo_dollar to score the list price. "
        "Do not use this tool to invent a best promo; quote that from the analysis. "
        "There is no horizon argument. Later seasons are not estimated."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "list_price": {"type": "number", "description": "List price in dollars."},
            "promo_dollar": {
                "type": "number",
                "description": "Promo dollar. Omit it to score the list price.",
            },
            "group": {"type": "string", "enum": list(LIST_GROUP_TYPES)},
        },
        "required": ["list_price", "group"],
    },
}


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class Turn:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class Outcome:
    ok: bool
    text: str
    scenario: Scenario | None


def load_analysis() -> str:
    """The written analysis. This file is a copy of the pricing summary."""
    path = Path(__file__).resolve().parents[1] / "knowledge" / "analysis.md"
    return path.read_text()


def execute_simulate(arguments: dict) -> tuple[str, Scenario | None]:
    """Run one tool call. A ValueError comes back as text and does not score a price."""
    try:
        list_price = float(arguments["list_price"])
        group = str(arguments["group"])
    except (KeyError, TypeError, ValueError):
        return "The simulator could not read those inputs.", None
    promo = arguments.get("promo_dollar", None)
    if promo is not None:
        try:
            promo = float(promo)
        except (TypeError, ValueError):
            return "The simulator could not read those inputs.", None
    mode = "list" if promo is None else "promo"
    if mode == "promo" and _outside_promo_grid(list_price, promo):
        return f"{promo_grid_sentence(list_price)} {_NOT_SCORED}", None
    scenario = Scenario(list_price, promo, group, 0, mode)
    try:
        result = simulate(scenario)
    except ValueError as exc:
        return str(exc), None
    body = json.dumps(asdict(result))
    if mode == "list" and _between_observed(list_price):
        body = f"{_ASSUMPTION} {body}"
    return body, scenario


def ask_ai(
    *,
    message: str,
    history: list[dict],
    analysis: str,
    client,
    settings: AiSettings,
    on_text: Callable[[str], None],
    session,
    daily,
    day,
) -> Outcome:
    """Count the daily attempt when the call starts, and the session question only on success."""
    daily.record_attempt(day)
    outcome = run_question(
        message=message,
        history=history,
        analysis=analysis,
        client=client,
        settings=settings,
        on_text=on_text,
    )
    if outcome.ok:
        session.record_success()
    return outcome


def run_question(
    *,
    message: str,
    history: list[dict],
    analysis: str,
    client,
    settings: AiSettings,
    on_text: Callable[[str], None],
) -> Outcome:
    """One user question. Tool rounds are capped. An API error returns ok=False and no text."""
    messages = build_messages(history, message, settings)
    scenario = None
    try:
        for round_index in range(MAX_TOOL_ROUNDS + 1):
            include_tools = round_index < MAX_TOOL_ROUNDS
            payload = _payload(analysis, messages, settings, include_tools=include_tools)
            turn = client.round(payload, on_text)
            if turn.tool_calls and include_tools:
                scenario = _apply_tools(messages, turn, scenario)
                continue
            if not getattr(client, "emits_text", False) and turn.text:
                on_text(turn.text)
            return Outcome(True, turn.text, scenario)
        return Outcome(True, "", scenario)
    except Exception as exc:
        log_api_error(exc)
        return Outcome(False, "", None)


def _apply_tools(messages: list[dict], turn: Turn, scenario: Scenario | None) -> Scenario | None:
    results = []
    for call in turn.tool_calls:
        if call.name != "simulate":
            results.append("That tool is not available.")
            continue
        result_text, scored = execute_simulate(call.arguments)
        results.append(result_text)
        if scored is not None:
            scenario = scored
    _append_tool_round(messages, turn, results)
    return scenario


def _payload(analysis: str, messages: list[dict], settings: AiSettings, *, include_tools: bool) -> dict:
    payload = {
        "model": settings.model,
        "max_tokens": settings.max_output_tokens,
        "timeout_s": settings.request_timeout_s,
        "system": build_system_prompt(analysis),
        "messages": messages,
    }
    if include_tools:
        payload["tools"] = [SIMULATE_TOOL]
    return payload


def _append_tool_round(messages: list[dict], turn: Turn, results: list[str]) -> None:
    content = []
    if turn.text:
        content.append({"type": "text", "text": turn.text})
    for call in turn.tool_calls:
        content.append(
            {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
        )
    messages.append({"role": "assistant", "content": content})
    messages.append(
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": call.id, "content": result}
                for call, result in zip(turn.tool_calls, results)
            ],
        }
    )


def _between_observed(price: float) -> bool:
    return 12.0 < float(price) < 15.0 and abs(float(price) - 12.0) > 1e-9 and abs(float(price) - 15.0) > 1e-9


def _outside_promo_grid(list_price: float, promo: float) -> bool:
    bounds = promo_bounds(list_price)
    if bounds is None:
        return True
    low, high = bounds
    return float(promo) < low or float(promo) > high


class AnthropicClient:
    """Live client. The key stays inside the SDK object and is not copied onto payloads."""

    emits_text = True

    def __init__(self, api_key: str, timeout_s: float) -> None:
        import anthropic

        self._timeout_s = timeout_s
        self._sdk = anthropic.Anthropic(api_key=api_key, timeout=timeout_s, max_retries=0)

    def __repr__(self) -> str:
        return "AnthropicClient()"

    def round(self, payload: dict, on_text: Callable[[str], None]) -> Turn:
        kwargs = {
            "model": payload["model"],
            "max_tokens": payload["max_tokens"],
            "system": payload["system"],
            "messages": payload["messages"],
            "timeout": self._timeout_s,
        }
        if payload.get("tools"):
            kwargs["tools"] = payload["tools"]
        with self._sdk.messages.stream(**kwargs) as stream:
            saw_tool = False
            parts: list[str] = []
            for chunk in stream:
                if getattr(chunk, "type", "") == "content_block_start":
                    block = getattr(chunk, "content_block", None)
                    if getattr(block, "type", "") == "tool_use":
                        saw_tool = True
                if (
                    not saw_tool
                    and getattr(chunk, "type", "") == "content_block_delta"
                    and getattr(getattr(chunk, "delta", None), "type", "") == "text_delta"
                ):
                    piece = chunk.delta.text
                    parts.append(piece)
                    on_text(piece)
            final = stream.get_final_message()
        return Turn(_message_text(final), _message_tools(final))


def _message_text(message) -> str:
    parts = []
    for block in getattr(message, "content", ()):
        if getattr(block, "type", "") == "text":
            parts.append(block.text)
    return "".join(parts)


def _message_tools(message) -> tuple[ToolCall, ...]:
    calls = []
    for block in getattr(message, "content", ()):
        if getattr(block, "type", "") == "tool_use":
            calls.append(ToolCall(block.id, block.name, dict(block.input)))
    return tuple(calls)
