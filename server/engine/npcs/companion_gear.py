# engine/npcs/companion_gear.py
"""What a companion wears, and what the player can see of them.

A companion (`npcs/companions.py`) is an authored NPC that travels with a player. This gives it what a player has: gear in
the same slots (`EQUIPMENT_SLOTS`), put on from the player's pack with `equip <item> on <name>` and taken off with
`unequip <slot or item> from <name>`, and a sheet (`companion <name>`) that shows its level, health, attack, defence,
stats, abilities and gear.

Gear counts. A weapon in the main hand adds its damage to the companion's attack and armour adds its defence to the
companion's defence, read the way a player's are (`contracts/equipment.py`, installed attachments), and a worn weapon
sets the type of blow it deals. The bonus is kept as a difference from the base values the NPC was made with
(`_gear_attack`, `_gear_defense`), so taking a thing off puts the number back exactly and a saved NPC's base is never
mistaken for its geared total.

A template may name what an NPC starts in: `equipment: {"main_hand": "item_iron_sword"}` (slot -> item id). A saved NPC
brings back what it was wearing, not the template's.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from engine.config import EQUIPMENT_SLOTS, EQUIPMENT_VALID_SLOTS_BY_TYPE
from engine.contracts.equipment import armor_defense, weapon_damage, weapon_damage_type
from engine.items.attachments import attachment_modifier
from engine.npcs import companions
from engine.utils.articles import the

_SLOT_WORDS = {"main_hand": "main hand", "off_hand": "off hand"}


def slot_label(slot: str) -> str:
    return _SLOT_WORDS.get(slot, slot.replace("_", " "))


def empty_equipment() -> Dict[str, Optional[Any]]:
    return {slot: None for slot in EQUIPMENT_SLOTS}


def _worn_items(npc: Any) -> List[Any]:
    equipment = getattr(npc, "equipment", None) or {}
    return [item for item in equipment.values() if item is not None and item.get_property("durability", 1) > 0]


def bonuses(npc: Any) -> Tuple[int, int]:
    """(attack, defence) the worn gear adds."""
    world = getattr(npc, "world", None)
    attack = defense = 0
    for slot, item in (getattr(npc, "equipment", None) or {}).items():
        if item is None or item.get_property("durability", 1) <= 0:
            continue
        if slot == "main_hand":
            attack += weapon_damage(world, item)
        attack += attachment_modifier(item, "attack")
        defense += armor_defense(world, item) + attachment_modifier(item, "defense")
    return attack, defense


def refresh(npc: Any) -> None:
    """Bring the NPC's attack and defence in line with what it wears."""
    attack, defense = bonuses(npc)
    delta_attack = attack - getattr(npc, "_gear_attack", 0)
    delta_defense = defense - getattr(npc, "_gear_defense", 0)
    npc.attack_power += delta_attack
    npc.defense += delta_defense
    if isinstance(getattr(npc, "stats", None), dict):
        npc.stats["defense"] = npc.stats.get("defense", 0) + delta_defense   # what damage mitigation reads
    npc._gear_attack, npc._gear_defense = attack, defense


def weapon_type_of(npc: Any) -> Optional[str]:
    """The weapon-damage type of what is in the main hand, or None when nothing (usable) is."""
    weapon = (getattr(npc, "equipment", None) or {}).get("main_hand")
    if weapon is None or weapon.get_property("durability", 1) <= 0:
        return None
    return weapon_damage_type(getattr(npc, "world", None), weapon)


def valid_slots(npc: Any, item: Any) -> List[str]:
    """Where `item` may be worn: its own `equip_slot`, else the slots for its kind."""
    equipment = getattr(npc, "equipment", None) or {}
    declared = item.get_property("equip_slot")
    if isinstance(declared, str):
        declared = [declared]
    if isinstance(declared, list):
        found = [slot for slot in declared if slot in equipment]
        if found:
            return found
    return [slot for slot in EQUIPMENT_VALID_SLOTS_BY_TYPE.get(item.__class__.__name__, []) if slot in equipment]


