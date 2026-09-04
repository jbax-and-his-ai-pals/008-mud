# engine/items/loot_generator.py
import random
from typing import Optional, Dict, Any

from engine.items.item import Item
from engine.items.item_factory import ItemFactory
from engine.items.affix_data import PREFIXES, SUFFIXES

class LootGenerator:
    @staticmethod
    def generate_loot(base_template_id: str, world, level: int = 1, rarity_roll: float = 0.5) -> Optional[Item]:
        """
        Generates an item based on a template, potentially applying prefixes and suffixes.
        rarity_roll: 0.0 to 1.0. Higher means better chance of affixes.
        """
        # 1. Create Base Item
        item = ItemFactory.create_item_from_template(base_template_id, world)
        if not item: return None

        # Determine eligible slots (Weapon/Armor check)
        item_type = item.__class__.__name__

        # 2. Roll for Affixes
        chance_mod = min(0.5, (level / 20.0))
        base_chance = 0.2 + (rarity_roll * 0.3) + chance_mod

        prefix_data = None
        suffix_data = None
        prefix_name = ""
        suffix_name = ""

        if random.random() < base_chance:
            prefix_name, prefix_data = LootGenerator._pick_affix(PREFIXES, item_type, level)

        if random.random() < base_chance:
            suffix_name, suffix_data = LootGenerator._pick_affix(SUFFIXES, item_type, level)

        # 3. Apply Affixes
        if prefix_data:
            LootGenerator._apply_prefix(item, prefix_data)
            item.name = f"{prefix_name} {item.name}"

        if suffix_data:
            LootGenerator._apply_suffix(item, suffix_data)
            item.name = f"{item.name} {suffix_name}"

        # 4. Construct Composite Equip Effect (Merging Stats)
        combined_stats = {}
        buff_name = None

        # Gather existing effect if template had one
        existing_effect = item.get_property("equip_effect")
        if existing_effect and existing_effect.get("type") == "stat_mod":
            combined_stats.update(existing_effect.get("modifiers", {}))
            
        # Merge Suffix Stats
        if suffix_data and "equip_stats" in suffix_data:
            for stat, val in suffix_data["equip_stats"].items():
                combined_stats[stat] = combined_stats.get(stat, 0) + val
                
        # Handle named buff (e.g. Vampirism)
        if suffix_data and "equip_buff" in suffix_data:
            buff_name = suffix_data["equip_buff"]

        # Apply merged effect
        if combined_stats or buff_name:
            final_effect_name = buff_name if buff_name else f"Enchantment of {item.name}"
            
            new_effect = {
                "type": "stat_mod" if not buff_name else "buff",
                "name": final_effect_name,
                "modifiers": combined_stats
            }
            item.update_property("equip_effect", new_effect)
            item.description += f" It hums with magical energy."

        return item

    @staticmethod
    def _pick_affix(pool: Dict[str, Any], item_type: str, level: int) -> tuple[str, Dict]:
        valid = []
        for name, data in pool.items():
            if "All" in data["allowed_types"] or item_type in data["allowed_types"]:
                if level >= data.get("level_min", 1):
                    valid.append((name, data))
        
        if not valid: return "", {}
        return random.choice(valid)

    @staticmethod
    def _apply_prefix(item: Item, data: Dict):
        # Prefixes modify the Item's direct properties
        mods = data.get("modifiers", {})
        
        if "damage" in mods:
            cur = item.get_property("damage")
            if cur is not None: item.update_property("damage", cur + mods["damage"])
            
        if "defense" in mods:
            cur = item.get_property("defense")
            if cur is not None: item.update_property("defense", cur + mods["defense"])
            
        if "durability" in mods:
            cur = item.get_property("durability", 0)
            mx = item.get_property("max_durability", 0)
            item.update_property("durability", cur + mods["durability"])
            item.update_property("max_durability", mx + mods["durability"])

        if "weight" in mods:
            item.weight = max(0.1, item.weight + mods["weight"])
            item.update_property("weight", item.weight)

        mult = data.get("value_mult", 1.0)
        item.value = int(item.value * mult)
        item.update_property("value", item.value)

    @staticmethod
    def _apply_suffix(item: Item, data: Dict):
        mult = data.get("value_mult", 1.0)
        item.value = int(item.value * mult)
        item.update_property("value", item.value)