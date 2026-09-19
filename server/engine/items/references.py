# engine/items/references.py
"""What a piece of content means when it names an item.

An author rarely wants to name one template. A recipe wants "any salvaged part
good enough to use", a vendor's buy order wants "two clay of at least fine
grade", a salvage rule wants "the scrap this came from". Written as item ids,
each of those is a list that has to be kept in step with the item files by hand;
written as a *reference*, it is a question about a set of items.

Three kinds, resolved in this order:

    {"item_id": "item_iron_ingot"}                      one exact template
    {"item_family": "salvaged_part", "min_material_quality": 2}
    {"capability": "crafting_material"}

``item_id`` wins when more than one is present, so content written before
families existed resolves exactly as it did -- the migration is one reference at
a time rather than a flag day. ``min_material_quality`` is the floor a member of
a family or a capability has to reach: the rule says *what kind of thing*, the
floor says *how good*. It applies only to the rule kinds, because a template
reference has already answered the question the floor asks.

One matcher, one description, one enumeration, in one file, because a recipe
that *looks* satisfiable and then fails is worse than one that says what it is
missing -- and two implementations of "does this count?" is how that happens.
"""

from typing import Any, Callable, Dict, List, Optional, Sequence

# The keys that can carry a reference, in resolution order.
REFERENCE_KEYS = ("item_id", "item_family", "capability")

# Older content spelled the material-grade floor `min_material_quality_score`
# (vendor orders used it first). Both are read; content should author the
# shorter one.
QUALITY_FLOOR_KEYS = ("min_material_quality", "min_material_quality_score")

# Sentinel for "this content names no item at all".
NOTHING: Dict[str, Any] = {}


def reference_kind(reference: Any) -> str:
    """Which of the three keys this reference uses, or "" for none of them."""
    if not isinstance(reference, dict):
        return ""
    for key in REFERENCE_KEYS:
        if str(reference.get(key, "") or "").strip():
            return key
    return ""


def names_something(reference: Any) -> bool:
    """Whether this reference names anything at all.

    An object with no reference key is a content mistake, not a wildcard: it
    would silently match nothing, so callers check this and say so.
    """
    return reference_kind(reference) != ""


def minimum_quality(reference: Any) -> int:
    """The material grade floor this reference asks for, 0 when it asks for none."""
    if not isinstance(reference, dict):
        return 0
    for key in QUALITY_FLOOR_KEYS:
        if key not in reference:
            continue
        raw = reference[key]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return 0
        return max(0, int(raw))
    return 0


def reference_value(reference: Any) -> str:
    """What the reference names: the id, the family, or the capability."""
    kind = reference_kind(reference)
    return str(reference.get(kind, "") or "").strip() if kind else ""


def matches(
    reference: Any,
    item: Any,
    *,
    quality_of: Callable[[Any], int],
    item_family: Callable[[Any], str],
    family_has_capability: Callable[[str, str], bool],
    identity_of: Callable[[Any], str],
) -> bool:
    """Whether one held or offered item satisfies one reference.

    Every question about the world is passed in rather than reached for, so the
    same rule serves a crafting manager that has a `World`, a vendor command
    that has a player, and a test that has neither.
    """
    if not isinstance(reference, dict):
        return False
    item_id = str(reference.get("item_id", "") or "").strip()
    if item_id:
        return str(identity_of(item)) == item_id

    floor = minimum_quality(reference)
    if floor and quality_of(item) < floor:
        return False

    family = str(reference.get("item_family", "") or "").strip()
    if family:
        return str(item_family(item)) == family

    capability = str(reference.get("capability", "") or "").strip()
    if capability:
        declared_in = str(item_family(item))
        return bool(declared_in) and bool(family_has_capability(declared_in, capability))
    return False


def describe(
    reference: Any,
    name_of_template: Optional[Callable[[str], str]] = None,
    family_label: Optional[Callable[[str], str]] = None,
    *,
    include_floor: bool = True,
) -> str:
    """A player-readable name for what a reference wants.

    Genre-neutral on purpose: an item id becomes its template's authored name, a
    family becomes the label the content set gave it, and a capability becomes
    its own words. A floor, when there is one, is stated -- "any salvaged part
    (grade 2+) is a different request from "any salvaged part" -- unless the
    caller is already saying it somewhere else, which is why `include_floor`
    exists rather than every caller composing the phrase itself.
    """
    kind = reference_kind(reference)
    if kind == "item_id":
        item_id = reference_value(reference)
        if name_of_template is not None:
            return str(name_of_template(item_id) or item_id)
        return item_id

    label = reference_value(reference)
    if kind == "item_family" and family_label is not None:
        label = str(family_label(label) or label)
    elif kind == "capability":
        label = label.replace("_", " ")
    elif kind != "item_family":
        return "something"

    return _with_floor(label, reference) if include_floor else label


