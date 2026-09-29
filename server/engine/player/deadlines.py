"""The clock readings a player carries, and moving them onto a new clock.

Most of a player's timers are *durations* (an effect's `duration_remaining`), which
mean the same after a restart. A few are absolute readings of the world's clock: the
moment a sentence ends, when a spell can be cast again, when a job finishes, when a
repeatable quest is offered again. After a restart the clock is a different one (a
simulated clock starts over; a wall clock kept running while the server was stopped),
so a reading saved on the old clock is meaningless on the new one.

`shift_deadlines` moves every such reading by the difference between the two clocks,
which is what makes downtime not count (chunks-of-work.md, Decision 1): a sentence
with a minute left has a minute left after the restart.
"""

from __future__ import annotations

from typing import Any


def _shifted(value: Any, delta: float) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    return value + delta


def shift_deadlines(player: Any, delta: float) -> None:
    """Move every absolute clock reading on `player` by `delta` seconds."""
    if not delta:
        return
    player.jailed_until = _shifted(getattr(player, "jailed_until", None), delta)

    state = getattr(player, "runtime_state", None)
    magic = getattr(state, "magic", None)
    if magic is not None and isinstance(magic.cooldowns, dict):
        magic.cooldowns = {spell: _shifted(until, delta) for spell, until in magic.cooldowns.items()}

    work = getattr(state, "work", None)
    if work is not None:
        for job in getattr(work, "jobs", []) or []:
            if isinstance(job, dict):
                for key in ("ends_at", "started_at"):
                    if key in job:
                        job[key] = _shifted(job[key], delta)

    quests = getattr(state, "quests", None)
    if quests is not None and isinstance(getattr(quests, "repeatable_available_at", None), dict):
        quests.repeatable_available_at = {
            template: _shifted(at, delta) for template, at in quests.repeatable_available_at.items()
        }
