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


class TestCraftingLedgerPayload(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True)
        self.session = self.server.create_session()
        self.server.execute_command(self.session.session_id, "char create Crafter")

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_recipes_command_emits_structured_ledger_with_material_counts(self):
        events = self.server.execute_command(self.session.session_id, "recipes")
        ledger = next(event["payload"] for event in events if event["type"] == "crafting")
        recipe = next(entry for entry in ledger["recipes"] if entry["recipe_id"] == "stitch_leather_cap")
        self.assertEqual("handcraft", recipe["station"])
        self.assertEqual("item_leather_cap", recipe["result"]["item_id"])
        self.assertEqual("item_leather_strip", recipe["ingredients"][0]["item_id"])
        self.assertEqual(0, recipe["craft_count"])
        self.assertEqual("Unpracticed", recipe["familiarity_label"])
        self.assertEqual(0, recipe["material_quality_score"])


class TestCollectionsLedgerPayload(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True)
        self.session = self.server.create_session()
        self.server.execute_command(self.session.session_id, "char create Collector")

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_turnin_emits_structured_collection_progress(self):
        events = self.server.execute_command(self.session.session_id, "turnin")
        ledger = next(event["payload"] for event in events if event["type"] == "collections")
        gem_ledger = next(entry for entry in ledger["collections"] if entry["collection_id"] == "riverside_gem_ledger")
        self.assertFalse(gem_ledger["discovered"])
        self.assertEqual(44, gem_ledger["required_count"])
        rose_quartz = next(item for item in gem_ledger["items"] if item["item_id"] == "item_rose_quartz")
        self.assertEqual("rose quartz", rose_quartz["name"])


class TestDiscoveriesLedgerPayload(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True)
        self.session = self.server.create_session()
        self.server.execute_command(self.session.session_id, "char create Researcher")

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_discovery_command_emits_only_unlocked_structured_entries(self):
        empty = self.server.execute_command(self.session.session_id, "discoveries")
        initial = next(event["payload"] for event in empty if event["type"] == "discoveries")
        self.assertEqual([], initial["discoveries"])
        self.assertEqual(4, initial["total_authored"])

        player = self.server.get_player_for_session(self.session.session_id)
        from engine.items.item_factory import ItemFactory
        item = ItemFactory.create_item_from_template("item_rose_quartz", self.server.world)
        self.assertIsNotNone(item)
        player.inventory.add_item(item)
        note = self.server.discovery_manager.handle_item_discovery(player, item)
        self.assertIn("New discovery", note)

        events = self.server.execute_command(self.session.session_id, "discoveries")
        payload = next(event["payload"] for event in events if event["type"] == "discoveries")
        self.assertEqual({"fieldcraft_basics", "rose_quartz"}, {entry["discovery_id"] for entry in payload["discoveries"]})

        from engine.player import Player
        restored = Player.from_dict(player.to_dict(self.server.world), self.server.world)
        self.assertEqual(set(player.discoveries), set(restored.discoveries))


class TestRelationshipsPayload(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True)
        self.session = self.server.create_session()
        self.server.execute_command(self.session.session_id, "char create SocialTester")

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_relationship_ledger_emits_structured_scores_and_milestones(self):
        player = self.server.get_player_for_session(self.session.session_id)
        player.npc_relationships["curator"] = 9
        events = self.server.execute_command(self.session.session_id, "relationships")
        payload = next(event["payload"] for event in events if event["type"] == "relationships")
        curator = next(entry for entry in payload["relationships"] if entry["npc_id"] == "curator")
        self.assertEqual("Curator Vane", curator["name"])
        self.assertEqual(10, curator["next_milestone"])


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

    def test_kill_objective_exposes_a_ui_ready_progress_summary(self):
        entries = self.server._normalize_quest_entries(
            {
                "q1": {
                    "title": "Rat Trouble",
                    "state": "active",
                    "current_stage_index": 0,
                    "stages": [{
                        "type": "kill",
                        "target_name_plural": "giant rats",
                        "current_quantity": 1,
                        "required_quantity": 3,
                        "location_hint": "the old sewer",
                    }],
                }
            },
            include_states={"active"},
        )
        objective = entries[0]["objective"]
        self.assertEqual("kill", objective["kind"])
        self.assertEqual("Defeat giant rats.", objective["summary"])
        self.assertEqual(1, objective["progress_current"])
        self.assertEqual(3, objective["progress_required"])
        self.assertEqual("the old sewer", objective["location_hint"])


class TestCombatPayload(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True)
        self.session = self.server.create_session()
        self.server.execute_command(self.session.session_id, "char create EncounterHero")
        self.player = self.server.get_player_for_session(self.session.session_id)

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_attack_emits_live_combat_and_status_payloads(self):
        from engine.npcs.npc import NPC

        target = NPC(obj_id="feedback_goblin", name="Feedback Goblin", description="A test foe.", friendly=False)
        target.faction = "hostile"
        target.max_health = 50
        target.health = 50
        target.current_region_id = self.player.current_region_id
        target.current_room_id = self.player.current_room_id
        self.server.world.add_npc(target)

        events = self.server.execute_command(self.session.session_id, "attack feedback goblin")
        combat = next(event["payload"] for event in events if event["type"] == "combat")
        self.assertTrue(any(event["type"] == "status" for event in events))
        self.assertTrue(combat["active"])
        self.assertEqual("Feedback Goblin", combat["targets"][0]["name"])
        self.assertIn("attack Feedback Goblin", combat["suggested_actions"])


if __name__ == "__main__":
    unittest.main()
