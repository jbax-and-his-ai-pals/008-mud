# engine/core/kill_credit.py
"""Who gets experience when something dies: everyone who hurt it, in proportion.

Each creature keeps a tally of the damage dealt to it, by whom. A player's own blows count for them,
and so do those of anything they own (a summon, a companion); anyone else who fought it (an NPC ally,
another player) is on the tally under their own name. When it dies, each player on the tally earns a
share of the experience equal to their share of the damage, however many of them there are and whoever
struck the last blow. NPCs earn nothing, so their share is simply not paid out.

A share under `MIN_SHARE` earns nothing (a stray hit does not make anyone a participant), except for the
player who landed the killing blow, who always gets at least that.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

# How a kill's experience is shared (`ruleset.combat.experience_sharing.mode`):
#   proportional  each participant earns their share of the damage (the default)
#   equal         every participant earns the same share, whoever did more
#   killer        the one who lands the killing blow earns all of it
EXPERIENCE_SHARING_MODES = ("proportional", "equal", "killer")
DEFAULT_SHARING_MODE = "proportional"
MIN_SHARE = 0.05   # the default for `min_share`: the least a player must have done to be a participant
DEFAULT_MEMORY_SECONDS = 300   # the default for `memory_seconds`: how long a blow counts toward the kill (0: for ever)


def sharing_settings(world: Any):
    """(mode, min_share) the content set asks for, with the defaults for anything it does not say."""
    section = {}
    try:
        section = world.ruleset_section("combat").get("experience_sharing", {}) if world is not None else {}
    except Exception:  # noqa: BLE001 - a world without rules plays by the defaults
        section = {}
    section = section if isinstance(section, dict) else {}
    mode = section.get("mode")
    minimum = section.get("min_share")
    valid_minimum = isinstance(minimum, (int, float)) and not isinstance(minimum, bool) and 0 <= minimum < 1
    return (mode if mode in EXPERIENCE_SHARING_MODES else DEFAULT_SHARING_MODE,
            float(minimum) if valid_minimum else MIN_SHARE)


def memory_seconds(world: Any) -> float:
    """How long a blow stays on the tally (`ruleset.combat.experience_sharing.memory_seconds`); 0 is for ever."""
    try:
        section = world.ruleset_section("combat").get("experience_sharing", {}) if world is not None else {}
    except Exception:  # noqa: BLE001 - a world without rules plays by the defaults
        section = {}
    value = section.get("memory_seconds") if isinstance(section, dict) else None
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return float(DEFAULT_MEMORY_SECONDS)


def _now(world: Any) -> float:
    clock = getattr(world, "clock", None)
    return float(clock.now()) if clock is not None else 0.0


def _credited(attacker: Any, world: Any) -> Any:
    """Whom a blow is counted for: an owned creature's blows are its owner's."""
    props = getattr(attacker, "properties", None)
    owner_id = props.get("owner_id") if isinstance(props, dict) else None
    if owner_id and world is not None and hasattr(world, "get_player_by_id"):
        owner = world.get_player_by_id(owner_id)
        if owner is not None:
            return owner
    return attacker


def record_damage(victim: Any, attacker: Any, amount: float, health_before: Optional[float] = None) -> None:
    """Note that `attacker` did `amount` damage to `victim`, who had `health_before` health when it landed."""
    if attacker is None or attacker is victim or not amount or amount <= 0:
        return
    world = getattr(victim, "world", None)
    who = _credited(attacker, world)
    # A creature that was at full health before this blow is in a new fight: whatever was hurting it
    # before (and has long since healed) does not share in this one.
    max_health = getattr(victim, "max_health", 0) or 0
    if health_before is not None and max_health and health_before >= max_health:
        clear(victim)
    log = victim.__dict__.setdefault("_damage_log", {})
    key = str(getattr(who, "obj_id", id(who)))
    entry = log.get(key)
    now = _now(world)
    if entry is None:
        log[key] = [who, float(amount), now]
    else:
        entry[1] += float(amount)
        entry[2] = now


def player_shares(victim: Any) -> List[Tuple[Any, float]]:
    """(player, share of the damage) for each player who did enough of it. Empty when nothing is known."""
    from engine.player import Player

    mode, minimum = sharing_settings(getattr(victim, "world", None))
    if mode == "killer":
        return []   # nobody is a participant: the killing blow takes it all (share_of answers 1.0)
    log = getattr(victim, "__dict__", {}).get("_damage_log") or {}
    world = getattr(victim, "world", None)
    memory = memory_seconds(world)
    now = _now(world)
    # Blows from long ago (a fight that was left and has been picked up again) no longer count.
    counted = [(who, damage) for who, damage, last in log.values() if memory <= 0 or now - last <= memory]
    total = sum(damage for _who, damage in counted)
    if total <= 0:
        return []
    shares = [
        (who, damage / total) for who, damage in counted
        if isinstance(who, Player) and damage / total >= minimum
    ]
    if mode == "equal" and shares:
        shares = [(who, 1.0 / len(shares)) for who, _ in shares]
    return shares


def share_of(player: Any, shares: List[Tuple[Any, float]], world: Any = None) -> float:
    """What fraction of the experience `player` has earned: their share, at least MIN_SHARE, or all of it
    when no tally exists (a kill that nothing recorded is the killer's, as it always was)."""
    if not shares:
        return 1.0
    mine = next((share for who, share in shares if who is player), 0.0)
    return max(mine, sharing_settings(world)[1])


def experience_for(player: Any, victim: Any, share: float, formula: Any = None) -> int:
    """`share` of what `player` would earn for `victim`; `formula` is the caller's experience function."""
    from engine.utils.utils import calculate_xp_gain

    calculate_xp_gain = formula or calculate_xp_gain
    progression = player.runtime_state.progression
    if progression is None:
        return 0
    base = calculate_xp_gain(progression.level, getattr(victim, "level", 1), getattr(victim, "max_health", 10))
    return max(1, int(round(base * share))) if base > 0 else 0


def roll_gold(victim: Any) -> int:
    """The money `victim` drops this time (its loot table's `gold_value`), before anyone's share of it."""
    import random

    table = getattr(victim, "loot_table", None)
    data = table.get("gold_value") if isinstance(table, dict) else None
    if isinstance(data, dict) and random.random() < data.get("chance", 0.0):
        low, high = data.get("quantity", [1, 1])
        return random.randint(low, high)
    return 0


def gold_for(drop: int, share: float) -> int:
    """`share` of the money dropped, at least 1 when any dropped."""
    return max(1, int(round(drop * share))) if drop > 0 else 0


def award_participants(world: Any, victim: Any, shares: List[Tuple[Any, float]], skip: Any = None,
                       formula: Any = None, gold: int = 0, inline: Any = None) -> str:
    """Give each player on the tally their experience and share of the money (not `skip`, who is paid with
    the kill itself) and tell them, wherever they are: `inline` is told by the text this returns, which the
    caller puts in the kill's own message; everyone else by a notice. The tally is spent."""
    from engine.utils.utils import format_name_for_display

    told_inline = ""
    for who, share in shares:
        if who is skip:
            continue
        xp = experience_for(who, victim, share, formula)
        coins = gold_for(gold, share) if getattr(who.runtime_state, "gold", None) is not None else 0
        if xp <= 0 and coins <= 0:
            continue
        lines = []
        if xp > 0:
            leveled, level_msg = who.gain_experience(xp)
            name = format_name_for_display(who, victim, start_of_sentence=False)
            lines.append(f"You gain {xp} experience for your part in defeating {name}.")
            if leveled and level_msg:
                lines.append(level_msg)
        if coins > 0:
            who.runtime_state.gold += coins
            lines.append(f"You find {coins} {world.currency_name()}.")
        text = "\n".join(lines)
        if who is inline:
            told_inline = text
        elif hasattr(world, "notify_player"):
            world.notify_player(who, text)
    clear(victim)
    return told_inline


def clear(victim: Any) -> None:
    getattr(victim, "__dict__", {}).pop("_damage_log", None)