def _check_companion(world: Any, player: Any, npc: Any) -> Optional[str]:
    if npc is None or not companions.is_companion(npc) or npc.properties.get("owner_id") != getattr(player, "obj_id", None):
        return "That is not one of your companions."
    if not npc.is_alive:
        return "%s is not able to." % npc.name
    if (npc.current_region_id, npc.current_room_id) != (player.current_region_id, player.current_room_id):
        return "%s is not here." % npc.name
    return None


def find_companion(world: Any, player: Any, name: str) -> Optional[Any]:
    """One of the player's companions by (part of) its name, or None."""
    wanted = name.strip().lower()
    if not wanted:
        return None
    mine = companions.companions_of(world, player, alive_only=False)
    exact = [npc for npc in mine if wanted in (npc.name.lower(), npc.template_id, npc.obj_id)]
    if exact:
        return exact[0]
    partial = [npc for npc in mine if wanted in npc.name.lower()]
    return partial[0] if partial else None


def parse_for_companion(world: Any, player: Any, args: List[str], prepositions: Tuple[str, ...]) -> Optional[Tuple[str, Any, Optional[str]]]:
    """`<thing> on <name> [to <slot>]` (or `from <name>`): (the thing, the companion, the slot), when `<name>` is one of
    the player's companions; None otherwise, so a plain `equip <item>` (an item whose name has an "on" in it) is untouched."""
    lowered = [word.lower() for word in args]
    for index, word in enumerate(lowered):
        if word not in prepositions or index == 0:
            continue
        rest = args[index + 1:]
        rest_lowered = lowered[index + 1:]
        slot = None
        if "to" in rest_lowered:
            cut = rest_lowered.index("to")
            slot = " ".join(rest[cut + 1:]).lower().replace(" ", "_") or None
            rest = rest[:cut]
        npc = find_companion(world, player, " ".join(rest))
        if npc is not None:
            return " ".join(args[:index]).lower(), npc, slot
    return None


def equip(world: Any, player: Any, npc: Any, item: Any, slot: Optional[str] = None) -> Tuple[bool, str]:
    """Put `item` from the player's pack on a companion. Returns (done, what to tell the player)."""
    problem = _check_companion(world, player, npc)
    if problem:
        return False, problem
    requirements = item.get_property("requirements", {})
    for stat, needed in (requirements.items() if isinstance(requirements, dict) else []):
        have = npc.get_effective_stat(stat)
        if have < needed:
            return False, "%s needs %s %s to use %s (has %s)." % (npc.name, needed, str(stat).capitalize(), the(item.name), have)
    slots = valid_slots(npc, item)
    if not slots:
        return False, "%s cannot wear %s." % (npc.name, the(item.name))
    if slot is not None:
        if slot not in slots:
            return False, "%s cannot go in %s's %s slot. It fits: %s." % (the(item.name, capital=True), npc.name, slot_label(slot), ", ".join(slot_label(s) for s in slots))
        target = slot
    else:
        target = next((s for s in slots if npc.equipment.get(s) is None), slots[0])
    if not player.inventory.get_item(item.obj_id):
        return False, "You don't have %s." % the(item.name)

    swapped = ""
    worn = npc.equipment.get(target)
    if worn is not None:
        if worn.get_property("cursed"):
            return False, "%s cannot give up %s." % (npc.name, the(worn.name))
        added, why = player.inventory.add_item(worn, 1)
        if not added:
            return False, "You cannot take back %s to make room: %s" % (the(worn.name), why)
        swapped = " (%s returns %s to you)" % (npc.name, the(worn.name))
    taken, _count, note = player.inventory.remove_item(item.obj_id, 1)
    if not taken:
        if worn is not None:
            player.inventory.remove_item(worn.obj_id, 1)   # undo the swap
        return False, "Could not take %s from your pack: %s" % (the(item.name), note)
    npc.equipment[target] = taken
    refresh(npc)
    return True, "%s equips %s (%s).%s" % (npc.name, the(taken.name), slot_label(target), swapped)


