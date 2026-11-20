"""Basic-mode reasons and the setup check. Failures do not print secret values."""

from __future__ import annotations

import logging

from chat.status import (
    REASON_DAILY,
    REASON_NO_SECRETS,
    REASON_NOT_CONNECTED,
    REASON_PACKAGE,
    REASON_PASSCODE,
    REASON_SESSION,
    REASON_UNAVAILABLE,
    log_api_error,
    mode_reason,
    setup_report,
)


def _reason(**overrides) -> str | None:
    flags = {
        "secrets_ok": True,
        "unlocked": True,
        "package_importable": True,
        "session_open": True,
        "daily_open": True,
        "service_unavailable": False,
        "client_connected": True,
    }
    flags.update(overrides)
    return mode_reason(**flags)


def test_each_basic_mode_reason():
    assert _reason(secrets_ok=False, package_importable=False) == REASON_NO_SECRETS
    assert _reason(unlocked=False) == REASON_PASSCODE
    assert _reason(package_importable=False) == REASON_PACKAGE
    assert _reason(session_open=False) == REASON_SESSION
    assert _reason(daily_open=False) == REASON_DAILY
    assert _reason(service_unavailable=True) == REASON_UNAVAILABLE
    assert _reason(client_connected=False) == REASON_NOT_CONNECTED
    assert _reason() is None


def test_setup_report_is_yes_no_only():
    planted = "sk-ant-planted-value"
    report = setup_report(
        secrets_file_found=True,
        api_key_present=True,
        passcode_present=False,
        package_importable=True,
        model_set=True,
    )
    answers = {label: value for label, value in report}
    assert answers["secrets file found"] == "yes"
    assert answers["API key present"] == "yes"
    assert answers["passcode present"] == "no"
    assert answers["anthropic package importable"] == "yes"
    assert answers["model name set"] == "yes"
    shown = " ".join(value for _, value in report)
    if planted in shown or planted in " ".join(answers):
        raise AssertionError("a secret-like string was found in the setup report")
    assert set(shown.split()) <= {"yes", "no"}


def test_api_error_log_keeps_only_the_class_and_status(caplog):
    class RateLimit(Exception):
        status_code = 429

        def __str__(self) -> str:
            return "sk-ant-planted-value"

    with caplog.at_level(logging.WARNING, logger="lorehaven.chat"):
        log_api_error(RateLimit())
        log_api_error(TimeoutError("sk-ant-planted-value"))
    text = caplog.text
    assert "RateLimit" in text
    assert "429" in text
    assert "TimeoutError" in text
    if "sk-ant-planted-value" in text:
        raise AssertionError("a secret-like string was found in the log")
