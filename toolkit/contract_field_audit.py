# toolkit/contract_field_audit.py
"""Every contract field has to say who reads it.

The rule this enforces, in the project's own words: **a primitive with no consumer
is worse than none.** A declared field that no code reads is not a harmless
placeholder -- it is a promise to an author (and to the editor, which offers it as
a dropdown) that the engine will do something with the value. When it does not,
the author's only clue is that nothing happened.

Why this is a ledger and not a scanner
--------------------------------------
The obvious implementation -- grep the engine for each field name -- **does not
work here, and producing a false report is worse than producing none.** Measured
on this codebase:

* `item_families[].attack_profile` and `defense_profile` have *zero* occurrences as
  quoted literals outside `contracts/`, yet `equipment.profile_for()` reads both:
  it does `family.get(key, "")` where `key` is a parameter. The field names live in
  a lookup table, not at the call site.
* `debug_only`, `cooldown`, `resource_cost`, `size_tiers`, `quality_tiers`,
  `size_bias`, `quality_bias` and the `value_multiplier` family all have readers
  that a quoted-literal scan *does* find, but nothing distinguishes those from a
  field read only by the validator that exists to validate it.
* The reverse error is just as easy: `tier.weight` is declared in `TIER_FIELDS`,
  and `instance_generator` mentions "weight" 20+ times -- in `_weights_for`,
  in `item.weight`, in `_roll_quality`. None of them is the tier's declared
  `weight`; the weight is computed from a positional curve and the author's value
  is ignored.

So the verdict for each field is **recorded once, with its evidence, by a person
who checked** -- and this tool's job is to make that record impossible to leave
stale. It fails when a field is declared and unclassified, which makes "I added a
contract field" and "I decided who reads it" the same act.

Usage:
    python toolkit/contract_field_audit.py            # report; exit 1 if unclassified
    python toolkit/contract_field_audit.py --verbose  # list every field and verdict
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_ROOT = REPO_ROOT / "server"
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from engine.contracts import registry as contract_registry  # noqa: E402


# -- the verdicts ------------------------------------------------------------

# Read by engine code that acts on the value. The reader is named so the claim can
# be checked, and so a refactor that removes the reader has somewhere to look.
READ = "read"
# Carried for display, validation or authoring only. Legitimately read by nothing
# that changes behaviour: the editor, a help text or a validator consumes it.
DISPLAY = "display"
# Declared, validated, and read by nothing at all. This is the state the rule
# forbids; an entry here is a known debt, not an approval.
UNREAD = "unread"

VERDICTS = (READ, DISPLAY, UNREAD)


# {section: {field: (verdict, who reads it / why it is unread)}}
LEDGER: Dict[str, Dict[str, Tuple[str, str]]] = {
    "item_families": {
        "id": (READ, "registry.family() lookup key"),
        "label": (DISPLAY, "editor picker and operator listings"),
        "description": (DISPLAY, "authoring prose"),
        "item_class": (READ, "equipment.item_class_for_template resolves the engine class"),
        "capabilities": (READ, "equipment.capabilities_of; the engine queries capability, not type"),
        "generation_profile": (READ, "instance_generator picks the roll profile by it"),
        "attack_profile": (READ, "equipment.profile_for(item, 'attack_profile'), which includes "
                                 "the family fallback -- so this has no quoted-literal call site"),
        "defense_profile": (READ, "equipment.profile_for(item, 'defense_profile'), same as above"),
        "icon_style": (READ, "item_factory copies it onto the instance and icons.py reads it "
                             "to pick a style class; declared by every family in both sets"),
        "resource": (DISPLAY, "no engine reader: registry.py checks only that a declared name "
                              "resolves to a resource, and no shipped family declares one. "
                              "Kept classified rather than deleted because the validation is "
                              "real, but nothing acts on the value"),
        "debug_only": (READ, "chest_loot_generator and instance_generator both exclude these "
                             "templates from loot and generation"),
    },
    "generation_profiles": {
        "id": (READ, "instance_generator profile lookup"),
        "label": (DISPLAY, "authoring"),
        "item_family": (READ, "profiles are selected per family"),
        "rarity_tiers": (READ, "instance_generator rarity roll"),
        "size_tiers": (READ, "instance_generator._roll_size"),
        "quality_tiers": (READ, "instance_generator._roll_quality and the crafting tracker"),
        "size_bias": (READ, "instance_generator._roll_size bias argument"),
        "quality_bias": (READ, "instance_generator._roll_quality bias argument"),
        "name_template": (READ, "instance_generator name substitution"),
        "property_prefix": (READ, "instance_generator property naming"),
    },
    "resources": {
        "id": (READ, "the pool's identity; ability_resource and node tool resolution"),
        "label": (DISPLAY, "player-facing pool name"),
        "short": (READ, "the short form shown in status payloads"),
        "kind": (READ, "splits the ability pool from ordinary resources"),
        "regenerates": (READ, "regeneration is gated on it"),
        "regeneration_stat": (READ, "which stat drives refill"),
        "max_stat": (READ, "which stat sets pool size"),
    },
    "attack_profiles": {
        "id": (READ, "profile lookup key"),
        "label": (DISPLAY, "authoring"),
        "damage_type": (READ, "equipment.weapon_damage_type, the channel a weapon deals"),
        "weapon_damage_type": (READ, "equipment.weapon_damage_type resolves here first"),
        "damage": (READ, "equipment.weapon_damage"),
        "cooldown": (UNREAD, "no reader: weapon cooldowns are not implemented. Attack profiles "
                             "declare it and the registry validates its type, and nothing else "
                             "touches it"),
        "resource_cost": (UNREAD, "no reader: registry.py reads it only to validate that the "
                                  "named resource exists, and no code charges it -- a weapon's "
                                  "cost to swing is not implemented"),
        "resource_cost.resource": (UNREAD, "no reader: the resource a swing would consume. "
                                           "Reached only through the unread resource_cost above"),
        "resource_cost.amount": (UNREAD, "no reader: how much a swing would consume. Reached "
                                         "only through the unread resource_cost above"),
        "tags": (READ, "combat resolution and the editor's filtering"),
    },
    "defense_profiles": {
        "id": (READ, "profile lookup key"),
        "label": (DISPLAY, "authoring"),
        "defense": (READ, "equipment.armor_defense"),
        "resistances": (READ, "equipment.armor_resistances, per-key override"),
        "material": (READ, "equipment.armor_material, which selects the damage-type multiplier row"),
        "tags": (READ, "combat resolution and editor filtering"),
    },
    "abilities": {
        "id": (READ, "registry.ability() lookup, and ability_for_spell maps a spell to it"),
        "label": (DISPLAY, "the ability listing"),
        "description": (DISPLAY, "the ability listing"),
        "effect_packet": (UNREAD, "no reader: the registry validates that it names a declared "
                                  "packet, and equipment.ability_numbers reads cost/cooldown/"
                                  "targeting/level but never the packet. Effect application is "
                                  "per-spell code in magic.py. This is the last mile of "
                                  "cross_theme_engine_contracts.md section 2"),
        "cost": (READ, "equipment.ability_numbers reads the cost object"),
        "cost.resource": (READ, "ability_resource_id comparison inside ability_numbers"),
        "cost.amount": (READ, "the charged amount"),
        "cooldown": (READ, "equipment.ability_numbers; magic.py stores the expiry from it"),
        "target_type": (READ, "equipment.ability_numbers targeting"),
        "level_required": (READ, "equipment.ability_numbers level gate"),
    },
    "effect_packets": {
        "id": (READ, "registry.effect_packet() lookup, and the ability reference check"),
        "label": (DISPLAY, "authoring"),
        "description": (DISPLAY, "authoring"),
        "resource": (DISPLAY, "the registry validator checks a packet's resource name resolves "
                              "to a declared resource; no code acts on it, because nothing "
                              "executes a packet at all yet"),
        "kind": (UNREAD, "no reader: declared as the neutral effect kind (damage/restore/teach) "
                         "and read by nothing; the per-spell code in magic.py decides"),
        "value": (UNREAD, "no reader: the amount lives on the spell, not the packet"),
        "duration": (UNREAD, "no reader: durations have no engine support yet"),
        "tags": (UNREAD, "no reader: packet tags would let content classify effects for "
                         "filtering or resistance, and nothing consults them"),
        "payload": (UNREAD, "no reader: the free-form escape hatch is never consulted"),
    },
    "work": {
        "id": (READ, "registry.work_declaration() lookup key, and the id a timer names"),
        "label": (READ, "work.observe() reports it, so `status` can name work it has never "
                        "heard of"),
        "description": (DISPLAY, "authoring prose; read by nothing"),
        "duration_days": (READ, "work.duration_seconds() -- the one field that makes a "
                                "declaration take time at all"),
        "inputs": (READ, "work.start() selects exactly these from the player's inventory and "
                         "consumes them; a missing one refuses the start before anything is "
                         "spent"),
        "outputs": (READ, "work.start() builds them to check the result will fit, and "
                          "work.collect() adds them once the clock reaches the end"),
        "skill": (READ, "work.declaration_issues() checks it against `difficulty`, and "
                        "work.collect() rolls it through SkillSystem.practice_check"),
        "difficulty": (READ, "work.declaration_issues(), and the number work.collect() rolls "
                             "against -- a failed roll halves the yield"),
        "station": (READ, "work.start() compares it against the station types the caller "
                          "found nearby, and refuses with the name when it is not there"),
        "tags": (UNREAD, "no reader: work tags would let content group jobs (a station that "
                         "accepts drying, say) and nothing consults them"),
    },
}


def declared_fields() -> List[Tuple[str, str]]:
    """Every `(section, field)` the contract schemas declare, nested included."""

    def walk(spec: Any, prefix: str = "") -> List[str]:
        found: List[str] = []
        if not isinstance(spec, dict):
            return found
        for key, sub in spec.items():
            if isinstance(sub, dict) and "type" in sub:
                found.append(prefix + key)
                if isinstance(sub.get("fields"), dict):
                    found.extend(walk(sub["fields"], prefix + key + "."))
        return found

    out: List[Tuple[str, str]] = []
    for section, spec in contract_registry.CONTRACT_SCHEMAS.items():
        for field in walk(spec):
            out.append((section, field))
    return out


def audit() -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]], List[Tuple[str, str]]]:
    """Return (unclassified, unread, orphaned_ledger_entries)."""
    unclassified: List[Tuple[str, str]] = []
    unread: List[Tuple[str, str]] = []
    seen: Dict[str, set] = {}

    for section, field in declared_fields():
        seen.setdefault(section, set()).add(field)
        entry = LEDGER.get(section, {}).get(field)
        if entry is None:
            unclassified.append((section, field))
            continue
        verdict, _why = entry
        if verdict == UNREAD:
            unread.append((section, field))

    orphaned: List[Tuple[str, str]] = []
    for section, fields in LEDGER.items():
        for field in fields:
            if field not in seen.get(section, set()):
                orphaned.append((section, field))
    return unclassified, unread, orphaned


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verbose", action="store_true",
                        help="list every field with its verdict and reader")
    args = parser.parse_args()

    unclassified, unread, orphaned = audit()
    declared = declared_fields()

    if args.verbose:
        for section, field in declared:
            verdict, who = LEDGER.get(section, {}).get(field, ("?", "not classified"))
            print("[%s] %s.%s -- %s" % (verdict, section, field, who))
        print()

    failed = False

    if unclassified:
        failed = True
        print("Unclassified contract fields (%d). Each needs a read-or-delete verdict:" % len(unclassified))
        for section, field in unclassified:
            print("  %s.%s" % (section, field))
        print("  Add each to LEDGER in this file with its reader, or remove the field.")

    if orphaned:
        failed = True
        print("Ledger entries that no longer exist in the schemas (%d):" % len(orphaned))
        for section, field in orphaned:
            print("  %s.%s" % (section, field))
        print("  The field was removed or renamed; drop or update the ledger entry.")

    if not failed:
        print("Contract fields: %d declared, all classified." % len(declared))

    if unread:
        print()
        print("Declared but read by nothing (%d). The rule says a primitive with no" % len(unread))
        print("consumer is worse than none -- these are known debt, listed so the count")
        print("can only shrink:")
        for section, field in unread:
            print("  %s.%s" % (section, field))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