def unequip(world: Any, player: Any, npc: Any, identifier: str) -> Tuple[bool, str]:
    """Take a companion's gear back into the player's pack, named by slot or by item."""
    problem = _check_companion(world, player, npc)
    if problem:
        return False, problem
    wanted = identifier.strip().lower()
    slot = wanted.replace(" ", "_")
    if slot not in npc.equipment:
        matches = [s for s, item in npc.equipment.items() if item is not None and wanted in item.name.lower()]
        exact = [s for s in matches if npc.equipment[s].name.lower() == wanted]
        matches = exact or matches
        if not matches:
            return False, "%s is not wearing '%s'." % (npc.name, identifier.strip())
        slot = matches[0]
    item = npc.equipment.get(slot)
    if item is None:
        return False, "%s has nothing in the %s." % (npc.name, slot_label(slot))
    if item.get_property("cursed"):
        return False, "%s cannot give up %s." % (npc.name, the(item.name))
    added, why = player.inventory.add_item(item, 1)
    if not added:
        return False, "You cannot carry %s: %s" % (the(item.name), why)
    npc.equipment[slot] = None
    refresh(npc)
    return True, "%s hands you %s (%s)." % (npc.name, the(item.name), slot_label(slot))


def sheet(world: Any, npc: Any) -> str:
    """A companion's character sheet, as lines of text."""
    from engine.magic.spell_registry import get_spell

    lines = ["%s  (level %d)" % (npc.name, npc.level),
             "Health: %d/%d" % (npc.health, npc.max_health)]
    if getattr(npc, "max_mana", 0):
        lines[-1] += "   Mana: %d/%d" % (npc.mana, npc.max_mana)
    lines.append("Attack: %d   Defense: %d" % (npc.attack_power, npc.stats.get("defense", npc.defense)))
    shown = [(name, value) for name, value in npc.stats.items() if isinstance(value, (int, float)) and name != "defense"]
    if shown:
        lines.append("Stats: " + ", ".join("%s %d" % (name.replace("_", " ").title(), value) for name, value in shown))
    abilities = [get_spell(spell_id) for spell_id in getattr(npc, "usable_spells", [])]
    names = [spell.name for spell in abilities if spell is not None]
    if names:
        lines.append("Abilities: " + ", ".join(names))
    lines.append("Gear:")
    for slot in EQUIPMENT_SLOTS:
        item = (getattr(npc, "equipment", None) or {}).get(slot)
        if item is None:
            lines.append("  %s: (nothing)" % slot_label(slot).capitalize())
        else:
            durability = item.get_property("durability")
            max_durability = item.get_property("max_durability")
            tail = " [%s/%s]" % (durability, max_durability) if durability is not None and max_durability else ""
            lines.append("  %s: %s%s" % (slot_label(slot).capitalize(), item.name, tail))
    return "\n".join(lines)


def starting_gear(world: Any, npc: Any, template: Dict[str, Any]) -> None:
    """Put on what the template says the NPC starts in (`equipment: {slot: item_id}`)."""
    from engine.items.item_factory import ItemFactory
    from engine.utils.logger import Logger

    declared = template.get("equipment")
    if not isinstance(declared, dict):
        return
    for slot, item_id in declared.items():
        if slot not in npc.equipment or not isinstance(item_id, str):
            Logger.warning("NPCFactory", "Skipping gear %r in slot %r for '%s'." % (item_id, slot, template.get("name")))
            continue
        item = ItemFactory.create_item_from_template(item_id, world)
        if item is None:
            Logger.warning("NPCFactory", "Skipping missing gear template '%s' for '%s'." % (item_id, template.get("name")))
            continue
        npc.equipment[slot] = item
    refresh(npc)
