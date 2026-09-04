# tests/singles/test_npc_ai_specialized.py
"""Coverage for engine/npcs/ai/specialized.py: perform_healer_logic (no
location, no usable heal spell, no wounded targets, successful heal with/
without a viewer) and perform_minion_logic's remaining branches (no owner
-> despawn, expired summon duration -> despawn, following an absent owner,
assisting an owner mid-combat, intercepting an attacker targeting the
owner, and attacking a hostile NPC when idle) -- most of which
test_minion_complex.py's kill-credit-focused tests don't reach."""

import time
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.npcs.ai.specialized import perform_healer_logic, perform_minion_logic


def _npc(world, template, instance_id):
    npc = NPCFactory.create_npc_from_template(template, world, instance_id=instance_id)
    world.add_npc(npc)
    return npc


class TestPerformHealerLogic(GameTestBase):
    def setUp(self):
        super().setUp()
        self.healer = _npc(self.world, "village_elder", "healer_npc")
        self.healer.current_region_id = self.player.current_region_id
        self.healer.current_room_id = self.player.current_room_id
        self.healer.usable_spells = ["minor_heal"]
        self.healer.mana = 50
        self.healer.max_mana = 50

    def test_no_location_returns_none(self):
        self.healer.current_region_id = None
        self.healer.current_room_id = None
        self.assertIsNone(perform_healer_logic(self.healer, self.world, time.time(), self.player))

    def test_no_usable_heal_spell_returns_none(self):
        self.healer.usable_spells = []
        self.assertIsNone(perform_healer_logic(self.healer, self.world, time.time(), self.player))

    def test_spell_on_cooldown_is_not_usable(self):
        self.healer.spell_cooldowns["minor_heal"] = time.time() + 100
        self.assertIsNone(perform_healer_logic(self.healer, self.world, time.time(), self.player))

    def test_insufficient_mana_is_not_usable(self):
        self.healer.mana = 0
        self.assertIsNone(perform_healer_logic(self.healer, self.world, time.time(), self.player))

    def test_no_wounded_targets_returns_none(self):
        self.player.health = self.player.max_health
        self.assertIsNone(perform_healer_logic(self.healer, self.world, time.time(), self.player))

    def test_heals_most_wounded_ally_with_viewer_present(self):
        self.player.health = 1
        result = perform_healer_logic(self.healer, self.world, time.time(), self.player)
        self.assertIsNotNone(result)

    def test_hostile_wounded_target_is_ignored(self):
        hostile = _npc(self.world, "goblin", "healer_hostile_target")
        hostile.current_region_id = self.player.current_region_id
        hostile.current_room_id = self.player.current_room_id
        hostile.health = 1
        self.player.health = self.player.max_health
        result = perform_healer_logic(self.healer, self.world, time.time(), self.player)
        self.assertIsNone(result)

    def test_heal_without_a_viewer_returns_none(self):
        self.player.health = 1
        with patch.object(self.world, "get_viewer_for_npc", return_value=None):
            result = perform_healer_logic(self.healer, self.world, time.time(), self.player)
        self.assertIsNone(result)


