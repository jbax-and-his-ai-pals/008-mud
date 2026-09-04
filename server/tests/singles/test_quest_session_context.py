import unittest

from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class TestQuestSessionContext(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        self.session_a = self.server.create_session(player_id="quest_ctx_a")
        self.server.mark_session_connected(self.session_a.session_id)
        self.server.execute_command(self.session_a.session_id, "char create QuestHeroA")
        self.player_a = self.server.get_player_for_session(self.session_a.session_id)
        assert self.player_a is not None

        self.session_b = self.server.create_session(player_id="quest_ctx_b")
        self.server.mark_session_connected(self.session_b.session_id)
        self.server.execute_command(self.session_b.session_id, "char create QuestHeroB")
        self.player_b = self.server.get_player_for_session(self.session_b.session_id)
        assert self.player_b is not None

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_clear_region_completion_uses_tracked_player_not_legacy_world_player(self) -> None:
        quest_id = "clear_ctx"
        objective_data = {
            "type": "clear_region",
            "target_template_id": "giant_rat",
        }
        assert self.player_a.runtime_state.quests is not None
        self.player_a.runtime_state.quests.active[quest_id] = {
            "instance_id": quest_id,
            "type": "instance",
            "state": "active",
            "instance_region_id": "dynamic_cellar",
            "completion_check_enabled": True,
            "current_stage_index": 0,
            "objective": objective_data,
            "stages": [
                {
                    "stage_index": 0,
                    "objective": objective_data,
                }
            ],
        }
        self.player_a.current_region_id = "dynamic_cellar"
        self.player_a.current_room_id = "entry_hall"
        self.player_b.current_region_id = "town"
        self.player_b.current_room_id = "town_square"
        self.server.world.player = self.player_b

        self.server.world.quest_manager.check_quest_completion()

        self.assertEqual(self.player_a.runtime_state.quests.active[quest_id]["state"], "ready_to_complete")
        assert self.player_b.runtime_state.quests is not None
        self.assertNotIn(quest_id, self.player_b.runtime_state.quests.active)

    def test_clear_region_completion_works_without_legacy_player_binding(self) -> None:
        quest_id = "clear_ctx_no_legacy"
        objective_data = {
            "type": "clear_region",
            "target_template_id": "giant_rat",
        }
        assert self.player_a.runtime_state.quests is not None
        self.player_a.runtime_state.quests.active[quest_id] = {
            "instance_id": quest_id,
            "type": "instance",
            "state": "active",
            "instance_region_id": "dynamic_cellar",
            "completion_check_enabled": True,
            "current_stage_index": 0,
            "objective": objective_data,
            "stages": [
                {
                    "stage_index": 0,
                    "objective": objective_data,
                }
            ],
        }
        self.player_a.current_region_id = "dynamic_cellar"
        self.player_a.current_room_id = "entry_hall"
        self.player_b.current_region_id = "town"
        self.player_b.current_room_id = "town_square"
        self.server.world._legacy_player_id = None

        self.server.world.quest_manager.check_quest_completion()

        self.assertEqual(self.player_a.runtime_state.quests.active[quest_id]["state"], "ready_to_complete")
        assert self.player_b.runtime_state.quests is not None
        self.assertNotIn(quest_id, self.player_b.runtime_state.quests.active)
