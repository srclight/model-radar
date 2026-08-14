"""Process-local provider cooldown after 401/402/429/529."""

from __future__ import annotations

import time

COOLDOWN_SECONDS = 600.0


class CooldownBook:
    """provider -> (until_monotonic, reason). Inject `now` in tests."""

    def __init__(self) -> None:
        self._until: dict[str, tuple[float, str]] = {}

    def record(
        self,
        provider: str,
        reason: str,
        seconds: float = COOLDOWN_SECONDS,
        now: float | None = None,
    ) -> None:
        t = time.monotonic() if now is None else now
        self._until[provider] = (t + seconds, reason)

    def is_cooled(self, provider: str, now: float | None = None) -> bool:
        return self.remaining(provider, now=now) > 0.0

    def remaining(self, provider: str, now: float | None = None) -> float:
        entry = self._until.get(provider)
        if not entry:
            return 0.0
        t = time.monotonic() if now is None else now
        left = entry[0] - t
        if left <= 0:
            self._until.pop(provider, None)
            return 0.0
        return left

    def reason(self, provider: str) -> str | None:
        entry = self._until.get(provider)
        return None if entry is None else entry[1]

    def clear(self, provider: str | None = None) -> None:
        if provider is None:
            self._until.clear()
        else:
            self._until.pop(provider, None)


COOLDOWNS = CooldownBook()
