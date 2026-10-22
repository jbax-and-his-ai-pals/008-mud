# engine/items/step_healing.py
"""Gear that mends its wearer a little with every step.

An item's `properties.heal_per_step` (a whole number of health) is what it gives each time its wearer moves to another room; the
worn items' amounts add. Nothing is said: it is the gear's quiet work.
"""

from typing import Any


def heal_for_step(player: Any) -> int:
    equipment = getattr(player, "equipment", None)
    if not isinstance(equipment, dict) or not getattr(player, "is_alive", False):
        return 0
    amount = 0
    for item in equipment.values():
        value = item.get_property("heal_per_step", 0) if item is not None else 0
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            amount += int(value)
    if amount <= 0 or player.health >= player.max_health:
        return 0
    healed = min(amount, int(player.max_health - player.health))
    player.health += healed
    return healed
