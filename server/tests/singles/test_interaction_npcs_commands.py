# tests/singles/test_interaction_npcs_commands.py
"""Coverage for engine/commands/interaction/npcs.py: talk, ask, turnin,
follow, guide, negotiate, and the quest turn-in dialogue flow they share.

Note: _handle_quest_dialogue's `if not dialogue or dialogue ==
"QUEST_COMPLETE":` (inside the block already gated by `if dialogue ==
"QUEST_COMPLETE":`, with no reassignment of `dialogue` in between) always
evaluates True in that call path, so its False arm -- keeping the literal
string "QUEST_COMPLETE" as the displayed npc dialogue -- is unreachable.
Left untested as dead code, consistent with this codebase's established
precedent for a redundant guard following an equivalent earlier check."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.commands.interaction.npcs import talk_handler, turnin_handler, follow_handler, guide_handler


def _place_npc(world, template_id, instance_id, region_id, room_id, **overrides):
    npc = NPCFactory.create_npc_from_template(template_id, world, instance_id=instance_id, **overrides)
    npc.current_region_id = region_id
    npc.current_room_id = room_id
    world.add_npc(npc)
    return npc


class _NpcTestBase(GameTestBase):
    def setUp(self):
        super().setUp()
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        # Start each test with a clean room; real content spawns crowds here.
        self.world.npcs = {}


class TestResolveTargetNpcFallbacks(_NpcTestBase):
    def test_trading_with_is_used_when_no_args_given(self):
        vendor = _place_npc(self.world, "village_elder", "vendor1", "town", "town_square", name="Vendor")
        self.player.trading_with = vendor.obj_id
        result = self.game.process_command("ask price")
        self.assertNotIn("no one here", result)

    def test_last_talked_to_is_used_when_no_args_given_and_colocated(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Elder")
        self.player.trading_with = None
        self.player.last_talked_to = elder.obj_id
        result = self.game.process_command("ask price")
        self.assertNotIn("no one here", result)

    def test_falls_back_to_any_non_hostile_npc_in_room(self):
        _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Elder")
        self.player.trading_with = None
        self.player.last_talked_to = None
        result = self.game.process_command("ask price")
        self.assertNotIn("no one here", result)

    def test_no_npc_at_all_is_reported(self):
        self.player.trading_with = None
        self.player.last_talked_to = None
        result = self.game.process_command("ask price")
        self.assertIn("no one here", result)

    def test_last_talked_to_not_colocated_falls_through_to_any_npc(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "market_square", name="Elder")
        _place_npc(self.world, "village_elder", "elder2", "town", "town_square", name="Nearby Elder")
        self.player.trading_with = None
        self.player.last_talked_to = elder.obj_id  # exists, but in a different room
        result = self.game.process_command("ask price")
        self.assertNotIn("no one here", result)


class TestTalkHandlerDirectGuards(_NpcTestBase):
    def test_no_player_in_context_reports_start_or_load(self):
        result = talk_handler([], {"world": self.world, "player": None})
        self.assertIn("start or load a game", result)

    def test_no_target_npc_is_reported(self):
        result = talk_handler([], {"world": self.world, "player": self.player})
        self.assertIn("no one here to talk", result)


class TestTalkCommand(_NpcTestBase):
    def test_hostile_npc_refuses_to_talk(self):
        _place_npc(self.world, "giant_rat", "rat1", "town", "town_square")
        result = self.game.process_command("talk rat")
        self.assertIn("refuses to listen", result)

    def test_topic_with_known_response(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        self.game.knowledge_manager.topics["favorite_color"] = {
            "display_name": "Favorite Color",
            "responses": [{"text": "I like blue.", "conditions": {}, "priority": 0}],
        }
        result = self.game.process_command("talk Sage about favorite color")
        self.assertIn("I like blue", result)

    def test_topic_with_no_response_is_reported(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        result = self.game.process_command("talk Sage about something_totally_unconfigured")
        self.assertIn("nothing to say", result)

    def test_default_greeting_hints_at_generic_quest_giver(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        elder.properties["can_give_generic_quests"] = True
        result = self.game.process_command("talk Sage")
        self.assertIn("CONVERSATION WITH", result)
        self.assertIn("job", result.lower())

    def test_greeting_hints_at_ready_to_complete_quest(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        self.player.runtime_state.quests.active["q1"] = {
            "instance_id": "q1", "title": "Errand", "giver_instance_id": elder.obj_id,
            "state": "ready_to_complete", "current_stage_index": 0, "stages": [{"stage_index": 0}],
        }
        result = self.game.process_command("talk Sage")
        self.assertIn("returned", result)
        self.assertIn("complete", result.lower())

    def test_greeting_with_active_but_not_ready_quest_uses_plain_default(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        self.player.runtime_state.quests.active["q1"] = {
            "instance_id": "q1", "title": "Errand", "giver_instance_id": elder.obj_id,
            "state": "active", "current_stage_index": 0, "stages": [{"stage_index": 0}],
        }
        result = self.game.process_command("talk Sage")
        self.assertIn("CONVERSATION WITH", result)
        self.assertNotIn("returned", result)

    def test_greeting_quest_with_no_stages_falls_back_to_giver_id(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        self.player.runtime_state.quests.active["q1"] = {
            "instance_id": "q1", "title": "Errand", "giver_instance_id": elder.obj_id,
            "state": "ready_to_complete", "current_stage_index": 0, "stages": [],
        }
        result = self.game.process_command("talk Sage")
        self.assertIn("returned", result)

    def test_greeting_scans_past_a_non_matching_quest_first(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        self.player.runtime_state.quests.active["q_other"] = {
            "instance_id": "q_other", "title": "Not This NPC's Quest",
            "giver_instance_id": "some_totally_different_npc",
            "state": "ready_to_complete", "current_stage_index": 0, "stages": [{"stage_index": 0}],
        }
        self.player.runtime_state.quests.active["q_mine"] = {
            "instance_id": "q_mine", "title": "My Errand", "giver_instance_id": elder.obj_id,
            "state": "ready_to_complete", "current_stage_index": 0, "stages": [{"stage_index": 0}],
        }
        result = self.game.process_command("talk Sage")
        self.assertIn("My Errand", result)

    def test_greeting_quest_with_unrecognized_state_is_ignored(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        self.player.runtime_state.quests.active["q1"] = {
            "instance_id": "q1", "title": "Errand", "giver_instance_id": elder.obj_id,
            "state": "some_unrecognized_state", "current_stage_index": 0, "stages": [{"stage_index": 0}],
        }
        result = self.game.process_command("talk Sage")
        self.assertIn("CONVERSATION WITH", result)
        self.assertNotIn("returned", result)


class TestAskCommand(_NpcTestBase):
    def test_no_args_shows_usage(self):
        result = self.game.process_command("ask")
        self.assertIn("Ask who/what", result)

    def test_hostile_npc_refuses(self):
        _place_npc(self.world, "giant_rat", "rat1", "town", "town_square")
        result = self.game.process_command("ask rat about anything")
        self.assertIn("refuses to listen", result)

    def test_no_topic_words_is_reported(self):
        _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        result = self.game.process_command("ask Sage")
        self.assertIn("about what", result)

    def test_topic_with_known_response(self):
        _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        self.game.knowledge_manager.topics["local_history"] = {
            "display_name": "Local History",
            "responses": [{"text": "This town is old.", "conditions": {}, "priority": 0}],
        }
        result = self.game.process_command("ask Sage about local history")
        self.assertIn("This town is old", result)


class TestHandleAcceptOffer(_NpcTestBase):
    def test_no_npc_present(self):
        result = self.game.process_command("accept")
        self.assertIn("No one here has offered", result)

    def test_npc_present_but_no_offer_configured(self):
        _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        result = self.game.process_command("accept")
        self.assertIn("No one here has offered", result)


class TestTurninCommand(_NpcTestBase):
    def test_no_collector_present_is_reported(self):
        result = self.game.process_command("turnin")
        self.assertIn("no one here to accept", result)

    def test_collector_in_room_is_used(self):
        collector = _place_npc(self.world, "village_elder", "collector1", "town", "town_square", name="Collector")
        collector.properties["is_collector"] = True
        result = self.game.process_command("turnin")
        # No collection configured, but a real collector was found and the
        # command reached collection_manager.turn_in_items rather than erroring out.
        self.assertNotIn("no one here to accept", result)


class TestFollowCommand(_NpcTestBase):
    def test_no_args_and_no_target_asks_whom(self):
        self.assertEqual("Follow whom?", self.game.process_command("follow"))

    def test_no_args_reports_current_target(self):
        npc = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Guide")
        self.player.follow_target = npc.obj_id
        result = self.game.process_command("follow")
        self.assertIn("currently following Guide", result)

    def test_stop_with_no_target_is_reported(self):
        self.player.follow_target = None
        result = self.game.process_command("follow stop")
        self.assertEqual("You aren't following anyone.", result)

    def test_stop_clears_target(self):
        npc = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Guide")
        self.player.follow_target = npc.obj_id
        result = self.game.process_command("follow stop")
        self.assertIn("stop following", result)
        self.assertIsNone(self.player.follow_target)

    def test_follow_unknown_npc_is_reported(self):
        result = self.game.process_command("follow nobody_here")
        self.assertIn("here to follow", result)

    def test_follow_sets_target(self):
        _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Guide")
        result = self.game.process_command("follow Guide")
        self.assertIn("start following", result)
        self.assertIsNotNone(self.player.follow_target)

    def test_follow_same_target_twice_is_reported(self):
        _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Guide")
        self.game.process_command("follow Guide")
        result = self.game.process_command("follow Guide")
        self.assertIn("already following", result)


class TestFollowHandlerDirectGuards(_NpcTestBase):
    def test_no_player_reports_start_or_load(self):
        result = follow_handler(["someone"], {"world": self.world, "player": None})
        self.assertIn("start or load a game", result)

    def test_dead_player_cannot_follow(self):
        self.player.health = 0
        self.player.is_alive = False
        result = follow_handler(["someone"], {"world": self.world, "player": self.player})
        self.assertIn("dead", result)


class TestGuideCommand(_NpcTestBase):
    def test_no_args_shows_usage(self):
        result = self.game.process_command("guide")
        self.assertIn("Who do you want", result)

    def test_unknown_npc_is_reported(self):
        result = self.game.process_command("guide nobody_here")
        self.assertIn("don't see", result)

    def test_hostile_npc_refuses_to_guide(self):
        _place_npc(self.world, "giant_rat", "rat1", "town", "town_square")
        result = self.game.process_command("guide rat")
        self.assertIn("won't guide", result)

    def test_npc_without_matching_quest_has_not_offered_to_guide(self):
        _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Guide")
        result = self.game.process_command("guide Guide")
        self.assertIn("has not offered to guide", result)

    def test_no_player_or_game_reports_system_error(self):
        result = guide_handler(["someone"], {"world": self.world, "player": None, "game": None})
        self.assertIn("System error", result)

    def test_scans_past_a_non_matching_quest_before_finding_the_guide_quest(self):
        guide = _place_npc(self.world, "village_elder", "guide_scan", "town", "town_square", name="Pathfinder")
        self.player.runtime_state.quests.active["q_other"] = {
            "instance_id": "q_other", "title": "Unrelated", "type": "instance",
            "giver_instance_id": "someone_else_entirely", "current_stage_index": 0,
            "rewards": {}, "state": "active", "objective": {},
            "stages": [{"stage_index": 0, "objective": {}}],
            "entry_point": None,
        }
        self.player.runtime_state.quests.active["q_guide_scan"] = {
            "instance_id": "q_guide_scan", "title": "Guided Quest", "type": "instance",
            "giver_instance_id": guide.obj_id, "current_stage_index": 0,
            "rewards": {}, "state": "active", "objective": {},
            "stages": [{"stage_index": 0, "objective": {}}],
            "entry_point": None,
        }
        result = self.game.process_command("guide Pathfinder")
        self.assertIn("no destination", result)


class TestNegotiateCommand(_NpcTestBase):
    def test_negotiate_proxies_to_talk_handler(self):
        _place_npc(self.world, "giant_rat", "rat1", "town", "town_square")
        # Proxies straight into talk_handler; a hostile target still refuses.
        result = self.game.process_command("negotiate rat")
        self.assertIn("refuses to listen", result)


class TestQuestTurnInDialogue(_NpcTestBase):
    def test_ready_kill_quest_completes_via_talk(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        self.player.runtime_state.quests.active["q1"] = {
            "instance_id": "q1", "title": "Rat Problem", "type": "kill",
            "giver_instance_id": elder.obj_id, "current_stage_index": 0,
            "rewards": {"xp": 10}, "state": "ready_to_complete",
            "objective": {"type": "kill"},
            "stages": [{"stage_index": 0, "objective": {"type": "kill"}}],
        }
        result = self.game.process_command("talk Sage complete")
        self.assertIn("Quest Complete", result)
        self.assertNotIn("q1", self.player.runtime_state.quests.active)

    def test_active_fetch_quest_reports_missing_items(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        self.player.runtime_state.quests.active["q1"] = {
            "instance_id": "q1", "title": "Fetch Ingot", "type": "fetch",
            "giver_instance_id": elder.obj_id, "current_stage_index": 0,
            "rewards": {}, "state": "active",
            "objective": {"type": "fetch", "item_id": "item_iron_ingot", "required_quantity": 1},
            "stages": [{"stage_index": 0, "objective": {"type": "fetch", "item_id": "item_iron_ingot", "required_quantity": 1}}],
        }
        result = self.game.process_command("talk Sage complete")
        self.assertIn("haven't fully met the requirements", result)
        self.assertIn("q1", self.player.runtime_state.quests.active)

    def test_active_fetch_quest_advances_to_next_stage_when_satisfied(self):
        from engine.items.item_factory import ItemFactory

        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        ingot = ItemFactory.create_item_from_template("item_iron_ingot", self.world)
        self.player.inventory.add_item(ingot)
        objective = {"type": "fetch", "item_id": "item_iron_ingot", "required_quantity": 1}
        self.player.runtime_state.quests.active["q1"] = {
            "instance_id": "q1", "title": "Fetch Ingot", "type": "fetch",
            "giver_instance_id": elder.obj_id, "current_stage_index": 0,
            "rewards": {}, "state": "active", "objective": objective,
            "stages": [
                {"stage_index": 0, "objective": objective, "description": "Stage one."},
                {"stage_index": 1, "objective": {"type": "fetch", "item_id": "item_iron_ingot", "required_quantity": 1}, "description": "Stage two."},
            ],
        }
        result = self.game.process_command("talk Sage complete")
        self.assertIn("Objective Complete", result)
        self.assertEqual(1, self.player.runtime_state.quests.active["q1"]["current_stage_index"])
        self.assertEqual(0, self.player.inventory.count_item("item_iron_ingot"))

    def test_no_matching_quest_reports_not_expecting_anything(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        result = self.game.process_command("talk Sage complete")
        self.assertIn("doesn't seem to be expecting anything", result)

    def test_quest_missing_stages_falls_back_to_giver_instance_id(self):
        # With no stages, get_active_objective() legitimately has nothing to
        # return -- this test's point is that the scan loop's stage lookup
        # (idx < len(stages)) safely skips and still matches this NPC via
        # giver_instance_id, reaching the "objective data missing" branch
        # instead of crashing.
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        self.player.runtime_state.quests.active["q_no_stages"] = {
            "instance_id": "q_no_stages", "title": "No Stages", "type": "kill",
            "giver_instance_id": elder.obj_id, "current_stage_index": 0,
            "rewards": {}, "state": "ready_to_complete", "objective": {"type": "kill"},
            "stages": [],
        }
        result = self.game.process_command("talk Sage complete")
        self.assertIn("objective data missing", result)

    def test_non_matching_quest_is_skipped_before_matching_one_is_found(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        other_npc_id = "some_other_npc_entirely"
        self.player.runtime_state.quests.active["q_other"] = {
            "instance_id": "q_other", "title": "Someone Else's Quest", "type": "kill",
            "giver_instance_id": other_npc_id, "current_stage_index": 0,
            "rewards": {}, "state": "ready_to_complete", "objective": {"type": "kill"},
            "stages": [{"stage_index": 0, "objective": {"type": "kill"}}],
        }
        self.player.runtime_state.quests.active["q_mine"] = {
            "instance_id": "q_mine", "title": "My Quest", "type": "kill",
            "giver_instance_id": elder.obj_id, "current_stage_index": 0,
            "rewards": {}, "state": "ready_to_complete", "objective": {"type": "kill"},
            "stages": [{"stage_index": 0, "objective": {"type": "kill"}}],
        }
        result = self.game.process_command("talk Sage complete")
        self.assertIn("My Quest", result)

    def test_negotiate_objective_success_completes_quest(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Negotiator")
        objective = {
            "type": "negotiate", "skill": "diplomacy", "difficulty": 1,
            "choices": {"success": {"next_stage": 1, "description": "Deal made."}},
        }
        self.player.runtime_state.quests.active["q_neg"] = {
            "instance_id": "q_neg", "title": "A Negotiation", "type": "instance",
            "giver_instance_id": elder.obj_id, "current_stage_index": 0,
            "rewards": {}, "state": "active", "objective": objective,
            "stages": [{"stage_index": 0, "objective": objective}],
        }
        with patch("engine.commands.interaction.npcs.SkillSystem.attempt_check", return_value=(True, "Roll succeeded!")):
            result = self.game.process_command("talk Negotiator negotiate")
        self.assertIn("Quest Complete", result)
        self.assertNotIn("q_neg", self.player.runtime_state.quests.active)

    def test_negotiate_objective_failure_advances_with_fail_dialogue(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Negotiator")
        objective = {
            "type": "negotiate", "skill": "diplomacy", "difficulty": 99,
            "choices": {
                "success": {"next_stage": 1, "description": "Deal made."},
                "fail": {"next_stage": 0, "description": "They refused."},
            },
        }
        self.player.runtime_state.quests.active["q_neg_fail"] = {
            "instance_id": "q_neg_fail", "title": "A Tough Negotiation", "type": "instance",
            "giver_instance_id": elder.obj_id, "current_stage_index": 0,
            "rewards": {}, "state": "active", "objective": objective,
            "stages": [
                {"stage_index": 0, "objective": objective, "completion_dialogue": "Let's talk."},
                {"stage_index": 0, "objective": objective, "completion_dialogue": "Try again."},
            ],
        }
        with patch("engine.commands.interaction.npcs.SkillSystem.attempt_check", return_value=(False, "Roll failed.")):
            result = self.game.process_command("talk Negotiator negotiate")
        self.assertIn("Negotiation FAIL", result)
        self.assertIn("They refused", result)

    def test_negotiate_objective_with_unconfigured_choice_reports_config_error(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Negotiator")
        objective = {
            "type": "negotiate", "skill": "diplomacy", "difficulty": 99,
            "choices": {"success": {"next_stage": 1, "description": "Deal made."}},
        }
        self.player.runtime_state.quests.active["q_neg_cfg_err"] = {
            "instance_id": "q_neg_cfg_err", "title": "Misconfigured Negotiation", "type": "instance",
            "giver_instance_id": elder.obj_id, "current_stage_index": 0,
            "rewards": {}, "state": "active", "objective": objective,
            "stages": [{"stage_index": 0, "objective": objective}],
        }
        with patch("engine.commands.interaction.npcs.SkillSystem.attempt_check", return_value=(False, "Roll failed.")):
            result = self.game.process_command("talk Negotiator negotiate")
        self.assertIn("Negotiation config error", result)

    def test_deliver_objective_missing_item_instance_reports_missing_package(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        objective = {
            "type": "deliver", "item_id": "item_iron_ingot", "item_instance_id": "pkg_never_owned",
            "item_to_deliver_name": "Special Package",
        }
        self.player.runtime_state.quests.active["q_deliver_missing"] = {
            "instance_id": "q_deliver_missing", "title": "Deliver It", "type": "deliver",
            "giver_instance_id": elder.obj_id, "current_stage_index": 0,
            "rewards": {}, "state": "active", "objective": objective,
            "stages": [{"stage_index": 0, "objective": objective}],
        }
        result = self.game.process_command("talk Sage complete")
        self.assertIn("don't have the Special Package", result)

    def test_deliver_objective_with_item_present_completes_quest(self):
        from engine.items.item_factory import ItemFactory

        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        package = ItemFactory.create_item_from_template("quest_package_generic", self.world)
        package.obj_id = "pkg_owned_123"
        self.player.inventory.add_item(package)
        objective = {
            "type": "deliver", "item_id": "item_iron_ingot", "item_instance_id": "pkg_owned_123",
            "item_to_deliver_name": "Special Package",
        }
        self.player.runtime_state.quests.active["q_deliver_present"] = {
            "instance_id": "q_deliver_present", "title": "Deliver It", "type": "deliver",
            "giver_instance_id": elder.obj_id, "current_stage_index": 0,
            "rewards": {}, "state": "active", "objective": objective,
            "stages": [{"stage_index": 0, "objective": objective}],
        }
        result = self.game.process_command("talk Sage complete")
        self.assertIn("Quest Complete", result)
        self.assertIsNone(self.player.inventory.find_item_by_id("pkg_owned_123"))

    def test_active_quest_with_unready_objective_type_is_not_ready(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        objective = {"type": "kill"}
        self.player.runtime_state.quests.active["q_active_kill"] = {
            "instance_id": "q_active_kill", "title": "Ongoing Hunt", "type": "kill",
            "giver_instance_id": elder.obj_id, "current_stage_index": 0,
            "rewards": {}, "state": "active", "objective": objective,
            "stages": [{"stage_index": 0, "objective": objective}],
        }
        result = self.game.process_command("talk Sage complete")
        self.assertIn("doesn't seem to be expecting anything", result)

    def test_unrecognized_objective_type_defaults_to_success_resolution(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        objective = {"type": "totally_unrecognized_objective_type"}
        self.player.runtime_state.quests.active["q_unrecognized"] = {
            "instance_id": "q_unrecognized", "title": "Mystery Quest", "type": "kill",
            "giver_instance_id": elder.obj_id, "current_stage_index": 0,
            "rewards": {}, "state": "ready_to_complete", "objective": objective,
            "stages": [{"stage_index": 0, "objective": objective}],
        }
        result = self.game.process_command("talk Sage complete")
        self.assertIn("Quest Complete", result)


class TestHandleAcceptOfferSuccess(_NpcTestBase):
    def test_configured_offer_is_returned(self):
        elder = _place_npc(self.world, "village_elder", "elder1", "town", "town_square", name="Sage")
        self.game.knowledge_manager.topics["accept"] = {
            "display_name": "Accept",
            "responses": [{"text": "Please help me with this task.", "conditions": {}, "priority": 0}],
        }
        result = self.game.process_command("accept")
        self.assertIn("Please help me with this task", result)


class TestTurninHandlerDirectGuards(_NpcTestBase):
    def test_no_player_returns_generic_error(self):
        result = turnin_handler([], {"world": self.world, "player": None, "game": self.game})
        self.assertEqual("Error.", result)

    def test_trading_with_is_used_when_set(self):
        collector = _place_npc(self.world, "village_elder", "collector_trading", "town", "town_square", name="Collector")
        collector.properties["is_collector"] = True
        self.player.trading_with = collector.obj_id
        self.player.last_talked_to = None
        result = self.game.process_command("turnin")
        self.assertNotIn("no one here to accept", result)

    def test_last_talked_to_used_when_colocated(self):
        collector = _place_npc(self.world, "village_elder", "collector1", "town", "town_square", name="Collector")
        collector.properties["is_collector"] = True
        self.player.trading_with = None
        self.player.last_talked_to = collector.obj_id
        result = self.game.process_command("turnin")
        self.assertNotIn("no one here to accept", result)

    def test_neither_trading_with_nor_last_talked_to_set_falls_to_room_scan(self):
        collector = _place_npc(self.world, "village_elder", "collector_direct", "town", "town_square", name="Collector")
        collector.properties["is_collector"] = True
        self.player.trading_with = None
        self.player.last_talked_to = None
        result = turnin_handler([], {"world": self.world, "player": self.player, "game": self.game})
        self.assertNotIn("no one here to accept", result)

    def test_multiple_npcs_in_room_scans_past_non_collectors(self):
        _place_npc(self.world, "village_elder", "bystander1", "town", "town_square", name="Bystander")
        collector = _place_npc(self.world, "village_elder", "collector1", "town", "town_square", name="Collector")
        collector.properties["is_collector"] = True
        self.player.trading_with = None
        self.player.last_talked_to = None
        result = self.game.process_command("turnin")
        self.assertNotIn("no one here to accept", result)


class TestGuideCommandSuccess(_NpcTestBase):
    def _guide_quest(self, npc_obj_id, entry_point=None):
        self.player.runtime_state.quests.active["q_guide"] = {
            "instance_id": "q_guide", "title": "Guided Quest", "type": "instance",
            "giver_instance_id": npc_obj_id, "current_stage_index": 0,
            "rewards": {}, "state": "active", "objective": {},
            "stages": [{"stage_index": 0, "objective": {}}],
            "entry_point": entry_point,
        }

    def test_matching_quest_with_no_entry_point_reports_no_destination(self):
        guide = _place_npc(self.world, "village_elder", "guide1", "town", "town_square", name="Pathfinder")
        self._guide_quest(guide.obj_id, entry_point=None)
        result = self.game.process_command("guide Pathfinder")
        self.assertIn("no destination", result)

    def test_unreachable_destination_reports_confusion(self):
        guide = _place_npc(self.world, "village_elder", "guide2", "town", "town_square", name="Pathfinder")
        self._guide_quest(guide.obj_id, entry_point={"region_id": "totally_bogus_region", "room_id": "totally_bogus_room"})
        result = self.game.process_command("guide Pathfinder")
        self.assertIn("can't find a path", result)

    def test_already_at_destination_is_reported(self):
        guide = _place_npc(self.world, "village_elder", "guide3", "town", "town_square", name="Pathfinder")
        self._guide_quest(guide.obj_id, entry_point={
            "region_id": self.player.current_region_id, "room_id": self.player.current_room_id,
        })
        result = self.game.process_command("guide Pathfinder")
        self.assertIn("already at the destination", result)

    def test_successful_guide_starts_auto_travel(self):
        from engine.world.room import Room

        region = self.world.get_region("town")
        destination_room = Room("Destination", "A place to go.", obj_id="guide_destination_room")
        region.add_room("guide_destination_room", destination_room)
        town_square = region.get_room("town_square")
        town_square.exits["north"] = "guide_destination_room"

        guide = _place_npc(self.world, "village_elder", "guide4", "town", "town_square", name="Pathfinder")
        self._guide_quest(guide.obj_id, entry_point={"region_id": "town", "room_id": "guide_destination_room"})
        with patch.object(self.game, "start_auto_travel") as mock_travel:
            result = self.game.process_command("guide Pathfinder")
        mock_travel.assert_called_once()
        self.assertNotIn("confused", result)
        self.assertNotIn("already at the destination", result)
