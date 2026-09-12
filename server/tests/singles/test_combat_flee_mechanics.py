# tests/singles/test_combat_flee_mechanics.py
"""Retreat is now contested (see test_meaningful_retreat.py for the new
mechanic's own dedicated coverage): World._attempt_combat_retreat rolls
a stealth check against the toughest engaged hostile before any
movement-while-in-combat is allowed to proceed, in place of the old
free/guaranteed escape this file used to document."""

from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.world.room import Room


class TestCombatFleeMechanics(GameTestBase):

    def setUp(self):
        super().setUp()
        region = self.world.get_region("town")
        r1 = Room("Arena", "Fight here", {"north": "Safe"}, obj_id="Arena")
        r2 = Room("Safe", "Safe here", {"south": "Arena"}, obj_id="Safe")
        region.add_room("Arena", r1)
        region.add_room("Safe", r2)

        self.player.current_region_id = "town"
        self.player.current_room_id = "Arena"
        self.world.current_region_id = "town"
        self.world.current_room_id = "Arena"

        self.goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        self.goblin.current_region_id = "town"
        self.goblin.current_room_id = "Arena"
        self.world.add_npc(self.goblin)
        self.player.enter_combat(self.goblin)

    def test_flee_updates_state_on_a_successful_check(self):
        """A successful retreat check moves the player away from the
        hostile. Combat state itself isn't force-cleared (the goblin left
        behind keeps remembering the fight, matching existing aggro
        persistence -- see test_npc_aggro_persistence.py); it clears
        naturally once the goblin's own AI finds no same-room target."""
        with patch("engine.world.world.SkillSystem.attempt_check", return_value=(True, "rolled well")):
            result = self.game.process_command("north")

        self.assertIsNotNone(result)
        self.assertIn("SAFE", result)
        self.assertEqual(self.player.current_room_id, "Safe")
        self.assertNotIn(self.goblin, self.world.get_current_room_npcs())

    def test_failed_retreat_keeps_the_player_in_the_fight(self):
        """A failed retreat check blocks the move entirely -- combat continues."""
        with patch("engine.world.world.SkillSystem.attempt_check", return_value=(False, "rolled poorly")):
            result = self.game.process_command("north")

        self.assertIn("can't break away", result)
        self.assertEqual(self.player.current_room_id, "Arena")
        self.assertTrue(self.player.runtime_state.combat.in_combat)
        self.assertIn(self.goblin, self.player.runtime_state.combat.targets)
