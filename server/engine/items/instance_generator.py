"""Rolled item instances, from any family that declares it rolls them.

One template, many materially distinct objects. A found stone is not the same
object as the next found stone: it rolls its own size and quality, and so its
own name and value, without an authored template for every combination.

Since P9 the tables are a **contract**. Content declares a generation profile
(rarity ranks, size bands, quality bands, and how an instance is named), a
template names its family, and the family names the profile. Nothing here asks
what a thing is called: the engine reads the declaration, so a content set whose
instances are salvage components or alloy ingots rides the same pipeline as one
whose instances are cut stones.

The word "generated" throughout means *rolled at find time*, which is the only
thing the engine knows about it. What it is, what it is worth, and what it is
named are all content decisions.

Two vocabularies, deliberately:

* `instance_*` is what the resolver writes, and it is neutral. `instance_source`
  is the template the instance came from; `instance_rarity`, `instance_size` and
  `instance_quality` are the rolled bands.
* `material_quality*` is the cross-system compatibility trio. Crafting, quest
  objectives, appraisal, vendor orders and inventory sorting already speak it, so
  an instance participates in all of them without an adapter. It is a resolved
  *number*, not a genre word.

A content set that speaks a third vocabulary declares `property_prefix` on its
profile and gets that family of keys alongside the neutral ones. That is how
pre-P9 content keeps reading `gem_size` while the resolver itself never says
"gem".
"""
import random
import re
from typing import Any, Dict, Optional, Sequence

from engine.contracts.registry import (
    generation_profile_for_template,
    registry_for,
)
from engine.items.item import Item
from engine.items.item_factory import ItemFactory

# Neutral fallback tables, for a content set that declares a profile without
# bands of its own. Ranks and bands only -- no genre vocabulary anywhere.
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

# How an instance is named when its profile does not say. The tokens are the
# rolled bands and the template's own name; the bands a content set does not use
# render empty and are cleaned up, so "standard" size never leaves a double
# space behind.
DEFAULT_NAME_TEMPLATE = "{quality} {size} {base}"

_TOKENS = ("base", "quality", "size", "rarity", "profile")

# The rolled bands an instance records. A profile that declares a
# `property_prefix` gets one prefixed key per band.
BAND_SUFFIXES = (
    "rarity",
    "size",
    "size_label",
    "size_score",
    "quality",
    "quality_label",
    "quality_score",
)

_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,.;:)\]])")
_EMPTY_GROUP = re.compile(r"[(\[]\s*[)\]]")
_WHITESPACE = re.compile(r"\s+")


def _registry(world: Any):
    return registry_for(world)


def _profile_id_of(world: Any, template: dict) -> str:
    """A template's generation profile: its own, else its family's."""
    return generation_profile_for_template(world, template)


def _profile_of(world: Any, template: dict) -> Dict[str, Any]:
    registry = _registry(world)
    profile_id = _profile_id_of(world, template)
    if registry is None or not profile_id:
        return {}
    return dict(registry.generation_profile(profile_id) or {})


def _tiers(world: Any, template: dict, tier_kind: str, fallback: Sequence[Dict[str, Any]]):
    registry = _registry(world)
    profile_id = _profile_id_of(world, template)
    if registry is not None and profile_id:
        tiers = registry.tiers(profile_id, tier_kind)
        if tiers:
            return tiers
    return fallback


def _rarity_table(world: Any, template: dict) -> Dict[str, Dict[str, Any]]:
    tiers = _tiers(world, template, "rarity_tiers", ())
    if not tiers:
        return RARITY_TIERS
    table: Dict[str, Dict[str, Any]] = {}
    for entry in tiers:
        identifier = str(entry.get("id", "") or "")
        if identifier:
            table[identifier] = entry
    return table or RARITY_TIERS


