"""Passcode gate. The expected code stays on this object and is never rendered."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping

MAX_PASSCODE_ATTEMPTS = 5


def secrets_present(values: Mapping[str, str]) -> bool:
    """Both secrets must be non-empty before the AI assistant can run."""
    key = str(values.get("ANTHROPIC_API_KEY", "")).strip()
    code = str(values.get("APP_PASSCODE", "")).strip()
    return bool(key) and bool(code)


def passcode_matches(provided: str, expected: str) -> bool:
    """Compare digests so unequal lengths still use compare_digest."""
    left = hashlib.sha256(str(provided).encode()).digest()
    right = hashlib.sha256(str(expected).encode()).digest()
    return hmac.compare_digest(left, right)


class PasscodeGate:
    """Five wrong tries lock the session. A later correct code does not open it."""

    def __init__(self, expected: str, max_attempts: int = MAX_PASSCODE_ATTEMPTS) -> None:
        self._expected = expected
        self.max_attempts = max_attempts
        self.failures = 0
        self.unlocked = False

    def __repr__(self) -> str:
        return f"PasscodeGate(unlocked={self.unlocked}, failures={self.failures})"

    def locked_out(self) -> bool:
        return self.failures >= self.max_attempts and not self.unlocked

    def try_passcode(self, provided: str) -> bool:
        if self.unlocked:
            return True
        if self.locked_out():
            return False
        if passcode_matches(provided, self._expected):
            self.unlocked = True
            return True
        self.failures += 1
        return False