def options(reference: Any) -> List[Dict[str, Any]]:
    """The acceptable references for one content slot: the authored primary
    first, then any declared substitutes.

    Each option carries a ``quality_penalty`` (0 for the primary unless
    overridden, 0 for a substitute that does not author one) applied to the
    slot's material-grade contribution when that option is the one actually
    spent -- the trade-off in a substitution.
    """
    if not isinstance(reference, dict):
        return []
    primary = dict(reference, quality_penalty=_penalty(reference))
    options_out = [primary]
    alternatives = reference.get("alternatives", [])
    if isinstance(alternatives, list):
        for alternative in alternatives:
            if isinstance(alternative, dict) and names_something(alternative):
                options_out.append(dict(alternative, quality_penalty=_penalty(alternative)))
    return options_out


def penalty_of(option: Any) -> int:
    """The authored quality penalty on one resolved option."""
    return _penalty(option)


def _penalty(reference: Any) -> int:
    if not isinstance(reference, dict):
        return 0
    raw = reference.get("quality_penalty", 0)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return 0
    return max(0, int(raw))


def _with_floor(label: str, reference: Any) -> str:
    floor = minimum_quality(reference)
    return "%s (grade %d+)" % (label, floor) if floor else label


def match_plan(
    reference: Any,
    inventory: Any,
    quantity: int,
    *,
    quality_of: Callable[[Any], int],
    qualifies: Optional[Callable[[Any], bool]] = None,
    minimum_grade: int = 0,
    **questions: Any,
) -> Optional[Dict[str, Any]]:
    """The units that would satisfy this reference, and what they cost.

    A recipe ingredient and a vendor's buy order are the same question asked of
    two different inventories, so they are answered by the same code. Tries the
    authored primary first -- which preserves how every pre-reference piece of
    content behaved -- and only falls through to a substitute when the primary
    is short, because the primary is what the author actually asked for.

    Two optional conditions ride alongside the reference:

    * `qualifies` is the caller's own requirement on the item (a vendor order
      that only takes work the player made themselves);
    * `minimum_grade` is the caller treating a floor as a floor. A recipe does
      not need this -- its floor lives inside the family or capability rule it
      was written beside -- but a vendor's buy order writes the floor at the top
      level, including next to an exact template, and a floor that only applied
      to some of the ways an order can be written would be a trap.

    Returns ``{"reference", "items", "quality", "penalty"}`` or ``None`` when
    nothing acceptable is held. ``items`` is the exact list a caller may spend;
    ``quality`` is the limiting material grade *after* the matched option's
    penalty, which is what makes a substitution a trade-off rather than a free
    swap.
    """
    quantity = max(1, int(quantity))
    floor = max(0, int(minimum_grade))

    def eligible(item: Any, option: Dict[str, Any]) -> bool:
        if floor and quality_of(item) < floor:
            return False
        if not matches(option, item, quality_of=quality_of, **questions):
            return False
        return qualifies is None or qualifies(item)

    for option in options(reference):
        held = inventory.select_items_matching(
            quantity,
            predicate=lambda item, _option=option: eligible(item, _option),
            sort_key=quality_of,
        )
        if len(held) != quantity:
            continue
        grades = [max(0, int(quality_of(item)) - penalty_of(option)) for item in held]
        return {
            "reference": option,
            "items": held,
            "quality": min(grades) if grades else 0,
            "penalty": penalty_of(option),
        }
    return None


def count_matching(
    reference: Any,
    inventory: Any,
    quantity: int,
    *,
    quality_of: Callable[[Any], int],
    **questions: Any,
) -> int:
    """How many units of the best acceptable reference the holder is carrying.

    The count is for the *best* acceptable reference, so content that either of
    two things can satisfy reports whichever the holder has more of rather than
    a per-reference number that reads as a shortfall.
    """
    quantity = max(1, int(quantity))
    best = 0
    for option in options(reference):
        available = inventory.count_items_matching(
            predicate=lambda item, _option=option: matches(_option, item, quality_of=quality_of, **questions)
        )
        if available >= quantity:
            return available
        best = max(best, available)
    return best


def matching_option(
    reference: Any,
    item: Any,
    **questions: Any,
) -> Optional[Dict[str, Any]]:
    """Which of a slot's options this item satisfies, or None.

    Returns the option (with its penalty), so a spent unit is scored against the
    reference it actually matched rather than against a guessed id.
    """
    for option in options(reference):
        if matches(option, item, **questions):
            return option
    return None


def resolve_template_id(
    reference: Any,
    family_of_template: Callable[[str], str],
    family_has_capability: Callable[[str, str], bool],
    template_ids: Sequence[str],
) -> Optional[str]:
    """A concrete template that would satisfy this reference, if one exists.

    Only for tooling that has to *hand someone the thing* rather than check for
    it (debug commands, content tooling, the editor's previews). Player-facing
    code never guesses: it counts what the player is actually holding.
    """
    for option in options(reference):
        item_id = str(option.get("item_id", "") or "").strip()
        if item_id:
            return item_id
        family = str(option.get("item_family", "") or "").strip()
        capability = str(option.get("capability", "") or "").strip()
        if not (family or capability):
            continue
        for candidate_id in sorted(template_ids):
            candidate_family = family_of_template(candidate_id)
            if family and candidate_family != family:
                continue
            if capability and not family_has_capability(candidate_family, capability):
                continue
            return str(candidate_id)
    return None
