# engine/crafting/recipe.py
from typing import List, Dict, Any

from engine.items import references
from engine.utils import content_values as cv


def _optional_difficulty(data: Dict[str, Any], path: str) -> Any:
    """The authored skill-check difficulty, or None to derive it from value.

    A whole float is read as that integer; a fractional one is refused rather
    than truncated, because the difficulty check is a threshold and 7.5 is not 7.
    """
    value = cv.present(data, "difficulty")
    if cv.absent(value) or value is None:
        return None
    return cv.as_int(value, "%s.difficulty" % path, minimum=0)


def _milestones(data: Dict[str, Any], path: str) -> List[Dict[str, Any]]:
    """Authored familiarity milestones, each with a readable craft count.

    Read strictly rather than filtered: the old reader kept a milestone only when
    `isinstance(count, int)`, so a float count removed it from the list and the
    player was told about a *later* milestone at the wrong time.
    """
    raw = cv.optional_sequence(data, "familiarity_milestones", path)
    if cv.absent(raw):
        return []
    entries = cv.list_of_objects(raw, "%s.familiarity_milestones" % path)
    milestones: List[Dict[str, Any]] = []
    for index, entry in enumerate(entries):
        where = "%s.familiarity_milestones[%d]" % (path, index)
        milestone = dict(entry)
        milestone["count"] = cv.optional_int(entry, "count", where, minimum=1)
        if milestone["count"] is None:
            raise cv.ContentValueError("%s.count" % where, "an integer of at least 1", None)
        for key in ("label", "message"):
            if not cv.absent(cv.present(entry, key)):
                milestone[key] = cv.as_text(cv.present(entry, key), "%s.%s" % (where, key))
        milestones.append(milestone)
    return milestones


def _quality_tiers(data: Dict[str, Any], path: str) -> List[Dict[str, Any]]:
    """Authored quality tiers, gated on crafts and optionally on material grade.

    The same strict read, and the case that started this: a tier whose
    `min_crafts` was a float used to be dropped in silence, and the craft it
    belonged to then reported no quality at all while every gate passed.
    """
    raw = cv.optional_sequence(data, "quality_tiers", path)
    if cv.absent(raw):
        return []
    entries = cv.list_of_objects(raw, "%s.quality_tiers" % path)
    tiers: List[Dict[str, Any]] = []
    for index, entry in enumerate(entries):
        where = "%s.quality_tiers[%d]" % (path, index)
        tier = dict(entry)
        tier["min_crafts"] = cv.optional_int(entry, "min_crafts", where, minimum=1)
        if tier["min_crafts"] is None:
            raise cv.ContentValueError("%s.min_crafts" % where, "an integer of at least 1", None)
        for key, minimum in (("min_material_quality", 0), ("rank", 1)):
            if not cv.absent(cv.present(entry, key)) and cv.present(entry, key) is not None:
                tier[key] = cv.as_int(cv.present(entry, key), "%s.%s" % (where, key), minimum=minimum)
        tiers.append(tier)
    return tiers


class Recipe:
    """One recipe, read strictly.

    Every field the engine reads is read through `engine/utils/content_values.py`,
    which refuses a value that is not what the field means and says which field
    in the file it was. That is not fussiness: this class is the *only* reader of
    a recipe, and the content-set validator does not check most of these fields,
    so a lenient read here had no second line of defence. A float `min_crafts`
    kept the tier list empty; `requires_discovery: "false"` made a recipe
    permanently unlearnable; `result_quantity: "2"` made `craft` produce `"22"`.
    None of those raised, and none of them was reported.
    """

    def __init__(self, recipe_id: str, data: Dict[str, Any]):
        self.recipe_id = recipe_id
        self._path = "recipes.%s" % recipe_id

        if not isinstance(data, dict):
            raise cv.ContentValueError(self._path, "an object", data)

        self.name = cv.optional_text(data, "name", self._path, default="Unknown Recipe")
        self.description = cv.optional_text(data, "description", self._path, default="Creates an item.")

        # The template ID of the item created
        self.result_item_id = cv.optional_text(data, "result_item_id", self._path)
        self.result_quantity = cv.optional_int(data, "result_quantity", self._path, default=1, minimum=1)

        # "anvil", "alchemy_table", "campfire", or None (handcrafting)
        self.station_required = cv.optional_text(data, "station_required", self._path)
        # A recipe every player can attempt from the start unless content
        # opts it into being taught/found first (see Player.learn_recipe).
        self.requires_discovery: bool = cv.optional_bool(data, "requires_discovery", self._path, default=False)
        # ``None`` preserves the content-neutral default difficulty derived
        # from result value. A content set may use 0 for a guaranteed beginner
        # recipe or supply an explicit positive skill-check difficulty.
        self.difficulty = _optional_difficulty(data, self._path)

        # List of dicts: {"item_id":Str, "quantity":Int}
        self.ingredients: List[Dict[str, Any]] = list(
            cv.optional_sequence(data, "ingredients", self._path)
        )
        # An ingredient is a reference, not an id -- see `Recipe.references_item`.
        for index, ingredient in enumerate(self.ingredients):
            if not isinstance(ingredient, dict):
                raise cv.ContentValueError(
                    "%s.ingredients[%d]" % (self._path, index), "an object", ingredient,
                )
        # Alternative names a player might type for this recipe, resolved by
        # engine/naming.py. The recipe's own `name` is authored as an
        # instruction ("Tie Wildflower Posy"); an alias is what someone would
        # actually ask for ("posy", "flowers").
        raw_aliases = cv.optional_sequence(data, "aliases", self._path)
        self.aliases: List[str] = []
        for index, alias in enumerate(raw_aliases):
            where = "%s.aliases[%d]" % (self._path, index)
            if isinstance(alias, bool) or not isinstance(alias, (str, int)):
                raise cv.ContentValueError(where, "a string", alias)
            text = str(alias).strip()
            if not text:
                raise cv.ContentValueError(where, "a non-empty string", alias)
            self.aliases.append(text)
        # Optional content metadata. The engine records familiarity for every
        # recipe, but only authored milestones turn it into player feedback.
        self.familiarity_milestones: List[Dict[str, Any]] = _milestones(data, self._path)
        self.quality_tiers: List[Dict[str, Any]] = _quality_tiers(data, self._path)
        
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
