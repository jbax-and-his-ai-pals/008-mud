# engine/crafting/recipe.py
from typing import List, Dict, Any

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
        # ``None`` preserves the content-neutral default difficulty derived
        # from result value. A content set may use 0 for a guaranteed beginner
        # recipe or supply an explicit positive skill-check difficulty.
        self.difficulty = data.get("difficulty")
        
        # List of dicts: {"item_id":Str, "quantity":Int}
        self.ingredients: List[Dict[str, Any]] = data.get("ingredients", [])
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
            key=lambda entry: int(entry.get("rank", int(entry["min_crafts"]) + int(entry.get("min_material_quality", 0)))),
        ) if reached else None
