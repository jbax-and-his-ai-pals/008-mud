# tests/singles/test_npc_ai_dispatcher_full.py
"""Coverage for engine/npcs/ai/dispatcher.py's handle_ai: the stunned-NPC
short-circuit, the schedule-override's no-game skip and forced-aggression-
scan-finds-nothing fallthrough, the retreating_for_mana direct dispatch,
the in-combat flee-attempt-failed fallthrough to try_attack, the patrol/
follower direct dispatches, and an unrecognized behavior_type producing no
idle-movement message."""

import time
import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.npcs.ai.dispatcher import handle_ai


def _npc(world, template, instance_id, **overrides):
    npc = NPCFactory.create_npc_from_template(template, world, instance_id=instance_id, **overrides)
    world.add_npc(npc)
    return npc


class TestHandleAiEarlyExits(GameTestBase):
    def test_stunned_npc_returns_none(self):
        npc = _npc(self.world, "goblin", "dispatcher_stunned")
        npc.active_effects.append({"name": "Stun", "tags": []})
        self.assertIsNone(handle_ai(npc, self.world, time.time(), self.player))


class TestScheduleOverride(GameTestBase):
    def test_no_game_skips_schedule_override(self):
        npc = _npc(self.world, "village_elder", "dispatcher_no_game")
        npc.behavior_type = "scheduled"
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        npc.last_moved = 0
        original_game = self.world.game
        self.world.game = None
        try:
            result = handle_ai(npc, self.world, time.time(), self.player)  # must not raise
        finally:
            self.world.game = original_game

    def test_forced_aggression_scan_finding_nothing_falls_through(self):
        npc = _npc(self.world, "village_elder", "dispatcher_forced_aggro")
        npc.behavior_type = "scheduled"
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        npc.schedule = {str(self.game.time_manager.hour): {"behavior_override": "aggressive"}}
        with patch("engine.npcs.ai.dispatcher.scan_for_targets", return_value=None) as mock_scan:
            handle_ai(npc, self.world, time.time(), self.player)
        mock_scan.assert_any_call(npc, self.world, self.player, force_aggression=True)


class TestSpecializedBehaviors(GameTestBase):
    def test_retreating_for_mana_dispatches_directly(self):
        npc = _npc(self.world, "goblin", "dispatcher_retreat")
        npc.behavior_type = "retreating_for_mana"
        with patch("engine.npcs.ai.dispatcher.perform_retreat", return_value="retreating!") as mock_retreat:
            result = handle_ai(npc, self.world, time.time(), self.player)
        mock_retreat.assert_called_once()
        self.assertEqual(result, "retreating!")


class TestCombatFleeFallthrough(GameTestBase):
    def test_failed_flee_attempt_falls_through_to_attack(self):
        npc = _npc(self.world, "goblin", "dispatcher_flee_fail")
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        npc.in_combat = True
        npc.health = 1
        npc.max_health = 100
        npc.flee_threshold = 0.5
        with patch("engine.npcs.ai.dispatcher.try_flee", return_value=None) as mock_flee:
            with patch("engine.npcs.ai.dispatcher.npc_combat.try_attack", return_value="attacks!") as mock_attack:
                result = handle_ai(npc, self.world, time.time(), self.player)
        mock_flee.assert_called_once()
        mock_attack.assert_called_once()
        self.assertEqual(result, "attacks!")


class TestIdleMovementDispatch(GameTestBase):
    def _idle_npc(self, template, instance_id, behavior_type):
        npc = _npc(self.world, template, instance_id)
        npc.behavior_type = behavior_type
        npc.last_moved = 0
        return npc

    def test_patrol_behavior_dispatches_directly(self):
        npc = self._idle_npc("village_elder", "dispatcher_patrol", "patrol")
        with patch("engine.npcs.ai.dispatcher.perform_patrol", return_value="patrolling") as mock_patrol:
            with patch("engine.npcs.ai.dispatcher.scan_for_targets", return_value=None):
                handle_ai(npc, self.world, time.time(), self.player)
        mock_patrol.assert_called_once()

    def test_follower_behavior_dispatches_directly(self):
        npc = self._idle_npc("village_elder", "dispatcher_follower", "follower")
        with patch("engine.npcs.ai.dispatcher.perform_follow", return_value="following") as mock_follow:
            with patch("engine.npcs.ai.dispatcher.scan_for_targets", return_value=None):
                handle_ai(npc, self.world, time.time(), self.player)
        mock_follow.assert_called_once()

    def test_unrecognized_behavior_type_produces_no_movement(self):
        npc = self._idle_npc("village_elder", "dispatcher_unknown_behavior", "totally_unrecognized_behavior")
        with patch("engine.npcs.ai.dispatcher.scan_for_targets", return_value=None):
            result = handle_ai(npc, self.world, time.time(), self.player)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
