import unittest
from pathlib import Path
from unittest.mock import patch

from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class _NoCharacterTestBase(unittest.TestCase):
    """A session that has NOT yet run 'char create', so get_player_for_session
    is None -- the branch every payload builder falls back to."""

    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))
        self.session = self.server.create_session()

    def tearDown(self) -> None:
        self.server.shutdown()


class TestBuildStatusPayloadNoPlayer(_NoCharacterTestBase):
    def test_returns_placeholder_payload(self):
        payload = self.server._build_status_payload(self.session.session_id)
        self.assertEqual("Unknown", payload["name"])
        self.assertFalse(payload["alive"])
        self.assertEqual([], payload["effects"])

    def test_includes_zeroed_mana_when_content_set_has_magic(self):
        payload = self.server._build_status_payload(self.session.session_id)
        self.assertIn("mana", payload)
        self.assertEqual({"current": 0, "max": 0}, payload["mana"])


class TestBuildStatusPayloadEffects(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True)
        self.session = self.server.create_session()
        self.server.execute_command(self.session.session_id, "char create Tester")
        self.player = self.server.get_player_for_session(self.session.session_id)

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_active_effect_dicts_are_rendered_by_name(self):
        from engine.magic.debug_effects import DEBUG_EFFECTS
        self.player.apply_effect(DEBUG_EFFECTS["debug_poison"], 0.0)
        payload = self.server._build_status_payload(self.session.session_id)
        self.assertEqual(["Debug Poison"], payload["effects"])

    def test_progression_fields_present_for_a_leveled_content_set(self):
        payload = self.server._build_status_payload(self.session.session_id)
        self.assertIn("level", payload)
        self.assertIn("experience", payload)


