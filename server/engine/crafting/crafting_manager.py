# engine/crafting/crafting_manager.py
import json
import os
from typing import Dict, List, Tuple, Optional, TYPE_CHECKING

from engine.config import FORMAT_ERROR, FORMAT_RESET, FORMAT_SUCCESS
from engine.crafting.recipe import Recipe
from engine.items.item import Item
from engine.items.item_factory import ItemFactory
from engine.core.skill_system import SkillSystem
from engine.core import advancement

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
                    with open(file_path, 'r', encoding='utf-8') as f:
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

        # 1. Check Discovery
        if recipe.requires_discovery and recipe.recipe_id not in getattr(player, "known_recipe_ids", set()):
            return False, "You haven't learned this recipe yet."

        # 2. Check Station
        if recipe.station_required:
            nearby = self.get_nearby_stations(player)
            if recipe.station_required not in nearby:
                return False, f"You need a {recipe.station_display} to craft this."

        # 3. Check Ingredients (the primary item_id, or any authored substitute)
        for ing in recipe.ingredients:
            req_qty = ing["quantity"]
            options = Recipe.ingredient_options(ing)
            has_any = any(player.inventory.count_item(opt["item_id"]) >= req_qty for opt in options)
            if not has_any:
                req_id = ing["item_id"]
                template = ItemFactory.get_template(req_id, self.world)
                name = template.get("name", req_id) if template else req_id
                has_qty = player.inventory.count_item(req_id)
                message = f"Missing ingredient: {name} ({has_qty}/{req_qty})"
                alt_names = []
                for opt in options[1:]:
                    alt_template = ItemFactory.get_template(opt["item_id"], self.world)
                    alt_names.append(alt_template.get("name", opt["item_id"]) if alt_template else opt["item_id"])
                if alt_names:
                    message += f" -- or: {', '.join(alt_names)}"
                return False, message

        return True, "Ready to craft."

    @staticmethod
    def _material_quality_score(item: Item) -> int:
        raw_score = item.get_property("material_quality_score", 0)
        return int(raw_score) if isinstance(raw_score, int) and not isinstance(raw_score, bool) else 0

    def select_recipe_ingredients(self, player: 'Player', recipe: Recipe) -> Optional[List[Item]]:
        """Choose the exact, highest-quality input units for a recipe.

        Tries each ingredient's primary item_id first -- preserving today's
        behavior exactly for every recipe without alternatives, and keeping
        the primary preferred even when it does have substitutes -- and
        only falls through to an authored alternative when the primary is
        short."""
        selected: List[Item] = []
        for ingredient in recipe.ingredients:
            quantity = max(1, int(ingredient.get("quantity", 1)))
            chosen: Optional[List[Item]] = None
            for option in Recipe.ingredient_options(ingredient):
                candidate = player.inventory.select_items(
                    str(option["item_id"]), quantity, sort_key=self._material_quality_score
                )
                if len(candidate) == quantity:
                    chosen = candidate
                    break
            if chosen is None:
                return None
            selected.extend(chosen)
        return selected

    def ingredient_quality_score(self, player: 'Player', recipe: Recipe, selected_items: Optional[List[Item]] = None) -> int:
        """Return the limiting score among the exact quality-setting inputs."""
        if selected_items is not None:
            selected_scores: List[int] = []
            offset = 0
            for ingredient in recipe.ingredients:
                quantity = max(1, int(ingredient.get("quantity", 1)))
                chosen = selected_items[offset:offset + quantity]
                if len(chosen) != quantity:
                    return 0
                if ingredient.get("quality_contributes", True) is not False:
                    base_score = min(self._material_quality_score(item) for item in chosen)
                    chosen_item_id = str(getattr(chosen[0], "obj_id", ""))
                    penalty = next(
                        (int(opt["quality_penalty"]) for opt in Recipe.ingredient_options(ingredient) if opt["item_id"] == chosen_item_id),
                        0,
                    )
                    selected_scores.append(max(0, base_score - penalty))
                offset += quantity
            return min(selected_scores) if selected_scores else 0

        # Compatibility path for callers that only need a preview.
        selected_scores: List[int] = []
        for ingredient in recipe.ingredients:
            if ingredient.get("quality_contributes", True) is False:
                continue
            item_id = str(ingredient.get("item_id", ""))
            quantity = max(1, int(ingredient.get("quantity", 1)))
            scores: List[int] = []
            for slot in player.inventory.slots:
                item = slot.item
                if item is None or str(getattr(item, "obj_id", "")) != item_id:
                    continue
                score = self._material_quality_score(item)
                scores.extend([score] * min(quantity, int(slot.quantity)))
            if len(scores) < quantity:
                return 0
            selected_scores.append(min(sorted(scores, reverse=True)[:quantity]))
        return min(selected_scores) if selected_scores else 0

    def quality_preview(self, player: 'Player', recipe: Recipe) -> Dict[str, object]:
        """Describe the next craft's material-grade outcome without spending.

        This intentionally returns generic recipe/item identifiers and tier
        metadata; presentation layers may use any genre vocabulary they need.
        """
        selected = self.select_recipe_ingredients(player, recipe)
        material_score = self.ingredient_quality_score(player, recipe, selected) if selected else 0
        next_craft_count = int(getattr(player, "recipe_craft_counts", {}).get(recipe.recipe_id, 0)) + 1
        tier = recipe.quality_tier(next_craft_count, material_score)
        contributors = [
            {
                "item_id": str(ingredient.get("item_id", "")),
                "quantity": max(1, int(ingredient.get("quantity", 1))),
            }
            for ingredient in recipe.quality_ingredients()
        ]
        return {
            "next_craft_count": next_craft_count,
            "material_quality_score": material_score,
            "tier": tier,
            "next_tier": recipe.next_quality_tier(next_craft_count, material_score),
            "contributors": contributors,
        }

    def craft(self, player: 'Player', recipe_id: str) -> str:
        """Executes the crafting process: consume ingredients, create result."""
        recipe = self.recipes.get(recipe_id)
        if not recipe: return "Unknown recipe."
        
        # Explicit check for result ID to ensure validity
        if not recipe.result_item_id:
            return "Unknown recipe configuration: Missing result item."

        can_craft, msg = self.can_craft(player, recipe)
        if not can_craft: return msg
        selected_ingredients = self.select_recipe_ingredients(player, recipe)
        if selected_ingredients is None:
            return "The selected ingredients are no longer available."

        # --- NEW: Skill Check Logic ---
        # By default, result value informs a skill check. Content can opt a
        # recipe into a guaranteed beginner craft (difficulty <= 0), or author
        # a specific positive difficulty without changing engine mechanics.
        template = ItemFactory.get_template(recipe.result_item_id, self.world)
        item_value = template.get("value", 10) if template else 10
        try:
            configured_difficulty = None if recipe.difficulty is None else int(recipe.difficulty)
        except (TypeError, ValueError):
            return "Unknown recipe configuration: difficulty must be an integer."
        difficulty = configured_difficulty if configured_difficulty is not None else 10 + int(item_value / 5)
        if difficulty <= 0:
            success, roll_msg = True, "(Beginner recipe: no skill check required)"
        else:
            success, roll_msg = SkillSystem.attempt_check(player, "crafting", difficulty)
        
        if not success:
            # Failure logic: Let's keep it simple: Fail but keep mats for now (less frustrating)
            SkillSystem.grant_xp(player, "crafting", 2) # Consolation XP
            return f"{FORMAT_ERROR}You failed to craft the item. The materials were difficult to work with.{FORMAT_RESET} {roll_msg}"

        # 1. Create the result item FIRST (to ensure it works before taking mats)
        result_item = ItemFactory.create_item_from_template(recipe.result_item_id, self.world)
        if not result_item:
            return "Error: Could not create result item. Crafting aborted."
        # Provenance lets the social layer distinguish a personal creation
        # from an identical shop purchase without changing base item data.
        result_item.properties["crafted_by_player"] = True
        result_item.properties["crafted_recipe_id"] = recipe.recipe_id
        prior_crafts = int(getattr(player, "recipe_craft_counts", {}).get(recipe.recipe_id, 0))
        result_item.properties["crafted_recipe_count"] = prior_crafts + 1
        material_quality_score = self.ingredient_quality_score(player, recipe, selected_ingredients)
        quality_tier = recipe.quality_tier(prior_crafts + 1, material_quality_score)
        quality_note = ""
        if quality_tier:
            quality_id = str(quality_tier.get("id", "standard")).strip() or "standard"
            quality_label = str(quality_tier.get("label", quality_id.replace("_", " ").title())).strip()
            try:
                multiplier = max(0.0, float(quality_tier.get("value_multiplier", 1.0)))
                gift_bonus = max(0, int(quality_tier.get("gift_bonus", 0)))
            except (TypeError, ValueError):
                return "Unknown recipe configuration: quality tier values must be numeric."
            result_item.value = max(0, int(round(result_item.value * multiplier)))
            result_item.update_property("value", result_item.value)
            # Different qualities must remain distinct inventory instances;
            # stacking would silently discard their value and gift provenance.
            result_item.stackable = False
            result_item.update_property("stackable", False)
            result_item.properties["craft_quality"] = quality_id
            result_item.properties["craft_quality_label"] = quality_label
            result_item.properties["material_quality_score"] = material_quality_score
            result_item.properties["gift_quality_bonus"] = gift_bonus
            quality_note = f"\nCraft quality: {quality_label}."

        # 2. Check output capacity after the exact ingredients are removed.
        can_add, space_msg = player.inventory.can_add_item_after_removing(
            result_item, recipe.result_quantity, selected_ingredients
        )
        if not can_add:
            return f"Not enough inventory space: {space_msg}"

        # 3. Consume the same exact ingredients whose quality was evaluated.
        if selected_ingredients and not player.inventory.remove_item_instances(selected_ingredients):
            return "The selected ingredients are no longer available."

        # 4. Add Result
        added, add_message = player.inventory.add_item(result_item, recipe.result_quantity)
        if not added:
            # Capacity was preflighted against this exact spend, so reaching
            # here requires an external mutation. Never present it as a
            # successful craft.
            return f"Unable to add the crafted item: {add_message}"
        player.recipe_craft_counts[recipe.recipe_id] = prior_crafts + 1
        if self.world.quest_manager:
            self.world.quest_manager.handle_item_crafted(player, recipe, quality_tier)
        discovery_manager = getattr(getattr(self.world, "game", None), "discovery_manager", None)
        discovery_note = discovery_manager.handle_item_discovery(player, result_item) if discovery_manager else ""
        
        # Grant XP
        xp_gain = max(10, item_value // 2)
        xp_msg = SkillSystem.grant_xp(player, "crafting", xp_gain)

        # A recipe made for the first time is a recognised activity and pays
        # advancement XP once. Distinct from the crafting *skill* XP above,
        # which is the repetition-rewarding track.
        recipe_id = str(getattr(recipe, "recipe_id", "") or "")
        first_craft_note = advancement.award(
            player, advancement.KIND_RECIPE, recipe_id, payload={"recipe_id": recipe_id}
        )

        familiarity_note = ""
        milestone = recipe.familiarity_milestone(prior_crafts + 1)
        if milestone and int(milestone["count"]) == prior_crafts + 1:
            message = str(milestone.get("message", "")).strip()
            familiarity_note = f"\n{message}" if message else f"\nFamiliarity milestone: {prior_crafts + 1} crafts."
        result = f"{FORMAT_SUCCESS}Successfully crafted {recipe.result_quantity} x {result_item.name}.{FORMAT_RESET} {roll_msg}{xp_msg}{familiarity_note}{quality_note}"
        notes = [note for note in (discovery_note, first_craft_note) if note]
        return f"{result}\n" + "\n".join(notes) if notes else result

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
             
        can_add, space_message = player.inventory.can_add_item_after_removing(mat, output_qty, [item])
        if not can_add:
            return f"{FORMAT_ERROR}You cannot salvage the {item.name}: {space_message}{FORMAT_RESET}"
        if not player.inventory.remove_item_instances([item]):
            return f"{FORMAT_ERROR}You cannot salvage the {item.name} safely.{FORMAT_RESET}"
        added, add_message = player.inventory.add_item(mat, output_qty)
        if not added:
            return f"{FORMAT_ERROR}Unable to recover salvage: {add_message}{FORMAT_RESET}"
        
        return f"{FORMAT_SUCCESS}You salvage the {item.name} and recover {output_qty} {mat.name}.{FORMAT_RESET}"
