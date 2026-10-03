# engine/utils/messages.py
"""The engine's own words for the moments every game has, which a content set can say its own way.

A kill's reward, a level gained, falling in battle, a quest handed in: each used to be one English sentence in
the engine. They are named here with the fields each can mention, and a ruleset's `messages` section replaces
any of them:

    "messages": {
        "kill_experience": "{amount} experience earned.",
        "defeated": "Your vision fades..."
    }

A template may use only the fields listed for it, written `{name}`. A template that cannot be used (an unknown
field, a stray brace) is ignored and the engine's own words stand, so a bad message can never break the moment it
describes. Colour and layout stay with the engine; these are only the words.
"""

from __future__ import annotations

import string
from typing import Any, Dict, Tuple

# key -> (the engine's words, the fields that may be used)
MESSAGES: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "kill_experience": ("You gain {amount} experience!", ("amount",)),
    "kill_gold": ("You find {amount} {currency}.", ("amount", "currency")),
    "shared_experience": ("You gain {amount} experience for your part in defeating {name}.", ("amount", "name")),
    "level_reached": ("You have reached level {level}!", ("level",)),
    "levels_gained": ("You have gained {count} levels and are now level {level}!", ("count", "level")),
    "defeated": ("You have been defeated!", ()),
    "respawn_hint": ("Type 'respawn' to rise again at {place}.", ("place",)),
    "summon_departs": ("Your {name} crumbles to dust.", ("name",)),
    "quest_complete": ("[Quest Complete] {title}", ("title",)),
}


def template_problems(template: Any, key: str) -> list:
    """Why `template` cannot stand in for message `key` (empty when it can)."""
    if key not in MESSAGES:
        return [f"{key!r} is not a message the engine says (known: {', '.join(MESSAGES)})"]
    if not isinstance(template, str) or not template.strip():
        return ["it must be text"]
    allowed = MESSAGES[key][1]
    problems = []
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as error:
        return [f"it has a stray brace ({error})"]
    for _literal, field, spec, conversion in parsed:
        if field is None:
            continue
        if field not in allowed or spec or conversion:
            problems.append(
                f"{{{field}}} is not a field this message has (it may use: "
                + (", ".join("{%s}" % name for name in allowed) if allowed else "none")
                + ")"
            )
    return problems


def _override(world: Any, key: str) -> Any:
    try:
        section = world.ruleset_section("messages") if world is not None else {}
    except Exception:  # noqa: BLE001 - a world without rules says what the engine says
        return None
    return section.get(key) if isinstance(section, dict) else None


def message(world: Any, key: str, **fields: Any) -> str:
    """The words for `key`: the content set's, when it has said some that can be used; the engine's otherwise."""
    default = MESSAGES[key][0]
    custom = _override(world, key)
    template = custom if isinstance(custom, str) and not template_problems(custom, key) else default
    try:
        return template.format(**fields)
    except (KeyError, IndexError, ValueError):
        return default.format(**fields)