class TestIsInventoryCommand(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_recognizes_inventory_aliases(self):
        for text in ("inventory", "inv", "i", "  INVENTORY  "):
            self.assertTrue(self.server._is_inventory_command(text))

    def test_rejects_unrelated_commands(self):
        self.assertFalse(self.server._is_inventory_command("look"))


class TestBuildInventoryPayloadNoPlayer(_NoCharacterTestBase):
    def test_returns_empty_placeholder(self):
        payload = self.server._build_inventory_payload(self.session.session_id)
        self.assertEqual([], payload["items"])
        self.assertEqual(0, payload["slots_used"])


class TestIsQuestCommand(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_recognizes_quest_journal_aliases(self):
        for text in ("journal", "quests", "log", "j"):
            self.assertTrue(self.server._is_quest_command(text))

    def test_empty_text_is_not_a_quest_command(self):
        self.assertFalse(self.server._is_quest_command("   "))

    def test_unrelated_command_is_not_a_quest_command(self):
        self.assertFalse(self.server._is_quest_command("look"))


class TestBuildQuestsPayloadNoPlayer(_NoCharacterTestBase):
    def test_returns_empty_lists(self):
        payload = self.server._build_quests_payload(self.session.session_id)
        self.assertEqual({"active": [], "completed": [], "archived": []}, payload)


class TestQuestStateSignature(_NoCharacterTestBase):
    def test_none_player_returns_empty_tuples(self):
        self.assertEqual(((), (), ()), self.server._quest_state_signature(None))


class TestIsNearbyCommand(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_recognizes_explicit_nearby_aliases(self):
        for text in ("nearby", "scan", "who"):
            self.assertTrue(self.server._is_nearby_command(text))

    def test_recognizes_movement_and_look_commands(self):
        for text in ("look", "l", "go", "north", "n"):
            self.assertTrue(self.server._is_nearby_command(text))

    def test_empty_text_is_not_a_nearby_command(self):
        self.assertFalse(self.server._is_nearby_command("   "))

    def test_unrelated_command_is_not_a_nearby_command(self):
        self.assertFalse(self.server._is_nearby_command("inventory"))


class TestBuildNearbyPayload(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True)

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_explicit_nearby_alias_renders_observation_instead_of_unknown_command(self):
        session = self.server.create_session()
        self.server.execute_command(session.session_id, "char create NearbyHero")

        events = self.server.execute_command(session.session_id, "nearby")
        text = "\n".join(str(event["payload"]) for event in events if event["type"] == "text")

        self.assertIn("TOWN SQUARE", text)
        self.assertNotIn("Unknown command", text)
        self.assertTrue(any(event["type"] == "nearby" for event in events))
    def test_no_player_falls_back_to_world_cursor_and_finds_no_room(self):
        session = self.server.create_session()
        payload = self.server._build_nearby_payload(session.session_id)
        self.assertEqual("Unknown", payload["location"]["region_name"])
        self.assertEqual([], payload["npcs"])

    def test_unknown_room_returns_placeholder(self):
        session = self.server.create_session()
        self.server.execute_command(session.session_id, "char create RoomlessHero")
        player = self.server.get_player_for_session(session.session_id)
        player.current_region_id = "not_a_real_region"
        player.current_room_id = "not_a_real_room"
        payload = self.server._build_nearby_payload(session.session_id)
        self.assertEqual("", payload["location"]["region_id"])
        self.assertEqual("Unknown", payload["location"]["room_name"])


    def test_fixed_items_are_not_advertised_as_portable_or_take_actions(self):
        session = self.server.create_session()
        self.server.execute_command(session.session_id, "char create PuzzleHero")
        player = self.server.get_player_for_session(session.session_id)
        player.current_region_id = "obsidian_trial"
        player.current_room_id = "hall_of_gates"

        payload = self.server._build_nearby_payload(session.session_id)
        gate = next(item for item in payload["items"] if item["name"] == "massive obsidian gate")

        self.assertFalse(gate["portable"])
        self.assertNotIn("take massive obsidian gate", payload["interactions"])

class TestHeadlessRespawnCommand(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True)
        self.session = self.server.create_session()
        self.server.execute_command(self.session.session_id, "char create RespawnHero")
        self.player = self.server.get_player_for_session(self.session.session_id)

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_dead_player_can_respawn_through_the_server_command(self):
        self.player.current_region_id = "caves"
        self.player.current_room_id = "main_cavern"
        self.player.die(self.server.world)

        events = self.server.execute_command(self.session.session_id, "respawn")
        text = "\n".join(str(event["payload"]) for event in events if event["type"] == "text")

        self.assertTrue(self.player.is_alive)
        self.assertEqual("town", self.player.current_region_id)
        self.assertEqual("town_square", self.player.current_room_id)
        self.assertIn("spirit return", text)

    def test_living_player_is_not_relocated_by_respawn(self):
        events = self.server.execute_command(self.session.session_id, "respawn")
        text = "\n".join(str(event["payload"]) for event in events if event["type"] == "text")

        self.assertIn("already alive", text)
        self.assertEqual("town_square", self.player.current_room_id)

class TestHeadlessPersistenceBoundary(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True
        )
        self.session = self.server.create_session()
        self.server.execute_command(self.session.session_id, "char create PersistenceHero")

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_manual_save_is_not_allowed_to_serialize_the_shared_world(self):
        with patch.object(self.server.world, "save_game") as save_game:
            events = self.server.execute_command(self.session.session_id, "save alternate_world")

        text = "\n".join(str(event["payload"]) for event in events if event["type"] == "text")
        save_game.assert_not_called()
        self.assertIn("saved automatically", text)
        self.assertIn("shared world", text)

    def test_manual_load_is_not_allowed_to_replace_the_shared_world(self):
        with patch.object(self.server.world, "load_save_game") as load_save_game:
            events = self.server.execute_command(self.session.session_id, "load alternate_world")

        text = "\n".join(str(event["payload"]) for event in events if event["type"] == "text")
        load_save_game.assert_not_called()
        self.assertIn("saved automatically", text)
        self.assertIn("shared world", text)

class TestNormalizeQuestEntries(unittest.TestCase):

    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_non_dict_quest_map_returns_empty_list(self):
        self.assertEqual([], self.server._normalize_quest_entries("not-a-dict", include_states=None))

    def test_non_dict_entries_are_skipped(self):
        entries = self.server._normalize_quest_entries({"q1": "not-a-dict"}, include_states=None)
        self.assertEqual([], entries)

    def test_state_filter_excludes_non_matching_entries(self):
        quest_map = {
            "q1": {"title": "Active One", "state": "active"},
            "q2": {"title": "Abandoned One", "state": "abandoned"},
        }
        entries = self.server._normalize_quest_entries(quest_map, include_states={"active", "ready_to_complete"})
        self.assertEqual(["Active One"], [e["title"] for e in entries])

    def test_none_state_filter_includes_everything(self):
        quest_map = {"q1": {"title": "Any State", "state": "abandoned"}}
        entries = self.server._normalize_quest_entries(quest_map, include_states=None)
        self.assertEqual(["Any State"], [e["title"] for e in entries])


if __name__ == "__main__":
    unittest.main()
