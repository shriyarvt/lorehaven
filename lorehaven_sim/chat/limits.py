"""Session and daily question limits. No pricing math."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import date

SESSION_LIMIT_CAPTION = (
    "You've used your 15 AI questions for this session. "
    "The basic assistant can still run scenarios."
)
OVERSIZE_MESSAGE = "That message is too long. Please keep it under 1,000 characters."
DAILY_CAP_CAPTION = "Basic mode. The daily question limit has been reached."
BASIC_CAPTION = "Basic mode."


@dataclass(frozen=True)
class AiSettings:
    """Caps and the model name. Secrets are not stored here."""

    model: str = "claude-haiku-5-5"
    max_questions_per_session: int = 15
    global_daily_questions: int = 200
    max_history_turns: int = 6
    max_output_tokens: int = 400
    max_input_chars: int = 1000
    request_timeout_s: int = 30


def settings_from_env() -> AiSettings:
    """Optional env vars override the defaults. Missing vars keep the default."""
    return AiSettings(
        model=os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5") or "claude-haiku-5-5",
        max_questions_per_session=_env_int("MAX_QUESTIONS_PER_SESSION", 15),
        global_daily_questions=_env_int("GLOBAL_DAILY_QUESTIONS", 200),
        max_history_turns=_env_int("MAX_HISTORY_TURNS", 6),
        max_output_tokens=_env_int("MAX_OUTPUT_TOKENS", 400),
        max_input_chars=_env_int("MAX_INPUT_CHARS", 1000),
        request_timeout_s=_env_int("REQUEST_TIMEOUT_S", 30),
    )


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return int(raw)


class SessionQuota:
    """Counts successful AI replies only."""

    def __init__(self, maximum: int = 15) -> None:
        self.maximum = maximum
        self.used = 0

    def remaining(self) -> int:
        return max(0, self.maximum - self.used)

    def allow(self) -> bool:
        return self.remaining() > 0

    def record_success(self) -> None:
        if self.used < self.maximum:
            self.used += 1


class DailyCap:
    """Shared counter. A failed call counts. The key is the UTC date."""

    def __init__(self, maximum: int = 200) -> None:
        self.maximum = maximum
        self._lock = threading.Lock()
        self._counts: dict[date, int] = {}

    def used(self, day: date) -> int:
        with self._lock:
            return self._counts.get(day, 0)

    def allow(self, day: date) -> bool:
        return self.used(day) < self.maximum

    def record_attempt(self, day: date) -> None:
        with self._lock:
            self._counts[day] = self._counts.get(day, 0) + 1


def trim_history(turns: list[dict], max_turns: int) -> list[dict]:
    """Keep the last N turns. A turn is a user message plus its reply, when one exists."""
    if max_turns <= 0:
        return []
    grouped: list[list[dict]] = []
    current: list[dict] = []
    for item in turns:
        if item.get("role") == "user" and current:
            grouped.append(current)
            current = [item]
        else:
            current.append(item)
    if current:
        grouped.append(current)
    kept: list[dict] = []
    for turn in grouped[-max_turns:]:
        kept.extend(turn)
    return kept


def reject_oversize(message: str, max_chars: int) -> str | None:
    if len(message) > max_chars:
        return OVERSIZE_MESSAGE
    return None
