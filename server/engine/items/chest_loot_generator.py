# engine/items/chest_loot_generator.py
"""Generates a randomized, level-scaled locked chest.

Content-neutral by design: every pool this draws from (chest materials,
gems, equipment, junk) is discovered from whatever the loaded content set
authored (`world.item_templates`), not hardcoded to any one setting's item
ids. Reuses three systems that already exist elsewhere in the engine rather
than inventing new randomization machinery: `LootGenerator`'s level-scaled
affix rolls for equipment, the gathering system's material-quality-score
convention for gems, and `weighted_choice` for category selection. The one
genuinely new piece is `roll_around` (engine/utils/utils.py), since nothing
in this engine previously rolled a "usually expected, rarely a big swing"
value.
"""
import random
from typing import TYPE_CHECKING, List, Optional, Tuple

from engine.config import CHEST_TRAP_CHANCE
from engine.items.container import Container
from engine.items.item import Item
from engine.items.item_factory import ItemFactory
from engine.items.loot_generator import LootGenerator
from engine.utils.utils import roll_around, weighted_choice

if TYPE_CHECKING:
    from engine.world.world import World


_CHEST_MATERIALS = ("item_chest_wooden", "item_chest_iron_bound", "item_chest_gilded")

# Score -> (id, label), mirroring the gathering system's material-quality
# convention (engine/items/resource_node.py) so a chest-found gem behaves
# identically to a gathered one in later appraisal/crafting.
_QUALITY_TIERS = {
    1: ("common", "Common"),
    2: ("fine", "Fine"),
    3: ("exceptional", "Exceptional"),
}


class ChestLootGenerator:
    @staticmethod
    def generate_chest(world: 'World', level: int = 1) -> Optional[Container]:
        level = max(1, int(level))

        material_id = ChestLootGenerator._roll_material(world, level)
        difficulty = round(roll_around(10 + level * 3, 4 + level * 0.5, minimum=5))
        trapped, trap_kind, trap_difficulty = ChestLootGenerator._roll_trap(level)
        overrides = {"lock_difficulty": difficulty, "trapped": trapped}
        if trapped:
            overrides["trap_kind"] = trap_kind
            overrides["trap_difficulty"] = trap_difficulty
        chest = ItemFactory.create_item_from_template(
            material_id, world, properties_override=overrides,
        )
        if not isinstance(chest, Container):
            return None

        slot_count = max(1, min(3, round(roll_around(1.5, 1.0, minimum=1, maximum=3))))
        contents = chest.properties.setdefault("contains", [])
        for _ in range(slot_count):
            item = ChestLootGenerator._generate_slot_item(world, level)
            if item:
                # Not Container.add_item(): that enforces the container
                # being open, which is a player-interaction rule and
                # doesn't apply to seeding a freshly-generated chest's
                # contents (mirrors how Container.__init__ itself hydrates
                # authored `contains` data with no open/closed gate).
                contents.append(item)

        return chest

    @staticmethod
    def generate_household_loot(world: 'World', container: Container) -> None:
        """Lazily fill a piece of home furniture the first time it's
        looted, rather than hand-authoring its contents -- reuses the same
        per-slot item generation chests use, just fewer slots pinned to a
        low level (household goods, not dungeon loot). A no-op on every
        call after the first, so it's safe to call unconditionally."""
        if container.properties.get("loot_generated"):
            return
        container.properties["loot_generated"] = True

        contents = container.properties.setdefault("contains", [])
        slot_count = max(1, min(2, round(roll_around(1.2, 0.8, minimum=1, maximum=2))))
        for _ in range(slot_count):
            item = ChestLootGenerator._generate_slot_item(world, level=1)
            if item:
                contents.append(item)

    @staticmethod
    def _roll_material(world: 'World', level: int) -> str:
        available = [m for m in _CHEST_MATERIALS if m in world.item_templates]
        if not available:
            return _CHEST_MATERIALS[0]
        # Weight shifts toward rarer materials as level rises, without ever
        # making the common case disappear entirely.
        weights = {}
        for index, material_id in enumerate(available):
            weights[material_id] = max(1, 10 - index * 4 + index * level)
        return weighted_choice(weights) or available[0]

    @staticmethod
    def _roll_trap(level: int) -> Tuple[bool, Optional[str], Optional[int]]:
        """Independent of lock difficulty and contents -- a chest's
        difficulty says nothing about whether it's trapped."""
        if random.random() >= CHEST_TRAP_CHANCE:
            return False, None, None
        kind = weighted_choice({"damage": 3, "poison": 2})
        difficulty = round(roll_around(10 + level * 3, 4 + level * 0.5, minimum=5))
        return True, kind, difficulty

    @staticmethod
    def _generate_slot_item(world: 'World', level: int) -> Optional[Item]:
        category = weighted_choice({"junk": 4, "currency": 3, "gem": 2, "equipment": 1})
        item: Optional[Item] = None

        if category == "currency":
            quantity = max(1, round(roll_around(5 + level * 4, 3 + level, minimum=1)))
            item = ItemFactory.create_item_from_template("item_gold_coin", world)
            if item:
                item.value = max(1, int(item.value)) * quantity
                item.update_property("value", item.value)
                item.description = f"{item.description} ({quantity} coins)"
        elif category == "gem":
            gem_id = ChestLootGenerator._pick_template(world, "Gem")
            if gem_id:
                item = ItemFactory.create_item_from_template(gem_id, world)
                if item:
                    ChestLootGenerator._apply_gem_quality(item, level)
        elif category == "equipment":
            base_id = ChestLootGenerator._pick_template(world, "Weapon", "Armor")
            if base_id:
                item = LootGenerator.generate_loot(
                    base_id, world, level=level, rarity_roll=roll_around(0.5, 0.35, minimum=0.0, maximum=1.0),
                )
        else:  # junk
            junk_id = ChestLootGenerator._pick_template(world, "Junk", "Treasure")
            if junk_id:
                item = ItemFactory.create_item_from_template(junk_id, world)

        if item:
            ChestLootGenerator._apply_quality_value_roll(item)
        return item

    @staticmethod
    def _pick_template(world: 'World', *type_names: str) -> Optional[str]:
        candidates = [
            item_id for item_id, template in world.item_templates.items()
            if isinstance(template, dict) and template.get("type") in type_names
            and not template.get("properties", {}).get("debug_only")
        ]
        return random.choice(candidates) if candidates else None

    @staticmethod
    def _apply_gem_quality(item: Item, level: int) -> None:
        score = round(roll_around(1 + level / 6.0, 1.0, minimum=1, maximum=3))
        quality_id, quality_label = _QUALITY_TIERS.get(score, _QUALITY_TIERS[1])
        item.properties["material_quality"] = quality_id
        item.properties["material_quality_label"] = quality_label
        item.properties["material_quality_score"] = score
        item.stackable = False
        item.update_property("stackable", False)

    @staticmethod
    def _apply_quality_value_roll(item: Item) -> None:
        """Every generated chest item -- not just gems -- gets its own
        recursive quality-value roll, usually near 1x but occasionally a
        notable bargain or windfall."""
        multiplier = roll_around(1.0, 0.5, minimum=0.4, maximum=2.0)
        item.value = max(0, int(round(item.value * multiplier)))
        item.update_property("value", item.value)