def _weights_for(tiers: list, canonical: list) -> list:
    """One weight per declared tier, from the five-band curve this shipped with.

    The curve is tuned for five bands, and the shipped profiles declare five, so
    that case returns it unchanged — moving the tables into content did not
    change a single roll. Content may declare any number of bands, though, and a
    profile with two of them used to crash `random.choices` (five weights, two
    tiers); the curve is sampled at evenly spaced positions instead, so two
    bands become "the ordinary band and the rare band" rather than an error.
    """
    count = len(tiers)
    if count == len(canonical):
        return canonical
    if count == 1:
        return [max(1.0, sum(canonical) / len(canonical))]
    last = len(canonical) - 1
    weights = []
    for index in range(count):
        position = index * last / (count - 1)
        low = int(position)
        high = min(last, low + 1)
        fraction = position - low
        weights.append(max(1.0, canonical[low] * (1.0 - fraction) + canonical[high] * fraction))
    return weights


def _tidy(text: str) -> str:
    """Collapse the gaps an unused band leaves in an assembled name."""
    text = _WHITESPACE.sub(" ", str(text)).strip()
    text = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", text)
    text = _EMPTY_GROUP.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


def _rarity_entry(table: Dict[str, Dict[str, Any]], rarity: str) -> Dict[str, Any]:
    """One rarity's entry, or the commonest declared band.

    Content may name its rarity bands anything -- a sci-fi set's grades are not
    `common` and `rare` -- and a template that authors no rarity at all is
    inferred into the historic band names, which then may not exist in the
    table. Falling back to the *lowest-ranked* declared band is the only reading
    that says what it means: an ungraded specimen is an ordinary one. The
    alternative was a weight of zero, which made every candidate weightless and
    crashed the roll.
    """
    entry = table.get(rarity)
    if entry is not None:
        return entry
    if not table:
        return {"weight": 0, "rank": 1}
    return min(table.values(), key=lambda tier: (int(tier.get("rank", 1)), str(tier.get("id", ""))))


