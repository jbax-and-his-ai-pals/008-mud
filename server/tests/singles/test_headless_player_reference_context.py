import json
import os
import stat
import time
import unittest

from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class TestHeadlessPlayerReferenceContext(unittest.TestCase):
    TEST_SAVE_FILE = "headless_reference_context_save.json"

    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        self.session_a = self.server.create_session(player_id="reference_ctx_a")
        self.server.mark_session_connected(self.session_a.session_id)
        self.server.execute_command(self.session_a.session_id, "char create ReferenceHeroA")
        self.player_a = self.server.get_player_for_session(self.session_a.session_id)
        assert self.player_a is not None

        self.session_b = self.server.create_session(player_id="reference_ctx_b")
        self.server.mark_session_connected(self.session_b.session_id)
        self.server.execute_command(self.session_b.session_id, "char create ReferenceHeroB")
        self.player_b = self.server.get_player_for_session(self.session_b.session_id)
        assert self.player_b is not None

    def tearDown(self) -> None:
        self.server.shutdown()
        save_path = os.path.join("data", "saves", self.TEST_SAVE_FILE)
        if os.path.exists(save_path):
            for _ in range(3):
                try:
                    os.chmod(save_path, stat.S_IWRITE)
                    os.remove(save_path)
                    break
                except PermissionError:
                    time.sleep(0.1)

    def _text_payloads(self, events: list[dict]) -> list[str]:
        return [str(event.get("payload", "")) for event in events if event.get("type") == "text"]

    def test_journal_uses_invoking_session_player_not_legacy_world_player(self) -> None:
        self.player_a.runtime_state.quests.active["reference_quest"] = {
            "instance_id": "reference_quest",
            "title": "Reference Quest",
            "state": "active",
            "giver_instance_id": "quest_board",
            "current_stage_index": 0,
            "objective": {"type": "unknown", "description": "Do the thing."},
            "stages": [{"stage_index": 0, "description": "Do the thing.", "objective": {"type": "unknown"}}],
        }
        self.player_b.runtime_state.quests.active["other_quest"] = {
            "instance_id": "other_quest",
            "title": "Other Quest",
            "state": "active",
            "giver_instance_id": "quest_board",
            "current_stage_index": 0,
            "objective": {"type": "unknown", "description": "Something else."},
            "stages": [{"stage_index": 0, "description": "Something else.", "objective": {"type": "unknown"}}],
        }
        self.server.world.player = self.player_b

        events = self.server.execute_command(self.session_a.session_id, "journal")
        payloads = self._text_payloads(events)

        self.assertTrue(any("Reference Quest" in payload for payload in payloads))
        self.assertFalse(any("Other Quest" in payload for payload in payloads))

    def test_save_game_uses_explicit_player_not_legacy_world_player(self) -> None:
        self.player_a.runtime_state.gold = 777
        self.player_b.runtime_state.gold = 5
        self.server.world.player = self.player_b

        success = self.server.world.save_game(self.TEST_SAVE_FILE, player=self.player_a)
        self.assertTrue(success)

        save_path = os.path.join("data", "saves", self.TEST_SAVE_FILE)
        with open(save_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)

        self.assertEqual(payload["player"]["gameplay"]["economy"]["gold"], 777)
        self.assertEqual(payload["player"]["name"], self.player_a.name)
