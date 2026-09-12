# engine/npcs/elite.py
"""Generic elite-encounter promotion: any hostile template spawned via
the ambient Spawner has a content-configured chance to be promoted to
an "elite" instance -- boosted stats, guaranteed/bigger loot, and a
randomized flavor name -- without needing a dedicated template per
species. Tuned entirely via the "elites" ruleset section; a content
set that never defines one gets a chance of 0 and this is a no-op."""
import random
from typing import Any, Dict, Optional


def roll_elite_overrides(template: Dict[str, Any], world) -> Optional[Dict[str, Any]]:
    config = world.ruleset_section("elites")
    chance = float(config.get("chance", 0.0))
    if chance <= 0.0 or random.random() >= chance:
        return None

    multiplier = float(config.get("stat_multiplier", 1.5))
    stats = {key: max(1, int(value * multiplier)) for key, value in template.get("stats", {}).items()}
    attack_power = max(1, int(template.get("attack_power", 3) * multiplier))
    defense = max(0, int(template.get("defense", 2) * multiplier))

    guaranteed_chance = min(1.0, float(config.get("loot_guaranteed_chance", 1.0)))
    quantity_multiplier = float(config.get("loot_quantity_multiplier", 1.5))
    loot_table: Dict[str, Any] = {}
    for item_id, entry in template.get("loot_table", {}).items():
        new_entry = dict(entry)
        if "chance" in new_entry:
            new_entry["chance"] = max(float(new_entry["chance"]), guaranteed_chance)
        quantity = new_entry.get("quantity")
        if isinstance(quantity, list) and len(quantity) == 2:
            new_entry["quantity"] = [max(1, int(quantity[0] * quantity_multiplier)), max(1, int(quantity[1] * quantity_multiplier))]
        loot_table[item_id] = new_entry

    prefixes = config.get("prefixes", [])
    prefix = random.choice(prefixes) if prefixes else "Elite"
    name_pattern = config.get("name_pattern", "{prefix} {name}")
    elite_name = name_pattern.format(prefix=prefix, name=template.get("name", "creature"))

    return {
        "name": elite_name,
        "stats": stats,
        "attack_power": attack_power,
        "defense": defense,
        "loot_table": loot_table,
        "properties_override": {"is_elite": True},
    }
