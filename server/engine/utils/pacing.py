# engine/utils/pacing.py
"""How fast a client should reveal a piece of text.

Text arrives whole and is, by default, shown at once. Content can ask for a passage to be
revealed a few characters at a time -- the king delivering his orders, a vision -- so it reads
as a story beat to be paid attention to rather than a log line to be scanned. The server only
*marks* the passage (`[[PACE:25]]...[[/PACE]]`, in the same markup as colours and links);
a client that does not reveal gradually shows it at once, and one that does lets the player
skip ahead.

A pace is a name from `TEXT_PACES` or a number of characters per second within `PACE_RANGE`.
Absent, `"instant"` or anything else is no pacing at all.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Characters revealed per second.
TEXT_PACES = {
    "brisk": 180,
    "measured": 110,
    "slow": 70,
    "solemn": 40,
}
PACE_RANGE = (5, 200)


def resolve_pace(value: Any) -> Optional[int]:
    """Characters per second for a pace, or None when it is not a pace (so, shown at once)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        return TEXT_PACES.get(value.strip().lower())
    if isinstance(value, (int, float)) and PACE_RANGE[0] <= value <= PACE_RANGE[1]:
        return int(round(value))
    return None


def paced(text: str, pace: Any) -> str:
    """`text` marked for gradual reveal at `pace`, or unchanged when there is no such pace."""
    speed = resolve_pace(pace)
    if speed is None or not text:
        return text
    return f"[[PACE:{speed}]]{text}[[/PACE]]"


# -- a policy: which text is story text ---------------------------------------------------

# Text a quest produces begins with one of these (after any colour markup), and runs to the next
# blank line: "[Quest Accepted] Title" and the sentence under it, "[Quest Update] ...", "New
# Objective: ...". It is story the player should read, so by default it is paced.
QUEST_TEXT_PREFIXES = ("[Quest ", "[Objective ", "New Objective:")
DEFAULT_QUEST_TEXT_PACE = "slow"

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


def effective_quest_text_pace(operator: Any, content_set: Any) -> Any:
    """The pace quest text is revealed at: what the server's operator set, else what the content set asks for
    (`presentation.quest_text_pace`), else the engine's default. "instant" is a choice (nothing is paced by
    default); `None`, or something that is not a pace, is "not said"."""
    for value in (operator, content_set):
        if isinstance(value, str) and value.strip().lower() == "instant":
            return "instant"
        if resolve_pace(value) is not None:
            return value
    return DEFAULT_QUEST_TEXT_PACE


def pace_quest_text(text: str, pace: Any = DEFAULT_QUEST_TEXT_PACE) -> str:
    """Mark each paragraph of `text` that is quest text for gradual reveal at `pace`.

    A paragraph is a run of lines up to a blank one. Text already paced (a dialogue node that
    asked for its own speed) is left alone, as is everything when `pace` is not a pace.
    """
    if resolve_pace(pace) is None or not any(prefix in text for prefix in QUEST_TEXT_PREFIXES):
        return text
    lines = text.split("\n")
    out = []
    block = []

    def flush() -> None:
        if block:
            out.append(paced("\n".join(block), pace) if _is_quest_block(block) else "\n".join(block))
            block.clear()

    for line in lines:
        if line.strip():
            block.append(line)
        else:
            flush()
            out.append(line)
    flush()
    return "\n".join(out)


def _is_quest_block(block: list) -> bool:
    first = _MARKUP.sub("", block[0]).lstrip()
    if not first.startswith(QUEST_TEXT_PREFIXES):
        return False
    return not any("[[PACE:" in line for line in block)
