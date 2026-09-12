# tests/singles/test_meaningful_retreat.py
"""Coverage for the new `flee` command and World._attempt_combat_retreat:
retreat is now a contested stealth check against the toughest engaged
hostile (server/engine/world/world.py), not a free escape. `flee` is a
thin convenience wrapper that auto-picks an exit (preferring a safe
destination) and funnels through the exact same check as ordinary
directional movement."""

from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.world.room import Room


class TestFleeCommand(GameTestBase):
    def setUp(self):
        super().setUp()
        region = self.world.get_region("town")
        battle_room = Room(
            "Battle Room", "A dangerous crossroads.",
            {"north": "town_square", "south": "forest:forest_edge"},
            obj_id="battle_room",
        )
        region.add_room("battle_room", battle_room)

        self.player.current_region_id = "town"
        self.player.current_room_id = "battle_room"

        self.goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        self.goblin.current_region_id = "town"
        self.goblin.current_room_id = "battle_room"
        self.world.add_npc(self.goblin)
        self.player.enter_combat(self.goblin)

    def test_flee_prefers_a_safe_destination(self):
        with patch("engine.world.world.SkillSystem.attempt_check", return_value=(True, "rolled well")):
            result = self.game.process_command("flee")
        self.assertIn("TOWN SQUARE", result)
        self.assertEqual("town_square", self.player.current_room_id)

    def test_failed_flee_keeps_the_player_in_the_fight(self):
        with patch("engine.world.world.SkillSystem.attempt_check", return_value=(False, "rolled poorly")):
            result = self.game.process_command("flee")
        self.assertIn("can't break away", result)
        self.assertEqual("battle_room", self.player.current_room_id)
        self.assertTrue(self.player.runtime_state.combat.in_combat)

    def test_flee_when_not_in_combat_is_rejected(self):
        self.player.exit_combat()
        result = self.game.process_command("flee")
        self.assertIn("not in combat", result)
        self.assertEqual("battle_room", self.player.current_room_id)

    def test_flee_with_no_exits_reports_nowhere_to_run(self):
        region = self.world.get_region("town")
        dead_end = Room("Dead End", "Walls on every side.", {}, obj_id="dead_end")
        region.add_room("dead_end", dead_end)
        self.player.current_room_id = "dead_end"
        self.goblin.current_room_id = "dead_end"

        result = self.game.process_command("flee")
        self.assertIn("nowhere to run", result)
        self.assertEqual("dead_end", self.player.current_room_id)


class TestOrdinaryMovementUnaffectedOutsideCombat(GameTestBase):
    def test_movement_is_free_when_not_in_combat(self):
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        with patch("engine.world.world.SkillSystem.attempt_check") as mock_check:
            self.game.process_command("east")
            mock_check.assert_not_called()
