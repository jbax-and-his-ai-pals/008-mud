# engine/core/crime_manager.py
"""Theft witnessing, reputation consequences, and custody resolution.

All vocabulary, values, progression requirements, and emergency-item
choices are authored under a content set's ``crime`` ruleset section.
"""
import time
from typing import TYPE_CHECKING, Optional

from engine.config import FORMAT_ERROR, FORMAT_RESET, FORMAT_SUCCESS
from engine.core.skill_system import SkillSystem
from engine.items.inventory import Inventory
from engine.items.item_factory import ItemFactory
from engine.items.lockpick import Lockpick

if TYPE_CHECKING:
    from engine.npcs.npc import NPC
    from engine.player import Player
    from engine.world.world import World


class CrimeManager:
    def __init__(self, world: 'World'):
        self.world = world

    def _section(self, name: str = "") -> dict:
        value = self.world.ruleset_section("crime")
        if name:
            value = value.get(name, {}) if isinstance(value, dict) else {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _number(value, default=0):
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else default

    def is_enabled(self) -> bool:
        return self._section().get("enabled", False) is True

    def _npc_perception_difficulty(self, npc: 'NPC') -> int:
        witness = self._section("witness")
        rank_key = str(witness.get("rank_attribute", "")).strip()
        rank = self._number(getattr(npc, rank_key, 0), 0) if rank_key else 0
        difficulty = self._number(witness.get("base_difficulty")) + rank * self._number(witness.get("rank_multiplier"))
        authority_key = str(witness.get("authority_property", "")).strip()
        if authority_key and npc.properties.get(authority_key):
            difficulty += self._number(witness.get("authority_bonus"))
        return difficulty

    def attempt_witness(self, player: 'Player') -> Optional['NPC']:
        """Roll a single perception-vs-stealth check against the sharpest
        NPC in the player's current room. Returns the witnessing NPC, or
        None if the theft goes unnoticed. Grants stealth XP either way."""
        if not self.is_enabled():
            return None
        witness_config = self._section("witness")
        excluded = set(witness_config.get("excluded_factions", [])) if isinstance(witness_config.get("excluded_factions", []), list) else set()
        witnesses = [
            npc for npc in self.world.get_npcs_for_player(player)
            if npc.faction not in excluded
        ]
        if not witnesses:
            return None

        sharpest = max(witnesses, key=self._npc_perception_difficulty)
        difficulty = self._npc_perception_difficulty(sharpest)
        skill = str(witness_config.get("skill", "")).strip()
        if not skill:
            return None
        success, _, _ = SkillSystem.attempt_check_with_margin(player, skill, difficulty)

        if success:
            SkillSystem.grant_xp(player, skill, int(self._number(witness_config.get("xp_success"))))
            return None
        SkillSystem.grant_xp(player, skill, int(self._number(witness_config.get("xp_caught"))))
        return sharpest

    def resolve_crime(self, player: 'Player', theft_value: int) -> str:
        """Called once a witness sees a theft. Updates notoriety and the
        running stolen-value total, then decides fine vs. jail."""
        if not self.is_enabled():
            return "This content set does not define ownership consequences."
        consequence = self._section("consequences")
        theft_value = max(0, int(theft_value))
        player.total_theft_value += theft_value

        reputation_key = str(consequence.get("reputation_key", "")).strip()
        notoriety_loss = max(1, round(theft_value * self._number(consequence.get("reputation_per_value"))))
        player.adjust_reputation(reputation_key, -notoriety_loss)
        reputation = player.get_reputation(reputation_key)

        goes_to_jail = (
            theft_value >= self._number(consequence.get("custody_value_threshold"))
            or player.total_theft_value >= self._number(consequence.get("custody_cumulative_threshold"))
            or reputation <= self._number(consequence.get("custody_reputation_threshold"))
        )

        fine = max(int(self._number(consequence.get("fine_minimum"))), round(theft_value * self._number(consequence.get("fine_rate"))))
        if not goes_to_jail:
            if player.runtime_state.gold >= fine:
                player.runtime_state.gold -= fine
                return (
                    f"\n{FORMAT_ERROR}You're caught! You pay a {fine} {self.world.currency_name()} "
                    f"fine to avoid worse.{FORMAT_RESET}"
                )
            goes_to_jail = True  # can't afford the fine -- escalates

        custody = self._section("custody")
        sentence_seconds = self._number(custody.get("base_seconds")) + theft_value * self._number(custody.get("seconds_per_value"))
        return self.send_to_jail(player, sentence_seconds)

    def _find_jail_cell(self):
        """Locate the authored jail cell room by its `is_jail_cell` flag
        rather than a hardcoded region/room id, keeping this engine module
        content-neutral."""
        for region_id, region in self.world.regions.items():
            for room_id, room in region.rooms.items():
                if room.properties.get(str(self._section("custody").get("room_property", ""))):
                    return region_id, room_id
        return None, None

    def has_concealed_pick_bottleneck(self, player: 'Player') -> bool:
        requirements = self._section("custody").get("concealed_tool_requirements", [])
        return isinstance(requirements, list) and bool(requirements) and all(
            isinstance(entry, dict)
            and player.get_skill_level(str(entry.get("skill", ""))) >= int(self._number(entry.get("minimum")))
            for entry in requirements
        )

    def send_to_jail(self, player: 'Player', sentence_seconds: float) -> str:
        flavor = ""
        has_bottleneck = self.has_concealed_pick_bottleneck(player)
        if has_bottleneck and not player.discovered_concealed_pick_trick:
            player.discovered_concealed_pick_trick = True
            flavor = "\nYou've learned to keep a spare pick where a search won't find it."

        confiscated = player.inventory
        player.inventory = Inventory(max_slots=confiscated.max_slots, max_weight=confiscated.max_weight)

        if has_bottleneck:
            exempt_slot = next((slot for slot in confiscated.slots if isinstance(slot.item, Lockpick)), None)
            if exempt_slot and exempt_slot.item:
                pick, _ = exempt_slot.remove(1)
                if pick:
                    player.inventory.add_item(pick)
            else:
                custody = self._section("custody")
                item_id = str(custody.get("emergency_tool_item_id", "")).strip()
                durability = int(self._number(custody.get("emergency_tool_durability")))
                shiv = ItemFactory.create_item_from_template(
                    item_id, self.world,
                    properties_override={"durability": durability, "max_durability": durability},
                )
                if shiv:
                    player.inventory.add_item(shiv)

        player.confiscated_inventory = confiscated
        player.jailed_until = time.time() + sentence_seconds

        region_id, room_id = self._find_jail_cell()
        if region_id and room_id:
            player.current_region_id = region_id
            player.current_room_id = room_id

        return (
            f"\n{FORMAT_ERROR}The guards seize you and haul you off to a cell! "
            f"Your belongings are confiscated.{FORMAT_RESET}{flavor}"
        )

    def release_from_jail(self, player: 'Player') -> str:
        """Sentence served in full -- restore property without silent loss."""
        restored = player.confiscated_inventory
        held_items = [
            (slot.item, slot.quantity)
            for slot in player.inventory.slots
            if slot.item is not None and slot.quantity > 0
        ]
        if restored is not None:
            # The confiscated backpack was valid before the sentence, so make
            # it the authoritative restored state rather than trying to pour
            # it one slot at a time into a potentially occupied jail pack.
            player.inventory = restored
        player.confiscated_inventory = None
        player.jailed_until = None
        release_room = self._move_to_release_destination(player)
        overflow = []
        if restored is not None:
            for item, quantity in held_items:
                added, _ = player.inventory.add_item(item, quantity)
                if not added and release_room is not None:
                    for _ in range(quantity):
                        release_room.add_item(item)
                    overflow.append(item.name)
        message = f"{FORMAT_SUCCESS}Your sentence is served. The guard returns your belongings and lets you out.{FORMAT_RESET}"
        if overflow:
            message += f" The guard sets aside your {', '.join(overflow)} nearby because your pack is full."
        return message

    def _move_to_release_destination(self, player: 'Player'):
        """Move a released prisoner to an authored, valid destination.

        The destination belongs to the jail-cell content, rather than the
        engine assuming a named town, guardhouse, or exit layout.  Keeping a
        fallback to the cell's first real exit preserves compatibility for
        older content while still ensuring release never depends on a locked
        door or a player command.
        """
        room = self.world.get_current_room(player)
        room_property = str(self._section("custody").get("room_property", "")).strip()
        if room is None or not room_property or not room.properties.get(room_property):
            return None

        destination = room.properties.get(str(self._section("custody").get("release_destination_property", "release_destination")))
        if not isinstance(destination, str) or not destination.strip():
            destination = next(iter(room.exits.values()), "")
        if not isinstance(destination, str) or not destination.strip():
            return None

        region_id, room_id = (
            destination.split(":", 1)
            if ":" in destination
            else (player.current_region_id, destination)
        )
        region = self.world.get_region(region_id)
        destination_room = region.get_room(room_id) if region is not None else None
        if destination_room is not None:
            player.current_region_id = region_id
            player.current_room_id = room_id
            return destination_room
        return None

    def forfeit_confiscated_items(self, player: 'Player') -> None:
        """An escape leaves confiscated belongings behind for good."""
        player.confiscated_inventory = None
        player.jailed_until = None
