#!/usr/bin/env python3
"""Normalise whole-number floats back to integers in authored content.

JSON has one number type, so `2.0` and `2` parse identically in some languages
and differently in others -- and Python is one of the others. `isinstance(2.0,
int)` is False, so a content field the engine means as an integer stops being
one the moment a JSON writer with only floats touches the file. That is not
hypothetical: the world editor's GDScript `JSON.stringify` writes every number
as a float, and one editor save turned 2,058 values across `fantasy_frontier`
into floats, which broke the content validator for that whole set (ingredient
quantities, region level bands, vendor orders, quest stage indexes, material
grades) while every test that never read those fields kept passing.

This undoes that, under a rule narrow enough to be safe:

    convert a whole-number float to an int **only where the schema says the
    field is an integer**.

Nothing else is touched. A field the engine reads as a float keeps whatever
precision it has -- `weight`, `chance`, `value_multiplier` and the rest are
numbers where `2.5` and `3.0` are both legitimate, and "3.0 looks like an
integer" is not a reason to change what an author wrote. That is also why this
is a normaliser and not a general formatter: the only values it moves are ones
the engine will otherwise reject or misread.

    python toolkit/normalize_content_numbers.py --check          # report only
    python toolkit/normalize_content_numbers.py --apply          # rewrite

`--check` is what the content gate runs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVER_ROOT = _REPO_ROOT / "server"
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

CONTENT_SETS_DIR = _REPO_ROOT / "content_sets"

# Directories under a content set that hold editor state rather than content the
# game reads. Layout coordinates there are genuinely fractional.
EXCLUDED_DIRECTORIES = ("editor",)


# --- what the schema says is an integer --------------------------------------
#
# Contract fields carry their own types, so those are read from the schemas
# rather than listed. Everything below is the part of content that has no
# schema: the entity files, whose integer fields are the ones the content-set
# validator checks with `isinstance(value, int)`.
#
# A field name alone is not enough -- `weight` is a float on a tier and an
# item's weight may legitimately be 2.5 -- so each rule names the context it
# applies in. `None` means "anywhere".

# Fields that are an integer wherever they appear, because their name has no
# meaning other than that in this content format.
#
# This is measured, not guessed: every name below is one that appears *only* as
# a whole number across all four shipped content sets. A name that appears both
# whole and fractional somewhere -- `cooldown`, `value_multiplier`, `chance`,
# `weight` -- is not on the list, because a JSON writer that turned `3` into
# `3.0` did not make it a different kind of field, and "3.0 looks like an
# integer" is not a reason to rewrite what an author wrote.
INT_FIELDS_ANYWHERE = frozenset({
    "quantity",             # recipe ingredients, buy orders, loot, starting kits
    "current_quantity",
    "required_quantity",
    "result_quantity",      # what a recipe produces
    "min_crafts",           # a quality tier's practice gate, read with isinstance(int)
    "rank",                 # a quality tier's ordering, read with int()
    "count",                # familiarity milestones and quest counters
    "required_count",
    "target_count",
    "stage_index",
    "next_stage",
    "tier",
    "gold",
    "xp",
    "reward_gold",
    "relationship_amount",
    "relationship_min",
    "required_score",
    "replacement_key_cost",
    "min_material_quality",
    "min_material_quality_score",
    "quality_penalty",
    "min_rooms",
    "max_rooms",
    "min",
    "max",
    "uses",
    "max_uses",
    "charges",
    "max_charges",
    "capacity",
    "durability",
    "max_durability",
    "health",
    "max_health",
    "level",
    "level_required",
    "mana_cost",
    "max_mana",
    "max_summons",
    "strength",
    "dexterity",
    "constitution",
    "agility",
    "intelligence",
    "wisdom",
    "defense",
    "attack_power",
    "spell_power",
    "magic_resist",
    "resist_fire",
    "resist_cold",
    "resist_poison",
    "summon_duration",
    "base_duration",
    "dot_duration",
    "dot_damage_per_tick",
    "dot_tick_interval",
    "damage_per_tick",
    "hazard_damage",
    "hazard_tick_interval",
    "effect_value",
    "damage_amount",
    "tick_interval",
    "move_cooldown",
    "respawn_cooldown",
    "respawn_days",
    "gift_bonus",
    "difficulty",
})

# Fields that are an integer only inside a named container. The container is the
# immediate parent key: `spawner.level_range`, `properties.level_band`.
INT_FIELDS_IN_CONTEXT: Dict[str, frozenset] = {
    "level_band": frozenset({"min", "max"}),
    "level_range": frozenset({"*"}),  # every element of the array
    # A resource node's declared grade, on the node or on one yield-table entry.
    "material_quality": frozenset({"score"}),
}

# Fields that look like integers and are not. Listed explicitly so the reason is
# recorded rather than implied by absence: these are read as floats and their
# fractional part is meaningful.
FLOAT_FIELDS = frozenset({
    "weight", "value", "value_multiplier", "weight_multiplier", "chance",
    "price_multiplier", "wander_chance", "flee_threshold", "spell_cast_chance",
    "aggression", "cooldown", "attack_cooldown", "quantity_per_weight",
    "size_bias", "quality_bias", "x", "y", "damage", "defense",
    "vendor_discount", "sell_rate_multiplier",
})


def _is_int_like(value: Any) -> bool:
    """A float that is a whole number, and not a bool."""
    return isinstance(value, float) and not isinstance(value, bool) and value.is_integer()


def normalize_schema_numbers(value: Any, fields: Dict[str, Any]) -> Tuple[Any, int]:
    """Convert whole floats to ints in a contract object, guided by its schema."""
    if not isinstance(fields, dict):
        return value, 0
    changed = 0
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, entry in value.items():
            spec = fields.get(key)
            if not isinstance(spec, dict):
                out[key] = entry
                continue
            converted, count = _normalize_by_spec(entry, spec)
            out[key] = converted
            changed += count
        return out, changed
    if isinstance(value, list):
        converted, count = _normalize_by_spec(value, {"type": "list_of", "of": {"type": "object", "fields": fields}})
        return converted, count
    return value, 0


def _normalize_by_spec(value: Any, spec: Dict[str, Any]) -> Tuple[Any, int]:
    kind = str(spec.get("type", ""))
    if kind == "int":
        if _is_int_like(value):
            return int(value), 1
        return value, 0
    if kind == "list_of":
        inner = spec.get("of")
        if isinstance(value, list):
            changed = 0
            out: List[Any] = []
            for entry in value:
                if isinstance(inner, dict):
                    converted, count = _normalize_by_spec(entry, inner)
                else:
                    converted, count = entry, 0
                out.append(converted)
                changed += count
            return out, changed
        return value, 0
    if kind == "object":
        return normalize_schema_numbers(value, spec.get("fields", {}))
    if kind == "map":
        inner = spec.get("of")
        if isinstance(value, dict) and isinstance(inner, dict):
            changed = 0
            out: Dict[str, Any] = {}
            for key, entry in value.items():
                converted, count = _normalize_by_spec(entry, inner)
                out[key] = converted
                changed += count
            return out, changed
        return value, 0
    return value, 0


# --- the entity half, which has no schema ------------------------------------


def normalize_entity_numbers(value: Any, path: Tuple[str, ...] = ()) -> Tuple[Any, int]:
    """Convert whole floats to ints in a schema-less content object.

    `path` is every key descended through to reach this value, because the
    context a rule needs is the *nearest* one, not the immediate parent: a
    region's band is `region.properties.level_band.min`, and the rule is about
    `level_band` however deep the author nested it.
    """
    if _is_int_like(value):
        if not path:
            return value, 0
        field = path[-1]
        if field in INT_FIELDS_ANYWHERE:
            return int(value), 1
        # A field named by the context it sits in: `level_band.min`.
        allowed = _field_context(path[:-1])
        if allowed and field in allowed:
            return int(value), 1
        return value, 0
    if isinstance(value, dict):
        changed = 0
        out: Dict[str, Any] = {}
        for child_key, child in value.items():
            converted, count = normalize_entity_numbers(child, path + (str(child_key),))
            out[child_key] = converted
            changed += count
        return out, changed
    if isinstance(value, list):
        changed = 0
        out_list: List[Any] = []
        for entry in value:
            # An array standing in for a vector or a pair: `level_range: [1, 3]`.
            if _is_int_like(entry) and _vector_context(path) is not None:
                out_list.append(int(entry))
                changed += 1
                continue
            converted, count = normalize_entity_numbers(entry, path)
            out_list.append(converted)
            changed += count
        return out_list, changed
    return value, 0


def _vector_context(path: Tuple[str, ...]) -> Optional[frozenset]:
    """The field-name whitelist for a list, if the nearest key declares one."""
    if not path:
        return None
    allowed = INT_FIELDS_IN_CONTEXT.get(path[-1])
    if allowed and "*" in allowed:
        return allowed
    return None


def _field_context(path: Tuple[str, ...]) -> Optional[frozenset]:
    """The field-name whitelist for an object, if the nearest key declares one."""
    if not path:
        return None
    return INT_FIELDS_IN_CONTEXT.get(path[-1])


def normalize_document(payload: Any, contracts_schemas: Dict[str, Dict[str, Any]], is_contracts: bool) -> Tuple[Any, int]:
    """Normalise one parsed JSON document, returning it and how many values moved."""
    if is_contracts and isinstance(payload, dict):
        changed = 0
        out: Dict[str, Any] = {}
        for key, value in payload.items():
            schema = contracts_schemas.get(key)
            if schema is None:
                out[key] = value
                continue
            converted, count = normalize_schema_numbers(value, schema)
            out[key] = converted
            changed += count
        return out, changed
    return normalize_entity_numbers(payload)


# --- walking a content set ---------------------------------------------------


def content_json_files(content_set: Path) -> Iterator[Path]:
    for path in sorted(content_set.rglob("*.json")):
        if any(part in EXCLUDED_DIRECTORIES for part in path.relative_to(content_set).parts):
            continue
        yield path


def _contract_schemas() -> Dict[str, Dict[str, Any]]:
    from engine.contracts.registry import CONTRACT_SCHEMAS

    return CONTRACT_SCHEMAS


def normalize_content_set(content_set: Path, apply: bool = False) -> Tuple[int, List[str]]:
    """Normalise one set. Returns how many values moved, and which files.

    With `apply` the file is rewritten only when something actually moved, so a
    clean set is never touched -- no mtime churn, no diff noise, and no risk of
    clobbering a hand edit with a re-serialised copy of itself.

    Serialisation matches the editor's (`indent=4`, keys in authored order,
    trailing newline), so a normalised file differs from what the editor would
    write only in the numbers that changed.
    """
    schemas = _contract_schemas()
    total = 0
    touched: List[str] = []
    for path in content_json_files(content_set):
        try:
            original = path.read_text(encoding="utf-8")
            payload = json.loads(original)
        except (OSError, json.JSONDecodeError) as error:
            print("  skip  %s (%s)" % (path.name, error))
            continue
        is_contracts = path.parent.name == "contracts"
        normalized, changed = normalize_document(payload, schemas, is_contracts)
        if not changed:
            continue
        total += changed
        touched.append("%s (%d)" % (path.relative_to(content_set).as_posix(), changed))
        if apply:
            text = json.dumps(normalized, indent=4, ensure_ascii=False) + "\n"
            path.write_text(text, encoding="utf-8")
    return total, touched


def content_sets() -> List[Path]:
    if not CONTENT_SETS_DIR.is_dir():
        return []
    return sorted(
        path for path in CONTENT_SETS_DIR.iterdir()
        if path.is_dir() and (path / "content_set.manifest.json").is_file()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="rewrite the files (default is to report only)")
    parser.add_argument("--set", dest="only", default=None, help="limit to one content set id")
    args = parser.parse_args()

    sets = content_sets()
    if args.only:
        sets = [path for path in sets if path.name == args.only]
    if not sets:
        print("No content sets found under %s." % CONTENT_SETS_DIR)
        return 2

    # `--apply` rewrites in place, so the report has to be produced first and
    # then re-run by the caller; doing both here would report the pre-fix counts
    # as though they were the post-fix ones.
    grand_total = 0
    for content_set in sets:
        total, touched = normalize_content_set(content_set, apply=args.apply)
        grand_total += total
        if args.apply:
            # The second pass is the proof: a normaliser that is not idempotent
            # has a rule it applies inconsistently.
            again, _ = normalize_content_set(content_set, apply=True)
            print("%-18s %d value(s) converted%s" % (
                content_set.name, total, "" if again == 0 else " -- NOT IDEMPOTENT (%d on re-run)" % again
            ))
        elif total:
            print("%-18s %d whole-number float(s) in integer fields" % (content_set.name, total))
        else:
            print("%-18s clean" % content_set.name)
        for entry in touched[:40]:
            print("    %s" % entry)
        if len(touched) > 40:
            print("    ... and %d more file(s)" % (len(touched) - 40))

    if args.apply:
        print("\nConverted %d value(s). Re-run with --check to confirm." % grand_total)
        return 0

    if grand_total:
        print(
            "\n%d whole-number float(s) sit in fields the engine means as integers.\n"
            "Run with --apply to convert them; nothing else will be changed." % grand_total
        )
        return 1
    print("\nAll content numbers match the types the engine reads.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
