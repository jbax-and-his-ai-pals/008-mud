# engine/core/clock.py
"""A shared, injectable source of "current time" for gameplay timers.

TimeManager already advances the in-world calendar purely from a
caller-supplied dt, with no wall-clock dependency. This module is for the
*other* kind of timer that has historically called time.time() directly:
absolute-timestamp cooldowns and expiries (combat/spell cooldowns, NPC move
and respawn timers, jail sentences, DOT/buff ticks) set once as
`clock.now() + duration` and later compared against a fresh `clock.now()`.

WallClock preserves today's real-time behavior exactly (the default for a
live server or the desktop client). SimulatedClock lets a headless journey
or test advance those same timers deterministically, in lockstep with the
game calendar's own dt, without sleeping real seconds.
"""
import time
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float:
        """Current time, in seconds, on whatever timeline this clock tracks."""

    def advance(self, seconds: float) -> None:
        """Move the clock forward. A no-op for a clock backed by real time."""


class WallClock:
    """Backed by the real system clock. Real time passes regardless of
    whether advance() is called, matching a live server's actual behavior."""

    def now(self) -> float:
        return time.time()

    def advance(self, seconds: float) -> None:
        pass


class SimulatedClock:
    """A manually-driven clock for deterministic simulation.

    Defaults to a large epoch, not a small one, for the same reason
    time.time() is always a huge number: plenty of existing code seeds a
    "never happened yet" timestamp as 0.0 (a fresh player's last_attack_time,
    an NPC's last_moved) and expects `clock.now() - 0.0` to already clear any
    realistic cooldown on the very first check. Starting near zero would
    make that comparison fail until the clock had advanced past the
    cooldown itself, blocking a freshly-created actor's first action.
    """

    def __init__(self, start: float = 1_000_000.0) -> None:
        self._now = start

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def set(self, value: float) -> None:
        self._now = value
