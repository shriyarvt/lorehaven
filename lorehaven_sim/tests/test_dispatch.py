"""Mode switch, buttons, and fallbacks. The client is a mock."""

from __future__ import annotations

from datetime import date

from chat.dispatch import (
    AI_BUTTONS,
    CANNOT_ANSWER,
    MODE_AI,
    MODE_BASIC,
    UNAVAILABLE_NOTE,
    ai_buttons_enabled,
    apply_radio,
    take_turn,
)
from chat.limits import AiSettings, DailyCap, SessionQuota
from chat.llm_assistant import Turn
from chat.status import REASON_DAILY, REASON_PASSCODE, REASON_SESSION, REASON_UNAVAILABLE
from chat.templates import HELP_EXAMPLES
from sim.model import preset_scenario

DAY = date(2026, 11, 19)


class ScriptedClient:
    emits_text = False

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def round(self, payload, on_text):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _turn(text, **overrides):
    scenario = preset_scenario("current_policy")
    session = overrides.pop("session", SessionQuota())
    daily = overrides.pop("daily", DailyCap())
    client = overrides.pop("client", ScriptedClient(Turn("AI answer.")))
    args = {
        "radio": MODE_BASIC,
        "unlocked": False,
        "locked_basic": False,
        "lock_reason": "",
        "history": [],
        "session": session,
        "daily": daily,
        "day": DAY,
        "scenario": scenario,
        "pending": None,
        "secrets_ok": True,
        "client_factory": lambda: client,
        "settings": AiSettings(),
        "on_text": lambda _piece: None,
    }
    args.update(overrides)
    return take_turn(text, **args), session, client


def test_each_basic_button_is_scripted():
    for label in HELP_EXAMPLES:
        taken, session, client = _turn(label, radio=MODE_BASIC, secrets_ok=False, unlocked=False)
        assert taken.reply
        assert taken.called_client is False
        assert client.calls == 0
        assert session.used == 0
        assert CANNOT_ANSWER not in taken.reply


def test_each_ai_button_uses_one_question():
    session = SessionQuota()
    client = ScriptedClient(Turn("From the analysis."))
    for label in AI_BUTTONS:
        taken, _session, _client = _turn(
            label,
            radio=MODE_AI,
            unlocked=True,
            session=session,
            client=client,
        )
        assert taken.called_client is True
        assert taken.reply == "From the analysis."
        assert taken.radio == MODE_AI
    assert session.used == len(AI_BUTTONS)
    assert client.calls == len(AI_BUTTONS)


def test_switching_modes_keeps_history_and_the_counter():
    history = [{"role": "user", "text": "What is the best promo?"}]
    session = SessionQuota()
    session.used = 2
    assert apply_radio(MODE_BASIC, locked_basic=False) == MODE_BASIC
    assert apply_radio(MODE_AI, locked_basic=False) == MODE_AI
    taken, _session, client = _turn(
        "Compare to baseline",
        radio=MODE_BASIC,
        unlocked=True,
        history=history,
        session=session,
    )
    assert history == [{"role": "user", "text": "What is the best promo?"}]
    assert session.used == 2
    assert client.calls == 0
    assert taken.reply


def test_basic_works_with_no_passcode_and_no_secrets():
    taken, session, client = _turn(
        "What is the best promo?",
        radio=MODE_BASIC,
        unlocked=False,
        secrets_ok=False,
    )
    assert taken.called_client is False
    assert client.calls == 0
    assert session.used == 0
    assert "best" in taken.reply.lower()


def test_session_limit_moves_the_radio_to_basic_and_blocks_return():
    session = SessionQuota(maximum=5)
    session.used = 5
    taken, _session, client = _turn(
        "What is the best promo?",
        radio=MODE_AI,
        unlocked=True,
        session=session,
    )
    assert taken.radio == MODE_BASIC
    assert taken.locked_basic is True
    assert taken.lock_reason == REASON_SESSION
    assert taken.reason == REASON_SESSION
    assert client.calls == 0
    assert session.used == 5
    assert apply_radio(MODE_AI, locked_basic=True) == MODE_BASIC


def test_daily_cap_moves_the_radio_to_basic_and_blocks_return():
    daily = DailyCap(maximum=0)
    taken, session, client = _turn(
        "What is the best promo?",
        radio=MODE_AI,
        unlocked=True,
        daily=daily,
    )
    assert taken.radio == MODE_BASIC
    assert taken.locked_basic is True
    assert taken.reason == REASON_DAILY
    assert client.calls == 0
    assert session.used == 0
    assert apply_radio(MODE_AI, locked_basic=True) == MODE_BASIC


def test_failed_ai_call_answers_with_the_scripted_assistant_and_uses_no_question():
    class RateLimit(Exception):
        status_code = 429

        def __str__(self) -> str:
            return "sk-ant-planted-value"

    taken, session, client = _turn(
        "What is the best promo?",
        radio=MODE_AI,
        unlocked=True,
        client=ScriptedClient(RateLimit()),
    )
    assert client.calls == 1
    assert session.used == 0
    assert taken.radio == MODE_BASIC
    assert taken.locked_basic is False
    assert taken.reason == REASON_UNAVAILABLE
    assert taken.reply.startswith(UNAVAILABLE_NOTE)
    assert "best" in taken.reply.lower()
    if "sk-ant-planted-value" in taken.reply:
        raise AssertionError("a secret-like string was found in the reply")


def test_failed_ai_call_on_an_unknown_question_is_one_line():
    taken, session, _client = _turn(
        "What does 'parallel trends' mean?",
        radio=MODE_AI,
        unlocked=True,
        client=ScriptedClient(TimeoutError("timed out")),
    )
    assert taken.reply == CANNOT_ANSWER
    assert session.used == 0
    assert taken.radio == MODE_BASIC


def test_ai_buttons_are_disabled_before_the_passcode():
    assert ai_buttons_enabled(
        radio=MODE_AI, unlocked=False, locked_basic=False, secrets_ok=True
    ) is False
    taken, session, client = _turn(
        "What does 'at risk' mean?",
        radio=MODE_AI,
        unlocked=False,
        secrets_ok=True,
    )
    assert taken.reason == REASON_PASSCODE
    assert taken.called_client is False
    assert client.calls == 0
    assert session.used == 0
    assert taken.radio == MODE_AI


def test_typed_question_before_the_passcode_uses_the_scripted_assistant():
    taken, session, client = _turn("Compare to baseline", radio=MODE_AI, unlocked=False)
    assert taken.reason == REASON_PASSCODE
    assert taken.called_client is False
    assert client.calls == 0
    assert session.used == 0
    assert taken.reply
