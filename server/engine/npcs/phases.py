# engine/npcs/phases.py
"""A creature that changes state during a fight: `properties.phases`.

    "phases": [
        {"name": "solid", "seconds": 14, "message": "The Fog Drake's scales harden.",
         "hint": {"npc": "captain_kessa", "text": "Now! It is solid, hit it!"}},
        {"name": "mist", "seconds": 8, "message": "The Fog Drake thins into mist.", "untouchable": true,
         "counter": "mist_breath", "counter_cooldown": 4, "miss_text": "The blow passes through the mist.",
         "hint": {"npc": "captain_kessa", "text": "It is only mist! Wait for it to harden!"},
         "counter_hint": {"npc": "captain_kessa", "text": "Stop! You are only angering it!"}}
    ]

While it is in a fight it cycles through the phases in order, each lasting `seconds`, and tells the room each change
(`message`, then a `hint` spoken by an NPC who is in the room and alive: a companion helping the player read the fight).
Out of a fight it rests in the first phase.

An `untouchable` phase cannot be hurt. Whoever tries (a blow, or an ability that would damage it) misses, whatever their
skill, and if the phase has a `counter` the creature answers with that ability, used on every enemy in the room at once
(at most once every `counter_cooldown` seconds, so a party all swinging is answered once, not four times). The creature's
allies in the room do not attack it while it is untouchable.

The state (which phase, until when) is not saved: a creature that is loaded starts again in its first phase.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.config import FORMAT_GREEN, FORMAT_RESET, FORMAT_YELLOW

PHASE_KEYS = ("name", "seconds", "message", "hint", "untouchable", "counter", "counter_cooldown", "counter_hint", "miss_text")
HINT_KEYS = ("npc", "text")
DEFAULT_COUNTER_COOLDOWN = 3.0
DEFAULT_MISS_TEXT = "The blow passes straight through {defender}!"


def phases_of(npc: Any) -> List[Dict[str, Any]]:
    properties = getattr(npc, "properties", None)
    raw = properties.get("phases") if isinstance(properties, dict) else None
    return [p for p in raw if isinstance(p, dict)] if isinstance(raw, list) else []


def current(npc: Any) -> Optional[Dict[str, Any]]:
    """The phase it is in now, or None when it has none or is not in a fight."""
    phases = phases_of(npc)
    if not phases or not getattr(npc, "in_combat", False) or getattr(npc, "phase_until", None) is None:
        return None
    return phases[getattr(npc, "phase_index", 0) % len(phases)]


def is_untouchable(npc: Any) -> bool:
    phase = current(npc)
    return bool(phase and phase.get("untouchable") is True)


def _seconds(phase: Dict[str, Any]) -> float:
    try:
        return max(1.0, float(phase.get("seconds", 10)))
    except (TypeError, ValueError):
        return 10.0


def _hint_line(npc: Any, world: Any, hint: Any) -> Optional[str]:
    """What the named NPC says, when that NPC is alive and in the creature's room."""
    if not isinstance(hint, dict) or world is None:
        return None
    wanted = str(hint.get("npc", "") or "")
    text = str(hint.get("text", "") or "").strip()
    if not wanted or not text:
        return None
    for other in world.get_npcs_in_room(npc.current_region_id, npc.current_room_id):
        if other.is_alive and other is not npc and wanted in (other.template_id, other.obj_id):
            return '%s%s shouts:%s %s"%s"%s' % (FORMAT_YELLOW, other.name, FORMAT_RESET, FORMAT_GREEN, text, FORMAT_RESET)
    return None


def update(npc: Any, world: Any, now: float) -> List[str]:
    """Move the creature on to its next phase when this one is over. The lines to tell the room (none when nothing changed)."""
    phases = phases_of(npc)
    if not phases:
        return []
    if not npc.in_combat:
        npc.phase_index, npc.phase_until = 0, None
        return []
    if getattr(npc, "phase_until", None) is None:
        npc.phase_index = 0
        npc.phase_until = now + _seconds(phases[0])
        return []
    if now < npc.phase_until:
        return []
    npc.phase_index = (getattr(npc, "phase_index", 0) + 1) % len(phases)
    phase = phases[npc.phase_index]
    npc.phase_until = now + _seconds(phase)
    lines = []
    message = str(phase.get("message", "") or "").strip()
    if message:
        lines.append(message)
    hint = _hint_line(npc, world, phase.get("hint"))
    if hint:
        lines.append(hint)
    return lines


def miss_text(npc: Any, attacker_name: str, defender_name: str) -> str:
    phase = current(npc) or {}
    template = str(phase.get("miss_text") or DEFAULT_MISS_TEXT)
    try:
        return template.format(attacker=attacker_name, defender=defender_name)
    except (KeyError, IndexError, ValueError):
        return DEFAULT_MISS_TEXT.format(attacker=attacker_name, defender=defender_name)


def on_blocked_attack(npc: Any, viewer: Any = None) -> str:
    """Someone struck at the creature while it was untouchable: its counter, as the text to tell ('' when there is none yet)."""
    phase = current(npc)
    world = getattr(npc, "world", None)
    if not phase or world is None or not phase.get("counter"):
        return ""
    now = world.clock.now()
    try:
        cooldown = float(phase.get("counter_cooldown", DEFAULT_COUNTER_COOLDOWN))
    except (TypeError, ValueError):
        cooldown = DEFAULT_COUNTER_COOLDOWN
    if now - float(getattr(npc, "phase_counter_at", -1e9)) < cooldown:
        return ""
    from engine.magic.effects import apply_spell_effect
    from engine.magic.spell_registry import get_spell
    from engine.npcs import combat as npc_combat

    spell = get_spell(str(phase["counter"]))
    if spell is None:
        return ""
    npc.phase_counter_at = now
    targets: List[Any] = list(world.get_players_in_room(npc.current_region_id, npc.current_room_id, alive_only=True))
    for other in world.get_npcs_in_room(npc.current_region_id, npc.current_room_id):
        if other is not npc and other.is_alive and npc_combat.is_hostile_to(npc, other) and not npc_combat.is_untargetable(other):
            targets.append(other)
    lines = [spell.format_cast_message(npc)]
    for index, target in enumerate(targets):
        _value, text = apply_spell_effect(npc, target, spell, viewer, first_target=index == 0)
        if text:
            lines.append(text)
    hint = _hint_line(npc, world, phase.get("counter_hint"))
    if hint:
        lines.append(hint)
    return "\n".join(lines)
