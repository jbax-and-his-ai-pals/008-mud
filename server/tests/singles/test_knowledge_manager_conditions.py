# tests/singles/test_knowledge_manager_conditions.py
"""Coverage for engine/core/knowledge_manager.py's condition matching,
topic listing, reward bundling, and dialogue-effect branches that the
existing knowledge/dialogue test files don't reach: region/faction/
template_id conditions, all three knowledge_state sub-cases, campaign_state
sub-cases, quest_state's from_this/pattern continues, get_topics_for_npc,
item/generated-item local reward bundling, and the start_quest/start_campaign/
give_item dialogue effects."""

from unittest.mock import MagicMock, patch

from tests.fixtures import GameTestBase
from engine.core.knowledge_manager import KnowledgeManager
from engine.npcs.npc_factory import NPCFactory


def _villager(world):
    if "villager" not in world.npc_templates:
        world.npc_templates["villager"] = {
            "name": "Villager", "description": "Normal.", "faction": "neutral",
        }
    npc = NPCFactory.create_npc_from_template("villager", world)
    world.add_npc(npc)
    return npc


class TestConstructorAndWarnings(GameTestBase):
    def test_mismatched_data_root_raises(self):
        with self.assertRaises(ValueError):
            KnowledgeManager(self.world, data_root="/not/the/real/root")

    def test_matching_data_root_is_accepted(self):
        km = KnowledgeManager(self.world, data_root=self.world.data_root)
        self.assertIsInstance(km.topics, dict)

    def test_emit_warning_without_sink_prints(self):
        km = self.game.knowledge_manager
        with patch("builtins.print") as mock_print:
            km._emit_warning("some.code", "a warning message")
            mock_print.assert_called_once_with("a warning message")

    def test_emit_warning_with_sink_calls_sink(self):
        sink = MagicMock()
        km = KnowledgeManager(self.world, warning_sink=sink)
        km._emit_warning("some.code", "a warning message")
        sink.assert_called_once_with("some.code", "a warning message", "content")


