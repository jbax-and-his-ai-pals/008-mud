# engine/core/crime_manager.py
"""Theft witnessing, notoriety, and jail resolution.

Content-neutral: notoriety lives in the player's existing free-form
`reputation` dict under a "town_guard" key, isolated from the real NPC
combat-faction list (FACTIONS in engine/config/config_world.py) so it
never touches aggro decisions. An NPC witness doesn't get a tracked
skill -- it gets a derived "perception" difficulty (level + a flat base +
a guard bonus) fed into the same SkillSystem.attempt_check_with_margin
call used for every other skill check in the engine.
"""
import time
from typing import TYPE_CHECKING, Optional

from engine.config import (
    CONCEALED_PICK_LOCKPICKING_FLOOR, CONCEALED_PICK_STEALTH_FLOOR,
    CRIME_FINE_MINIMUM, CRIME_FINE_RATE, CRIME_JAIL_CUMULATIVE_THRESHOLD,
    CRIME_JAIL_REPUTATION_THRESHOLD, CRIME_JAIL_VALUE_THRESHOLD,
    CRIME_NOTORIETY_PER_THEFT_VALUE, EMERGENCY_LOCKPICK_DURABILITY,
    FORMAT_ERROR, FORMAT_RESET, FORMAT_SUCCESS,
    GUARD_PERCEPTION_BONUS, JAIL_BASE_SENTENCE_SECONDS,
    JAIL_SENTENCE_PER_THEFT_VALUE, NPC_BASE_PERCEPTION, NPC_PERCEPTION_PER_LEVEL,
    THEFT_STEALTH_XP_CAUGHT, THEFT_STEALTH_XP_SUCCESS,
)
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

    def _npc_perception_difficulty(self, npc: 'NPC') -> int:
        difficulty = NPC_BASE_PERCEPTION + npc.level * NPC_PERCEPTION_PER_LEVEL
        if npc.properties.get("is_guard"):
            difficulty += GUARD_PERCEPTION_BONUS
        return difficulty

    def attempt_witness(self, player: 'Player') -> Optional['NPC']:
        """Roll a single perception-vs-stealth check against the sharpest
        NPC in the player's current room. Returns the witnessing NPC, or
        None if the theft goes unnoticed. Grants stealth XP either way."""
        witnesses = [
            npc for npc in self.world.get_npcs_for_player(player)
            if npc.faction not in ("hostile", "player_minion")
        ]
        if not witnesses:
            return None

        sharpest = max(witnesses, key=self._npc_perception_difficulty)
        difficulty = self._npc_perception_difficulty(sharpest)
        success, _, _ = SkillSystem.attempt_check_with_margin(player, "stealth", difficulty)

        if success:
            SkillSystem.grant_xp(player, "stealth", THEFT_STEALTH_XP_SUCCESS)
            return None
        SkillSystem.grant_xp(player, "stealth", THEFT_STEALTH_XP_CAUGHT)
        return sharpest

    def resolve_crime(self, player: 'Player', theft_value: int) -> str:
        """Called once a witness sees a theft. Updates notoriety and the
        running stolen-value total, then decides fine vs. jail."""
        theft_value = max(0, int(theft_value))
        player.total_theft_value += theft_value

        notoriety_loss = max(1, round(theft_value * CRIME_NOTORIETY_PER_THEFT_VALUE))
        player.adjust_reputation("town_guard", -notoriety_loss)
        reputation = player.get_reputation("town_guard")

        goes_to_jail = (
            theft_value >= CRIME_JAIL_VALUE_THRESHOLD
            or player.total_theft_value >= CRIME_JAIL_CUMULATIVE_THRESHOLD
            or reputation <= CRIME_JAIL_REPUTATION_THRESHOLD
        )

        fine = max(CRIME_FINE_MINIMUM, round(theft_value * CRIME_FINE_RATE))
        if not goes_to_jail:
            if player.runtime_state.gold >= fine:
                player.runtime_state.gold -= fine
                return (
                    f"\n{FORMAT_ERROR}You're caught! You pay a {fine} {self.world.currency_name()} "
                    f"fine to avoid worse.{FORMAT_RESET}"
                )
            goes_to_jail = True  # can't afford the fine -- escalates

        sentence_seconds = JAIL_BASE_SENTENCE_SECONDS + theft_value * JAIL_SENTENCE_PER_THEFT_VALUE
        return self.send_to_jail(player, sentence_seconds)

    def _find_jail_cell(self):
        """Locate the authored jail cell room by its `is_jail_cell` flag
        rather than a hardcoded region/room id, keeping this engine module
        content-neutral."""
        for region_id, region in self.world.regions.items():
            for room_id, room in region.rooms.items():
                if room.properties.get("is_jail_cell"):
                    return region_id, room_id
        return None, None

    def has_concealed_pick_bottleneck(self, player: 'Player') -> bool:
        return (
            player.get_skill_level("stealth") >= CONCEALED_PICK_STEALTH_FLOOR
            and player.get_skill_level("lockpicking") >= CONCEALED_PICK_LOCKPICKING_FLOOR
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
                shiv = ItemFactory.create_item_from_template(
                    "item_lockpick_shiv", self.world,
                    properties_override={"durability": EMERGENCY_LOCKPICK_DURABILITY,
                                          "max_durability": EMERGENCY_LOCKPICK_DURABILITY},
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
        """Sentence served in full -- everything confiscated comes back."""
        restored = player.confiscated_inventory
        player.confiscated_inventory = None
        player.jailed_until = None
        if restored:
            for slot in restored.slots:
                if slot.item:
                    player.inventory.add_item(slot.item, slot.quantity)
        return f"{FORMAT_SUCCESS}Your sentence is served. The guard returns your belongings and lets you out.{FORMAT_RESET}"

    def forfeit_confiscated_items(self, player: 'Player') -> None:
        """An escape leaves confiscated belongings behind for good."""
        player.confiscated_inventory = None
        player.jailed_until = None
