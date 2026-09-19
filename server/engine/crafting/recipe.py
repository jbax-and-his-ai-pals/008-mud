# engine/crafting/recipe.py
from typing import List, Dict, Any

from engine.items import references


class Recipe:
    def __init__(self, recipe_id: str, data: Dict[str, Any]):
        self.recipe_id = recipe_id
        self.name = data.get("name", "Unknown Recipe")
        self.description = data.get("description", "Creates an item.")
        
        # The template ID of the item created
        self.result_item_id = data.get("result_item_id")
        self.result_quantity = data.get("result_quantity", 1)
        
        # "anvil", "alchemy_table", "campfire", or None (handcrafting)
        self.station_required = data.get("station_required")
        # A recipe every player can attempt from the start unless content
        # opts it into being taught/found first (see Player.learn_recipe).
        self.requires_discovery: bool = bool(data.get("requires_discovery", False))
        # ``None`` preserves the content-neutral default difficulty derived
        # from result value. A content set may use 0 for a guaranteed beginner
        # recipe or supply an explicit positive skill-check difficulty.
        self.difficulty = data.get("difficulty")
        
        # List of dicts: {"item_id":Str, "quantity":Int}
        self.ingredients: List[Dict[str, Any]] = data.get("ingredients", [])
        # Alternative names a player might type for this recipe, resolved by
        # engine/naming.py. The recipe's own `name` is authored as an
        # instruction ("Tie Wildflower Posy"); an alias is what someone would
        # actually ask for ("posy", "flowers").
        raw_aliases = data.get("aliases", [])
        self.aliases: List[str] = [
            str(alias).strip() for alias in raw_aliases
            if isinstance(alias, (str, int)) and str(alias).strip()
        ] if isinstance(raw_aliases, list) else []
        # Optional content metadata. The engine records familiarity for every
        # recipe, but only authored milestones turn it into player feedback.
        raw_milestones = data.get("familiarity_milestones", [])
        self.familiarity_milestones: List[Dict[str, Any]] = [
            milestone for milestone in raw_milestones
            if isinstance(milestone, dict) and isinstance(milestone.get("count"), int)
            and not isinstance(milestone.get("count"), bool) and int(milestone["count"]) > 0
        ] if isinstance(raw_milestones, list) else []
        raw_quality_tiers = data.get("quality_tiers", [])
        self.quality_tiers: List[Dict[str, Any]] = [
            tier for tier in raw_quality_tiers
            if isinstance(tier, dict) and isinstance(tier.get("min_crafts"), int)
            and not isinstance(tier.get("min_crafts"), bool) and int(tier["min_crafts"]) > 0
            and ("min_material_quality" not in tier or (isinstance(tier["min_material_quality"], int) and not isinstance(tier["min_material_quality"], bool)))
            and ("rank" not in tier or (isinstance(tier["rank"], int) and not isinstance(tier["rank"], bool)))
        ] if isinstance(raw_quality_tiers, list) else []
        
    @property
    def station_display(self) -> str:
        if not self.station_required:
            return "Handcrafting"
        return self.station_required.replace("_", " ").title()

    def familiarity_milestone(self, craft_count: int) -> Dict[str, Any] | None:
        """Return the highest authored milestone reached by this recipe."""
        reached = [entry for entry in self.familiarity_milestones if int(entry["count"]) <= craft_count]
        return max(reached, key=lambda entry: int(entry["count"])) if reached else None

    def quality_tier(self, craft_count: int, material_quality_score: int = 0) -> Dict[str, Any] | None:
        """Return the highest authored craft-quality tier reached."""
        reached = [
            entry for entry in self.quality_tiers
            if int(entry["min_crafts"]) <= craft_count
            and int(entry.get("min_material_quality", 0)) <= material_quality_score
        ]
        return max(
            reached,
            key=self.quality_rank,
        ) if reached else None

    @staticmethod
    def quality_rank(entry: Dict[str, Any]) -> int:
        return int(entry.get("rank", int(entry["min_crafts"]) + int(entry.get("min_material_quality", 0))))

    def next_quality_tier(self, craft_count: int, material_quality_score: int = 0) -> Dict[str, Any] | None:
        """Return the nearest authored tier above the next craft's outcome."""
        current = self.quality_tier(craft_count, material_quality_score)
        current_rank = self.quality_rank(current) if current else -1
        higher = [tier for tier in self.quality_tiers if self.quality_rank(tier) > current_rank]
        return min(higher, key=self.quality_rank) if higher else None

    @staticmethod
    def ingredient_options(ingredient: Dict[str, Any]) -> List[Dict[str, Any]]:
        """The acceptable item_ids for one ingredient slot: the authored
        primary first, then any content-declared substitutes. Each option
        carries a quality_penalty (0 for the primary unless overridden,
        defaulting to 0 for an alternative that doesn't author one) applied
        to that slot's material-grade contribution when it's the one
        actually spent -- the "trade-off" in a substitution."""
        options = [dict(ingredient, quality_penalty=0)]
        alternatives = ingredient.get("alternatives", [])
        if isinstance(alternatives, list):
            for alternative in alternatives:
                if isinstance(alternative, dict) and Recipe.references_item(alternative):
                    options.append(dict(alternative, quality_penalty=max(0, int(alternative.get("quality_penalty", 0) or 0))))
        return options

    # -- what an ingredient asks for ------------------------------------------
    # An ingredient used to be an item id and nothing else. It may now name a
    # *rule* instead, and the rule lives in `engine/items/references.py` because
    # vendor orders ask the same question about the same items:
    #
    #   {"item_id": "item_iron_ingot", "quantity": 2}          exact template
    #   {"item_family": "salvaged_part", "min_material_quality": 2, ...}
    #   {"capability": "crafting_material", "min_material_quality": 1, ...}
    #
    # which is what lets a recipe say "any part good enough to use" rather than
    # listing every id, and what makes a content set's own vocabulary the thing
    # a recipe is written against.

    @staticmethod
    def references_item(ingredient: Dict[str, Any]) -> bool:
        """Whether this ingredient names something at all.

        `item_id` wins when present, so every recipe written before families
        existed resolves exactly as it did.
        """
        return references.names_something(ingredient)

    @staticmethod
    def minimum_quality(ingredient: Dict[str, Any]) -> int:
        return references.minimum_quality(ingredient)

    @staticmethod
    def reference_label(ingredient: Dict[str, Any]) -> str:
        """What kind of thing this ingredient names: an id, a family, a capability.

        Previews and the editor show this so an author can see that a recipe
        asks for *any* member of a family rather than one template.
        """
        return references.reference_kind(ingredient)

    @staticmethod
    def ingredient_options(ingredient: Dict[str, Any]) -> List[Dict[str, Any]]:
        """The acceptable references for one ingredient slot."""
        return references.options(ingredient)

    @staticmethod
    def describe_reference(ingredient: Dict[str, Any], world: Any = None) -> str:
        """A name for what this ingredient wants, for messages and previews."""
        def name_of_template(item_id: str) -> str:
            from engine.items.item_factory import ItemFactory

            template = ItemFactory.get_template(item_id, world) if world is not None else None
            return str(template.get("name", item_id)) if template else item_id

        def family_label(family_id: str) -> str:
            registry = getattr(world, "contract_registry", None)
            declared = registry.family(family_id) if registry is not None else None
            return str(declared.get("label", family_id) or family_id) if declared else family_id

        return references.describe(ingredient, name_of_template, family_label)

    def quality_ingredients(self) -> List[Dict[str, Any]]:
        """Return inputs which set the craft's material-grade outcome.

        Ingredients contribute by default so existing content preserves its
        behavior.  Content may set ``quality_contributes`` to false for a
        binding, container, fuel, or other required input whose grade should
        not diminish the authored primary material.
        """
        return [
            ingredient for ingredient in self.ingredients
            if ingredient.get("quality_contributes", True) is not False
        ]
