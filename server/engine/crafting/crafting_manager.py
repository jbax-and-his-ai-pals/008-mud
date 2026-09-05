# engine/crafting/crafting_manager.py
import json
import os
from typing import Dict, List, Tuple, Optional, TYPE_CHECKING

from engine.config import FORMAT_ERROR, FORMAT_RESET, FORMAT_SUCCESS
from engine.crafting.recipe import Recipe
from engine.items.item import Item
from engine.items.item_factory import ItemFactory
from engine.core.skill_system import SkillSystem

if TYPE_CHECKING:
    from engine.world.world import World
    from engine.player import Player

class CraftingManager:
    def __init__(self, world: 'World'):
        self.world = world
        self.content_root = world.content_root
        self.recipes: Dict[str, Recipe] = {}
        self._load_recipes()

    def _load_recipes(self):
        """Loads all recipe JSON files from data/crafting."""
        crafting_dir = os.path.join(self.content_root, "crafting")
        if not os.path.exists(crafting_dir):
            return

        for filename in os.listdir(crafting_dir):
            if filename.endswith(".json"):
                file_path = os.path.join(crafting_dir, filename)
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        for r_id, r_data in data.items():
                            self.recipes[r_id] = Recipe(r_id, r_data)
                except Exception as e:
                    print(f"{FORMAT_ERROR}Error loading recipes from {filename}: {e}{FORMAT_RESET}")

    def get_nearby_stations(self, player: Optional['Player'] = None) -> List[str]:
        stations = []
        active_player = player or self.world.resolve_reference_player()
        if not active_player:
            return stations
        # 1. Check Room Items (e.g. Anvil, Workbench)
        for item in self.world.get_items_in_current_room(active_player):
            station_type = item.get_property("crafting_station_type")
            if station_type:
                stations.append(station_type)
        
        # 2. Check Player Inventory (e.g. Mortar & Pestle, Portable Kit)
        for slot in active_player.inventory.slots:
            if slot.item:
                station_type = slot.item.get_property("crafting_station_type")
                if station_type:
                    stations.append(station_type)
        
        return stations

    def can_craft(self, player: 'Player', recipe: Recipe) -> Tuple[bool, str]:
        """Checks if player has ingredients, station, AND SKILL."""
        
        # 1. Check Station
        if recipe.station_required:
            nearby = self.get_nearby_stations(player)
            if recipe.station_required not in nearby:
                return False, f"You need a {recipe.station_display} to craft this."

        # 2. Check Ingredients
        for ing in recipe.ingredients:
            req_id = ing["item_id"]
            req_qty = ing["quantity"]
            has_qty = player.inventory.count_item(req_id)
            if has_qty < req_qty:
                template = ItemFactory.get_template(req_id, self.world)
                name = template.get("name", req_id) if template else req_id
                return False, f"Missing ingredient: {name} ({has_qty}/{req_qty})"

        return True, "Ready to craft."

    def craft(self, player: 'Player', recipe_id: str) -> str:
        """Executes the crafting process: consume ingredients, create result."""
        recipe = self.recipes.get(recipe_id)
        if not recipe: return "Unknown recipe."
        
        # Explicit check for result ID to ensure validity
        if not recipe.result_item_id:
            return "Unknown recipe configuration: Missing result item."

        can_craft, msg = self.can_craft(player, recipe)
        if not can_craft: return msg

        # --- NEW: Skill Check Logic ---
        # Base difficulty 10 + (result value / 5)
        # This makes valuable items harder to craft
        template = ItemFactory.get_template(recipe.result_item_id, self.world)
        item_value = template.get("value", 10) if template else 10
        difficulty = 10 + int(item_value / 5)
        
        success, roll_msg = SkillSystem.attempt_check(player, "crafting", difficulty)
        
        if not success:
            # Failure logic: Let's keep it simple: Fail but keep mats for now (less frustrating)
            SkillSystem.grant_xp(player, "crafting", 2) # Consolation XP
            return f"{FORMAT_ERROR}You failed to craft the item. The materials were difficult to work with.{FORMAT_RESET} {roll_msg}"

        # 1. Create the result item FIRST (to ensure it works before taking mats)
        result_item = ItemFactory.create_item_from_template(recipe.result_item_id, self.world)
        if not result_item:
            return "Error: Could not create result item. Crafting aborted."

        # 2. Check Inventory Space
        can_add, space_msg = player.inventory.can_add_item(result_item, recipe.result_quantity)
        if not can_add:
            return f"Not enough inventory space: {space_msg}"

        # 3. Consume Ingredients
        for ing in recipe.ingredients:
            player.inventory.remove_item(ing["item_id"], ing["quantity"])

        # 4. Add Result
        player.inventory.add_item(result_item, recipe.result_quantity)
        
        # Grant XP
        xp_gain = max(10, item_value // 2)
        xp_msg = SkillSystem.grant_xp(player, "crafting", xp_gain)
        
        return f"{FORMAT_SUCCESS}Successfully crafted {recipe.result_quantity} x {result_item.name}.{FORMAT_RESET} {roll_msg}{xp_msg}"

    def salvage(self, player: 'Player', item: Item) -> str:
        """Breaks down an item into basic materials.

        Output is determined by the item's own "salvage_output" property
        (an author-declared override), falling back to a ruleset-driven
        rule keyed by the item's class (Weapon/Armor/...), and finally a
        content-set-provided generic default. An item type/content set with
        no salvage rule configured simply cannot be salvaged.
        """
        salvage_rules = self.world.ruleset_section("crafting").get("salvage_rules", {})

        output_template_id = None
        output_qty = 1

        override = item.get_property("salvage_output")
        if isinstance(override, dict) and override.get("item_id"):
            output_template_id = override["item_id"]
            output_qty = max(1, int(item.weight * override.get("quantity_per_weight", 1.0)))
        else:
            rule = salvage_rules.get(item.__class__.__name__)
            if isinstance(rule, dict) and rule.get("item_id"):
                output_template_id = rule["item_id"]
                output_qty = max(1, int(item.weight * rule.get("quantity_per_weight", 1.0)))
            else:
                output_template_id = salvage_rules.get("default_item_id")

        if not output_template_id:
            return f"{FORMAT_ERROR}You cannot salvage the {item.name}.{FORMAT_RESET}"

        mat = ItemFactory.create_item_from_template(output_template_id, self.world)
        if not mat:
             return f"{FORMAT_ERROR}You cannot salvage the {item.name}.{FORMAT_RESET}"
             
        # 3. Remove Item
        # If stackable, we only salvage 1 unless we add qty logic. Assuming 1.
        player.inventory.remove_item(item.obj_id, 1)
        
        # 4. Add Materials
        player.inventory.add_item(mat, output_qty)
        
        return f"{FORMAT_SUCCESS}You salvage the {item.name} and recover {output_qty} {mat.name}.{FORMAT_RESET}"
