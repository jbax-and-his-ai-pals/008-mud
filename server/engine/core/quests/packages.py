"""The goods a delivery objective hands the player when they accept it.

A delivery quest is a *courier* task: the giver has something that needs to
reach somebody, so taking the job means being handed the thing. That was true
for `deliver` from the start -- accepting one creates the package and says so --
but `deliver_multi` was authored with no way to obtain its goods at all. The
tracking in `give_handler` (`use_give.py`) has always expected the player to be
carrying copies of one item; nothing ever put them there, so the objective type
could not be completed by any real player no matter how it was authored.

The rule here is one rule, applied once per recipient:

* `deliver` hands over one named package (instance-scoped: the tracking matches
  the exact `item_instance_id`, so several deliveries of the same template never
  collide).
* `deliver_multi` hands over one package per recipient entry, each carrying the
  *template* id as its `obj_id`, because that is what the multi-delivery
  tracking matches on. The packages are otherwise identical -- a courier run of
  sealed packets -- so the order they are handed over in does not matter.

Everything is created before anything is given, so a full pack refuses the job
instead of leaving the player holding half a delivery.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from engine.items.item import Item
from engine.items.item_factory import ItemFactory

# Which objective type hands over goods at all. Content decides what the goods
# are; the engine only knows that a delivery means carrying something.
COURIER_OBJECTIVE_TYPES = ("deliver", "deliver_multi")


def declared_packages(world, objective: Dict[str, Any]) -> Tuple[List[Item], str]:
    """Build the items an accepted delivery objective hands the player.

    Returns `(packages, "")` on success, or `([], reason)` when the objective is
    authored incompletely. The reason is player-facing and names the missing
    data rather than the field, because the transport may not be an error at all
    -- an older content set can have quests authored before this existed.
    """
    if not isinstance(objective, dict):
        return [], ""
    objective_type = str(objective.get("type", ""))
    if objective_type not in COURIER_OBJECTIVE_TYPES:
        return [], ""
    if objective.get("crafted_only", False):
        # Nothing is carried on the player's behalf: the point of the stage is
        # that they make the thing themselves.
        return [], ""

    item_template_id = str(objective.get("item_template_id", "")).strip()
    if not item_template_id:
        return [], "This delivery task has incomplete item data."

    if objective_type == "deliver":
        # An instance-scoped package. `item_instance_id` is the identity the
        # turn-in matches, so it is required for a single delivery.
        item_instance_id = str(objective.get("item_instance_id", "")).strip()
        if not item_instance_id:
            return [], "This delivery task has incomplete item data."
        package = _build_package(
            world,
            item_template_id,
            obj_id=item_instance_id,
            name=objective.get("item_to_deliver_name"),
            description=objective.get("item_to_deliver_description"),
        )
        if package is None:
            return [], "This delivery task names no deliverable item."
        return [package], ""

    recipients = [entry for entry in objective.get("recipients", []) if isinstance(entry, dict)]
    if not recipients:
        return [], "This delivery task names nobody to deliver to."

    packages: List[Item] = []
    for recipient in recipients:
        package = _build_package(
            world,
            item_template_id,
            obj_id=item_template_id,
            name=objective.get("item_to_deliver_name"),
            description=objective.get("item_to_deliver_description"),
        )
        if package is None:
            return [], "This delivery task names no deliverable item."
        packages.append(package)
    return packages, ""


def _build_package(world, item_template_id: str, *, obj_id: str, name, description) -> Item | None:
    """One package, with authored wording winning over the template's own.

    `name` and `description` are optional on purpose: a content set that writes
    "Sealed Package" on the template should not have to repeat itself on every
    quest that delivers one, and a set that wants "Nell's packet" can say so.
    """
    overrides = {"obj_id": obj_id}
    authored_name = str(name or "").strip()
    if authored_name:
        overrides["name"] = authored_name
    authored_description = str(description or "").strip()
    if authored_description:
        overrides["description"] = authored_description
    return ItemFactory.create_item_from_template(item_template_id, world, **overrides)