class TestResolveTopicIdAndCustomDialogue(GameTestBase):
    def test_no_match_returns_none(self):
        km = self.game.knowledge_manager
        km.topics["only_topic"] = {"display_name": "Only Topic", "keywords": ["kw"]}
        self.assertIsNone(km.resolve_topic_id("totally unrelated phrase"))

    def test_partial_startswith_match_returns_topic_id(self):
        km = self.game.knowledge_manager
        km.topics["prefix_topic"] = {"display_name": "Prefixed Display Name", "keywords": []}
        self.assertEqual("prefix_topic", km.resolve_topic_id("prefixed"))

    def test_custom_dialog_override_short_circuits_topic_lookup(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        npc.properties["custom_dialog"] = {"greeting": "Custom hello!"}
        result = km.get_response(npc, "greeting", self.player)
        self.assertEqual("Custom hello!", result)

    def test_unknown_topic_returns_none(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        self.assertIsNone(km.get_response(npc, "no_such_topic", self.player))

    def test_topic_with_no_matching_conditions_returns_none(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        km.topics["gated_topic"] = {
            "display_name": "Gated",
            "responses": [{"text": "secret", "conditions": {"faction": "impossible_faction"}}],
        }
        self.assertIsNone(km.get_response(npc, "gated_topic", self.player))


class TestCheckConditions(GameTestBase):
    def setUp(self):
        super().setUp()
        self.km = self.game.knowledge_manager
        self.npc = _villager(self.world)

    def test_region_id_condition_true_and_false(self):
        self.npc.current_region_id = self.player.current_region_id
        self.assertTrue(self.km._check_conditions(self.npc, self.player, {"region_id": self.npc.current_region_id}))
        self.assertFalse(self.km._check_conditions(self.npc, self.player, {"region_id": "somewhere_else"}))

    def test_faction_condition_true_and_false(self):
        self.assertTrue(self.km._check_conditions(self.npc, self.player, {"faction": self.npc.faction}))
        self.assertFalse(self.km._check_conditions(self.npc, self.player, {"faction": "definitely_not_it"}))

    def test_template_id_condition_true_and_false(self):
        self.assertTrue(self.km._check_conditions(self.npc, self.player, {"template_id": self.npc.template_id}))
        self.assertFalse(self.km._check_conditions(self.npc, self.player, {"template_id": "not_a_real_template"}))

    def test_knowledge_state_known(self):
        cond = {"knowledge_state": {"topic_id": "topicA", "state": "known"}}
        self.assertFalse(self.km._check_conditions(self.npc, self.player, cond))
        self.player.conversation.learn_vocabulary("topicA")
        self.assertTrue(self.km._check_conditions(self.npc, self.player, cond))

    def test_knowledge_state_discussed(self):
        cond = {"knowledge_state": {"topic_id": "topicB", "state": "discussed"}}
        self.assertFalse(self.km._check_conditions(self.npc, self.player, cond))
        self.player.conversation.mark_discussed(self.npc.obj_id, "topicB")
        self.assertTrue(self.km._check_conditions(self.npc, self.player, cond))

    def test_knowledge_state_revealed(self):
        cond = {"knowledge_state": {"topic_id": "topicC", "state": "revealed"}}
        self.assertFalse(self.km._check_conditions(self.npc, self.player, cond))
        self.player.conversation.reveal_topic(self.npc.obj_id, "topicC")
        self.assertTrue(self.km._check_conditions(self.npc, self.player, cond))

    def test_campaign_state_active(self):
        cond = {"campaign_state": {"campaign_id": "campX", "state": "active"}}
        self.assertFalse(self.km._check_conditions(self.npc, self.player, cond))
        self.player.runtime_state.quests.active_campaigns["campX"] = {}
        self.assertTrue(self.km._check_conditions(self.npc, self.player, cond))

    def test_campaign_state_completed(self):
        cond = {"campaign_state": {"campaign_id": "campY", "state": "completed"}}
        self.assertFalse(self.km._check_conditions(self.npc, self.player, cond))
        self.player.runtime_state.quests.completed_campaigns["campY"] = {}
        self.assertTrue(self.km._check_conditions(self.npc, self.player, cond))

    def test_campaign_state_not_active(self):
        cond = {"campaign_state": {"campaign_id": "campZ", "state": "not_active"}}
        self.assertTrue(self.km._check_conditions(self.npc, self.player, cond))
        self.player.runtime_state.quests.active_campaigns["campZ"] = {}
        self.assertFalse(self.km._check_conditions(self.npc, self.player, cond))

    def test_quest_state_active_with_from_this_and_pattern(self):
        self.player.runtime_state.quests.active["quest_other_npc"] = {
            "state": "active", "giver_instance_id": "some_other_npc",
        }
        self.player.runtime_state.quests.active["quest_match_pattern"] = {
            "state": "active", "giver_instance_id": self.npc.obj_id,
        }
        cond = {"quest_state": {"state": "active", "from_this_npc": True, "id_pattern": "match_pattern"}}
        self.assertTrue(self.km._check_conditions(self.npc, self.player, cond))

    def test_quest_state_active_from_this_excludes_other_givers(self):
        self.player.runtime_state.quests.active["quest_x"] = {
            "state": "active", "giver_instance_id": "some_other_npc",
        }
        cond = {"quest_state": {"state": "active", "from_this_npc": True}}
        self.assertFalse(self.km._check_conditions(self.npc, self.player, cond))

    def test_quest_state_active_pattern_mismatch_continues(self):
        self.player.runtime_state.quests.active["quest_x"] = {"state": "active"}
        cond = {"quest_state": {"state": "active", "id_pattern": "no_match_here"}}
        self.assertFalse(self.km._check_conditions(self.npc, self.player, cond))

    def test_quest_state_active_wrong_sub_state_continues(self):
        self.player.runtime_state.quests.active["quest_x"] = {"state": "not_ready"}
        cond = {"quest_state": {"state": "active"}}
        self.assertFalse(self.km._check_conditions(self.npc, self.player, cond))

    def test_quest_state_unrecognized_state_yields_no_logs(self):
        cond = {"quest_state": {"state": "some_unknown_state"}}
        self.assertFalse(self.km._check_conditions(self.npc, self.player, cond))

    def test_knowledge_state_unrecognized_state_is_ignored(self):
        cond = {"knowledge_state": {"topic_id": "topicD", "state": "some_unknown_state"}}
        self.assertTrue(self.km._check_conditions(self.npc, self.player, cond))


class TestParseAndHighlight(GameTestBase):
    def test_empty_text_returns_empty_string(self):
        km = self.game.knowledge_manager
        self.assertEqual("", km.parse_and_highlight("", self.player))

    def test_short_keyword_is_skipped(self):
        km = self.game.knowledge_manager
        km.topics["short_kw_topic"] = {"display_name": "Short", "keywords": ["ok"]}
        # "ok" is < 3 chars, so it must be skipped without raising or highlighting.
        result = km.parse_and_highlight("that seems ok to me", self.player)
        self.assertNotIn("[[CMD:", result)


class TestGetTopicsForNpc(GameTestBase):
    def test_splits_asked_and_unasked_and_sorts_by_display_name(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        km.topics["job"] = {"display_name": "Job", "responses": [{"text": "x", "conditions": {}}]}
        km.topics["rumors"] = {"display_name": "Rumors", "responses": [{"text": "y", "conditions": {}}]}
        self.player.conversation.mark_discussed(npc.obj_id, "job")

        unasked, asked = km.get_topics_for_npc(npc, self.player)
        self.assertEqual(["rumors"], unasked)
        self.assertEqual(["job"], asked)

    def test_revealed_npc_specific_topics_are_included(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        km.topics["secret_lore"] = {"display_name": "Secret Lore", "responses": [{"text": "z", "conditions": {}}]}
        self.player.conversation.reveal_topic(npc.obj_id, "secret_lore")

        unasked, asked = km.get_topics_for_npc(npc, self.player)
        self.assertIn("secret_lore", unasked)

    def test_common_topic_absent_from_topics_db_is_skipped(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        # "job" is a default common_topic but intentionally has no entry in km.topics.
        km.topics.pop("job", None)
        km.topics["rumors"] = {"display_name": "Rumors", "responses": [{"text": "y", "conditions": {}}]}
        unasked, asked = km.get_topics_for_npc(npc, self.player)
        self.assertEqual(["rumors"], unasked)

    def test_topic_with_no_valid_response_is_excluded(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        km.topics["job"] = {
            "display_name": "Job",
            "responses": [{"text": "x", "conditions": {"faction": "impossible"}}],
        }
        unasked, asked = km.get_topics_for_npc(npc, self.player)
        self.assertNotIn("job", unasked)
        self.assertNotIn("job", asked)


class TestLocalRewardBundleItems(GameTestBase):
    def test_item_rewards_are_added_to_inventory(self):
        km = self.game.knowledge_manager
        messages = km._apply_local_reward_bundle(
            self.player, {"items": [{"item_id": "item_starter_dagger", "quantity": 2}]}
        )
        self.assertEqual(2, len(messages))

    def test_item_rewards_skip_blank_id_and_negative_quantity(self):
        km = self.game.knowledge_manager
        messages = km._apply_local_reward_bundle(
            self.player,
            {"items": [{"item_id": "", "quantity": 1}, {"item_id": "item_starter_dagger", "quantity": -1}]},
        )
        self.assertEqual([], messages)

    def test_item_rewards_skip_unknown_template(self):
        km = self.game.knowledge_manager
        messages = km._apply_local_reward_bundle(
            self.player, {"items": [{"item_id": "not_a_real_item_template", "quantity": 1}]}
        )
        self.assertEqual([], messages)

    def test_generated_item_data_that_fails_to_build_yields_no_message(self):
        km = self.game.knowledge_manager
        with patch("engine.items.item_factory.ItemFactory.from_dict", return_value=None):
            messages = km._apply_local_reward_bundle(self.player, {"generated_item_data": {"type": "Item"}})
        self.assertEqual([], messages)

    def test_generated_item_data_is_added_to_inventory(self):
        km = self.game.knowledge_manager
        generated = {
            "obj_id": "generated_test_dagger",
            "name": "Generated Dagger",
            "description": "A generated blade.",
            "type": "Item",
        }
        messages = km._apply_local_reward_bundle(self.player, {"generated_item_data": generated})
        self.assertEqual(1, len(messages))
        self.assertIn("Generated Dagger", messages[0])


class TestDialogueEffects(GameTestBase):
    def test_start_quest_effect_invokes_quest_manager(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        km.topics["quest_topic"] = {
            "display_name": "Quest Topic",
            "responses": [{"text": "Go do this.", "conditions": {}, "effects": {"start_quest": "some_quest_id"}}],
        }
        with patch.object(self.world.quest_manager, "start_quest") as mock_start:
            km.get_response(npc, "quest_topic", self.player)
            mock_start.assert_called_once_with("some_quest_id", self.player)

    def test_start_campaign_effect_invokes_campaign_manager(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        km.topics["campaign_topic"] = {
            "display_name": "Campaign Topic",
            "responses": [
                {"text": "A larger tale begins.", "conditions": {}, "effects": {"start_campaign": "some_campaign_id"}}
            ],
        }
        with patch.object(self.world.campaign_manager, "start_campaign") as mock_start:
            km.get_response(npc, "campaign_topic", self.player)
            mock_start.assert_called_once_with("some_campaign_id", self.player)

    def test_give_item_effect_grants_item_to_player(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        km.topics["item_topic"] = {
            "display_name": "Item Topic",
            "responses": [
                {"text": "Take this.", "conditions": {}, "effects": {"give_item": "item_starter_dagger"}}
            ],
        }
        response = km.get_response(npc, "item_topic", self.player)
        self.assertIn("You receive", str(response))

    def test_give_item_effect_routes_through_party_loot_when_server_present(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        km.topics["item_topic_party"] = {
            "display_name": "Item Topic Party",
            "responses": [
                {"text": "Take this.", "conditions": {}, "effects": {"give_item": "item_starter_dagger"}}
            ],
        }
        other_player = MagicMock()
        other_player.name = "Ally"
        other_player.inventory.add_item = MagicMock()
        fake_server = MagicMock()
        fake_server.distribute_party_loot.return_value = (other_player, "note")
        self.world.server = fake_server
        try:
            response = km.get_response(npc, "item_topic_party", self.player)
            self.assertIn("Ally receives", str(response))
        finally:
            del self.world.server

    def test_start_quest_effect_is_a_no_op_when_quest_manager_missing(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        km.topics["quest_topic_no_mgr"] = {
            "display_name": "Quest Topic No Mgr",
            "responses": [{"text": "...", "conditions": {}, "effects": {"start_quest": "x"}}],
        }
        original = self.world.quest_manager
        self.world.quest_manager = None
        try:
            response = km.get_response(npc, "quest_topic_no_mgr", self.player)
            self.assertEqual('"..."', response)
        finally:
            self.world.quest_manager = original

    def test_start_campaign_effect_is_a_no_op_when_campaign_manager_missing(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        km.topics["campaign_topic_no_mgr"] = {
            "display_name": "Campaign Topic No Mgr",
            "responses": [{"text": "...", "conditions": {}, "effects": {"start_campaign": "x"}}],
        }
        original = self.world.campaign_manager
        self.world.campaign_manager = None
        try:
            response = km.get_response(npc, "campaign_topic_no_mgr", self.player)
            self.assertEqual('"..."', response)
        finally:
            self.world.campaign_manager = original

    def test_give_item_effect_with_unknown_template_grants_nothing(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        km.topics["item_topic_unknown"] = {
            "display_name": "Item Topic Unknown",
            "responses": [{"text": "...", "conditions": {}, "effects": {"give_item": "not_a_real_item_template"}}],
        }
        response = km.get_response(npc, "item_topic_unknown", self.player)
        self.assertEqual('"..."', response)

    def test_give_gold_server_routing_with_empty_string_grants_no_message(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        km.topics["gold_topic_empty_routing"] = {
            "display_name": "Gold Topic Empty Routing",
            "responses": [{"text": "...", "conditions": {}, "effects": {"give_gold": 10}}],
        }
        fake_server = MagicMock()
        fake_server.grant_party_gold.return_value = ""
        self.world.server = fake_server
        try:
            response = km.get_response(npc, "gold_topic_empty_routing", self.player)
            self.assertEqual('"..."', response)
        finally:
            del self.world.server

    def test_give_rewards_server_routing_with_empty_string_grants_no_message(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        km.topics["rewards_topic_empty_routing"] = {
            "display_name": "Rewards Topic Empty Routing",
            "responses": [{"text": "...", "conditions": {}, "effects": {"give_rewards": {"xp": 1}}}],
        }
        fake_server = MagicMock()
        fake_server.grant_party_rewards.return_value = ""
        self.world.server = fake_server
        try:
            response = km.get_response(npc, "rewards_topic_empty_routing", self.player)
            self.assertEqual('"..."', response)
        finally:
            del self.world.server

    def test_give_gold_zero_amount_grants_nothing(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        km.topics["free_topic"] = {
            "display_name": "Free Topic",
            "responses": [{"text": "Just words.", "conditions": {}, "effects": {"give_gold": 0}}],
        }
        response = km.get_response(npc, "free_topic", self.player)
        self.assertEqual('"Just words."', response)

    def test_give_gold_routes_through_server_when_present(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        km.topics["gold_topic_party"] = {
            "display_name": "Gold Topic Party",
            "responses": [{"text": "Split this.", "conditions": {}, "effects": {"give_gold": 10}}],
        }
        fake_server = MagicMock()
        fake_server.grant_party_gold.return_value = "Leader +5 Gold, Ally +5 Gold"
        self.world.server = fake_server
        try:
            response = km.get_response(npc, "gold_topic_party", self.player)
            self.assertIn("Rewards: Leader +5 Gold, Ally +5 Gold", str(response))
        finally:
            del self.world.server

    def test_give_rewards_routes_through_server_when_present(self):
        km = self.game.knowledge_manager
        npc = _villager(self.world)
        km.topics["rewards_topic_party"] = {
            "display_name": "Rewards Topic Party",
            "responses": [
                {"text": "Enjoy.", "conditions": {}, "effects": {"give_rewards": {"xp": 5}}}
            ],
        }
        fake_server = MagicMock()
        fake_server.grant_party_rewards.return_value = "Leader +5 XP"
        self.world.server = fake_server
        try:
            response = km.get_response(npc, "rewards_topic_party", self.player)
            self.assertIn("Leader +5 XP", str(response))
        finally:
            del self.world.server


if __name__ == "__main__":
    import unittest
    unittest.main()
