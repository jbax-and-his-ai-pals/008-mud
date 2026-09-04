import unittest
from dataclasses import replace
from pathlib import Path
import time
from unittest.mock import patch

from engine.magic.spell_registry import get_spell
from engine.server.headless_server import HeadlessServer
from engine.player import Player
from engine.server.content_set import GameContract, load_content_set
from poc_server import JsonLineMudServer
from poc_ws_server import JsonWebSocketMudServer


REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"
MODERN_CAPSULE = REPO_ROOT / "content_sets" / "modern_capsule"


class TestContentSetRuntime(unittest.TestCase):
    def test_headless_server_requires_a_content_set(self) -> None:
        with self.assertRaisesRegex(ValueError, "content_set_path is required"):
            HeadlessServer(db_path=":memory:")

    def test_headless_server_boots_selected_content_set(self) -> None:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            self.assertIsNotNone(server.content_set)
            assert server.content_set is not None
            self.assertEqual("fantasy_frontier", server.content_set.content_set_id)
            self.assertEqual(FANTASY_FRONTIER / "data", Path(server.data_root))
            self.assertEqual(0, server.world.definition_load_stats["spell_registry"]["overwrites"])
            self.assertEqual(0, server.world.definition_load_stats["item_templates"]["invalid_missing_required"])
            self.assertEqual(1, server.world.definition_load_stats["item_templates"]["metadata_files_skipped"])
            session = server.create_session()
            server.execute_command(session.session_id, "char create ContentTester")
            player = server.get_player_for_session(session.session_id)
            self.assertEqual("town", player.current_region_id)
            self.assertEqual("town_square", player.current_room_id)
            self.assertEqual({"magic_missile", "minor_heal"}, player.runtime_state.magic.known_spells)
            self.assertEqual(1, player.inventory.count_item("item_starter_dagger"))
            self.assertEqual(2, player.inventory.count_item("item_healing_potion_small"))
        finally:
            server.shutdown()

    def test_conflicting_data_root_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "data_root conflicts"):
            HeadlessServer(
                db_path=":memory:",
                content_set_path=str(FANTASY_FRONTIER),
                data_root=str(REPO_ROOT / "server" / "data_fixtures"),
            )

    def test_fantasy_frontier_opening_journey(self) -> None:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="opening_journey_player")
            creation_events = server.execute_command(session.session_id, "char create Rowan")
            self.assertIn("Character created: Rowan", [event["payload"] for event in creation_events])
            self.assertIn("Welcome to Riverside", "\n".join(str(event["payload"]) for event in creation_events))
            self.assertIn("Elder Thorne", "\n".join(str(event["payload"]) for event in creation_events))

            look_events = server.execute_command(session.session_id, "look")
            self.assertIn("Town Square", "\n".join(str(event["payload"]) for event in look_events))

            nearby_events = server.execute_command(session.session_id, "nearby")
            self.assertIn("Elder Thorne", "\n".join(str(event["payload"]) for event in nearby_events))

            server.execute_command(session.session_id, "north")
            player = server.get_player_for_session(session.session_id)
            self.assertEqual("town", player.current_region_id)
            self.assertEqual("north_gate_road", player.current_room_id)
        finally:
            server.shutdown()

    def test_modern_capsule_is_a_playable_non_fantasy_slice(self) -> None:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(MODERN_CAPSULE),
            deterministic_test_mode=True,
        )
        try:
            self.assertIsNone(server.world.quest_manager)
            self.assertIsNone(server.world.campaign_manager)
            self.assertIsNone(server.crafting_manager)
            self.assertFalse(server.world.definition_load_stats["spell_registry"]["enabled"])

            session = server.create_session(player_id="modern_capsule_player")
            created = server.execute_command(session.session_id, "char create Avery")
            created_text = "\n".join(str(event["payload"]) for event in created)
            self.assertIn("A Connection Across Town", created_text)
            self.assertIn("Maya Chen", created_text)
            status_events = [event for event in created if event["type"] == "status"]
            self.assertEqual(1, len(status_events))
            self.assertNotIn("mana", status_events[0]["payload"])
            self.assertNotIn("level", status_events[0]["payload"])
            self.assertNotIn("experience", status_events[0]["payload"])
            player = server.get_player_for_session(session.session_id)
            self.assertIsNone(player.runtime_state.magic)
            self.assertIsNone(player.runtime_state.combat)
            self.assertIsNone(player.runtime_state.progression)
            self.assertIsNone(player.runtime_state.gold)
            self.assertIsNone(player.runtime_state.quests)
            self.assertEqual(0, player.inventory.get_total_weight())
            status_text = "\n".join(str(event["payload"]) for event in server.execute_command(session.session_id, "status"))
            self.assertNotIn("Attack:", status_text)
            self.assertNotIn("Defense:", status_text)
            self.assertNotIn("Class:", status_text)
            self.assertNotIn("Level:", status_text)
            self.assertNotIn("Stats:", status_text)
            self.assertNotIn("Gold:", status_text)
            help_text = "\n".join(str(event["payload"]) for event in server.execute_command(session.session_id, "help"))
            self.assertNotIn("skills", help_text)
            self.assertNotIn("trade", help_text)
            self.assertNotIn("journal", help_text)
            self.assertNotIn("accept quest", help_text)
            skills_events = server.execute_command(session.session_id, "skills")
            self.assertIn("does not include the 'progression' system", "\n".join(str(event["payload"]) for event in skills_events))
            combat_events = server.execute_command(session.session_id, "attack maya")
            self.assertIn("does not include the 'combat' system", "\n".join(str(event["payload"]) for event in combat_events))
            quest_events = server.execute_command(session.session_id, "accept quest 1")
            self.assertIn("does not include the 'quests' system", "\n".join(str(event["payload"]) for event in quest_events))

            conversation = server.execute_command(session.session_id, "talk maya")
            self.assertIn("Morning.", "\n".join(str(event["payload"]) for event in conversation))
            server.execute_command(session.session_id, "east")
            player = server.get_player_for_session(session.session_id)
            self.assertEqual("midtown", player.current_region_id)
            self.assertEqual("corner_cafe", player.current_room_id)
        finally:
            server.shutdown()

    def test_mixed_contracts_compose_only_their_declared_player_aspects(self) -> None:
        """Exercise optional systems independently rather than as a fantasy bundle."""
        modern_definition, modern_issues = load_content_set(MODERN_CAPSULE)
        fantasy_definition, fantasy_issues = load_content_set(FANTASY_FRONTIER)
        self.assertIsNotNone(modern_definition, modern_issues)
        self.assertIsNotNone(fantasy_definition, fantasy_issues)
        assert modern_definition is not None
        assert fantasy_definition is not None

        combat_contract = GameContract(
            progression_model="level_based",
            systems=tuple(sorted({
                "inventory": True, "dialogue": True, "combat": True, "magic": False,
                "crafting": False, "quests": False, "progression": True, "economy": False,
            }.items())),
            status_fields=("name", "health", "level", "experience"),
            ui_sections=("log", "nearby", "status", "inventory"),
        )
        combat_definition = replace(
            modern_definition,
            content_set_id="combat_without_magic",
            capabilities=("inventory", "dialogue", "combat"),
            game_contract=combat_contract,
        )
        with patch("engine.server.headless_server.load_content_set", return_value=(combat_definition, [])):
            combat_server = HeadlessServer(
                db_path=":memory:",
                content_set_path=str(MODERN_CAPSULE),
                deterministic_test_mode=True,
            )
        try:
            combat_session = combat_server.create_session(player_id="combat_only_player")
            combat_server.execute_command(combat_session.session_id, "char create Casey")
            combat_player = combat_server.get_player_for_session(combat_session.session_id)
            self.assertIsNotNone(combat_player.runtime_state.combat)
            self.assertIsNone(combat_player.runtime_state.magic)
            self.assertIsNotNone(combat_player.runtime_state.progression)
            self.assertIsNone(combat_player.runtime_state.gold)
            self.assertIsNone(combat_player.runtime_state.quests)
            combat_target = next(iter(combat_server.world.npcs.values()))
            combat_player.enter_combat(combat_target)
            self.assertTrue(combat_player.runtime_state.combat.in_combat)
            combat_player.exit_combat(combat_target)
            attack_result = combat_player.attack(combat_target, combat_server.world)
            self.assertIn("message", attack_result)
            leveled_up, _message = combat_player.gain_experience(1000)
            self.assertTrue(leveled_up)
            combat_player.die()
            self.assertFalse(combat_player.is_alive)
            combat_player.respawn()
            self.assertTrue(combat_player.is_alive)
            combat_server.execute_command(combat_session.session_id, "status")
            combat_server.tick(combat_session.session_id)
        finally:
            combat_server.shutdown()

        magic_contract = GameContract(
            progression_model="none",
            systems=tuple(sorted({
                "inventory": True, "dialogue": True, "combat": False, "magic": True,
                "crafting": False, "quests": False, "progression": False, "economy": False,
            }.items())),
            status_fields=("name", "health", "mana"),
            ui_sections=("log", "nearby", "status", "inventory"),
        )
        magic_definition = replace(
            fantasy_definition,
            content_set_id="magic_without_progression",
            capabilities=("inventory", "dialogue", "magic"),
            game_contract=magic_contract,
        )
        with patch("engine.server.headless_server.load_content_set", return_value=(magic_definition, [])):
            magic_server = HeadlessServer(
                db_path=":memory:",
                content_set_path=str(FANTASY_FRONTIER),
                deterministic_test_mode=True,
            )
        try:
            magic_session = magic_server.create_session(player_id="magic_only_player")
            magic_server.execute_command(magic_session.session_id, "char create Morgan")
            magic_player = magic_server.get_player_for_session(magic_session.session_id)
            self.assertIsNotNone(magic_player.runtime_state.magic)
            self.assertIsNone(magic_player.runtime_state.combat)
            self.assertIsNone(magic_player.runtime_state.progression)
            self.assertIsNone(magic_player.runtime_state.gold)
            self.assertIsNone(magic_player.runtime_state.quests)
            status_text = "\n".join(
                str(event["payload"])
                for event in magic_server.execute_command(magic_session.session_id, "status")
            )
            self.assertIn("Mana:", status_text)
            self.assertNotIn("Level:", status_text)
            minor_heal = get_spell("minor_heal")
            self.assertIsNotNone(minor_heal)
            cast_result = magic_player.cast_spell(minor_heal, magic_player, time.time(), magic_server.world)
            self.assertTrue(cast_result["success"])
            saved_player = magic_player.to_dict(magic_server.world)
            self.assertEqual({"magic"}, set(saved_player["gameplay"]))
            restored_player = Player.from_dict(saved_player, magic_server.world)
            self.assertIsNotNone(restored_player.runtime_state.magic)
            self.assertIsNone(restored_player.runtime_state.progression)
        finally:
            magic_server.shutdown()

    def test_tcp_effective_settings_identify_content_set(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=str(FANTASY_FRONTIER),
        )
        try:
            content_set = app.effective_settings()["content_set"]
            self.assertEqual("fantasy_frontier", content_set["id"])
            self.assertEqual("town_square", content_set["start"]["room_id"])
        finally:
            app.shutdown()

    def test_modern_policy_publishes_non_fantasy_game_contract(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=str(MODERN_CAPSULE),
        )
        try:
            contract = app.build_server_policy_payload()["content_set"]["game_contract"]
            self.assertFalse(contract["systems"]["magic"])
            self.assertFalse(contract["systems"]["combat"])
            self.assertFalse(contract["systems"]["progression"])
            self.assertNotIn("mana", contract["status_fields"])
            self.assertNotIn("quests", contract["ui_sections"])
            self.assertIn("inventory", contract["ui_sections"])
        finally:
            app.shutdown()

    def test_websocket_policy_identifies_content_set(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=str(FANTASY_FRONTIER),
        )
        try:
            content_set = app.core.build_server_policy_payload()["content_set"]
            self.assertEqual("fantasy_frontier", content_set["id"])
            self.assertEqual("town", content_set["start"]["region_id"])
        finally:
            app.shutdown()


if __name__ == "__main__":
    unittest.main()
