from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after_s: float


class SessionRateLimiter:
    def __init__(self, rate_per_sec: float, burst: int) -> None:
        self.rate_per_sec = max(0.1, float(rate_per_sec))
        self.burst = max(1, int(burst))
        self._tokens_by_session: dict[str, float] = {}
        self._last_refill_by_session: dict[str, float] = {}

    def consume(self, session_id: str, cost: float = 1.0) -> RateLimitResult:
        sid = str(session_id).strip()
        if sid == "":
            return RateLimitResult(allowed=False, retry_after_s=1.0)
        now = time.monotonic()
        tokens = float(self._tokens_by_session.get(sid, float(self.burst)))
        last = float(self._last_refill_by_session.get(sid, now))
        elapsed = max(0.0, now - last)
        tokens = min(float(self.burst), tokens + (elapsed * self.rate_per_sec))
        self._last_refill_by_session[sid] = now
        if tokens >= cost:
            tokens -= cost
            self._tokens_by_session[sid] = tokens
            return RateLimitResult(allowed=True, retry_after_s=0.0)
        deficit = max(0.0, cost - tokens)
        retry_after = deficit / self.rate_per_sec
        self._tokens_by_session[sid] = tokens
        return RateLimitResult(allowed=False, retry_after_s=max(0.05, retry_after))

    def clear(self, session_id: str) -> None:
        sid = str(session_id).strip()
        if sid == "":
            return
        self._tokens_by_session.pop(sid, None)
        self._last_refill_by_session.pop(sid, None)


class InputSafeguards:
    def __init__(
        self,
        max_command_chars: int = 512,
        max_envelope_bytes: int = 8192,
        command_rate_limit_per_sec: float = 8.0,
        command_burst: int = 16,
    ) -> None:
        self.max_command_chars = max(1, int(max_command_chars))
        self.max_envelope_bytes = max(1, int(max_envelope_bytes))
        self.command_rate_limit_per_sec = max(0.1, float(command_rate_limit_per_sec))
        self.command_burst = max(1, int(command_burst))
        self._limiter = SessionRateLimiter(self.command_rate_limit_per_sec, self.command_burst)

    def check_envelope_size(self, raw_bytes_len: int) -> tuple[bool, str]:
        if int(raw_bytes_len) > self.max_envelope_bytes:
            return False, "Input rejected: envelope too large."
        return True, ""

    def check_command_text(self, command_text: str) -> tuple[bool, str]:
        if len(str(command_text)) > self.max_command_chars:
            return False, "Input rejected: command too long."
        return True, ""

    def consume_rate_budget(self, session_id: str) -> tuple[bool, float]:
        result = self._limiter.consume(session_id, 1.0)
        return result.allowed, result.retry_after_s

    def clear_session(self, session_id: str) -> None:
        self._limiter.clear(session_id)

    def evict_stale_sessions(self, active_session_ids: set) -> int:
        """Remove rate-limit state for sessions that are no longer active."""
        stale = set(self._limiter._tokens_by_session.keys()) - active_session_ids
        for sid in stale:
            self._limiter.clear(sid)
        return len(stale)
