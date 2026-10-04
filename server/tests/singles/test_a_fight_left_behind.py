# tests/singles/test_a_fight_left_behind.py
"""Running from a fight ends it for you once you are in another room.

A player who broke away successfully used to stay "in combat" in the empty room next door, and the
next step was refused ("You can't break away from the fight!") as a retreat from an enemy who was
not there.
"""

import unittest
from pathlib import Path
from unittest import mock

from engine.core.skill_system import SkillSystem
from engine.npcs.npc_factory import NPCFactory
from engine.server.headless_server import HeadlessServer

from tests.fixtures import STORY_FIXTURE

REPO_ROOT = Path(__file__).resolve().parents[3]


class TestAFightLeftBehind(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(STORY_FIXTURE),
            deterministic_test_mode=True, default_presentation_mode="player",
        )
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="run").session_id
        self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.player.current_region_id, self.player.current_room_id = "road", "castle_road"
        self.wolf = NPCFactory.create_npc_from_template("road_wolf", self.server.world, instance_id="chaser")
        self.wolf.current_region_id, self.wolf.current_room_id = "road", "castle_road"
        self.server.world.add_npc(self.wolf)
        self.player.enter_combat(self.wolf)

    def test_a_successful_retreat_ends_the_fight_for_the_player(self):
        with mock.patch.object(SkillSystem, "practice_check", return_value=(True, "")):
            exits = self.server.world.get_current_room(self.player).exits
            direction = next(iter(exits))
            self.server.world.change_room(direction, player=self.player)
        self.assertNotEqual("castle_road", self.player.current_room_id)
        self.assertFalse(self.player.runtime_state.combat.in_combat)
        self.assertEqual(set(), self.player.runtime_state.combat.targets)

    def test_the_next_step_is_not_a_second_retreat(self):
        calls = []

        def check(player, skill, difficulty):
            calls.append(skill)
            return (len(calls) == 1, "")

        with mock.patch.object(SkillSystem, "practice_check", side_effect=check):
            first = next(iter(self.server.world.get_current_room(self.player).exits))
            self.server.world.change_room(first, player=self.player)
            second = next(iter(self.server.world.get_current_room(self.player).exits))
            moved = self.server.world.change_room(second, player=self.player)
        self.assertEqual(1, len(calls), "only the first step, away from the wolf, was a retreat")
        self.assertNotIn("break away", moved)

    def test_an_enemy_still_in_the_room_still_holds_you(self):
        with mock.patch.object(SkillSystem, "practice_check", return_value=(False, "")):
            said = self.server.world.change_room(next(iter(self.server.world.get_current_room(self.player).exits)), player=self.player)
        self.assertIn("break away", said)
        self.assertEqual("castle_road", self.player.current_room_id)


if __name__ == "__main__":
    unittest.main()
