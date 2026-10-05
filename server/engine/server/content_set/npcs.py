"""NPC templates: vocabulary, trade and loot, property shapes.

Part of the content-set validator package (`engine/server/content_set/`); see `__init__.py`.
"""

from __future__ import annotations

import copy
import os
import json
import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from engine import conditions as _conditions
from engine.utils.messages import MESSAGES, template_problems
from .abilities import (_ability_ids)
from .core import (ContentSetIssue, _load_definitions, _load_json)
from .definitions import (_load_definition_ids)
from .knowledge import (_knowledge_campaign_ids)


def _validate_faction_rules(
    ruleset: Any,
    issues: list[ContentSetIssue],
    ruleset_path: Optional[Path] = None,
) -> None:
    """`ruleset.factions`: a set's own names for enemies, allies and bystanders.

    The engine's five factions and their attitudes have always been engine
    vocabulary, which is fine until a set wants to call its raiders something
    else -- and then two dozen call sites quietly stop working, because they used
    to ask the question by comparing the string `"hostile"`. The declaration is
    the fix; this is what refuses a malformed one, through the same `issues()`
    the reader uses, so the shape and its refusals cannot drift apart.
    """
    from engine.world import factions as faction_rules

    section = ruleset.get("factions") if isinstance(ruleset, dict) else None
    if section is None:
        return
    if not isinstance(section, dict):
        issues.append(ContentSetIssue(
            "error", str(ruleset_path or "ruleset"), "ruleset.factions must be an object"
        ))
        return

    for problem in faction_rules.issues(faction_rules.RulesetView({"factions": section})):
        issues.append(ContentSetIssue("error", str(ruleset_path or "ruleset"), problem))


def _validate_npc_vocabulary(
    content_root: Path,
    issues: list[ContentSetIssue],
    ruleset: Any = None,
) -> None:
    """The two engine-owned words an NPC template names: `faction`, `behavior_type`.

    Both are closed vocabularies, both are invisible from the content side, and a
    wrong value in either fails *quietly* and completely differently from what the
    author meant: an undeclared faction makes an NPC nobody can fight or talk to
    in the way they intended, and a misspelled `behavior_type` means no AI routine
    at all -- a guard who never moves and never reacts. Warnings, because both
    still load and run; the message names the consequence so the fix is obvious.
    """
    from engine.config import FACTION_DISPOSITIONS, NPC_BEHAVIOR_TYPES
    from engine.world import factions as faction_rules

    declared = faction_rules.dispositions(faction_rules.RulesetView(ruleset))
    known_behaviors = ", ".join(NPC_BEHAVIOR_TYPES)
    for path in sorted((content_root / "npcs").glob("*.json")):
        payload = _load_json(path, issues, "NPC definitions")
        if not isinstance(payload, dict):
            continue
        for template_id, template in payload.items():
            if str(template_id).startswith("_") or not isinstance(template, dict):
                continue
            behavior = template.get("behavior_type")
            if isinstance(behavior, str) and behavior.strip() and behavior.strip() not in NPC_BEHAVIOR_TYPES:
                issues.append(ContentSetIssue(
                    "warning", str(path),
                    f"NPC '{template_id}'.behavior_type '{behavior}' is not one of the engine's "
                    f"behaviours ({known_behaviors}); this NPC will stand still and do nothing",
                ))
            faction = template.get("faction")
            if not isinstance(faction, str) or not faction.strip():
                continue
            if faction.strip() not in declared:
                issues.append(ContentSetIssue(
                    "warning", str(path),
                    f"NPC '{template_id}'.faction '{faction}' is declared nowhere: not an engine "
                    f"faction, and not in this set's ruleset `factions`. It will be treated as a "
                    f"bystander -- no side, no attacks, no reputation. Declare it with a "
                    f"disposition (one of {', '.join(FACTION_DISPOSITIONS)}) to give it one",
                ))


_LOOT_ENTRY_KEYS = ("chance", "quantity", "is_chest")
_STOCK_ENTRY_KEYS = ("item_id", "price_multiplier", "relationship_min")
_GIFT_PREFERENCE_KEYS = ("preferred_item_ids", "preferred_categories", "preferred_gift_tags", "disliked_item_ids", "disliked_gift_tags")


