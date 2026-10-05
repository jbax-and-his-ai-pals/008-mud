# engine/magic/windup.py
"""An ability with a wind-up: the caster leaves the fight for a moment and comes down on the target.

    "jump": {
        "windup": {"seconds": 3, "leave_message": "{caster_name} leaps out of sight!",
                   "land_message": "{caster_name} drops from the sky onto {target_name}!"},
        "target_type": "enemy", "effects": [{"type": "damage", "value": 40, "damage_type": "physical"}]
    }

The cast costs and cools down as any cast does, and tells `leave_message`. For `seconds` the caster is *airborne*: it
takes no action, cannot be struck and is not picked as a target. Then it lands: `land_message` is told and the effects
fall on the target, if the target is still there and alive. If the caster has died, or the target has gone, nothing falls
and the caster simply comes down.
"""

from typing import Any, Dict, Optional

AIRBORNE_TAG = "airborne"
WINDUP_KEYS = ("seconds", "leave_message", "land_message")
SECONDS_RANGE = (1.0, 30.0)
MESSAGE_PLACEHOLDERS = ("caster_name", "target_name", "spell_name")


def windup_of(spell: Any) -> Optional[Dict[str, Any]]:
    value = getattr(spell, "windup", None)
    return value if isinstance(value, dict) and value else None


def is_airborne(entity: Any) -> bool:
    return hasattr(entity, "has_effect_tag") and entity.has_effect_tag(AIRBORNE_TAG)


def _say(template: Any, default: str, **names: str) -> str:
    text = template if isinstance(template, str) and template.strip() else default
    try:
        return text.format(**names)
    except (KeyError, IndexError, ValueError):
        return default.format(**names)


def _viewer(world: Any, caster: Any, viewer: Any) -> Any:
    if viewer is not None:
        return viewer
    if getattr(caster, "runtime_state", None) is not None:
        return caster
    return world.get_viewer_for_npc(caster) if world is not None and hasattr(world, "get_viewer_for_npc") else None


def begin(caster: Any, target: Any, spell: Any, viewer: Any):
    """Start the wind-up: the caster goes up, and `land` is scheduled. Returns (0, what is told now)."""
    from engine.utils.utils import format_name_for_display

    world = getattr(caster, "world", None)
    windup = windup_of(spell) or {}
    seconds = max(SECONDS_RANGE[0], min(SECONDS_RANGE[1], float(windup.get("seconds", 3))))
    names = {
        "caster_name": format_name_for_display(viewer, caster, start_of_sentence=True) if viewer else getattr(caster, "name", "Someone"),
        "target_name": format_name_for_display(viewer, target, start_of_sentence=False) if viewer else getattr(target, "name", "something"),
        "spell_name": getattr(spell, "name", "the ability"),
    }
    now = float(world.clock.now()) if world is not None and hasattr(world, "clock") else 0.0
    caster.apply_effect({"type": "status", "name": "Airborne", "tags": [AIRBORNE_TAG], "base_duration": seconds + 2.0}, now)
    if world is not None:
        world.schedule(seconds, lambda: land(caster, target, spell, viewer))
    return 0, _say(windup.get("leave_message"), "{caster_name} leaps high and is gone!", **names)


def land(caster: Any, target: Any, spell: Any, viewer: Any) -> None:
    """The caster comes down: the effects fall on the target if it is still there, and the room is told."""
    from engine.magic.effects import apply_spell_effect
    from engine.utils.utils import format_name_for_display

    world = getattr(caster, "world", None)
    if hasattr(caster, "remove_effects_by_tag"):
        caster.remove_effects_by_tag(AIRBORNE_TAG)
    if not getattr(caster, "is_alive", False) or world is None:
        return
    told = _viewer(world, caster, viewer)
    here = (getattr(caster, "current_region_id", None), getattr(caster, "current_room_id", None))
    there = (getattr(target, "current_region_id", None), getattr(target, "current_room_id", None))
    if not getattr(target, "is_alive", False) or here != there:
        text = "%s comes down with nothing beneath them." % getattr(caster, "name", "Someone")
    else:
        windup = windup_of(spell) or {}
        names = {
            "caster_name": format_name_for_display(told, caster, start_of_sentence=True) if told else getattr(caster, "name", "Someone"),
            "target_name": format_name_for_display(told, target, start_of_sentence=False) if told else getattr(target, "name", "something"),
            "spell_name": getattr(spell, "name", "the ability"),
        }
        landing = _say(windup.get("land_message"), "{caster_name} comes down on {target_name}!", **names)
        _, effect_text = apply_spell_effect(caster, target, spell, told, landing=True)
        text = landing + ("\n" + effect_text if effect_text else "")
    if told is not None and getattr(told, "is_alive", True) and (told.current_region_id, told.current_room_id) == here:
        world.notify_player(told, text)
