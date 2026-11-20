"""Session questions, the shared daily cap, and the request size."""

from __future__ import annotations

from datetime import date

from chat.gate import PasscodeGate
from chat.limits import (
    SESSION_LIMIT_CAPTION,
    AiSettings,
    DailyCap,
    SessionQuota,
    settings_from_env,
    trim_history,
)
from chat.router import submit

DAY = date(2026, 11, 19)
ANALYSIS = "Analysis body with no secrets."


class FakeClient:
    def __init__(self, fail: Exception | None = None) -> None:
        self.calls = 0
        self.payloads: list[dict] = []
        self.fail = fail

    def complete(self, payload: dict) -> str:
        self.calls += 1
        self.payloads.append(payload)
        if self.fail is not None:
            raise self.fail
        return "answered"


def _ask(client, session, daily, message="What changed?", history=None, settings=None):
    gate = PasscodeGate("alpha-passcode")
    gate.unlocked = True
    return submit(
        message,
        secrets_ok=True,
        gate=gate,
        session=session,
        daily=daily,
        day=DAY,
        history=history or [],
        analysis=ANALYSIS,
        client=client,
        settings=settings or AiSettings(),
    )


def test_sixth_question_falls_back_to_basic_mode():
    session = SessionQuota(maximum=5)
    daily = DailyCap()
    client = FakeClient()
    for _ in range(5):
        route = _ask(client, session, daily)
        assert route.mode == "ai"
    sixth = _ask(client, session, daily)
    assert sixth.mode == "basic"
    assert sixth.caption == SESSION_LIMIT_CAPTION
    assert client.calls == 5
    assert session.used == 5


def test_a_failed_call_does_not_use_a_session_question():
    session = SessionQuota(maximum=5)
    daily = DailyCap(maximum=200)
    for failure in (TimeoutError("timed out"), RuntimeError("429")):
        client = FakeClient(fail=failure)
        route = _ask(client, session, daily)
        assert route.mode == "basic"
        assert route.called_client is True
    assert session.used == 0
    assert session.remaining() == 5
    assert daily.used(DAY) == 2


def test_daily_cap_blocks_a_second_session():
    daily = DailyCap(maximum=1)
    first = SessionQuota()
    second = SessionQuota()
    client = FakeClient()
    opened = _ask(client, first, daily)
    assert opened.mode == "ai"
    blocked = _ask(client, second, daily)
    assert blocked.mode == "basic"
    assert "daily question limit" in blocked.caption
    assert client.calls == 1
    assert second.used == 0
    assert first.remaining() == 14


def test_history_max_tokens_and_oversize_input():
    settings = AiSettings()
    history = []
    for index in range(10):
        history.append({"role": "user", "content": f"q{index}"})
        history.append({"role": "assistant", "content": f"a{index}"})
    client = FakeClient()
    route = _ask(client, SessionQuota(), DailyCap(), message="now", history=history, settings=settings)
    assert route.mode == "ai"
    payload = client.payloads[0]
    assert payload["max_tokens"] == 400
    assert payload["timeout_s"] == 30
    prior = payload["messages"][:-1]
    assert sum(1 for item in prior if item["role"] == "user") == 6
    huge = "x" * 1001
    quota = SessionQuota()
    daily = DailyCap()
    rejected = _ask(FakeClient(), quota, daily, message=huge, settings=settings)
    assert rejected.called_client is False
    assert "1,000" in rejected.caption
    assert quota.used == 0
    assert daily.used(DAY) == 0


def test_default_session_limit_is_fifteen(monkeypatch):
    monkeypatch.delenv("MAX_QUESTIONS_PER_SESSION", raising=False)
    assert settings_from_env().max_questions_per_session == 15
    assert SessionQuota().maximum == 15


def test_trim_history_keeps_six_turns():
    turns = []
    for index in range(8):
        turns.append({"role": "user", "content": str(index)})
        turns.append({"role": "assistant", "content": str(index)})
    kept = trim_history(turns, 6)
    assert sum(1 for item in kept if item["role"] == "user") == 6
