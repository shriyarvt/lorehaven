"""Why the chat is in basic mode, and a yes/no setup check. No secret values."""

from __future__ import annotations

import logging

REASON_NO_SECRETS = "No passcode or API key configured"
REASON_PASSCODE = "Passcode required"
REASON_PACKAGE = "Anthropic package not installed"
REASON_SESSION = "Session question limit reached"
REASON_DAILY = "Daily limit reached"
REASON_UNAVAILABLE = "AI service unavailable, using basic mode"
REASON_NOT_CONNECTED = "AI assistant not connected yet"

_LOG = logging.getLogger("lorehaven.chat")


def mode_reason(
    *,
    secrets_ok: bool,
    unlocked: bool,
    package_importable: bool,
    session_open: bool,
    daily_open: bool,
    service_unavailable: bool,
    client_connected: bool,
) -> str | None:
    """The one basic-mode reason, or None when the AI assistant can answer."""
    if not secrets_ok:
        return REASON_NO_SECRETS
    if not unlocked:
        return REASON_PASSCODE
    if not package_importable:
        return REASON_PACKAGE
    if not session_open:
        return REASON_SESSION
    if not daily_open:
        return REASON_DAILY
    if service_unavailable:
        return REASON_UNAVAILABLE
    if not client_connected:
        return REASON_NOT_CONNECTED
    return None


def setup_report(
    *,
    secrets_file_found: bool,
    api_key_present: bool,
    passcode_present: bool,
    package_importable: bool,
    model_set: bool,
) -> tuple[tuple[str, str], ...]:
    """Yes/no lines. Callers pass flags, never the secret strings."""
    return (
        ("secrets file found", _yes_no(secrets_file_found)),
        ("API key present", _yes_no(api_key_present)),
        ("passcode present", _yes_no(passcode_present)),
        ("anthropic package importable", _yes_no(package_importable)),
        ("model name set", _yes_no(model_set)),
    )


def anthropic_importable() -> bool:
    try:
        import anthropic  # noqa: F401
    except Exception:
        return False
    return True


def log_api_error(exc: BaseException) -> None:
    """Console log: exception class and HTTP status only."""
    status = _status_code(exc)
    if status is None:
        _LOG.warning("AI request failed: %s", type(exc).__name__)
    else:
        _LOG.warning("AI request failed: %s status=%s", type(exc).__name__, status)


def _status_code(exc: BaseException) -> int | None:
    for name in ("status_code", "status"):
        value = getattr(exc, name, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    if isinstance(value, int):
        return value
    return None


def _yes_no(flag: bool) -> str:
    return "yes" if flag else "no"
