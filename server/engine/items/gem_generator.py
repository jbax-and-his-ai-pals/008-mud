"""Procedural gem instances built from authored Gem templates.

The template supplies the gemstone species and its intrinsic rarity.  A found
gem then rolls its own size and quality, so two rubies can be materially and
economically distinct without requiring a template for every combination.
"""
import random
from typing import Any, Optional

from engine.items.item import Item
from engine.items.item_factory import ItemFactory


RARITY_TIERS = {
    "common": {"rank": 1, "weight": 80},
    "uncommon": {"rank": 2, "weight": 28},
    "rare": {"rank": 3, "weight": 8},
    "legendary": {"rank": 4, "weight": 2},
}

SIZE_TIERS = (
    {"id": "tiny", "label": "tiny", "score": 1, "value_multiplier": 0.45, "weight_multiplier": 0.35},
    {"id": "small", "label": "small", "score": 2, "value_multiplier": 0.7, "weight_multiplier": 0.65},
    {"id": "standard", "label": "", "score": 3, "value_multiplier": 1.0, "weight_multiplier": 1.0},
    {"id": "large", "label": "large", "score": 4, "value_multiplier": 1.65, "weight_multiplier": 1.7},
    {"id": "magnificent", "label": "magnificent", "score": 5, "value_multiplier": 3.0, "weight_multiplier": 3.0},
)

QUALITY_TIERS = (
    {"id": "flawed", "label": "Flawed", "score": 1, "value_multiplier": 0.45},
    {"id": "rough", "label": "Rough", "score": 2, "value_multiplier": 0.7},
    {"id": "fine", "label": "Fine", "score": 3, "value_multiplier": 1.0},
    {"id": "exceptional", "label": "Exceptional", "score": 4, "value_multiplier": 1.6},
    {"id": "perfect", "label": "Perfect", "score": 5, "value_multiplier": 2.8},
)


class GemGenerator:
    @staticmethod
    def is_gem_template(world: Any, template_id: str) -> bool:
        template = getattr(world, "item_templates", {}).get(template_id, {})
        return isinstance(template, dict) and template.get("type") == "Gem"

    @staticmethod
    def generate_gem(
        world: Any,
        level: int = 1,
        template_id: Optional[str] = None,
        quality_score: Optional[int] = None,
    ) -> Optional[Item]:
        """Create one distinct gem instance.

        ``quality_score`` lets gathering nodes retain their authored regional
        material grade while still using the same size/value/name machinery.
        """
        level = max(1, int(level))
        if template_id is None:
            template_id = GemGenerator.pick_template_id(world, level)
        if not template_id or not GemGenerator.is_gem_template(world, template_id):
            return None
        item = ItemFactory.create_item_from_template(template_id, world)
        if item is None:
            return None
        template = world.item_templates[template_id]
        GemGenerator.decorate_gem(item, template, level, quality_score)
        return item

    @staticmethod
    def pick_template_id(world: Any, level: int = 1) -> Optional[str]:
        candidates: list[tuple[str, dict]] = [
            (item_id, template)
            for item_id, template in getattr(world, "item_templates", {}).items()
            if isinstance(template, dict)
            and template.get("type") == "Gem"
            and not template.get("properties", {}).get("debug_only")
        ]
        if not candidates:
            return None
        weights = []
        for _, template in candidates:
            rarity = GemGenerator.template_rarity(template)
            tier = RARITY_TIERS[rarity]
            # Higher-level sources increasingly have a chance to surface a
            # rarer species without removing the ordinary gems from play.
            weights.append(float(tier["weight"]) + (level - 1) * float(tier["rank"]) * 0.65)
        return random.choices([item_id for item_id, _ in candidates], weights=weights, k=1)[0]

    @staticmethod
    def template_rarity(template: dict) -> str:
        authored = str(template.get("rarity", "")).strip().lower()
        if authored in RARITY_TIERS:
            return authored
        # Legacy templates predate explicit rarity.  Their value already
        # encodes a useful authored ordering, so retain compatibility while
        # new content sets can declare rarity directly.
        value = float(template.get("value", 0) or 0)
        if value >= 600:
            return "legendary"
        if value >= 180:
            return "rare"
        if value >= 60:
            return "uncommon"
        return "common"

    @staticmethod
    def decorate_gem(item: Item, template: dict, level: int = 1, quality_score: Optional[int] = None) -> Item:
        rarity = GemGenerator.template_rarity(template)
        profile = template.get("gem_generation", {})
        profile = profile if isinstance(profile, dict) else {}
        size = GemGenerator._roll_size(rarity, level, float(profile.get("size_bias", 0.0) or 0.0))
        quality = GemGenerator._quality_for_score(quality_score) if quality_score else GemGenerator._roll_quality(rarity, level, float(profile.get("quality_bias", 0.0) or 0.0))
        base_name = str(template.get("name", item.name)).strip() or item.name
        adjectives = [quality["label"]]
        if size["label"]:
            adjectives.append(size["label"])
        item.name = "%s %s" % (" ".join(adjectives), base_name)
        item.value = max(1, int(round(float(template.get("value", item.value)) * size["value_multiplier"] * quality["value_multiplier"])))
        item.weight = max(0.01, float(template.get("weight", item.weight or 0.1)) * size["weight_multiplier"])
        item.stackable = False
        properties = {
            "gem_type_id": item.obj_id,
            "gem_rarity": rarity,
            "gem_size": size["id"],
            "gem_size_label": size["label"] or "standard",
            "gem_size_score": size["score"],
            "gem_quality": quality["id"],
            "gem_quality_label": quality["label"],
            "gem_quality_score": quality["score"],
            # Existing gathering, crafting, and appraisal code already speaks
            # this vocabulary, so gems participate without a compatibility
            # adapter.
            "material_quality": quality["id"],
            "material_quality_label": quality["label"],
            "material_quality_score": quality["score"],
            "stackable": False,
            "value": item.value,
            "weight": item.weight,
        }
        for key, value in properties.items():
            item.update_property(key, value)
        return item

    @staticmethod
    def _roll_size(rarity: str, level: int, bias: float = 0.0) -> dict:
        rank = int(RARITY_TIERS[rarity]["rank"])
        growth = min(3.0, (max(1, level) - 1) / 8.0)
        bias = max(-2.0, min(2.0, bias))
        weights = [
            max(1.0, 36 - rank * 2 - growth * 2 - bias * 5),
            max(1.0, 34 - rank - growth * 2 - bias * 4),
            24 + rank * 3 + growth * 2,
            7 + rank * 3 + growth * 2 + bias * 4,
            max(1.0, 1 + max(0, rank - 2) * 2 + growth + bias * 3),
        ]
        return random.choices(SIZE_TIERS, weights=weights, k=1)[0]

    @staticmethod
    def _roll_quality(rarity: str, level: int, bias: float = 0.0) -> dict:
        rank = int(RARITY_TIERS[rarity]["rank"])
        growth = min(3.0, (max(1, level) - 1) / 10.0)
        bias = max(-2.0, min(2.0, bias))
        weights = [
            max(1.0, 34 - rank * 2 - growth * 3 - bias * 5),
            max(1.0, 31 - rank - growth * 2 - bias * 4),
            25 + rank * 2 + growth * 2,
            8 + rank * 2 + growth * 2 + bias * 4,
            max(1.0, 1 + max(0, rank - 2) + growth + bias * 3),
        ]
        return random.choices(QUALITY_TIERS, weights=weights, k=1)[0]

    @staticmethod
    def _quality_for_score(score: int) -> dict:
        score = max(1, min(5, int(score)))
        return QUALITY_TIERS[score - 1]
