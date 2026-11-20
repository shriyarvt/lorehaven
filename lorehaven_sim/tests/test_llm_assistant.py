"""The LLM assistant, with a mocked client. No live API call and no secret values."""

from __future__ import annotations

import logging
from datetime import date

from chat.limits import AiSettings, DailyCap, SessionQuota
from chat.llm_assistant import (
    ToolCall,
    Turn,
    ask_ai,
    execute_simulate,
    run_question,
)
from chat.policy import PROMO_GRID_RULE

DAY = date(2026, 11, 19)
PLANTED = "sk-ant-planted-value"


class ScriptedClient:
    emits_text = False

    def __init__(self, turns: list) -> None:
        self._turns = list(turns)
        self.payloads: list[dict] = []

    def round(self, payload: dict, on_text) -> Turn:
        self.payloads.append(payload)
        item = self._turns.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _reject(text: str, where: str) -> None:
    if PLANTED in text:
        raise AssertionError(f"a secret-like string was found in {where}")


def test_system_prompt_uses_the_analysis_and_hides_secrets():
    client = ScriptedClient([Turn("From the analysis.")])
    chunks: list[str] = []
    outcome = run_question(
        message="What changed?",
        history=[],
        analysis="UNIQUE-ANALYSIS-SENTENCE",
        client=client,
        settings=AiSettings(),
        on_text=chunks.append,
    )
    payload = client.payloads[0]
    assert outcome.ok is True
    assert outcome.text == "From the analysis."
    assert chunks == ["From the analysis."]
    assert "UNIQUE-ANALYSIS-SENTENCE" in payload["system"]
    assert "Only list prices of $12 and $15 have promo data" in payload["system"]
    assert PROMO_GRID_RULE.split(".")[0] in payload["system"]
    assert payload["max_tokens"] == 400
    assert payload["model"] == "claude-haiku-5-5"
    assert "tools" in payload
    _reject(str(payload), "the model context")


def test_tool_error_is_text_and_the_next_round_continues():
    client = ScriptedClient(
        [
            Turn("", (ToolCall("tool-1", "simulate", {"list_price": 10, "group": "everyone"}),)),
            Turn("I can't use that."),
        ]
    )
    outcome = run_question(
        message="Score list 10",
        history=[],
        analysis="Analysis.",
        client=client,
        settings=AiSettings(),
        on_text=lambda _piece: None,
    )
    assert outcome.ok is True
    assert outcome.scenario is None
    tool_result = client.payloads[1]["messages"][-1]["content"][0]["content"]
    assert "from $12 to $15" in tool_result
    assert "Traceback" not in tool_result


def test_off_grid_promo_is_not_scored(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("simulate was called")

    monkeypatch.setattr("chat.llm_assistant.simulate", boom)
    text, scenario = execute_simulate(
        {"list_price": 15, "promo_dollar": 5, "group": "everyone"}
    )
    assert scenario is None
    assert "not scored" in text.lower()
    between, _unused = execute_simulate(
        {"list_price": 13.5, "promo_dollar": 8, "group": "everyone"}
    )
    assert "Only $12 and $15 have promo data" in between


def test_list_price_between_the_observed_points_is_labeled():
    text, scenario = execute_simulate({"list_price": 13.5, "group": "everyone"})
    assert scenario is not None
    assert scenario.mode == "list"
    assert text.startswith("Untested straight-line assumption, not a finding.")
    assert "membership_lift_pp" in text


def test_two_tool_rounds_then_a_final_answer():
    tool = ToolCall(
        "tool-1",
        "simulate",
        {"list_price": 12, "promo_dollar": 11, "group": "everyone"},
    )
    client = ScriptedClient([Turn("", (tool,)), Turn("", (tool,)), Turn("Done.")])
    outcome = run_question(
        message="Score it",
        history=[],
        analysis="Analysis.",
        client=client,
        settings=AiSettings(),
        on_text=lambda _piece: None,
    )
    assert outcome.ok is True
    assert outcome.scenario is not None
    assert outcome.scenario.list_price == 12
    assert [payload.get("tools") is not None for payload in client.payloads] == [True, True, False]
    assert outcome.text == "Done."


def test_api_error_does_not_use_a_session_question(caplog):
    class RateLimit(Exception):
        status_code = 429

        def __str__(self) -> str:
            return PLANTED

    session = SessionQuota()
    daily = DailyCap()
    client = ScriptedClient([RateLimit()])
    with caplog.at_level(logging.WARNING, logger="lorehaven.chat"):
        outcome = ask_ai(
            message="Hello",
            history=[],
            analysis="Analysis.",
            client=client,
            settings=AiSettings(),
            on_text=lambda _piece: None,
            session=session,
            daily=daily,
            day=DAY,
        )
    assert outcome.ok is False
    assert outcome.text == ""
    assert session.used == 0
    assert daily.used(DAY) == 1
    assert "RateLimit" in caplog.text
    assert "429" in caplog.text
    _reject(caplog.text, "the log")
    _reject(outcome.text, "the model output")
