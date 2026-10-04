"""Ability definitions.

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
from .core import (ContentSetIssue, _load_json)
from .references import (_format_placeholders)


def _condition_issues(node: Any, where: str, path: Path) -> list[ContentSetIssue]:
    """Walk a condition tree and report every malformed or unknown node.

    Shared by titles (P4) and dialogue (P5): both gate content on the same
    predicate language, and a typo in either must fail validation rather than
    silently leave a gate shut (or, worse, open).
    """
    from engine.conditions import KNOWN_KINDS

    found: list[ContentSetIssue] = []

    def walk(current: Any, label: str) -> None:
        if current is None or isinstance(current, (str, int, float, bool)):
            return
        if isinstance(current, list):
            for index, child in enumerate(current):
                walk(child, "%s[%d]" % (label, index))
            return
        if not isinstance(current, dict):
            found.append(ContentSetIssue("error", str(path), f"{label} must be a condition object"))
            return
        for composite in ("all", "any"):
            if composite in current:
                walk(current[composite], "%s.%s" % (label, composite))
                return
        if "not" in current:
            walk(current["not"], "%s.not" % label)
            return
        kind = str(current.get("kind", "")).strip()
        if not kind:
            found.append(ContentSetIssue("error", str(path), f"{label} has no 'kind'"))
        elif kind not in KNOWN_KINDS:
            found.append(ContentSetIssue(
                "error", str(path),
                f"{label} uses unknown condition kind '{kind}' "
                f"(known: {', '.join(sorted(KNOWN_KINDS))})",
            ))

    walk(node, where)
    return found


def _ability_ids(content_root: Path, issues: list[ContentSetIssue]) -> set[str]:
    """Every ability id this set defines, read from the files the engine reads.

    Not from `SPELL_REGISTRY`: that registry is populated when a `World` boots,
    and validation runs *before* one exists (`game_manager.py` loads the content
    set, then constructs the world). Reading it here returned an empty set, and
    an empty id set means "skip this check" -- so every `spell_known`,
    `teach_spell` and `known_spells` reference in the game was unchecked while
    the validator reported success.

    The directory choice mirrors `load_spells_from_json`: `abilities/` is what a
    set that does not call them spells uses, `magic/` is the older name, and the
    first one that exists wins.
    """
    for candidate in ("abilities", "magic"):
        directory = content_root / candidate
        if not directory.is_dir():
            continue
        ability_ids: set[str] = set()
        for path in sorted(directory.glob("*.json")):
            payload = _load_json(path, issues, "ability definitions")
            if isinstance(payload, dict):
                ability_ids |= {str(k) for k in payload if not str(k).startswith("_")}
        return ability_ids
    return set()


def _validate_abilities(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """`abilities/*.json` (else `magic/`): what `Spell(**entry)` builds and what
    `magic/effects.py::apply_spell_effect` then does with it.

    An unknown key is a `TypeError` and a missing name/description or an empty
    effects list a `ValueError`, and the registry skips that ability. Past the
    constructor the failures are silent: a target type the cast path does not
    resolve casts on yourself, an effect type nothing executes does nothing, a
    key its type does not read is ignored, an `apply_effect` without
    `effect_data` does nothing, and a message placeholder the engine does not
    fill raises mid-cast (the cast and remove-curse messages are unguarded).
    """
    import inspect

    from engine.magic.spell import (
        ABILITY_EFFECT_FIELDS, ABILITY_MESSAGE_PLACEHOLDERS, ABILITY_TARGET_TYPES, Spell,
    )

    directory = next((content_root / name for name in ("abilities", "magic") if (content_root / name).is_dir()), None)
    if directory is None:
        return
    parameters = inspect.signature(Spell.__init__).parameters
    accepted = [name for name in parameters if name not in ("self", "spell_id")]
    required = [name for name in accepted if parameters[name].default is inspect.Parameter.empty]
    npc_behaviors: dict[str, Any] = {}
    for npc_path in sorted((content_root / "npcs").glob("*.json")):
        npc_payload = _load_json(npc_path, [], "NPC definitions")
        if isinstance(npc_payload, dict):
            npc_behaviors.update({
                str(key): value.get("behavior_type") for key, value in npc_payload.items()
                if isinstance(value, dict) and not str(key).startswith("_")
            })
    damage_types: set[str] = set()
    elements_path = content_root / "combat" / "elements.json"
    elements = _load_json(elements_path, [], "combat vocabulary") if elements_path.is_file() else None
    if isinstance(elements, dict) and isinstance(elements.get("valid_damage_types"), list):
        damage_types = {str(value) for value in elements["valid_damage_types"]}

    def number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def integer(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    seen: dict[str, str] = {}
    for path in sorted(directory.glob("*.json")):
        payload = _load_json(path, issues, "ability definitions")
        if payload is None:
            continue
        source = str(path)
        if not isinstance(payload, dict):
            issues.append(ContentSetIssue("error", source, "an abilities file must be an object of ability id -> ability"))
            continue
        for ability_id, entry in payload.items():
            if str(ability_id).startswith("_"):
                continue
            label = str(ability_id)

            def error(message: str) -> None:
                issues.append(ContentSetIssue("error", source, f"{label}: {message}"))

            if ability_id in seen:
                issues.append(ContentSetIssue("warning", source, f"{label}: also defined in {seen[ability_id]}; the file loaded last wins"))
            seen[ability_id] = path.name
            if not isinstance(entry, dict):
                error("must be an object")
                continue
            for key in entry:
                if key not in accepted:
                    error(f"'{key}' is not an ability field, so the engine does not load this ability (known: {', '.join(accepted)})")
            for key in required:
                if key not in entry:
                    error(f"{key} is required, so the engine does not load this ability")
            for key in ("name", "description"):
                if key in entry and (not isinstance(entry[key], str) or (key == "name" and not entry[key].strip())):
                    error(f"{key} must be a {'non-empty ' if key == 'name' else ''}string")
            for key, minimum in (("mana_cost", 0), ("level_required", 1)):
                if key in entry and (not integer(entry[key]) or entry[key] < minimum):
                    error(f"{key} must be a whole number of at least {minimum}")
            if "cooldown" in entry and (not number(entry["cooldown"]) or entry["cooldown"] < 0):
                error("cooldown must be a number of seconds, 0 or more")
            if "health_cost_fraction" in entry and (not number(entry["health_cost_fraction"]) or not 0 <= entry["health_cost_fraction"] < 1):
                error("health_cost_fraction must be a number from 0 up to (not including) 1: the part of the caster's maximum health each cast costs")
            target_type = entry.get("target_type", "enemy")
            if target_type not in ABILITY_TARGET_TYPES:
                error(f"target_type '{target_type}' is not one the cast command resolves (known: {', '.join(ABILITY_TARGET_TYPES)}), so it is cast on yourself")
            for key, names in ABILITY_MESSAGE_PLACEHOLDERS.items():
                if key not in entry:
                    continue
                if not isinstance(entry[key], str):
                    error(f"{key} must be a string")
                    continue
                try:
                    unknown = sorted(_format_placeholders(entry[key]) - set(names))
                except ValueError as problem:
                    error(f"{key} is not a valid message template ({problem})")
                    continue
                if unknown:
                    error(f"{key} uses {', '.join('{' + name + '}' for name in unknown)}, which the engine does not fill (it offers {', '.join('{' + name + '}' for name in names)})")

            effects = entry.get("effects")
            if not isinstance(effects, list) or not effects:
                error("effects must be a non-empty array, so the engine does not load this ability")
                continue
            for index, effect in enumerate(effects):
                e_label = f"effects[{index}]"
                if not isinstance(effect, dict):
                    error(f"{e_label} must be an object")
                    continue
                effect_type = effect.get("type")
                if effect_type not in ABILITY_EFFECT_FIELDS:
                    error(f"{e_label}.type {effect_type!r} is not an effect the engine executes (known: {', '.join(ABILITY_EFFECT_FIELDS)}), so it does nothing")
                    continue
                reads = ("type", "damage_type") + ABILITY_EFFECT_FIELDS[effect_type]
                for key in effect:
                    if not str(key).startswith("_") and key not in reads:
                        error(f"{e_label}.{key} is not read by a {effect_type} effect (it reads: {', '.join(reads[1:]) or 'nothing else'})")
                for key in ("damage_type", "dot_damage_type"):
                    if key in effect and (not isinstance(effect[key], str) or (damage_types and effect[key] not in damage_types)):
                        error(f"{e_label}.{key} {effect[key]!r} is not a damage type combat/elements.json declares")
                if "value" in effect and not number(effect["value"]):
                    error(f"{e_label}.value must be a number")
                for key in ("dot_duration", "base_duration", "dot_tick_interval"):
                    if key in effect and (not number(effect[key]) or effect[key] <= 0):
                        error(f"{e_label}.{key} must be a number of seconds above 0")
                if "dot_damage_per_tick" in effect and not number(effect["dot_damage_per_tick"]):
                    error(f"{e_label}.dot_damage_per_tick must be a number")
                if "dot_name" in effect and (not isinstance(effect["dot_name"], str) or not effect["dot_name"].strip()):
                    error(f"{e_label}.dot_name must be a non-empty string (the effect is refreshed and expired by its name)")
                data = effect.get("effect_data")
                if "effect_data" in effect and not isinstance(data, dict):
                    error(f"{e_label}.effect_data must be an object")
                    data = None
                if effect_type == "apply_effect":
                    if not data:
                        error(f"{e_label} is an apply_effect with no effect_data, so it does nothing")
                    else:
                        if not isinstance(data.get("name"), str) or not data["name"].strip():
                            error(f"{e_label}.effect_data.name is required (the effect is refreshed and expired by its name)")
                        if data.get("type") == "stat_mod":
                            modifiers = data.get("modifiers")
                            if not isinstance(modifiers, dict) or not modifiers or not all(number(v) for v in modifiers.values()):
                                error(f"{e_label}.effect_data.modifiers must be a non-empty object of stat -> number for a stat_mod")
                        duration = data.get("base_duration", effect.get("dot_duration", effect.get("base_duration")))
                        if duration is None:
                            issues.append(ContentSetIssue("warning", source, f"{label}: {e_label} has no duration (effect_data.base_duration or dot_duration), so it never wears off"))
                        elif not number(duration) or duration <= 0:
                            error(f"{e_label}.effect_data.base_duration must be a number of seconds above 0")
                elif data is not None:
                    tags = data.get("tags")
                    extra = sorted(str(key) for key in data if key != "tags")
                    if extra:
                        error(f"{e_label}.effect_data.{extra[0]} is not read (a {effect_type} effect reads only effect_data.tags)")
                    if not isinstance(tags, list) or not tags or not all(isinstance(tag, str) and tag.strip() for tag in tags):
                        error(f"{e_label}.effect_data.tags must be a non-empty array of tags")
                if effect_type == "summon":
                    template = effect.get("summon_template_id")
                    if not isinstance(template, str) or not template.strip():
                        error(f"{e_label}.summon_template_id is required, so nothing is summoned")
                    elif template not in npc_behaviors:
                        error(f"{e_label}.summon_template_id references missing NPC template '{template}'")
                    elif npc_behaviors[template] != "minion":
                        error(f"{e_label}.summon_template_id '{template}' has behavior_type {npc_behaviors[template]!r}; only a 'minion' follows its summoner and expires")
                    if "summon_duration" in effect and (not number(effect["summon_duration"]) or effect["summon_duration"] < 0):
                        error(f"{e_label}.summon_duration must be a number of seconds, 0 or more")
                    if "max_summons" in effect and (not integer(effect["max_summons"]) or effect["max_summons"] < 1):
                        error(f"{e_label}.max_summons must be a whole number of at least 1")
                if effect_type in ("unlock", "lock") and target_type != "item":
                    error(f"{e_label} is a {effect_type} effect, which acts only on a container, but target_type is '{target_type}' (it must be 'item')")