class InstanceGenerator:
    """Rolls instances of any template whose contract says it rolls them."""

    @staticmethod
    def is_generated_template(world: Any, template_id: str) -> bool:
        """Whether instances of this template are rolled rather than authored.

        Asked of the *contract*: a family that declares the `generated_instance`
        capability and rides a generation profile has instances, whatever it is
        called. A sci-fi set's `salvage_component` therefore gets the same
        treatment as a fantasy set's cut stone, with no engine change -- which is
        the whole point of the registry.
        """
        template = getattr(world, "item_templates", {}).get(template_id, {})
        if not isinstance(template, dict):
            return False
        registry = _registry(world)
        if registry is None:
            return False
        family_id = str(template.get("item_family", "") or "")
        if not family_id:
            return False
        return (
            registry.family_has_capability(family_id, "generated_instance")
            and bool(_profile_id_of(world, template))
        )

    @staticmethod
    def generate(
        world: Any,
        level: int = 1,
        template_id: Optional[str] = None,
        quality_score: Optional[int] = None,
    ) -> Optional[Item]:
        """Create one distinct instance.

        ``quality_score`` lets a gathering node retain its authored regional
        material grade while still using the same size/value/name machinery.
        """
        level = max(1, int(level))
        if template_id is None:
            template_id = InstanceGenerator.pick_template_id(world, level)
        if not template_id or not InstanceGenerator.is_generated_template(world, template_id):
            return None
        item = ItemFactory.create_item_from_template(template_id, world)
        if item is None:
            return None
        template = world.item_templates[template_id]
        InstanceGenerator.decorate(world, item, template, level, quality_score)
        return item

    @staticmethod
    def pick_template_id(world: Any, level: int = 1) -> Optional[str]:
        candidates: list[tuple[str, dict]] = [
            (item_id, template)
            for item_id, template in getattr(world, "item_templates", {}).items()
            if isinstance(template, dict)
            and InstanceGenerator.is_generated_template(world, item_id)
            and not template.get("properties", {}).get("debug_only")
        ]
        if not candidates:
            return None
        weights = []
        for _, template in candidates:
            rarity = InstanceGenerator.template_rarity(template, world)
            tier = _rarity_entry(_rarity_table(world, template), rarity)
            # Higher-level sources increasingly have a chance to surface a
            # rarer species without removing the ordinary ones from play.
            weights.append(float(tier.get("weight", 0)) + (level - 1) * float(tier.get("rank", 1)) * 0.65)
        if sum(weights) <= 0:
            # No band declares a weight: every candidate is equally likely
            # rather than impossible.
            weights = [1.0] * len(candidates)
        return random.choices([item_id for item_id, _ in candidates], weights=weights, k=1)[0]

    @staticmethod
    def template_rarity(template: dict, world: Any = None) -> str:
        authored = str(template.get("rarity", "")).strip().lower()
        if authored in _rarity_table(world, template):
            return authored
        # Templates may predate explicit rarity. Their value already encodes a
        # useful authored ordering, so retain compatibility while new content
        # sets declare rarity directly.
        value = float(template.get("value", 0) or 0)
        for tier_id, threshold in (("legendary", 600), ("rare", 180), ("uncommon", 60)):
            if value >= threshold:
                return tier_id if tier_id in _rarity_table(world, template) else "common"
        return "common"

    @staticmethod
    def decorate(
        world: Any,
        item: Item,
        template: dict,
        level: int = 1,
        quality_score: Optional[int] = None,
    ) -> Item:
        """Roll this instance's bands and write its resolved identity onto it."""
        rarity = InstanceGenerator.template_rarity(template, world)
        profile = _profile_of(world, template)
        size_tiers = _tiers(world, template, "size_tiers", SIZE_TIERS)
        quality_tiers = _tiers(world, template, "quality_tiers", QUALITY_TIERS)
        ranking = _rarity_entry(_rarity_table(world, template), rarity)
        # Record the band the table actually resolved to, not the name the
        # lookup started from: a set whose bands are its own vocabulary must not
        # have instances carrying a band id that appears nowhere in its content.
        rarity = str(ranking.get("id", "") or rarity)
        size = InstanceGenerator._roll_size(
            int(ranking.get("rank", 1)), level, float(profile.get("size_bias", 0.0) or 0.0), size_tiers
        )
        quality = (
            InstanceGenerator._quality_for_score(quality_score, quality_tiers)
            if quality_score
            else InstanceGenerator._roll_quality(
                int(ranking.get("rank", 1)), level, float(profile.get("quality_bias", 0.0) or 0.0), quality_tiers
            )
        )
        base_name = str(template.get("name", item.name)).strip() or item.name
        item.name = InstanceGenerator.instance_name(
            world, template, base_name, quality, size, rarity
        )
        item.value = max(1, int(round(float(template.get("value", item.value)) * size["value_multiplier"] * quality["value_multiplier"])))
        item.weight = max(0.01, float(template.get("weight", item.weight or 0.1)) * size["weight_multiplier"])
        item.stackable = False

        properties = InstanceGenerator.instance_properties(world, item, template, rarity, size, quality)
        for key, value in properties.items():
            item.update_property(key, value)
        # A content set that names its own property family (pre-P9 content reads
        # `gem_size`) declares the prefix; the resolver writes it without knowing
        # what it means.
        prefix = str(profile.get("property_prefix", "") or "").strip()
        if prefix:
            for suffix in BAND_SUFFIXES:
                key = "instance_%s" % suffix
                if key in properties:
                    item.update_property("%s_%s" % (prefix, suffix), properties[key])
            item.update_property("%s_type_id" % prefix, item.obj_id)
        return item

    @staticmethod
    def instance_properties(
        world: Any,
        item: Item,
        template: dict,
        rarity: str,
        size: dict,
        quality: dict,
    ) -> Dict[str, Any]:
        """The resolved identity of one instance, in neutral terms."""
        return {
            "instance_source": item.obj_id,
            "instance_profile": _profile_id_of(world, template),
            "instance_rarity": rarity,
            "instance_size": size["id"],
            "instance_size_label": size["label"] or "standard",
            "instance_size_score": size["score"],
            "instance_quality": quality["id"],
            "instance_quality_label": quality["label"],
            "instance_quality_score": quality["score"],
            # Existing gathering, crafting, appraisal, vendor-order and quest
            # code already speaks this vocabulary, so instances participate in
            # all of it without a compatibility adapter.
            "material_quality": quality["id"],
            "material_quality_label": quality["label"],
            "material_quality_score": quality["score"],
            "stackable": False,
            "value": item.value,
            "weight": item.weight,
        }

    @staticmethod
    def name_template(world: Any, template: dict) -> str:
        authored = str(_profile_of(world, template).get("name_template", "") or "").strip()
        if not authored:
            return DEFAULT_NAME_TEMPLATE
        # An unauthorable template is a content mistake; the validator reports
        # the unknown field, and the roll still produces a sensible name.
        try:
            authored.format(**{token: "" for token in _TOKENS})
        except (KeyError, IndexError, ValueError):
            return DEFAULT_NAME_TEMPLATE
        return authored

    @staticmethod
    def instance_name(
        world: Any,
        template: dict,
        base_name: str,
        quality: dict,
        size: dict,
        rarity: str = "",
    ) -> str:
        """Assemble a name from the profile's template and the rolled bands."""
        pattern = InstanceGenerator.name_template(world, template)
        try:
            assembled = pattern.format(
                base=base_name,
                quality=quality.get("label", ""),
                size=size.get("label", ""),
                rarity=rarity,
                profile=_profile_id_of(world, template),
            )
        except (KeyError, IndexError, ValueError):
            assembled = DEFAULT_NAME_TEMPLATE.format(
                base=base_name, quality=quality.get("label", ""), size=size.get("label", ""), rarity=rarity
            )
        return _tidy(assembled) or base_name

    @staticmethod
    def _roll_size(rank: int, level: int, bias: float = 0.0, tiers=SIZE_TIERS) -> dict:
        """Roll a size band. Rarer sources and higher levels push toward larger.

        The weights are exactly the ones this generator shipped with; only the
        tier list and the rank's source became parameters, so moving the tables
        behind a contract did not change how a single instance rolls.
        """
        rank = max(1, int(rank))
        growth = min(3.0, (max(1, level) - 1) / 8.0)
        bias = max(-2.0, min(2.0, bias))
        canonical = [
            max(1.0, 36 - rank * 2 - growth * 2 - bias * 5),
            max(1.0, 34 - rank - growth * 2 - bias * 4),
            24 + rank * 3 + growth * 2,
            7 + rank * 3 + growth * 2 + bias * 4,
            max(1.0, 1 + max(0, rank - 2) * 2 + growth + bias * 3),
        ]
        return random.choices(list(tiers), weights=_weights_for(list(tiers), canonical), k=1)[0]

    @staticmethod
    def _roll_quality(rank: int, level: int, bias: float = 0.0, tiers=QUALITY_TIERS) -> dict:
        rank = max(1, int(rank))
        growth = min(3.0, (max(1, level) - 1) / 10.0)
        bias = max(-2.0, min(2.0, bias))
        canonical = [
            max(1.0, 34 - rank * 2 - growth * 3 - bias * 5),
            max(1.0, 31 - rank - growth * 2 - bias * 4),
            25 + rank * 2 + growth * 2,
            8 + rank * 2 + growth * 2 + bias * 4,
            max(1.0, 1 + max(0, rank - 2) + growth + bias * 3),
        ]
        return random.choices(list(tiers), weights=_weights_for(list(tiers), canonical), k=1)[0]

    @staticmethod
    def _quality_for_score(score: int, tiers=QUALITY_TIERS) -> dict:
        entries = list(tiers)
        score = max(1, min(len(entries), int(score)))
        return entries[score - 1]
