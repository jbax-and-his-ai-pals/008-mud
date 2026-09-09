# engine/world/housing_manager.py
import copy
from typing import TYPE_CHECKING, List, Optional, Tuple

from engine.items.item_factory import ItemFactory

if TYPE_CHECKING:
    from engine.npcs.npc import NPC
    from engine.player import Player
    from engine.world.region import Region
    from engine.world.world import World


class HousingManager:
    """Player-owned housing.

    Reuses InstanceManager.build_region/apply_entry_exit (the same
    region-creation + door-wiring mechanism quest instances use) but keeps
    all house-specific behavior -- ownership, payment, keys, a lifecycle
    that's never torn down -- separate from InstanceManager itself, so a
    bug here can't touch the well-covered quest-instance code paths.

    This first slice deliberately supports only one house existing in the
    world at a time: an offer's region_id is a single fixed string, so a
    second buyer is turned away, and every buyer of a given offer receives
    a key made from the same item template (ItemFactory sets a created
    item's obj_id to the template id itself, so all such keys are
    interchangeable). Making houses genuinely per-player -- a unique region
    and key per owner -- is real follow-up work, not an oversight.
    """

    def __init__(self, world: 'World'):
        self.world = world

    def get_owned_house(self, player: 'Player') -> Optional['Region']:
        """Return the region this player owns, if any.

        Ownership is tracked on the region itself (region.properties
        ["owner_player_id"]) rather than as a new Player field: Player has
        no generic properties dict the way NPC/Item do, and adding one
        just for a single-house MVP would expand its persistence surface
        for a shape that's expected to change once houses are per-player.
        """
        return next(
            (
                region for region in self.world.regions.values()
                if region.properties.get("owner_player_id") == player.obj_id
            ),
            None,
        )

    def buy_house(self, player: 'Player', agent: 'NPC') -> Tuple[bool, str]:
        if self.get_owned_house(player) is not None:
            return False, "You already own a house."

        offer = agent.properties.get("house_offer")
        if not isinstance(offer, dict):
            return False, f"{agent.name} has nothing to sell you."

        try:
            cost = int(offer.get("cost", 0))
        except (TypeError, ValueError):
            return False, "Unknown house offer configuration: cost must be an integer."

        if player.runtime_state.gold < cost:
            return False, (
                f"You need {cost} {self.world.currency_name()} for a house, "
                f"but only have {player.runtime_state.gold}."
            )

        region_id = str(offer.get("region_id", "")).strip()
        if not region_id:
            return False, "Unknown house offer configuration: missing region_id."
        if region_id in self.world.regions:
            return False, "That house is already spoken for."

        rooms_data = offer.get("rooms")
        entry_point = offer.get("entry_point")
        if not isinstance(rooms_data, dict) or not rooms_data or not isinstance(entry_point, dict):
            return False, "Unknown house offer configuration: missing rooms or entry_point."
        # build_region mutates its rooms_data in place (resolving the
        # "dynamic_exit" sentinel and relative exits into real destination
        # strings). offer.get("rooms") is the same nested dict object
        # living on the agent NPC's (persistent) properties, not a per-call
        # copy, so mutating it directly would corrupt the template the next
        # time it's read.
        rooms_data = copy.deepcopy(rooms_data)

        key_item_id = offer.get("key_item_id")
        exit_requirements = {"type": "locked", "key_id": key_item_id} if key_item_id else None

        region, entry_room_id = self.world.instance_manager.build_region(
            unique_region_id=region_id,
            region_name=offer.get("region_name", "House"),
            region_description=offer.get("region_description", "A modest house."),
            rooms_data=rooms_data,
            entry_point=entry_point,
            exit_requirements=exit_requirements,
        )
        if not self.world.instance_manager.apply_entry_exit(region):
            del self.world.regions[region_id]
            return False, "There's nowhere to put that house right now."

        region.properties["owner_player_id"] = player.obj_id
        region.properties["interior_room_id"] = entry_room_id
        region.properties["house_tier"] = 1

        if key_item_id:
            key_item = ItemFactory.create_item_from_template(key_item_id, self.world)
            if key_item:
                player.inventory.add_item(key_item, 1)

        player.runtime_state.gold -= cost
        return True, (
            f"You pay {cost} {self.world.currency_name()} and receive a key. "
            f"{agent.name} shows you to your new home."
        )

    def _next_tier_options(self, house: 'Region', contractor: 'NPC') -> Tuple[int, List[dict]]:
        """Return (next_tier_number, options_list). options_list is empty if
        the contractor has nothing configured for that tier."""
        current_tier = int(house.properties.get("house_tier", 1))
        next_tier = current_tier + 1
        tiers = contractor.properties.get("house_tiers")
        tier_config = tiers.get(str(next_tier)) if isinstance(tiers, dict) else None
        options = tier_config.get("options", []) if isinstance(tier_config, dict) else []
        return next_tier, [option for option in options if isinstance(option, dict)]

    def describe_house_status(self, player: 'Player', contractor: Optional['NPC']) -> str:
        """Read-only status: current tier/branch, and (if a contractor is
        present) the next tier's options -- the "look before you spend"
        step buy_house didn't need (one option only) but a branching choice
        does."""
        house = self.get_owned_house(player)
        if house is None:
            lines = ["You don't own a house yet."]
        else:
            tier = house.properties.get("house_tier", 1)
            branch = house.properties.get("house_branch")
            branch_note = f", {branch} branch" if branch else ""
            lines = [f"You own a house (tier {tier}{branch_note})."]

        if contractor is None:
            return "\n".join(lines)

        if house is None:
            return "\n".join(lines)

        next_tier, options = self._next_tier_options(house, contractor)
        if not options:
            lines.append(f"{contractor.name} has nothing more to build for you right now.")
            return "\n".join(lines)

        lines.append(f"{contractor.name} can build tier {next_tier}:")
        for option in options:
            materials = option.get("materials", [])
            material_text = ", ".join(
                f"{m.get('quantity', 1)}x {m.get('item_id', '?')}" for m in materials if isinstance(m, dict)
            )
            lines.append(
                f"  {option.get('branch', '?')}: {option.get('label', 'Upgrade')} -- "
                f"{option.get('cost', 0)} {self.world.currency_name()}"
                + (f" + {material_text}" if material_text else "")
            )
        return "\n".join(lines)

    def expand_house(self, player: 'Player', contractor: 'NPC', branch: str) -> Tuple[bool, str]:
        house = self.get_owned_house(player)
        if house is None:
            return False, "You don't own a house to expand."

        next_tier, options = self._next_tier_options(house, contractor)
        if not options:
            return False, f"There's nothing more {contractor.name} can build for you right now."

        branch = branch.strip().lower()
        if branch:
            matches = [option for option in options if str(option.get("branch", "")).lower() == branch]
        else:
            matches = options if len(options) == 1 else []

        if not matches:
            available = ", ".join(str(option.get("branch", "?")) for option in options)
            return False, f"Which upgrade did you have in mind? Options: {available}."

        option = matches[0]

        try:
            cost = int(option.get("cost", 0))
        except (TypeError, ValueError):
            return False, "Unknown house tier configuration: cost must be an integer."
        if player.runtime_state.gold < cost:
            return False, (
                f"You need {cost} {self.world.currency_name()} for that, "
                f"but only have {player.runtime_state.gold}."
            )

        materials = [m for m in option.get("materials", []) if isinstance(m, dict)]
        missing = []
        for material in materials:
            item_id = str(material.get("item_id", ""))
            quantity = int(material.get("quantity", 1))
            if player.inventory.count_item(item_id) < quantity:
                template = ItemFactory.get_template(item_id, self.world)
                name = template.get("name", item_id) if template else item_id
                missing.append(f"{name} ({player.inventory.count_item(item_id)}/{quantity})")
        if missing:
            return False, f"Missing materials: {', '.join(missing)}."

        player.runtime_state.gold -= cost
        for material in materials:
            player.inventory.remove_item(str(material.get("item_id", "")), int(material.get("quantity", 1)))

        room = house.get_room(house.properties.get("interior_room_id"))
        if room is not None:
            room.name = option.get("room_name", room.name)
            room.description = option.get("room_description", room.description)

        house.properties["house_tier"] = next_tier
        branch_id = option.get("branch")
        if branch_id:
            house.properties["house_branch"] = branch_id

        label = option.get("label", f"tier {next_tier}")
        return True, f"{contractor.name} gets to work. Your house is now a {label}!"