class TestPerformMinionLogic(GameTestBase):
    def _minion(self, instance_id="minion_npc"):
        minion = _npc(self.world, "skeleton_minion", instance_id)
        return minion

    def test_no_location_returns_none(self):
        minion = self._minion()
        minion.current_region_id = None
        minion.current_room_id = None
        self.assertIsNone(perform_minion_logic(minion, self.world, time.time(), self.player))

    def test_no_owner_despawns_silently(self):
        minion = self._minion()
        minion.current_region_id = "town"
        minion.current_room_id = "town_square"
        minion.properties["owner_id"] = "not_a_real_owner_id"
        perform_minion_logic(minion, self.world, time.time(), self.player)
        self.assertFalse(minion.is_alive)

    def test_expired_summon_duration_despawns(self):
        minion = self._minion()
        minion.current_region_id = self.player.current_region_id
        minion.current_room_id = self.player.current_room_id
        minion.properties["owner_id"] = self.player.obj_id
        minion.properties["creation_time"] = time.time() - 1000
        minion.properties["summon_duration"] = 10.0
        perform_minion_logic(minion, self.world, time.time(), self.player)
        self.assertFalse(minion.is_alive)

    def test_follows_owner_when_not_colocated(self):
        minion = self._minion()
        minion.current_region_id = "town"
        minion.current_room_id = "town_square"
        minion.properties["owner_id"] = self.player.obj_id
        self.player.current_region_id = "town"
        self.player.current_room_id = "market_square"
        with patch("engine.npcs.ai.specialized.perform_follow", return_value="follows you.") as mock_follow:
            result = perform_minion_logic(minion, self.world, time.time(), self.player)
        mock_follow.assert_called_once()
        self.assertEqual("follows you.", result)
        self.assertEqual(self.player.obj_id, minion.follow_target)

    def test_assists_owner_against_their_combat_target(self):
        minion = self._minion()
        target = _npc(self.world, "goblin", "minion_assist_target")
        minion.current_region_id = self.player.current_region_id
        minion.current_room_id = self.player.current_room_id
        target.current_region_id = self.player.current_region_id
        target.current_room_id = self.player.current_room_id
        minion.properties["owner_id"] = self.player.obj_id
        # .target (the player's chosen focus, as opposed to .targets, the
        # full engagement set) is set by Player.attack() when the player
        # explicitly attacks someone; simulate that directly here.
        self.player.enter_combat(target)
        self.player.runtime_state.combat.target = target
        result = perform_minion_logic(minion, self.world, time.time(), self.player)
        self.assertIn(target, minion.combat_targets)
        self.assertIn("moves to assist you", result)

    def test_dead_current_target_is_skipped_in_favor_of_intercept(self):
        minion = self._minion()
        dead_target = _npc(self.world, "goblin", "minion_dead_target")
        attacker = _npc(self.world, "goblin", "minion_dead_target_attacker")
        minion.current_region_id = self.player.current_region_id
        minion.current_room_id = self.player.current_room_id
        dead_target.current_region_id = self.player.current_region_id
        dead_target.current_room_id = self.player.current_room_id
        attacker.current_region_id = self.player.current_region_id
        attacker.current_room_id = self.player.current_room_id
        minion.properties["owner_id"] = self.player.obj_id
        # A stale/dead .target must be skipped (it's not a valid assist
        # target), falling through to the intercept-attacker check.
        self.player.runtime_state.combat.in_combat = True
        self.player.runtime_state.combat.target = dead_target
        dead_target.is_alive = False
        attacker.enter_combat(self.player)
        result = perform_minion_logic(minion, self.world, time.time(), self.player)
        self.assertIn(attacker, minion.combat_targets)
        self.assertIn("intercepts", result)

    def test_intercepts_attacker_targeting_owner(self):
        minion = self._minion()
        attacker = _npc(self.world, "goblin", "minion_intercept_attacker")
        minion.current_region_id = self.player.current_region_id
        minion.current_room_id = self.player.current_room_id
        attacker.current_region_id = self.player.current_region_id
        attacker.current_room_id = self.player.current_room_id
        minion.properties["owner_id"] = self.player.obj_id
        # The owner has not chosen a focus target (.target stays None,
        # since only Player.attack() sets it) but is being attacked --
        # exercises the "intercept" branch rather than "assist".
        attacker.enter_combat(self.player)
        result = perform_minion_logic(minion, self.world, time.time(), self.player)
        self.assertIn(attacker, minion.combat_targets)
        self.assertIn("intercepts", result)

    def test_attacks_hostile_npc_when_idle(self):
        minion = self._minion()
        hostile = _npc(self.world, "goblin", "minion_idle_hostile")
        minion.current_region_id = self.player.current_region_id
        minion.current_room_id = self.player.current_room_id
        hostile.current_region_id = self.player.current_region_id
        hostile.current_room_id = self.player.current_room_id
        minion.properties["owner_id"] = self.player.obj_id
        result = perform_minion_logic(minion, self.world, time.time(), self.player)
        self.assertIn(hostile, minion.combat_targets)
        self.assertIn("moves to attack", result)

    def test_nothing_to_do_returns_none(self):
        minion = self._minion()
        minion.current_region_id = self.player.current_region_id
        minion.current_room_id = self.player.current_room_id
        minion.properties["owner_id"] = self.player.obj_id
        result = perform_minion_logic(minion, self.world, time.time(), self.player)
        self.assertIsNone(result)


if __name__ == "__main__":
    import unittest
    unittest.main()
