# engine/crafting/crafting_manager.py
import json
import os
from typing import Any, Dict, List, Tuple, Optional, TYPE_CHECKING

from engine.config import FORMAT_ERROR, FORMAT_RESET, FORMAT_SUCCESS
from engine.crafting.recipe import Recipe
from engine.items import references
from engine.items.item import Item
from engine.utils.content_values import ContentValueError
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
        # Recipes refused at load, each message naming the field in the file.
        # A caller that wants to report them -- `boot_warnings`, a doctor
        # command -- reads this rather than grepping stdout.
        self.recipe_errors: List[str] = []
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
                            # `_comment` and friends are authoring notes, not
                            # recipes; every other loader in the engine skips
                            # them and this one used to crash on them.
                            if str(r_id).startswith("_"):
                                continue
                            if not isinstance(r_data, dict):
                                print(f"{FORMAT_ERROR}Skipping recipe '{r_id}' in {filename}: must be an object{FORMAT_RESET}")
                                continue
                            # One unusable recipe must not take the rest of the
                            # file with it: the refused value is named by
                            # `Recipe`, and the recipes that are well-formed
                            # still load. Before this, a single bad field was
                            # either silently ignored or lost the whole file.
                            try:
                                self.recipes[r_id] = Recipe(r_id, r_data)
                            except ContentValueError as refused:
                                self.recipe_errors.append("%s: %s" % (filename, refused))
                                print(f"{FORMAT_ERROR}Skipping recipe: {refused}{FORMAT_RESET}")
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

        # 3. Check Ingredients (each ingredient's primary reference, or any
        #    authored substitute; a reference may be a template, a family or a
        #    capability rather than one id)
        for ing in recipe.ingredients:
            req_qty = max(1, int(ing.get("quantity", 1)))
            options = Recipe.ingredient_options(ing)
            available = 0
            for option in options:
                available = len(player.inventory.select_items_matching(
                    req_qty, predicate=lambda item: self._ingredient_matches(option, item)
                ))
                if available >= req_qty:
                    break
            if available < req_qty:
                name = Recipe.describe_reference(ing, self.world)
                message = f"Missing ingredient: {name} ({available}/{req_qty})"
                alt_names = [
                    Recipe.describe_reference(option, self.world)
                    for option in options[1:]
                ]
                if alt_names:
                    message += f" -- or: {', '.join(alt_names)}"
                return False, message

        return True, "Ready to craft."

    @staticmethod
    def _material_quality_score(item: Item) -> int:
        raw_score = item.get_property("material_quality_score", 0)
        return int(raw_score) if isinstance(raw_score, int) and not isinstance(raw_score, bool) else 0

    # -- one matcher, every call site -----------------------------------------
    # An ingredient may name an exact template, a family, or a capability. The
    # rule itself lives in `engine/items/references.py`, because a vendor's buy
    # order asks the same question about the same items; what is here is the
    # world this manager answers it with. Counting, selecting, previewing and
    # spending all go through the methods below, because a recipe that *looks*
    # craftable and then fails to craft is worse than one that says what it is
    # missing.

    def _family_of(self, item: Item) -> str:
        """This item's family, falling back to the template it came from.

        Instances built before families existed -- or by a content set that
        declares none -- carry no `item_family` of their own.
        """
        family_id = str(item.get_property("item_family", "") or "")
        if family_id:
            return family_id
        template = getattr(self.world, "item_templates", {}).get(str(getattr(item, "obj_id", "")), {})
        return str(template.get("item_family", "") or "") if isinstance(template, dict) else ""

    def _family_declares(self, family_id: str, capability: str) -> bool:
        registry = getattr(self.world, "contract_registry", None)
        if registry is None or not family_id or not capability:
            return False
        return bool(registry.family_has_capability(family_id, capability))

    def _item_has_capability(self, item: Item, capability: str) -> bool:
        """Whether this item's family declares a capability."""
        return self._family_declares(self._family_of(item), capability)

    def _reference_questions(self) -> Dict[str, Any]:
        """The world's answers to the questions a reference asks."""
        return {
            "quality_of": self._material_quality_score,
            "item_family": self._family_of,
            "family_has_capability": self._family_declares,
            "identity_of": lambda item: str(getattr(item, "obj_id", "")),
        }

    def _ingredient_matches(self, option: Dict[str, Any], item: Item) -> bool:
        """Whether a held item satisfies one authored option."""
        return references.matches(option, item, **self._reference_questions())

    def resolve_reference_template(self, ingredient: Dict[str, Any]) -> Optional[str]:
        """A concrete template id that would satisfy this ingredient, if any.

        Only used by tooling that has to *hand someone the thing* rather than
        check for it (the `givemats` debug command). Player-facing code never
        guesses: it counts what the player is actually holding.
        """
        templates = getattr(self.world, "item_templates", {})
        return references.resolve_template_id(
            ingredient,
            family_of_template=lambda item_id: str(
                templates.get(item_id, {}).get("item_family", "") or ""
            ) if isinstance(templates.get(item_id), dict) else "",
            family_has_capability=self._family_declares,
            template_ids=list(templates),
        )

    def count_ingredient(self, player: 'Player', ingredient: Dict[str, Any]) -> int:
        """How many units of this ingredient the player is holding."""
        return references.count_matching(
            ingredient,
            player.inventory,
            max(1, int(ingredient.get("quantity", 1))),
            **self._reference_questions(),
        )

    def select_recipe_ingredients(self, player: 'Player', recipe: Recipe) -> Optional[List[Item]]:
        """Choose the exact, highest-quality input units for a recipe.

        Tries each ingredient's primary reference first -- preserving today's
        behavior exactly for every recipe without alternatives, and keeping
        the primary preferred even when it does have substitutes -- and
        only falls through to an authored alternative when the primary is
        short. A reference may be an exact template, a family or a capability;
        within one reference the highest material grades go first."""
        selected: List[Item] = []
        for ingredient in recipe.ingredients:
            plan = references.match_plan(
                ingredient,
                player.inventory,
                max(1, int(ingredient.get("quantity", 1))),
                **self._reference_questions(),
            )
            if plan is None:
                return None
            selected.extend(plan["items"])
        return selected

    def matched_option(self, ingredient: Dict[str, Any], item: Item) -> Optional[Dict[str, Any]]:
        """Which authored option of this ingredient the given item satisfies.

        Returns the option dict (with its ``quality_penalty``) so a spent unit
        is scored against the reference it actually matched, not against a
        guessed id. ``None`` when the item satisfies nothing here.
        """
        return references.matching_option(ingredient, item, **self._reference_questions())

    def _ingredient_penalty(self, ingredient: Dict[str, Any], item: Item) -> int:
        option = self.matched_option(ingredient, item)
        return references.penalty_of(option) if option is not None else 0

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
                    in_slot = [
                        max(0, self._material_quality_score(item) - self._ingredient_penalty(ingredient, item))
                        for item in chosen
                    ]
                    selected_scores.append(min(in_slot))
                offset += quantity
            return min(selected_scores) if selected_scores else 0

        # Compatibility path for callers that only need a preview.
        selected = self.select_recipe_ingredients(player, recipe)
        if selected is None:
            return 0
        return self.ingredient_quality_score(player, recipe, selected)

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
                "item_id": str(ingredient.get("item_id", "") or ""),
                "item_family": str(ingredient.get("item_family", "") or ""),
                "capability": str(ingredient.get("capability", "") or ""),
                "reference": Recipe.reference_label(ingredient),
                "name": Recipe.describe_reference(ingredient, self.world),
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

    def salvage_output_for(self, item: Item) -> Optional[Dict[str, Any]]:
        """Which salvage rule applies to this item, split into its two halves.

        Three places can answer, most specific first:

        1. the item's own `salvage_output` property -- an author saying what
           *this template* breaks down into;
        2. `salvage_rules.by_family[family]` -- the content set saying what a
           kind of thing breaks down into, which is the rule an author almost
           always means ("armour comes back as ingots"), and which does not go
           stale when a new template joins the family;
        3. `salvage_rules[ItemClass]` -- the older spelling, keyed by the engine
           class the family resolves to. Kept because content sets written
           before families existed still use it, and because a template with no
           family has no family key to be found under.

        Returns `{"reference": ..., "quantity_per_weight": ..., "source": ...}`.
        The reference is what the item breaks down *into* -- an item reference,
        the same shape a recipe ingredient and a vendor's buy order use -- and
        the rate is salvage's own key, which is why the two are separated here
        rather than left in one dict for callers to pick apart.
        """
        candidates: List[Tuple[str, Any]] = [("item", item.get_property("salvage_output"))]
        salvage_rules = self.world.ruleset_section("crafting").get("salvage_rules", {})
        if isinstance(salvage_rules, dict):
            by_family = salvage_rules.get("by_family", {})
            family_id = self._family_of(item)
            if family_id and isinstance(by_family, dict):
                candidates.append(("family", by_family.get(family_id)))
            candidates.append(("class", salvage_rules.get(item.__class__.__name__)))

        for source, authored in candidates:
            if not isinstance(authored, dict) or not references.names_something(authored):
                continue
            return {
                "reference": authored,
                "quantity_per_weight": authored.get("quantity_per_weight"),
                "source": source,
            }
        return None

    def salvage(self, player: 'Player', item: Item) -> str:
        """Breaks down an item into materials.

        What comes out is authored as an item *reference* -- the same shape a
        recipe ingredient and a vendor's buy order use -- so a rule can say "any
        part of grade 1 or better" rather than naming one template. An item this
        content set declares no rule for falls back to the set's scrap, and a
        set that declares neither simply cannot salvage it, and says so.
        """
        salvage_rules = self.world.ruleset_section("crafting").get("salvage_rules", {})
        rule = self.salvage_output_for(item)

        output_template_id: Optional[str] = None
        output_qty = 1
        if rule is not None:
            output_template_id = self.resolve_reference_template(rule["reference"])
            output_qty = self._salvage_quantity(rule, item)
        elif isinstance(salvage_rules, dict) and salvage_rules.get("default_item_id"):
            # A content set's last resort: everything breaks down into scrap,
            # and for an item this set declares no rule for it is also the only
            # answer -- an item nobody said how to break down does not break
            # down into nothing, it breaks down into the set's scrap.
            output_template_id = str(salvage_rules["default_item_id"])

        if not output_template_id:
            return f"{FORMAT_ERROR}You cannot salvage the {item.name}.{FORMAT_RESET}"

        result = ItemFactory.create_item_from_template(output_template_id, self.world)
        if not result:
            return f"{FORMAT_ERROR}You cannot salvage the {item.name}.{FORMAT_RESET}"

        can_add, space_message = player.inventory.can_add_item_after_removing(result, output_qty, [item])
        if not can_add:
            return f"{FORMAT_ERROR}You cannot salvage the {item.name}: {space_message}{FORMAT_RESET}"
        if not player.inventory.remove_item_instances([item]):
            return f"{FORMAT_ERROR}You cannot salvage the {item.name} safely.{FORMAT_RESET}"
        added, add_message = player.inventory.add_item(result, output_qty)
        if not added:
            return f"{FORMAT_ERROR}Unable to recover salvage: {add_message}{FORMAT_RESET}"

        return f"{FORMAT_SUCCESS}You salvage the {item.name} and recover {output_qty} {result.name}.{FORMAT_RESET}"

    def _salvage_quantity(self, rule: Dict[str, Any], item: Item) -> int:
        """How many units a broken-down item yields.

        Authored `quantity_per_weight` scales with the item's weight, which is
        what makes a heavier thing worth more of the material. A rule that
        names no rate yields exactly one, as the ruleset default always has.
        """
        raw = rule.get("quantity_per_weight")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return 1
        try:
            return max(1, int(float(item.weight) * float(raw)))
        except (TypeError, ValueError):
            return 1

    def _resolve_salvage_output(self, rule: Dict[str, Any], item: Item) -> Optional[str]:
        """Which template this rule actually produces for this item."""
        return self.resolve_reference_template(rule)
