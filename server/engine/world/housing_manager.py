# engine/world/housing_manager.py
import copy
from typing import TYPE_CHECKING, Optional, Tuple

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

        region, _entry_room_id = self.world.instance_manager.build_region(
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

        if key_item_id:
            key_item = ItemFactory.create_item_from_template(key_item_id, self.world)
            if key_item:
                player.inventory.add_item(key_item, 1)

        player.runtime_state.gold -= cost
        return True, (
            f"You pay {cost} {self.world.currency_name()} and receive a key. "
            f"{agent.name} shows you to your new home."
        )
