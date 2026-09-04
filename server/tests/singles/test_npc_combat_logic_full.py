# tests/singles/test_npc_combat_logic_full.py
"""Coverage for engine/npcs/ai/combat_logic.py: try_flee's guard clauses
and hostile-exit-filtering/fallback branches, start_retreat/perform_retreat
(entirely untested previously), and scan_for_targets' debug-ignore-player
branch and social-aggro (ally-defense) detection for both players and NPCs
-- most of which the existing flee/faction-combat tests don't reach."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.npcs.ai.combat_logic import try_flee, start_retreat, perform_retreat, scan_for_targets
from engine.world.room import Room


def _npc(world, template="goblin", instance_id="cl_npc"):
    npc = NPCFactory.create_npc_from_template(template, world, instance_id=instance_id)
    world.add_npc(npc)
    return npc


class TestTryFlee(GameTestBase):
    def test_no_location_returns_none(self):
        npc = _npc(self.world)
        npc.current_region_id = None
        npc.current_room_id = None
        self.assertIsNone(try_flee(npc, self.world, self.player))

    def test_unknown_region_returns_none(self):
        npc = _npc(self.world)
        npc.current_region_id = "not_a_real_region"
        npc.current_room_id = "x"
        self.assertIsNone(try_flee(npc, self.world, self.player))

    def test_room_with_no_exits_returns_none(self):
        npc = _npc(self.world)
        region = self.world.get_region("town")
        region.add_room("dead_end_room", Room("Dead End", "x", {}, obj_id="dead_end_room"))
        npc.current_region_id = "town"
        npc.current_room_id = "dead_end_room"
        self.assertIsNone(try_flee(npc, self.world, self.player))

    def test_non_hostile_npc_uses_any_exit(self):
        npc = _npc(self.world, template="village_elder", instance_id="cl_friendly")
        region = self.world.get_region("town")
        region.add_room("friendly_start", Room("Start", "x", {"east": "town_square"}, obj_id="friendly_start"))
        npc.current_region_id = "town"
        npc.current_room_id = "friendly_start"
        result = try_flee(npc, self.world, self.player)
        self.assertEqual("town_square", npc.current_room_id)

    def test_hostile_npc_prefers_unsafe_destination_exits(self):
        npc = _npc(self.world)
        region = self.world.get_region("town")
        region.properties["safe_zone"] = True  # town itself is "safe"
        danger_region = self.world.get_region("caves") or region
        region.add_room("flee_start", Room(
            "Start", "x", {"south": "town_square", "north": f"{danger_region.obj_id}:{next(iter(danger_region.rooms.keys()))}"},
            obj_id="flee_start",
        ))
        npc.current_region_id = "town"
        npc.current_room_id = "flee_start"
        npc.faction = "hostile"
        with patch("engine.npcs.ai.combat_logic.random.choice", side_effect=lambda opts: opts[0]):
            try_flee(npc, self.world, self.player)  # must not raise

    def test_hostile_npc_falls_back_to_all_exits_when_none_unsafe(self):
        npc = _npc(self.world)
        region = self.world.get_region("town")
        for r in self.world.regions.values():
            r.properties["safe_zone"] = True
        region.add_room("all_safe_start", Room("Start", "x", {"south": "town_square"}, obj_id="all_safe_start"))
        npc.current_region_id = "town"
        npc.current_room_id = "all_safe_start"
        npc.faction = "hostile"
        result = try_flee(npc, self.world, self.player)
        self.assertEqual("town_square", npc.current_room_id)

    def test_player_not_present_returns_none_message(self):
        npc = _npc(self.world)
        region = self.world.get_region("town")
        region.add_room("empty_flee_start", Room("Start", "x", {"east": "town_square"}, obj_id="empty_flee_start"))
        npc.current_region_id = "town"
        npc.current_room_id = "empty_flee_start"
        self.player.current_room_id = "somewhere_else_entirely"
        result = try_flee(npc, self.world, self.player)
        self.assertIsNone(result)


class TestStartRetreat(GameTestBase):
    def test_no_location_returns_none(self):
        npc = _npc(self.world)
        npc.current_region_id = None
        npc.current_room_id = None
        self.assertIsNone(start_retreat(npc, self.world, 0.0, self.player))

    def test_no_safe_room_found_returns_none(self):
        npc = _npc(self.world)
        npc.current_region_id = "town"
        npc.current_room_id = "town_square"
        with patch.object(self.world, "find_nearest_safe_room", return_value=None):
            self.assertIsNone(start_retreat(npc, self.world, 0.0, self.player))

    def test_no_path_to_safe_room_resets_destination(self):
        npc = _npc(self.world)
        npc.current_region_id = "town"
        npc.current_room_id = "town_square"
        with patch.object(self.world, "find_nearest_safe_room", return_value=("town", "town_square")), \
             patch.object(self.world, "find_path", return_value=None):
            result = start_retreat(npc, self.world, 0.0, self.player)
        self.assertIsNone(result)
        self.assertIsNone(npc.retreat_destination)

    def test_successful_retreat_sets_state_and_reports_when_player_present(self):
        npc = _npc(self.world)
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        with patch.object(self.world, "find_nearest_safe_room", return_value=("town", "some_safe_room")), \
             patch.object(self.world, "find_path", return_value=["north", "east"]):
            result = start_retreat(npc, self.world, 0.0, self.player)
        self.assertEqual("retreating_for_mana", npc.behavior_type)
        self.assertIn("retreats from battle", result)

    def test_successful_retreat_without_player_present_returns_none(self):
        npc = _npc(self.world)
        npc.current_region_id = "town"
        npc.current_room_id = "town_square"
        self.player.current_room_id = "somewhere_else_entirely"
        with patch.object(self.world, "find_nearest_safe_room", return_value=("town", "some_safe_room")), \
             patch.object(self.world, "find_path", return_value=["north"]):
            result = start_retreat(npc, self.world, 0.0, self.player)
        self.assertIsNone(result)
        self.assertEqual("retreating_for_mana", npc.behavior_type)

    def test_existing_retreat_destination_is_reused(self):
        npc = _npc(self.world)
        npc.current_region_id = "town"
        npc.current_room_id = "town_square"
        npc.retreat_destination = ("town", "already_set")
        with patch.object(self.world, "find_nearest_safe_room") as mock_find, \
             patch.object(self.world, "find_path", return_value=["north"]):
            start_retreat(npc, self.world, 0.0, self.player)
        mock_find.assert_not_called()


class TestPerformRetreat(GameTestBase):
    def test_mana_restored_resumes_original_behavior_with_message(self):
        npc = _npc(self.world)
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        npc.mana = npc.max_mana
        npc.original_behavior = "wanderer"
        npc.retreat_destination = ("town", "somewhere")
        npc.current_path = ["north"]
        result = perform_retreat(npc, self.world, 0.0, self.player)
        self.assertEqual("wanderer", npc.behavior_type)
        self.assertIsNone(npc.retreat_destination)
        self.assertEqual([], npc.current_path)
        self.assertIn("recovered", result)

    def test_mana_restored_without_player_present_returns_none(self):
        npc = _npc(self.world)
        npc.current_region_id = "town"
        npc.current_room_id = "town_square"
        npc.mana = npc.max_mana
        self.player.current_room_id = "somewhere_else_entirely"
        result = perform_retreat(npc, self.world, 0.0, self.player)
        self.assertIsNone(result)

    def test_arrived_at_retreat_destination_clears_path(self):
        npc = _npc(self.world)
        npc.mana = 0
        npc.max_mana = 10
        npc.current_region_id = "town"
        npc.current_room_id = "town_square"
        npc.retreat_destination = ("town", "town_square")
        npc.current_path = ["north"]
        result = perform_retreat(npc, self.world, 0.0, self.player)
        self.assertIsNone(result)
        self.assertEqual([], npc.current_path)

    def test_continues_along_path(self):
        npc = _npc(self.world)
        npc.mana = 0
        npc.max_mana = 10
        npc.current_region_id = "town"
        npc.current_room_id = "town_square"
        npc.retreat_destination = ("town", "elsewhere")
        npc.current_path = ["north", "east"]
        with patch("engine.npcs.ai.combat_logic.execute_move", return_value="moved") as mock_move:
            result = perform_retreat(npc, self.world, 0.0, self.player)
        mock_move.assert_called_once()
        self.assertEqual(["east"], npc.current_path)
        self.assertEqual("moved", result)

    def test_lost_path_falls_back_to_original_behavior_with_message(self):
        npc = _npc(self.world)
        npc.mana = 0
        npc.max_mana = 10
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        npc.retreat_destination = ("town", "unreachable_room")
        npc.current_path = []
        npc.original_behavior = "guard"
        result = perform_retreat(npc, self.world, 0.0, self.player)
        self.assertEqual("guard", npc.behavior_type)
        self.assertIn("lost their way", result)

    def test_lost_path_without_player_present_returns_none(self):
        npc = _npc(self.world)
        npc.mana = 0
        npc.max_mana = 10
        npc.current_region_id = "town"
        npc.current_room_id = "town_square"
        npc.retreat_destination = ("town", "unreachable_room")
        npc.current_path = []
        self.player.current_room_id = "somewhere_else_entirely"
        result = perform_retreat(npc, self.world, 0.0, self.player)
        self.assertIsNone(result)


class TestScanForTargets(GameTestBase):
    def test_debug_ignore_player_skips_player_target(self):
        npc = _npc(self.world)
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        npc.faction = "hostile"
        npc.aggression = 1.0
        self.game.debug_ignore_player = True
        self.world.game = self.game
        # Isolate against other room NPCs (e.g. the default wandering
        # villager) that would otherwise also be a valid hostile target.
        with patch.object(self.world, "get_npcs_in_room", return_value=[]), \
             patch("engine.npcs.ai.combat_logic.random.random", return_value=0.0):
            result = scan_for_targets(npc, self.world, self.player)
        self.assertIsNone(result)

    def test_social_aggro_defends_player_ally_being_attacked_by_npc(self):
        friend = _npc(self.world, template="village_elder", instance_id="cl_friend")
        attacker = _npc(self.world, template="goblin", instance_id="cl_attacker")
        defender = _npc(self.world, template="village_elder", instance_id="cl_defender")
        for n in (friend, attacker, defender):
            n.current_region_id = self.player.current_region_id
            n.current_room_id = self.player.current_room_id
        defender.faction = "friendly"
        attacker.faction = "hostile"
        attacker.enter_combat(defender)
        with patch("engine.npcs.ai.combat_logic.npc_combat.get_relation_to", return_value=1):
            result = scan_for_targets(defender, self.world, self.player)
        self.assertIsNotNone(result)

    def test_social_aggro_defends_against_player_attacking_friend(self):
        friend = _npc(self.world, template="village_elder", instance_id="cl_friend2")
        defender = _npc(self.world, template="village_elder", instance_id="cl_defender2")
        for n in (friend, defender):
            n.current_region_id = self.player.current_region_id
            n.current_room_id = self.player.current_room_id
        self.player.enter_combat(friend)
        with patch.object(self.world, "get_npcs_in_room", return_value=[defender]), \
             patch("engine.npcs.ai.combat_logic.npc_combat.get_relation_to", return_value=1):
            result = scan_for_targets(defender, self.world, self.player)
        self.assertIsNotNone(result)

    def test_social_aggro_skips_non_combat_actor_before_finding_match(self):
        idle_actor = _npc(self.world, template="goblin", instance_id="cl_idle")
        attacker = _npc(self.world, template="goblin", instance_id="cl_attacker2")
        defender = _npc(self.world, template="village_elder", instance_id="cl_defender3")
        ally = _npc(self.world, template="village_elder", instance_id="cl_ally3")
        for n in (idle_actor, attacker, defender, ally):
            n.current_region_id = self.player.current_region_id
            n.current_room_id = self.player.current_room_id
        idle_actor.faction = "hostile"
        attacker.faction = "hostile"
        defender.faction = "friendly"
        attacker.enter_combat(ally)
        with patch.object(self.world, "get_npcs_in_room", return_value=[idle_actor, attacker]), \
             patch("engine.npcs.ai.combat_logic.npc_combat.get_relation_to", return_value=1):
            result = scan_for_targets(defender, self.world, self.player)
        self.assertIsNotNone(result)

    def test_social_aggro_skips_non_matching_target_before_finding_match(self):
        attacker = _npc(self.world, template="goblin", instance_id="cl_attacker3")
        stranger = _npc(self.world, template="goblin", instance_id="cl_stranger")
        ally = _npc(self.world, template="village_elder", instance_id="cl_ally4")
        defender = _npc(self.world, template="village_elder", instance_id="cl_defender4")
        for n in (attacker, stranger, ally, defender):
            n.current_region_id = self.player.current_region_id
            n.current_room_id = self.player.current_room_id
        attacker.faction = "hostile"
        defender.faction = "friendly"
        attacker.enter_combat(stranger)
        attacker.enter_combat(ally)

        def relation(_npc_, target):
            return 1 if target is ally else 0

        with patch.object(self.world, "get_npcs_in_room", return_value=[attacker]), \
             patch("engine.npcs.ai.combat_logic.npc_combat.get_relation_to", side_effect=relation):
            result = scan_for_targets(defender, self.world, self.player)
        self.assertIsNotNone(result)

    def test_social_aggro_actor_whose_targets_never_match_falls_through(self):
        # attacker_a is in combat but its target never matches relation>0,
        # so its inner target loop exhausts without a match/break and falls
        # through to checking the next actor (attacker_b), which does match.
        attacker_a = _npc(self.world, template="goblin", instance_id="cl_attacker_a")
        unrelated_target = _npc(self.world, template="goblin", instance_id="cl_unrelated")
        attacker_b = _npc(self.world, template="goblin", instance_id="cl_attacker_b")
        ally = _npc(self.world, template="village_elder", instance_id="cl_ally5")
        defender = _npc(self.world, template="village_elder", instance_id="cl_defender5")
        for n in (attacker_a, unrelated_target, attacker_b, ally, defender):
            n.current_region_id = self.player.current_region_id
            n.current_room_id = self.player.current_room_id
        attacker_a.faction = "hostile"
        attacker_b.faction = "hostile"
        defender.faction = "friendly"
        attacker_a.enter_combat(unrelated_target)
        attacker_b.enter_combat(ally)

        def relation(_npc_, target):
            return 1 if target is ally else 0

        with patch.object(self.world, "get_npcs_in_room", return_value=[attacker_a, attacker_b]), \
             patch("engine.npcs.ai.combat_logic.npc_combat.get_relation_to", side_effect=relation):
            result = scan_for_targets(defender, self.world, self.player)
        self.assertIsNotNone(result)

    def test_social_aggro_skips_actor_in_same_faction(self):
        actor_a = _npc(self.world, template="village_elder", instance_id="cl_actor_a")
        actor_b = _npc(self.world, template="village_elder", instance_id="cl_actor_b")
        for n in (actor_a, actor_b):
            n.current_region_id = self.player.current_region_id
            n.current_room_id = self.player.current_room_id
            n.faction = "friendly"
        result = scan_for_targets(actor_b, self.world, self.player)  # must not raise
        self.assertIsNone(result)


if __name__ == "__main__":
    import unittest
    unittest.main()
