# engine/world/housing_manager.py
import copy
from typing import TYPE_CHECKING, List, Optional, Tuple

from engine.config import FORMAT_ERROR, FORMAT_RESET
from engine.items.item_factory import ItemFactory

if TYPE_CHECKING:
    from engine.npcs.npc import NPC
    from engine.player import Player
    from engine.world.region import Region
    from engine.world.world import World


# The shared, permanent house-exterior room's entry exit always points at
# this fixed sentinel rather than a literal per-owner destination -- only
# one destination string can ever occupy one exits-dict key at a time, so
# resolving "whose house is this" has to happen dynamically per player
# (World.change_room), not by baking one buyer's destination into shared
# room state. See HousingManager.resolve_personal_door.
HOUSE_ENTRY_SENTINEL = "__owned_house_entry__"


class HousingManager:
    """Player-owned housing.

    Reuses InstanceManager.build_region/apply_entry_exit (the same
    region-creation + door-wiring mechanism quest instances use) but keeps
    all house-specific behavior -- ownership, payment, keys, a lifecycle
    that's never torn down -- separate from InstanceManager itself, so a
    bug here can't touch the well-covered quest-instance code paths.

    Houses are genuinely per-player: each buyer gets a region id derived
    from their own player id and a key scoped to that specific house via
    its target_id property (the same target_id idiom Container.toggle_lock
    already uses for locked containers). The shared exterior's entry exit
    is a single fixed sentinel (HOUSE_ENTRY_SENTINEL) that World.change_room
    resolves to whichever house the acting player actually owns.
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

        base_region_id = str(offer.get("region_id", "")).strip()
        if not base_region_id:
            return False, "Unknown house offer configuration: missing region_id."
        # Per-player, not the offer's bare region_id: two buyers must never
        # collide on one house. Keeps the offer's own "dynamic_" prefix so
        # SaveManager and the finite-adventure world baseline -- both of
        # which already generically collect every dynamic_/instance_
        # region -- pick this up with no changes of their own.
        region_id = f"{base_region_id}_{player.obj_id}"

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
        key_item = None
        if key_item_id:
            # target_id scopes this specific key instance to this specific
            # house's region id -- the same idiom Container.toggle_lock
            # already uses for locked containers -- instead of every key
            # made from this template being interchangeable.
            key_item = ItemFactory.create_item_from_template(
                key_item_id, self.world, properties_override={"target_id": region_id},
            )
            if key_item is None:
                return False, "Unknown house offer configuration: missing key item template."
            can_add, space_message = player.inventory.can_add_item(key_item, 1)
            if not can_add:
                return False, f"You need room for the house key: {space_message}"

        region, entry_room_id = self.world.instance_manager.build_region(
            unique_region_id=region_id,
            region_name=offer.get("region_name", "House"),
            region_description=offer.get("region_description", "A modest house."),
            rooms_data=rooms_data,
            entry_point=entry_point,
            entry_destination_override=HOUSE_ENTRY_SENTINEL,
        )
        if not self.world.instance_manager.apply_entry_exit(region):
            del self.world.regions[region_id]
            return False, "There's nowhere to put that house right now."

        region.properties["owner_player_id"] = player.obj_id
        region.properties["interior_room_id"] = entry_room_id
        region.properties["house_tier"] = 1
        region.properties["key_item_id"] = key_item_id

        # A dependable place to keep things, from the moment the house
        # exists. Unlike the key, a missing/misconfigured storage template
        # doesn't lock the player out of anything -- skip it rather than
        # failing the whole purchase.
        storage_item_id = offer.get("storage_item_id")
        if storage_item_id:
            storage_item = ItemFactory.create_item_from_template(storage_item_id, self.world)
            interior_room = region.get_room(entry_room_id)
            if storage_item is not None and interior_room is not None:
                interior_room.add_item(storage_item)

        if key_item is not None:
            added, add_message = player.inventory.add_item(key_item, 1)
            if not added:
                # The preflight above makes this unreachable without an
                # external mutation. Roll back this player's own house --
                # but never the shared entry sentinel itself: it's the same
                # fixed value for every owner, so tearing it down here
                # could break another player who already owns a house.
                del self.world.regions[region_id]
                return False, f"Unable to issue the house key: {add_message}"

        player.runtime_state.gold -= cost
        return True, (
            f"You pay {cost} {self.world.currency_name()} and receive a key. "
            f"{agent.name} shows you to your new home."
        )

    def resolve_personal_door(self, player: 'Player') -> Tuple[Optional[str], Optional[str]]:
        """Resolve the shared HOUSE_ENTRY_SENTINEL exit to this specific
        player's own house. Returns (destination, None) on success, or
        (None, error_message) if they don't own a house here or aren't
        carrying its key."""
        house = self.get_owned_house(player)
        if house is None:
            return None, f"{FORMAT_ERROR}You don't own a house here.{FORMAT_RESET}"

        key_item_id = house.properties.get("key_item_id")
        if key_item_id:
            has_key = any(
                slot.item is not None and slot.item.get_property("target_id") == house.obj_id
                for slot in player.inventory.slots
            )
            if not has_key:
                return None, f"{FORMAT_ERROR}You don't have your house key with you.{FORMAT_RESET}"

        interior_room_id = house.properties.get("interior_room_id")
        return f"{house.obj_id}:{interior_room_id}", None

    def replace_house_key(self, player: 'Player', agent: 'NPC') -> Tuple[bool, str]:
        """Issue a fresh, correctly-scoped key for a house the player
        already owns -- the recovery path for a lost, dropped, or stolen
        key, since the original is never coming back on its own."""
        house = self.get_owned_house(player)
        if house is None:
            return False, "You don't own a house to make a key for."

        key_item_id = house.properties.get("key_item_id")
        if not key_item_id:
            return False, f"{agent.name} has no key on file for your house."

        offer = agent.properties.get("house_offer")
        offer = offer if isinstance(offer, dict) else {}
        try:
            cost = int(offer.get("replacement_key_cost", 100))
        except (TypeError, ValueError):
            return False, "Unknown house offer configuration: replacement_key_cost must be an integer."

        if player.runtime_state.gold < cost:
            return False, (
                f"You need {cost} {self.world.currency_name()} for a replacement key, "
                f"but only have {player.runtime_state.gold}."
            )

        key_item = ItemFactory.create_item_from_template(
            key_item_id, self.world, properties_override={"target_id": house.obj_id},
        )
        if key_item is None:
            return False, "Unknown house offer configuration: missing key item template."
        can_add, space_message = player.inventory.can_add_item(key_item, 1)
        if not can_add:
            return False, f"You need room for the new key: {space_message}"

        added, add_message = player.inventory.add_item(key_item, 1)
        if not added:
            return False, f"Unable to issue the replacement key: {add_message}"

        player.runtime_state.gold -= cost
        return True, f"{agent.name} cuts you a new key for {cost} {self.world.currency_name()}."

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

        selected_materials = []
        for material in materials:
            selected = player.inventory.select_items(
                str(material.get("item_id", "")), int(material.get("quantity", 1))
            )
            if len(selected) != int(material.get("quantity", 1)):
                return False, "The selected house materials are no longer available."
            selected_materials.extend(selected)
        if not player.inventory.remove_item_instances(selected_materials):
            return False, "The selected house materials are no longer available."

        player.runtime_state.gold -= cost

        room = house.get_room(house.properties.get("interior_room_id"))
        if room is not None:
            room.name = option.get("room_name", room.name)
            room.description = option.get("room_description", room.description)

            room_item_id = option.get("room_item_id")
            if room_item_id:
                room_item = ItemFactory.create_item_from_template(room_item_id, self.world)
                if room_item is not None:
                    room.add_item(room_item)

        house.properties["house_tier"] = next_tier
        branch_id = option.get("branch")
        if branch_id:
            house.properties["house_branch"] = branch_id

        label = option.get("label", f"tier {next_tier}")
        return True, f"{contractor.name} gets to work. Your house is now a {label}!"
