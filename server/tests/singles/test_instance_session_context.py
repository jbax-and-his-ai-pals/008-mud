import unittest

from engine.server.headless_server import HeadlessServer
from engine.world.region import Region
from tests.fixtures import FANTASY_FRONTIER


class TestInstanceSessionContext(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        self.session_a = self.server.create_session(player_id="instance_ctx_a")
        self.server.mark_session_connected(self.session_a.session_id)
        self.server.execute_command(self.session_a.session_id, "char create InstanceHeroA")
        self.player_a = self.server.get_player_for_session(self.session_a.session_id)
        assert self.player_a is not None

        self.session_b = self.server.create_session(player_id="instance_ctx_b")
        self.server.mark_session_connected(self.session_b.session_id)
        self.server.execute_command(self.session_b.session_id, "char create InstanceHeroB")
        self.player_b = self.server.get_player_for_session(self.session_b.session_id)
        assert self.player_b is not None

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_cleanup_quest_region_finds_completed_owner_not_legacy_world_player(self) -> None:
        quest_id = "instance_ctx_cleanup"
        region_id = "instance_ctx_region"
        assert self.player_a.runtime_state.quests is not None
        self.player_a.runtime_state.quests.completed[quest_id] = {
            "instance_id": quest_id,
            "instance_region_id": region_id,
            "entry_point": {"region_id": "town", "room_id": "town_square", "exit_command": "ctx_portal"},
        }
        self.server.world.add_region(region_id, Region("Ctx Region", "Test", obj_id=region_id))
        town_room = self.server.world.get_region("town").get_room("town_square")
        town_room.exits["ctx_portal"] = f"{region_id}:entry"
        self.server.world.player = self.player_b

        self.server.world.cleanup_quest_region(quest_id)

        self.assertNotIn(region_id, self.server.world.regions)
        self.assertNotIn("ctx_portal", town_room.exits)
        self.assertIn(quest_id, self.player_a.runtime_state.quests.archived)
        self.assertNotIn(quest_id, self.player_a.runtime_state.quests.completed)

    def test_cleanup_quest_region_works_without_legacy_player_binding(self) -> None:
        quest_id = "instance_ctx_cleanup_no_legacy"
        region_id = "instance_ctx_region_no_legacy"
        assert self.player_a.runtime_state.quests is not None
        self.player_a.runtime_state.quests.completed[quest_id] = {
            "instance_id": quest_id,
            "instance_region_id": region_id,
            "entry_point": {"region_id": "town", "room_id": "town_square", "exit_command": "ctx_portal_no_legacy"},
        }
        self.server.world.add_region(region_id, Region("Ctx Region", "Test", obj_id=region_id))
        town_room = self.server.world.get_region("town").get_room("town_square")
        town_room.exits["ctx_portal_no_legacy"] = f"{region_id}:entry"
        self.server.world._legacy_player_id = None

        self.server.world.cleanup_quest_region(quest_id)

        self.assertNotIn(region_id, self.server.world.regions)
        self.assertNotIn("ctx_portal_no_legacy", town_room.exits)
        self.assertIn(quest_id, self.player_a.runtime_state.quests.archived)
        self.assertNotIn(quest_id, self.player_a.runtime_state.quests.completed)