def _validate_npc_trade_and_loot(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """An NPC's `loot_table`, vendor stock, tariff and gift preferences.

    Each reader skips what it cannot use: `NPC.die` drops nothing for an item id
    with no template and `random.randint` raises on a reversed quantity; vendor
    stock with a missing item is left off the list; a misspelt gift-preference
    key is never read, so the NPC simply has no preferences.
    """
    npc_dir = content_root / "npcs"
    if not npc_dir.is_dir():
        return
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    campaign_ids = _knowledge_campaign_ids(content_root, issues)

    def number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    for path in sorted(npc_dir.glob("*.json")):
        payload = _load_json(path, [], "NPC definitions")
        if not isinstance(payload, dict):
            continue
        source = str(path)
        for template_id, template in payload.items():
            if str(template_id).startswith("_") or not isinstance(template, dict):
                continue

            def error(message: str) -> None:
                issues.append(ContentSetIssue("error", source, f"NPC '{template_id}'.{message}"))

            loot = template.get("loot_table")
            if loot is not None:
                if not isinstance(loot, dict):
                    error("loot_table must be an object of item id -> {chance, quantity}")
                    loot = {}
                for item_id, entry in loot.items():
                    label = f"loot_table.{item_id}"
                    if not isinstance(entry, dict):
                        error(f"{label} must be an object with chance and optional quantity")
                        continue
                    for key in entry:
                        if key not in _LOOT_ENTRY_KEYS:
                            error(f"{label}.{key} is not read (known: {', '.join(_LOOT_ENTRY_KEYS)})")
                    if item_id != "gold_value" and not entry.get("is_chest") and item_id not in item_ids:
                        error(f"{label} references missing item '{item_id}' (it is never dropped)")
                    chance = entry.get("chance", 0)
                    if not number(chance) or not 0 <= chance <= 1:
                        error(f"{label}.chance must be a number from 0 to 1")
                    if "quantity" in entry:
                        quantity = entry["quantity"]
                        low = 0 if item_id == "gold_value" else 1
                        if not (isinstance(quantity, list) and len(quantity) == 2
                                and all(isinstance(v, int) and not isinstance(v, bool) and v >= low for v in quantity)):
                            error(f"{label}.quantity must be [min, max], integers of at least {low}")
                        elif quantity[0] > quantity[1]:
                            error(f"{label}.quantity minimum ({quantity[0]}) is greater than its maximum ({quantity[1]})")
                    if "is_chest" in entry and not isinstance(entry["is_chest"], bool):
                        error(f"{label}.is_chest must be true or false")

            properties = template.get("properties")
            if not isinstance(properties, dict):
                continue
            stock = properties.get("sells_items")
            if stock is not None:
                if not isinstance(stock, list):
                    error("properties.sells_items must be an array of {item_id, price_multiplier}")
                    stock = []
                for index, entry in enumerate(stock):
                    label = f"properties.sells_items[{index}]"
                    if not isinstance(entry, dict):
                        error(f"{label} must be an object")
                        continue
                    for key in entry:
                        if key not in _STOCK_ENTRY_KEYS:
                            error(f"{label}.{key} is not read (known: {', '.join(_STOCK_ENTRY_KEYS)})")
                    if entry.get("item_id") not in item_ids:
                        error(f"{label}.item_id references missing item '{entry.get('item_id')}' (it is left off the list)")
                    if "price_multiplier" in entry and (not number(entry["price_multiplier"]) or entry["price_multiplier"] <= 0):
                        error(f"{label}.price_multiplier must be a positive number")
                    if "relationship_min" in entry and (not isinstance(entry["relationship_min"], int) or isinstance(entry["relationship_min"], bool) or not 0 <= entry["relationship_min"] <= 100):
                        error(f"{label}.relationship_min must be an integer from 0 to 100")
            if "sell_rate_multiplier" in properties and (not number(properties["sell_rate_multiplier"]) or properties["sell_rate_multiplier"] < 0):
                error("properties.sell_rate_multiplier must be a non-negative number")
            tariff = properties.get("tariff")
            if tariff is not None:
                if not isinstance(tariff, dict):
                    error("properties.tariff must be an object with campaign_id and rate")
                else:
                    if tariff.get("campaign_id") not in campaign_ids:
                        error(f"properties.tariff.campaign_id references missing campaign '{tariff.get('campaign_id')}' (the tariff never applies)")
                    if not number(tariff.get("rate")) or tariff.get("rate") < 0:
                        error("properties.tariff.rate must be a non-negative number")
            preferences = properties.get("gift_preferences")
            if preferences is not None:
                if not isinstance(preferences, dict):
                    error("properties.gift_preferences must be an object")
                    continue
                for key, values in preferences.items():
                    label = f"properties.gift_preferences.{key}"
                    if key not in _GIFT_PREFERENCE_KEYS:
                        error(f"{label} is not read (known: {', '.join(_GIFT_PREFERENCE_KEYS)})")
                        continue
                    if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                        error(f"{label} must be an array of non-empty strings")
                        continue
                    if key.endswith("_item_ids"):
                        for value in values:
                            if value not in item_ids:
                                error(f"{label} references missing item '{value}'")


# The properties the engine reads from an NPC. `properties` is open-ended on purpose (a set may keep its own
# notes there), so an unknown key is only reported when it is a near miss of one of these.
_NPC_PROPERTY_KEYS = (
    "aggression", "flee_threshold", "wander_chance", "spell_cast_chance", "move_cooldown", "attack_cooldown", "respawn_cooldown",
    "essential", "pacifist", "untargetable", "phases", "hides_when_hurt", "falls_when_defeated", "rejoin_health", "recovering", "unique", "companion", "owner_id", "summon_duration", "creation_time", "is_summoned",
    "despawn_message", "dialogue", "custom_dialog", "loot_tags", "sells_items", "is_vendor", "is_dealer",
    "is_collector", "can_repair", "can_give_generic_quests", "can_expand_houses", "sells_houses",
    "can_unlock_chests", "work_location", "tariff", "gift_preferences", "relationship_milestones",
    "weapon_damage_type", "damage_reactions", "special_abilities", "is_escort_target", "escort_quest_id",
    "ambient_wanderer", "buys_item_types", "dealer_game", "level_band", "weather_hazard_multipliers",
)


def _npc_property_near_misses(properties: dict, label: str) -> list[str]:
    import difflib

    messages = []
    for key in properties:
        if key in _NPC_PROPERTY_KEYS or str(key).startswith(("_", "minigame_", "house_")):
            continue
        near = difflib.get_close_matches(str(key), _NPC_PROPERTY_KEYS, n=1, cutoff=0.8)
        if near:
            messages.append(f"{label}.{key} is not a property the engine reads; did you mean '{near[0]}'?")
    return messages


def _phase_errors(phases: Any, label: str, spell_ids: set[str], npc_ids: set[str]) -> list[str]:
    """`properties.phases` (`npcs/phases.py`): a list of phases the creature cycles through in a fight."""
    from engine.npcs.phases import HINT_KEYS, PHASE_KEYS

    if not isinstance(phases, list) or not phases:
        return [f"{label}.phases must be a non-empty list of phases"]
    errors: list[str] = []
    for index, phase in enumerate(phases):
        where = f"{label}.phases[{index}]"
        if not isinstance(phase, dict):
            errors.append(f"{where} must be an object")
            continue
        for key in phase:
            if key not in PHASE_KEYS:
                errors.append(f"{where}.{key} is not read (known: {', '.join(PHASE_KEYS)})")
        seconds = phase.get("seconds")
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds < 1:
            errors.append(f"{where}.seconds is required: how long the phase lasts, a number of at least 1")
        for key in ("name", "message", "counter", "miss_text"):
            if key in phase and not isinstance(phase[key], str):
                errors.append(f"{where}.{key} must be text")
        if "untouchable" in phase and not isinstance(phase["untouchable"], bool):
            errors.append(f"{where}.untouchable must be true or false")
        if "resistances" in phase:
            from engine.npcs.phases import RESISTANCE_RANGE

            table = phase["resistances"]
            if not isinstance(table, dict) or not table:
                errors.append(f"{where}.resistances must be an object of damage type -> percent")
            else:
                for damage_type, percent in table.items():
                    if isinstance(percent, bool) or not isinstance(percent, (int, float)) or not RESISTANCE_RANGE[0] <= percent <= RESISTANCE_RANGE[1]:
                        errors.append(f"{where}.resistances.{damage_type} must be a percent from {RESISTANCE_RANGE[0]} to {RESISTANCE_RANGE[1]} (100 takes nothing; over 100 absorbs the blow as healing)")
        if "counter_cooldown" in phase:
            value = phase["counter_cooldown"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                errors.append(f"{where}.counter_cooldown must be a number of seconds, 0 or more")
        if isinstance(phase.get("counter"), str) and spell_ids and phase["counter"] not in spell_ids:
            errors.append(f"{where}.counter names ability '{phase['counter']}', which this content set does not define")
        if "counter" in phase and phase.get("untouchable") is not True:
            errors.append(f"{where}.counter only answers a blow struck at an untouchable phase: set untouchable, or drop the counter")
        if "counter_hint" in phase and not phase.get("counter"):
            errors.append(f"{where}.counter_hint is told when the counter is: there is no counter")
        for key in ("hint", "counter_hint"):
            if key not in phase:
                continue
            hint = phase[key]
            if not isinstance(hint, dict):
                errors.append(f"{where}.{key} must be an object {{npc, text}}")
                continue
            for hint_key in hint:
                if hint_key not in HINT_KEYS:
                    errors.append(f"{where}.{key}.{hint_key} is not read (known: {', '.join(HINT_KEYS)})")
            if not isinstance(hint.get("text"), str) or not hint["text"].strip():
                errors.append(f"{where}.{key}.text is required")
            if not isinstance(hint.get("npc"), str) or not hint["npc"].strip():
                errors.append(f"{where}.{key}.npc is required: who says it")
            elif npc_ids and hint["npc"] not in npc_ids:
                errors.append(f"{where}.{key}.npc names '{hint['npc']}', which is not an NPC of this content set")
    return errors


def _npc_property_errors(properties: dict, label: str, room_refs: set[str]) -> list[str]:
    """What `npc_factory.py` reads from an NPC's `properties`, whether the values
    come from the template or from a room placement's `properties_override`
    (merged over the template's). Other keys are open-ended and not checked."""
    errors: list[str] = []
    for field in ("aggression", "flee_threshold", "wander_chance", "spell_cast_chance"):
        value = properties.get(field)
        if field in properties and (isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1):
            errors.append(f"{label}.{field} must be a number from 0 to 1")
    if "move_cooldown" in properties:
        value = properties["move_cooldown"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(f"{label}.move_cooldown must be a non-negative integer")
    if "rejoin_health" in properties:
        value = properties["rejoin_health"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1:
            errors.append(f"{label}.rejoin_health must be a number above 0 and up to 1 (the health fraction a hurt companion rejoins at)")
    if "attack_cooldown" in properties:
        value = properties["attack_cooldown"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.5 <= value <= 120:
            errors.append(f"{label}.attack_cooldown must be a number of seconds from 0.5 to 120 (the pause between its blows)")
    if "despawn_message" in properties and not isinstance(properties["despawn_message"], str):
        errors.append(f"{label}.despawn_message must be text (how a summoned creature leaves)")
    if "unique" in properties and not isinstance(properties["unique"], bool):
        errors.append(f"{label}.unique must be true or false (true: referred to as \"the\" rather than \"a\"/\"an\")")
    if "hides_when_hurt" in properties and not isinstance(properties["hides_when_hurt"], bool):
        errors.append(f"{label}.hides_when_hurt must be true or false (true: a hurt companion hides in the room until the fight is over)")
    if "falls_when_defeated" in properties and not isinstance(properties["falls_when_defeated"], bool):
        errors.append(f"{label}.falls_when_defeated must be true or false (true: a companion struck down falls and can be revived, instead of dying)")
    if "untargetable" in properties and not isinstance(properties["untargetable"], bool):
        errors.append(f"{label}.untargetable must be true or false (true: no enemy picks it as a target and nothing hurts it)")
    if "pacifist" in properties and not isinstance(properties["pacifist"], bool):
        errors.append(f"{label}.pacifist must be true or false (true: never fights back, never starts a fight)")
    if "essential" in properties and not isinstance(properties["essential"], bool):
        errors.append(f"{label}.essential must be true or false (true: cannot be killed unless recruited as a companion)")
    if "respawn_cooldown" in properties:
        value = properties["respawn_cooldown"]
        # Summoned/minion definitions use -1 as their explicit no-respawn
        # sentinel: a real engine convention, not a malformed duration.
        if isinstance(value, bool) or not isinstance(value, int) or value < -1:
            errors.append(f"{label}.respawn_cooldown must be an integer of -1 or greater")
    for field in ("can_unlock_chests", "sells_houses"):
        if field in properties and not isinstance(properties[field], bool):
            errors.append(f"{label}.{field} must be a boolean")
    if "loot_tags" in properties:
        # npc.py::_matches_ambient_loot_pool drops anything but a list, so a
        # bare string would leave the NPC out of every tag-selected pool.
        tags = properties["loot_tags"]
        if not isinstance(tags, list) or not all(isinstance(tag, str) and tag.strip() for tag in tags):
            errors.append(f"{label}.loot_tags must be an array of non-empty strings")
    if "work_location" in properties:
        work_location = properties["work_location"]
        if not isinstance(work_location, str) or work_location not in room_refs:
            errors.append(f"{label}.work_location must name an authored region:room")
    return errors


def _validate_npc_template_runtime_shapes(
    content_root: Path,
    issues: list[ContentSetIssue],
) -> None:
    """Refuse malformed NPC values the runtime otherwise silently normalises.

    The template editor writes these fields directly.  A bad probability makes an
    NPC act in ways its author cannot reason about, a missing inventory/spell
    reference disappears at load, and a malformed direct schedule can reach the
    movement loop as a half-entry.  Keeping the contract here gives every editor
    surface one honest answer before a world is started.

    This intentionally validates *direct* schedules only.  The separate
    ``ruleset.npc_schedules`` generator has a broader, setting-owned vocabulary
    and remains read-only until it has its own complete validator and editor.
    """
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    spell_ids = _ability_ids(content_root, issues)

    room_refs: set[str] = set()
    for region_path in sorted((content_root / "regions").glob("*.json")):
        region = _load_json(region_path, issues, "region definitions")
        if not isinstance(region, dict):
            continue
        region_id = str(region.get("region_id", region_path.stem)).strip()
        rooms = region.get("rooms", {})
        if not region_id or not isinstance(rooms, dict):
            continue
        for room_id in rooms:
            if isinstance(room_id, str) and room_id.strip():
                room_refs.add(f"{region_id}:{room_id}")

    all_npc_ids: set[str] = set()
    for path in sorted((content_root / "npcs").glob("*.json")):
        known = _load_json(path, [], "NPC definitions")
        if isinstance(known, dict):
            all_npc_ids |= {str(key) for key in known if not str(key).startswith("_")}

    for path in sorted((content_root / "npcs").glob("*.json")):
        payload = _load_json(path, issues, "NPC definitions")
        if not isinstance(payload, dict):
            continue
        for npc_id, template in payload.items():
            if str(npc_id).startswith("_") or not isinstance(template, dict):
                continue
            label = f"NPC '{npc_id}'"

            for field in ("friendly",):
                if field in template and not isinstance(template[field], bool):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.{field} must be a boolean"))
            for field in ("level",):
                if field in template:
                    value = template[field]
                    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                        issues.append(ContentSetIssue("error", str(path), f"{label}.{field} must be an integer of at least 1"))
            for field in ("health", "max_mana", "attack_power", "defense"):
                if field in template:
                    value = template[field]
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                        issues.append(ContentSetIssue("error", str(path), f"{label}.{field} must be a non-negative number"))
            if "max_health" in template:
                value = template["max_health"]
                if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                    issues.append(ContentSetIssue("error", str(path), f"{label}.max_health must be a whole number of at least 1 (leave it out to derive it from level and constitution)"))
                elif isinstance(template.get("health"), (int, float)) and not isinstance(template.get("health"), bool) and template["health"] > value:
                    issues.append(ContentSetIssue(
                        "warning", str(path),
                        f"{label}.health {template['health']} is above its max_health {value}; it starts at {value}",
                    ))

            properties = template.get("properties", {})
            if properties is not None and not isinstance(properties, dict):
                issues.append(ContentSetIssue("error", str(path), f"{label}.properties must be an object"))
                properties = {}
            if isinstance(properties, dict):
                for message in _npc_property_errors(properties, f"{label}.properties", room_refs):
                    issues.append(ContentSetIssue("error", str(path), message))
                for message in _npc_property_near_misses(properties, f"{label}.properties"):
                    issues.append(ContentSetIssue("warning", str(path), message))
                if "phases" in properties:
                    for message in _phase_errors(properties["phases"], f"{label}.properties", spell_ids, all_npc_ids):
                        issues.append(ContentSetIssue("error", str(path), message))

            if "patrol_points" in template:
                points = template["patrol_points"]
                if not isinstance(points, list) or any(not isinstance(point, str) or not point.strip() for point in points):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.patrol_points must be an array of non-empty room ids"))
            if "usable_spells" in template:
                spells = template["usable_spells"]
                if not isinstance(spells, list):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.usable_spells must be an array"))
                else:
                    for spell_id in spells:
                        if not isinstance(spell_id, str) or spell_id not in spell_ids:
                            issues.append(ContentSetIssue("error", str(path), f"{label}.usable_spells references a missing ability: {spell_id!r}"))
            if "initial_inventory" in template:
                inventory = template["initial_inventory"]
                if not isinstance(inventory, list):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.initial_inventory must be an array"))
                else:
                    for index, entry in enumerate(inventory):
                        entry_label = f"{label}.initial_inventory[{index}]"
                        if not isinstance(entry, dict):
                            issues.append(ContentSetIssue("error", str(path), f"{entry_label} must be an object"))
                            continue
                        item_id = entry.get("item_id")
                        if not isinstance(item_id, str) or item_id not in item_ids:
                            issues.append(ContentSetIssue("error", str(path), f"{entry_label}.item_id references a missing item template"))
                        if "quantity" in entry:
                            quantity = entry["quantity"]
                            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
                                issues.append(ContentSetIssue("error", str(path), f"{entry_label}.quantity must be a positive integer"))

            if "equipment" in template:
                from engine.config import EQUIPMENT_SLOTS, EQUIPMENT_VALID_SLOTS_BY_TYPE

                gear = template["equipment"]
                if not isinstance(gear, dict):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.equipment must be an object of slot -> item id"))
                else:
                    item_definitions = _load_definitions(content_root / "items")
                    for slot, gear_id in gear.items():
                        gear_label = f"{label}.equipment[{slot!r}]"
                        if slot not in EQUIPMENT_SLOTS:
                            issues.append(ContentSetIssue("error", str(path), f"{gear_label} is not a slot (known: {', '.join(EQUIPMENT_SLOTS)})"))
                        if not isinstance(gear_id, str) or gear_id not in item_ids:
                            issues.append(ContentSetIssue("error", str(path), f"{gear_label} references a missing item template"))
                            continue
                        definition = item_definitions.get(gear_id, {})
                        declared = (definition.get("properties") or {}).get("equip_slot") if isinstance(definition, dict) else None
                        fits = [declared] if isinstance(declared, str) else declared if isinstance(declared, list) else \
                            EQUIPMENT_VALID_SLOTS_BY_TYPE.get(str(definition.get("type", "")), [])
                        if slot in EQUIPMENT_SLOTS and slot not in fits:
                            issues.append(ContentSetIssue("error", str(path), f"{gear_label}: {gear_id} cannot be worn there (it fits: {', '.join(fits) or 'nowhere'})"))

            if "schedule" not in template:
                continue
            schedule = template["schedule"]
            if not isinstance(schedule, dict):
                issues.append(ContentSetIssue("error", str(path), f"{label}.schedule must be an object keyed by hour"))
                continue
            for hour, entry in schedule.items():
                try:
                    hour_number = int(hour)
                except (TypeError, ValueError):
                    hour_number = -1
                entry_label = f"{label}.schedule[{hour!r}]"
                if not 0 <= hour_number <= 23:
                    issues.append(ContentSetIssue("error", str(path), f"{entry_label} must use an hour from 0 to 23"))
                if not isinstance(entry, dict):
                    issues.append(ContentSetIssue("error", str(path), f"{entry_label} must be an object"))
                    continue
                for field in ("region_id", "room_id", "activity"):
                    if field in entry and not isinstance(entry[field], str):
                        issues.append(ContentSetIssue("error", str(path), f"{entry_label}.{field} must be a string"))
                region_id = entry.get("region_id")
                room_id = entry.get("room_id")
                if isinstance(region_id, str) and isinstance(room_id, str) and f"{region_id}:{room_id}" not in room_refs:
                    issues.append(ContentSetIssue("error", str(path), f"{entry_label} names missing room '{region_id}:{room_id}'"))
                if "behavior_override" in entry and entry["behavior_override"] != "aggressive":
                    issues.append(ContentSetIssue(
                        "error", str(path),
                        f"{entry_label}.behavior_override must be 'aggressive' (the only override the scheduler reads)",
                    ))


_SIMPLE_RULESET_SECTION_KEYS = {
    "locksmithing": ("skill",),
    "economy": ("currency_name",),
    "calendar": ("day_names", "month_names", "start_time"),
    "spawning": ("no_spawn_keywords",),
    "elites": ("chance", "stat_multiplier", "loot_guaranteed_chance", "loot_quantity_multiplier", "name_pattern", "prefixes"),
    "player_defaults": ("player_class", "magic", "starting_inventory"),
    "npc_naming": ("first_names", "random_name_pattern"),
    "status": ("stats",),
    "combat": ("retreat", "experience_sharing", "pacing", "additional_blocked_command_names", "additional_combat_message_tokens"),
    "companions": ("max",),
    "messages": tuple(MESSAGES),
}
