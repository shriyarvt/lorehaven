"""Passcode gate. A wrong code never reaches the client."""

from __future__ import annotations

from datetime import date

from chat.gate import PasscodeGate, passcode_matches
from chat.limits import AiSettings, DailyCap, SessionQuota
from chat.router import submit

EXPECTED = "alpha-passcode"
KEY = "sk-ant-test-value-not-real"


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
        return "ok"


def _submit(gate: PasscodeGate, client: FakeClient, message: str = "What is the best promo?"):
    return submit(
        message,
        secrets_ok=True,
        gate=gate,
        session=SessionQuota(),
        daily=DailyCap(),
        day=date(2026, 11, 19),
        history=[],
        analysis="The analysis text.",
        client=client,
        settings=AiSettings(),
    )


def _reject_secret(text: str, where: str) -> None:
    """Fail without handing the matched text to pytest's assertion diff."""
    if KEY in text or EXPECTED in text:
        raise AssertionError(f"a secret-like string was found in {where}")


def test_wrong_passcode_never_reaches_the_client():
    gate = PasscodeGate(EXPECTED)
    client = FakeClient()
    assert gate.try_passcode("nope") is False
    route = _submit(gate, client)
    assert client.calls == 0
    assert route.called_client is False
    assert route.mode == "basic"
    _reject_secret(route.reply, "the model output")


def test_correct_passcode_reaches_the_client():
    gate = PasscodeGate(EXPECTED)
    client = FakeClient()
    assert gate.try_passcode(EXPECTED) is True
    route = _submit(gate, client)
    assert client.calls == 1
    assert route.mode == "ai"
    _reject_secret(str(client.payloads), "the model context")


def test_lockout_after_five_wrong_tries():
    gate = PasscodeGate(EXPECTED)
    client = FakeClient()
    for _ in range(5):
        assert gate.try_passcode("wrong") is False
    assert gate.locked_out() is True
    assert gate.try_passcode(EXPECTED) is False
    route = _submit(gate, client)
    assert client.calls == 0
    assert route.mode == "basic"


def test_missing_secrets_stay_in_basic_mode():
    from chat.gate import secrets_present

    assert secrets_present({}) is False
    assert secrets_present({"ANTHROPIC_API_KEY": " ", "APP_PASSCODE": EXPECTED}) is False
    gate = PasscodeGate(EXPECTED)
    gate.unlocked = True
    client = FakeClient()
    route = submit(
        "What is the best promo?",
        secrets_ok=False,
        gate=gate,
        session=SessionQuota(),
        daily=DailyCap(),
        day=date(2026, 11, 19),
        history=[],
        analysis="The analysis text.",
        client=client,
        settings=AiSettings(),
    )
    assert client.calls == 0
    assert route.mode == "basic"
    assert route.caption == "Basic mode."


def test_compare_digest_rejects_a_different_length():
    assert passcode_matches("short", EXPECTED) is False
    assert passcode_matches(EXPECTED, EXPECTED) is True
