# tests/singles/test_interaction_npcs_commands.py
"""Coverage for engine/commands/interaction/npcs.py: talk, ask, turnin,
follow, guide, negotiate, and the quest turn-in dialogue flow they share."""

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory


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
