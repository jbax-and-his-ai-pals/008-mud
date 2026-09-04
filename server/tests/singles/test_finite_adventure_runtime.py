import unittest
from pathlib import Path

from engine.campaign.campaign_models import CampaignDefinition, CampaignNode, CampaignTransition
from engine.items.item_factory import ItemFactory
from engine.server.headless_server import HeadlessServer

FANTASY_FRONTIER = Path(__file__).resolve().parents[3] / "content_sets" / "fantasy_frontier"


class TestFiniteAdventureRuntime(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))
        self.server.feature_profile.world_mode = "finite_adventure"
        self.server.feature_profile.raw = {
            "finite_adventure": {
                "default_campaign_id": "intro_story",
                "replay_supported": True,
            }
        }
        self.session = self.server.create_session(player_id="hero_player")
        self.server.execute_command(self.session.session_id, "char create Hero")
        self.player = self.server.get_player_for_session(self.session.session_id)

        quest_template = {
            "title": "Intro Step",
            "type": "fetch",
            "stages": [
                {
                    "stage_index": 0,
                    "description": "Do the thing.",
                    "objective": {"type": "fetch", "item_id": "rock", "required_quantity": 1},
                    "turn_in_id": "quest_giver",
                }
            ],
            "rewards": {"xp": 10},
        }
        self.server.world.quest_manager.quest_templates["intro_quest"] = quest_template
        self.server.world.campaign_manager.definitions["intro_story"] = CampaignDefinition(
            campaign_id="intro_story",
            name="Intro Story",
            description="Finite-adventure baseline campaign.",
            start_node_id="node_intro",
            nodes={
                "node_intro": CampaignNode(
                    node_id="node_intro",
                    description="Start",
                    quest_template_id="intro_quest",
                    transitions=[CampaignTransition(trigger="SUCCESS", target_node_id="node_end")],
                ),
                "node_end": CampaignNode(
                    node_id="node_end",
                    description="Finish",
                    node_type="END",
                    outcome="VICTORY",
                ),
            },
        )

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_adventure_start_uses_default_campaign_and_sets_active_state(self) -> None:
        events = self.server.execute_command(self.session.session_id, "adventure start")
        text_payloads = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
        self.assertTrue(any("Finite adventure started: intro_story" in payload for payload in text_payloads))
        self.assertTrue(any(event.get("type") == "quests" for event in events))

        state = self.server.build_finite_adventure_state_payload(self.session.session_id)
        self.assertEqual("active", state["status"])
        self.assertEqual("intro_story", state["campaign_id"])
        self.assertEqual("node_intro", state["current_node"])
        self.assertTrue(any(qid.startswith("intro_quest") for qid in self.player.runtime_state.quests.active))

    def test_adventure_list_emits_catalog_payload(self) -> None:
        events = self.server.execute_command(self.session.session_id, "adventure list")
        text_payloads = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
        self.assertTrue(any("Finite adventure campaigns:" in payload for payload in text_payloads))

        catalog_events = [event for event in events if event.get("type") == "finite_adventure_catalog"]
        self.assertTrue(catalog_events)
        payload = catalog_events[-1]["payload"]
        self.assertTrue(payload["enabled"])
        self.assertEqual("intro_story", payload["default_campaign_id"])
        self.assertGreaterEqual(len(payload["campaigns"]), 1)
        intro_entries = [entry for entry in payload["campaigns"] if entry.get("campaign_id") == "intro_story"]
        self.assertTrue(intro_entries)
        first = intro_entries[0]
        self.assertEqual("Intro Story", first["name"])
        self.assertEqual("node_intro", first["start_node_id"])
        self.assertEqual(2, first["node_count"])
        self.assertTrue(first["is_default"])

    def test_adventure_completion_marks_completed_outcome(self) -> None:
        self.server.execute_command(self.session.session_id, "adventure start")
        quest_id = next(qid for qid in self.player.runtime_state.quests.active if qid.startswith("intro_quest"))

        result = self.server.world.quest_manager.complete_quest(self.player, quest_id, resolution="SUCCESS")

        self.assertIn("Rewards:", result)
        state = self.server.build_finite_adventure_state_payload(self.session.session_id)
        self.assertEqual("completed", state["status"])
        self.assertEqual("intro_story", state["campaign_id"])
        self.assertEqual("VICTORY", state["outcome"])
        self.assertEqual("node_end", state["current_node"])
        summary = self.server.build_finite_adventure_summary_payload(self.session.session_id)
        self.assertTrue(summary["available"])
        self.assertEqual("completed", summary["status"])
        self.assertEqual("VICTORY", summary["outcome"])
        self.assertEqual("node_end", summary["final_node"])
        self.assertEqual(1, summary["history_count"])
        self.assertEqual(1, summary["resolution_counts"]["SUCCESS"])
        self.assertEqual("Hero", summary["player_name"])
        self.assertEqual(1, summary["player_level"])
        self.assertEqual("finite_adventure", summary["world_mode"])

    def test_adventure_checkpoint_and_restore_round_trip(self) -> None:
        self.server.execute_command(self.session.session_id, "adventure start")
        self.player.runtime_state.gold = 17
        self.player.health = max(1, self.player.max_health - 9)

        checkpoint_events = self.server.execute_command(self.session.session_id, "adventure checkpoint")
        checkpoint_text = [str(event.get("payload", "")) for event in checkpoint_events if event.get("type") == "text"]
        self.assertTrue(any("checkpoint saved" in payload.lower() for payload in checkpoint_text))

        self.player.runtime_state.gold = 99
        self.player.health = 1
        self.player.current_room_id = "north_gate"

        restore_events = self.server.execute_command(self.session.session_id, "adventure restore")
        restore_text = [str(event.get("payload", "")) for event in restore_events if event.get("type") == "text"]
        self.assertTrue(any("restored from checkpoint" in payload.lower() for payload in restore_text))

        state = self.server.build_finite_adventure_state_payload(self.session.session_id)
        self.assertEqual("active", state["status"])
        self.assertTrue(state["checkpoint_available"])
        self.assertEqual("node_intro", state["checkpoint_node"])
        self.assertEqual(17, self.player.runtime_state.gold)
        self.assertEqual(self.player.max_health - 9, self.player.health)
        self.assertEqual("town_square", self.player.current_room_id)

    def test_adventure_restore_after_completion_reactivates_checkpointed_run(self) -> None:
        self.server.execute_command(self.session.session_id, "adventure start")
        self.server.execute_command(self.session.session_id, "adventure checkpoint")
        quest_id = next(qid for qid in self.player.runtime_state.quests.active if qid.startswith("intro_quest"))
        self.server.world.quest_manager.complete_quest(self.player, quest_id, resolution="SUCCESS")

        restore_events = self.server.execute_command(self.session.session_id, "adventure restore")
        restore_text = [str(event.get("payload", "")) for event in restore_events if event.get("type") == "text"]
        self.assertTrue(any("restored from checkpoint" in payload.lower() for payload in restore_text))
        self.assertTrue(any(event.get("type") == "quests" for event in restore_events))

        state = self.server.build_finite_adventure_state_payload(self.session.session_id)
        self.assertEqual("active", state["status"])
        self.assertEqual("intro_story", state["campaign_id"])
        self.assertEqual("node_intro", state["current_node"])
        self.assertIn("intro_story", self.player.runtime_state.quests.active_campaigns)
        self.assertNotIn("intro_story", self.player.runtime_state.quests.completed_campaigns)

    def test_adventure_abandon_clears_active_run(self) -> None:
        self.server.execute_command(self.session.session_id, "adventure start")

        events = self.server.execute_command(self.session.session_id, "adventure abandon")
        text_payloads = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
        self.assertTrue(any("Finite adventure abandoned: intro_story" in payload for payload in text_payloads))
        quest_events = [event for event in events if event.get("type") == "quests"]
        self.assertTrue(quest_events)
        self.assertEqual([], quest_events[-1]["payload"]["active"])

        state = self.server.build_finite_adventure_state_payload(self.session.session_id)
        self.assertEqual("abandoned", state["status"])
        self.assertEqual("ABANDON", state["outcome"])
        self.assertTrue(state["last_summary_available"])
        self.assertFalse(self.player.runtime_state.quests.active)
        self.assertFalse(self.player.runtime_state.quests.active_campaigns)
        summary = self.server.build_finite_adventure_summary_payload(self.session.session_id)
        self.assertTrue(summary["available"])
        self.assertEqual("abandoned", summary["status"])
        self.assertEqual("ABANDON", summary["outcome"])

    def test_adventure_reset_and_replay_restore_not_started_then_active(self) -> None:
        self.server.execute_command(self.session.session_id, "adventure start")
        self.server.execute_command(self.session.session_id, "adventure checkpoint")
        quest_id = next(qid for qid in self.player.runtime_state.quests.active if qid.startswith("intro_quest"))
        self.server.world.quest_manager.complete_quest(self.player, quest_id, resolution="SUCCESS")

        reset_events = self.server.execute_command(self.session.session_id, "adventure reset")
        reset_text = [str(event.get("payload", "")) for event in reset_events if event.get("type") == "text"]
        self.assertTrue(any("Finite adventure reset: intro_story" in payload for payload in reset_text))
        reset_quest_events = [event for event in reset_events if event.get("type") == "quests"]
        self.assertTrue(reset_quest_events)
        self.assertEqual([], reset_quest_events[-1]["payload"]["active"])
        reset_state = self.server.build_finite_adventure_state_payload(self.session.session_id)
        self.assertEqual("not_started", reset_state["status"])
        self.assertFalse(reset_state["checkpoint_available"])
        self.assertTrue(reset_state["last_summary_available"])
        self.assertFalse(self.player.runtime_state.quests.active)
        self.assertFalse(self.player.runtime_state.quests.completed_campaigns)

        replay_events = self.server.execute_command(self.session.session_id, "adventure replay")
        replay_text = [str(event.get("payload", "")) for event in replay_events if event.get("type") == "text"]
        self.assertTrue(any("Finite adventure started: intro_story" in payload for payload in replay_text))
        replay_quest_events = [event for event in replay_events if event.get("type") == "quests"]
        self.assertTrue(replay_quest_events)
        self.assertTrue(replay_quest_events[-1]["payload"]["active"])
        replay_state = self.server.build_finite_adventure_state_payload(self.session.session_id)
        self.assertEqual("active", replay_state["status"])
        self.assertEqual("intro_story", replay_state["campaign_id"])
        self.assertTrue(replay_state["last_summary_available"])

    def test_reset_restores_bounded_world_baseline(self) -> None:
        self.server.execute_command(self.session.session_id, "adventure start")
        baseline_count = len(self.server.world.get_items_in_room("town", "town_square"))
        potion = ItemFactory.create_item_from_template("item_healing_potion_small", self.server.world)
        self.assertIsNotNone(potion)
        if potion is not None:
            self.server.world.add_item_to_room("town", "town_square", potion)
        self.server.world.quest_board.append({"title": "Mutation"})

        self.server.execute_command(self.session.session_id, "adventure abandon")
        self.server.execute_command(self.session.session_id, "adventure reset")

        room_items = self.server.world.get_items_in_room("town", "town_square")
        self.assertEqual(baseline_count, len(room_items))
        self.assertFalse(any(entry.get("title") == "Mutation" for entry in self.server.world.quest_board if isinstance(entry, dict)))

    def test_replay_restores_bounded_world_baseline_before_restarting(self) -> None:
        self.server.execute_command(self.session.session_id, "adventure start")
        baseline_count = len(self.server.world.get_items_in_room("town", "town_square"))
        potion = ItemFactory.create_item_from_template("item_healing_potion_small", self.server.world)
        self.assertIsNotNone(potion)
        if potion is not None:
            self.server.world.add_item_to_room("town", "town_square", potion)

        self.server.execute_command(self.session.session_id, "adventure abandon")
        self.server.execute_command(self.session.session_id, "adventure replay")

        room_items = self.server.world.get_items_in_room("town", "town_square")
        self.assertEqual(baseline_count, len(room_items))
        replay_state = self.server.build_finite_adventure_state_payload(self.session.session_id)
        self.assertEqual("active", replay_state["status"])

    def test_reset_restores_room_region_time_and_weather_state(self) -> None:
        self.server.execute_command(self.session.session_id, "adventure start")

        town_region = self.server.world.regions["town"]
        town_square = town_region.get_room("town_square")
        self.assertIsNotNone(town_square)
        if town_square is None:
            self.fail("Expected town_square room")

        baseline_region_properties = dict(town_region.properties)
        baseline_room_properties = dict(town_square.properties)
        baseline_visited = bool(town_square.visited)
        baseline_game_time = self.server.time_manager.game_time
        baseline_weather = self.server.weather_manager.current_weather
        baseline_intensity = self.server.weather_manager.current_intensity

        town_region.properties["finite_adventure_marker"] = "mutated"
        town_square.visited = not baseline_visited
        town_square.properties["finite_adventure_marker"] = "mutated"
        town_square.update_property("visited", town_square.visited)
        town_square.update_property("finite_adventure_marker", "mutated")
        self.server.time_manager.initialize_time(game_time=baseline_game_time + 43210.0)
        self.server.weather_manager.current_weather = "storm"
        self.server.weather_manager.current_intensity = "severe"

        self.server.execute_command(self.session.session_id, "adventure abandon")
        self.server.execute_command(self.session.session_id, "adventure reset")

        restored_region = self.server.world.regions["town"]
        restored_room = restored_region.get_room("town_square")
        self.assertIsNotNone(restored_room)
        if restored_room is None:
            self.fail("Expected restored town_square room")

        self.assertEqual(baseline_region_properties, restored_region.properties)
        self.assertEqual(baseline_room_properties, restored_room.properties)
        self.assertEqual(baseline_visited, restored_room.visited)
        self.assertEqual(baseline_game_time, self.server.time_manager.game_time)
        self.assertEqual(baseline_weather, self.server.weather_manager.current_weather)
        self.assertEqual(baseline_intensity, self.server.weather_manager.current_intensity)

    def test_reset_restores_field_state_and_clears_runtime_residue(self) -> None:
        self.server.execute_command(self.session.session_id, "adventure start")

        room = self.server.world.regions["town"].get_room("town_square")
        self.assertIsNotNone(room)
        if room is None:
            self.fail("Expected town_square room")

        baseline_fields = {field_id: heartbeat.snapshot() for field_id, heartbeat in self.server.fields.items()}
        baseline_default_field_id = self.server.default_field_id
        baseline_default_field_polarity = self.server.default_field_polarity

        room.active_env_effects = [{"action": "suppress_hazard", "original_value": "poison", "time_remaining": 5.0}]
        room._hazard_last_tick_by_entity["hero_player"] = 123.0
        self.player.active_effects = [{"name": "Burning", "duration_remaining": 7.0}]
        self.player.runtime_state.magic.cooldowns = {"test_spell": 42.0}
        self.player.runtime_state.magic.summons = {"spell_test": ["summon_1"]}
        self.player.active_minigame = {"type": "cards"}
        self.player.trading_with = "merchant_1"
        self.player.follow_target = "guide_1"
        self.player.last_talked_to = "elder_1"
        self.player.combat_messages = ["still fighting"]

        sanctity = self.server._ensure_field("sanctity")
        sanctity.seed_cell(1, 1, 0.75)
        sanctity.tick_index = 9
        self.server.default_field_id = "sanctity"
        self.server.default_field_polarity = "positive"

        self.server.execute_command(self.session.session_id, "adventure abandon")
        self.server.execute_command(self.session.session_id, "adventure reset")

        restored_room = self.server.world.regions["town"].get_room("town_square")
        self.assertIsNotNone(restored_room)
        if restored_room is None:
            self.fail("Expected restored town_square room")

        self.assertEqual([], restored_room.active_env_effects)
        self.assertEqual({}, restored_room._hazard_last_tick_by_entity)
        self.assertEqual([], self.player.active_effects)
        self.assertEqual({}, self.player.runtime_state.magic.cooldowns)
        self.assertEqual({}, self.player.runtime_state.magic.summons)
        self.assertIsNone(self.player.active_minigame)
        self.assertIsNone(self.player.trading_with)
        self.assertIsNone(self.player.follow_target)
        self.assertIsNone(self.player.last_talked_to)
        self.assertEqual([], self.player.combat_messages)

        restored_fields = {field_id: heartbeat.snapshot() for field_id, heartbeat in self.server.fields.items()}
        self.assertEqual(baseline_fields, restored_fields)
        self.assertEqual(baseline_default_field_id, self.server.default_field_id)
        self.assertEqual(baseline_default_field_polarity, self.server.default_field_polarity)

    def test_adventure_summary_command_emits_summary_payload(self) -> None:
        self.server.execute_command(self.session.session_id, "adventure start")
        quest_id = next(qid for qid in self.player.runtime_state.quests.active if qid.startswith("intro_quest"))
        self.server.world.quest_manager.complete_quest(self.player, quest_id, resolution="SUCCESS")

        events = self.server.execute_command(self.session.session_id, "adventure summary")
        summary_events = [event for event in events if event.get("type") == "finite_adventure_summary"]
        self.assertTrue(summary_events)
        payload = summary_events[-1]["payload"]
        self.assertTrue(payload["available"])
        self.assertEqual("completed", payload["status"])
        self.assertEqual("VICTORY", payload["outcome"])

    def test_adventure_summary_markdown_emits_report_payload(self) -> None:
        self.server.execute_command(self.session.session_id, "adventure start")
        quest_id = next(qid for qid in self.player.runtime_state.quests.active if qid.startswith("intro_quest"))
        self.server.world.quest_manager.complete_quest(self.player, quest_id, resolution="SUCCESS")

        events = self.server.execute_command(self.session.session_id, "adventure summary markdown")
        report_events = [event for event in events if event.get("type") == "finite_adventure_report"]
        self.assertTrue(report_events)
        payload = report_events[-1]["payload"]
        self.assertTrue(payload["available"])
        self.assertEqual("markdown", payload["format"])
        self.assertTrue(str(payload["file_name_hint"]).endswith(".md"))
        self.assertIn("# Adventure Summary:", str(payload["content"]))
        self.assertIn("Hero", str(payload["content"]))

    def test_adventure_summary_json_emits_report_payload(self) -> None:
        self.server.execute_command(self.session.session_id, "adventure start")
        quest_id = next(qid for qid in self.player.runtime_state.quests.active if qid.startswith("intro_quest"))
        self.server.world.quest_manager.complete_quest(self.player, quest_id, resolution="SUCCESS")

        events = self.server.execute_command(self.session.session_id, "adventure summary json")
        report_events = [event for event in events if event.get("type") == "finite_adventure_report"]
        self.assertTrue(report_events)
        payload = report_events[-1]["payload"]
        self.assertTrue(payload["available"])
        self.assertEqual("json", payload["format"])
        self.assertTrue(str(payload["file_name_hint"]).endswith(".json"))
        self.assertIn("\"campaign_id\": \"intro_story\"", str(payload["content"]))

    def test_checkpoint_restore_respects_disabled_policy(self) -> None:
        self.server.feature_profile.raw["finite_adventure"]["checkpoint_policy"] = "disabled"
        self.server.execute_command(self.session.session_id, "adventure start")

        checkpoint_events = self.server.execute_command(self.session.session_id, "adventure checkpoint")
        checkpoint_text = [str(event.get("payload", "")) for event in checkpoint_events if event.get("type") == "text"]
        self.assertTrue(any("disabled" in payload.lower() for payload in checkpoint_text))

        restore_events = self.server.execute_command(self.session.session_id, "adventure restore")
        restore_text = [str(event.get("payload", "")) for event in restore_events if event.get("type") == "text"]
        self.assertTrue(any("disabled" in payload.lower() for payload in restore_text))

    def test_adventure_status_text_before_any_run(self) -> None:
        events = self.server.execute_command(self.session.session_id, "adventure status")
        texts = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
        self.assertTrue(any("No finite adventure run started. Default campaign: intro_story." in t for t in texts))

    def test_adventure_status_text_while_active(self) -> None:
        self.server.execute_command(self.session.session_id, "adventure start")
        events = self.server.execute_command(self.session.session_id, "adventure status")
        texts = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
        self.assertTrue(any(t.startswith("Adventure active: intro_story at node") for t in texts))

    def test_adventure_status_text_after_completion(self) -> None:
        self.server.execute_command(self.session.session_id, "adventure start")
        quest_id = next(qid for qid in self.player.runtime_state.quests.active if qid.startswith("intro_quest"))
        self.server.world.quest_manager.complete_quest(self.player, quest_id, resolution="SUCCESS")
        events = self.server.execute_command(self.session.session_id, "adventure status")
        texts = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
        self.assertTrue(any("Adventure complete: intro_story ended with outcome 'VICTORY'." in t for t in texts))

    def test_adventure_status_text_after_abandon(self) -> None:
        self.server.execute_command(self.session.session_id, "adventure start")
        self.server.execute_command(self.session.session_id, "adventure abandon")
        events = self.server.execute_command(self.session.session_id, "adventure status")
        texts = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
        self.assertTrue(any("Adventure abandoned: intro_story." in t for t in texts))

    def test_adventure_summary_text_before_any_run(self) -> None:
        events = self.server.execute_command(self.session.session_id, "adventure summary")
        texts = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
        self.assertTrue(any(t.startswith("Last adventure summary:") for t in texts))

    def test_finite_adventure_blocks_secondary_session_commands(self) -> None:
        primary = self.session
        secondary = self.server.create_session(player_id="sidekick_player")
        self.server.execute_command(primary.session_id, "look")
        self.server.execute_command(secondary.session_id, "char create Sidekick")

        blocked = self.server.execute_command(secondary.session_id, "look")
        payloads = [str(event.get("payload", "")) for event in blocked if event.get("type") == "text"]
        self.assertTrue(any("finite_adventure" in payload for payload in payloads))


if __name__ == "__main__":
    unittest.main()
