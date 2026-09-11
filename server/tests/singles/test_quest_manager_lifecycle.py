# tests/singles/test_quest_manager_lifecycle.py
"""Coverage for engine/core/quests/manager.py's less-exercised paths: the
turn-in-name resolver's fallback chain, board-replenishment edge cases,
start_quest/complete_quest's party-server and campaign-context branches,
_grant_rewards' item/generated-item branches, advance_quest_stage's
dialogue-choice routing, _setup_stage_mechanics' procedural-item/escort/
boss-spawn branches, and handle_room_entry's spawn-on-entry/scout logic --
none of which the existing quest command/lifecycle tests happen to hit."""

from unittest.mock import MagicMock, patch

from tests.fixtures import GameTestBase
from engine.core.quests.manager import QuestManager
from engine.npcs.npc_factory import NPCFactory


class TestConstructor(GameTestBase):
    def test_mismatched_content_root_raises(self):
        with self.assertRaises(TypeError):
            QuestManager(self.world, content_root="/not/the/real/root")


class TestLoadNpcInterests(GameTestBase):
    def test_no_world_is_a_no_op(self):
        qm = self.world.quest_manager
        original_world = qm.world
        qm.world = None
        try:
            qm._load_npc_interests()  # must not raise
        finally:
            qm.world = original_world

    def test_non_dict_template_data_is_skipped(self):
        qm = self.world.quest_manager
        self.world.npc_templates["weird_template"] = "not_a_dict"
        qm._load_npc_interests()  # must not raise
        self.assertNotIn("weird_template", qm.npc_interests)


class TestResolveTurnInName(GameTestBase):
    def test_empty_stages_uses_the_literal_unknown_sentinel(self):
        # No stages at all means giver_id stays the truthy literal "unknown"
        # (which is not itself falsy, so the giver_instance_id fallback below
        # never triggers) -- it simply fails every subsequent lookup.
        qm = self.world.quest_manager
        result = qm.resolve_turn_in_name({"giver_instance_id": "some_npc", "stages": []})
        self.assertEqual("the quest giver", result)

    def test_stage_turn_in_id_missing_falls_back_to_giver_instance_id(self):
        qm = self.world.quest_manager
        npc = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="elder_fallback")
        self.world.add_npc(npc)
        quest_data = {
            "giver_instance_id": "elder_fallback",
            "current_stage_index": 0,
            "stages": [{"turn_in_id": None}],
        }
        self.assertEqual(npc.name, qm.resolve_turn_in_name(quest_data))

    def test_non_string_giver_id_returns_generic_label(self):
        qm = self.world.quest_manager
        self.assertEqual("the quest giver", qm.resolve_turn_in_name({"giver_instance_id": 12345}))

    def test_quest_board_giver_id_returns_quest_board_label(self):
        qm = self.world.quest_manager
        quest_data = {
            "giver_instance_id": "quest_board",
            "current_stage_index": 0,
            "stages": [{"turn_in_id": None}],
        }
        self.assertEqual("Quest Board", qm.resolve_turn_in_name(quest_data))

    def test_unknown_npc_falls_back_to_template_name(self):
        qm = self.world.quest_manager
        self.world.npc_templates["ghost_giver_template"] = {"name": "Ghost Giver"}
        quest_data = {
            "giver_instance_id": "ghost_giver_template",
            "current_stage_index": 0,
            "stages": [{"turn_in_id": None}],
        }
        result = qm.resolve_turn_in_name(quest_data)
        self.assertEqual("Ghost Giver", result)

    def test_completely_unknown_giver_returns_generic_label(self):
        qm = self.world.quest_manager
        quest_data = {
            "giver_instance_id": "totally_unknown_id",
            "current_stage_index": 0,
            "stages": [{"turn_in_id": None}],
        }
        result = qm.resolve_turn_in_name(quest_data)
        self.assertEqual("the quest giver", result)


class TestResolveReferencePlayer(GameTestBase):
    def test_no_world_returns_none(self):
        qm = self.world.quest_manager
        original_world = qm.world
        qm.world = None
        try:
            self.assertIsNone(qm._resolve_reference_player())
        finally:
            qm.world = original_world

    def test_delegates_to_world(self):
        qm = self.world.quest_manager
        self.assertIs(self.player, qm._resolve_reference_player())


class TestEnsureInitialQuests(GameTestBase):
    def test_no_world_is_a_no_op(self):
        qm = self.world.quest_manager
        original_world = qm.world
        qm.world = None
        try:
            qm.ensure_initial_quests(self.player)  # must not raise
        finally:
            qm.world = original_world

    def _authored_board_template_ids(self, qm):
        return [
            str(entry.get("template_id", ""))
            for entry in qm.config.get("authored_board_templates", [])
            if isinstance(entry, dict) and entry.get("template_id")
        ]

    def test_board_already_full_is_a_no_op(self):
        qm = self.world.quest_manager
        from engine.config import MAX_QUESTS_ON_BOARD
        # Content-authored board quests (e.g. commissions) are seeded before the
        # capacity-gated procedural fill loop and are exempt from its cap, so a
        # "board already full" fixture must already contain them -- otherwise
        # they'd still be appended even though the board is at capacity.
        board = [
            {"instance_id": f"authored_{template_id}", "template_id": template_id}
            for template_id in self._authored_board_template_ids(qm)
        ]
        while len(board) < MAX_QUESTS_ON_BOARD:
            board.append({"instance_id": f"filler_{len(board)}", "template_id": f"filler_template_{len(board)}"})
        self.world.quest_board = board
        with patch.object(qm.generator, "generate_instance_quest") as mock_instance, \
             patch.object(qm.generator, "generate_noninstance_quest") as mock_noninstance:
            qm.ensure_initial_quests(self.player)
            mock_instance.assert_not_called()
            mock_noninstance.assert_not_called()
        self.assertEqual(MAX_QUESTS_ON_BOARD, len(self.world.quest_board))

    def test_generator_returning_none_stops_the_fill_loop(self):
        qm = self.world.quest_manager
        self.world.quest_board = []
        with patch.object(qm.generator, "generate_instance_quest", return_value=None), \
             patch.object(qm.generator, "generate_noninstance_quest", return_value=None):
            qm.ensure_initial_quests(self.player)
        # Authored board quests are seeded independently of the (mocked-out)
        # procedural generator, so the board ends up holding exactly those.
        self.assertEqual(len(self._authored_board_template_ids(qm)), len(self.world.quest_board))

    def test_no_reference_player_is_a_no_op(self):
        qm = self.world.quest_manager
        self.world.quest_board = []
        self.world.player = None
        qm.ensure_initial_quests(None)  # must not raise
        self.assertEqual(0, len(self.world.quest_board))


class TestReplenishBoard(GameTestBase):
    def test_no_world_is_a_no_op(self):
        qm = self.world.quest_manager
        original_world = qm.world
        qm.world = None
        try:
            qm.replenish_board("some_id", self.player)  # must not raise
        finally:
            qm.world = original_world


class TestStartQuest(GameTestBase):
    def test_unknown_template_returns_false(self):
        qm = self.world.quest_manager
        self.assertFalse(qm.start_quest("not_a_real_quest_template", self.player))

    def test_generated_quest_without_stages_skips_stage_mechanics(self):
        qm = self.world.quest_manager
        qm.quest_templates["bare_template"] = {"title": "Bare", "type": "generic", "rewards": {}}
        with patch.object(qm.generator, "instantiate_quest", return_value={"title": "Bare", "type": "generic"}):
            result = qm.start_quest("bare_template", self.player)
        self.assertTrue(result)

    def test_preexisting_giver_instance_id_is_preserved(self):
        qm = self.world.quest_manager
        qm.quest_templates["giver_template"] = {"title": "Has Giver"}
        with patch.object(
            qm.generator, "instantiate_quest",
            return_value={"title": "Has Giver", "giver_instance_id": "specific_npc"},
        ):
            qm.start_quest("giver_template", self.player)
        active = list(self.player.runtime_state.quests.active.values())
        self.assertTrue(any(q.get("giver_instance_id") == "specific_npc" for q in active))

    def test_room_entry_updates_are_rendered_via_game_when_scout_matches_immediately(self):
        qm = self.world.quest_manager
        objective = {
            "type": "scout",
            "target_region": self.player.current_region_id,
            "target_room_id": self.player.current_room_id,
        }
        qm.quest_templates["instant_scout"] = {"title": "Instant Scout"}
        quest_payload = {
            "title": "Instant Scout",
            "objective": objective,
            "stages": [{"objective": objective}],
        }
        with patch.object(qm.generator, "instantiate_quest", return_value=quest_payload):
            qm.start_quest("instant_scout", self.player)
        joined = "\n".join(self.game.renderer.message_buffer)
        self.assertIn("reached the target location", joined)

    def test_mirrors_party_quest_acceptance_when_server_present(self):
        qm = self.world.quest_manager
        qm.quest_templates["party_template"] = {"title": "Party Quest"}
        fake_server = MagicMock()
        fake_server.mirror_party_quest_acceptance.return_value = ["event_a", "event_b"]
        fake_server.pending_broadcasts = []
        self.world.server = fake_server
        try:
            with patch.object(qm.generator, "instantiate_quest", return_value={"title": "Party Quest"}):
                qm.start_quest("party_template", self.player)
            self.assertEqual(["event_a", "event_b"], fake_server.pending_broadcasts)
        finally:
            del self.world.server

    def test_mirrors_party_quest_acceptance_without_pending_broadcasts_attribute(self):
        qm = self.world.quest_manager
        qm.quest_templates["party_template2"] = {"title": "Party Quest 2"}

        class _BareServer:
            def mirror_party_quest_acceptance(self, player, ids):
                return ["event_a"]

        self.world.server = _BareServer()
        try:
            with patch.object(qm.generator, "instantiate_quest", return_value={"title": "Party Quest 2"}):
                result = qm.start_quest("party_template2", self.player)
            self.assertTrue(result)  # must not raise despite no pending_broadcasts attr
        finally:
            del self.world.server


class TestStartCampaign(GameTestBase):
    def test_delegates_to_campaign_manager_when_present(self):
        qm = self.world.quest_manager
        with patch.object(self.world.campaign_manager, "start_campaign", return_value=True) as mock_start:
            result = qm.start_campaign("some_campaign", self.player)
        mock_start.assert_called_once_with("some_campaign", self.player)
        self.assertTrue(result)

    def test_returns_false_when_campaign_manager_missing(self):
        qm = self.world.quest_manager
        original = self.world.campaign_manager
        self.world.campaign_manager = None
        try:
            self.assertFalse(qm.start_campaign("some_campaign", self.player))
        finally:
            self.world.campaign_manager = original


class TestCompleteQuest(GameTestBase):
    def _active_quest(self, quest_id="complete_me", **overrides):
        data = {
            "instance_id": quest_id,
            "title": "Test Quest",
            "state": "active",
            "rewards": {},
        }
        data.update(overrides)
        self.player.runtime_state.quests.active[quest_id] = data
        return data

    def test_unknown_quest_id_returns_empty_string(self):
        qm = self.world.quest_manager
        self.assertEqual("", qm.complete_quest(self.player, "not_active_anywhere"))

    def test_instance_manager_cleanup_is_skipped_when_missing(self):
        qm = self.world.quest_manager
        self._active_quest("q1")
        original = self.world.instance_manager
        self.world.instance_manager = None
        try:
            result = qm.complete_quest(self.player, "q1")
            self.assertIsNotNone(result)
        finally:
            self.world.instance_manager = original

    def test_campaign_context_without_ids_skips_campaign_update(self):
        qm = self.world.quest_manager
        self._active_quest("q2", campaign_context={})
        result = qm.complete_quest(self.player, "q2")
        self.assertNotIn("\n", result)  # no campaign_update_msg appended

    def test_campaign_context_missing_node_id_skips_campaign_update(self):
        qm = self.world.quest_manager
        # Non-empty campaign_context (truthy) with campaign_manager present,
        # but no node_id -- the inner "if c_id and n_id" guard should skip.
        self._active_quest("q2b", campaign_context={"campaign_id": "camp1"})
        result = qm.complete_quest(self.player, "q2b")
        self.assertNotIn("\n", result)

    def test_campaign_context_with_ids_invokes_campaign_manager(self):
        qm = self.world.quest_manager
        self._active_quest("q3", campaign_context={"campaign_id": "camp1", "node_id": "node1"})
        with patch.object(
            self.world.campaign_manager, "handle_quest_completion", return_value="Campaign advances!",
        ) as mock_handle:
            result = qm.complete_quest(self.player, "q3")
        mock_handle.assert_called_once_with("camp1", "node1", "SUCCESS", self.player)
        self.assertIn("Campaign advances!", result)

    def test_completed_quest_with_campaign_context_skips_board_replenish(self):
        qm = self.world.quest_manager
        self._active_quest("q4", campaign_context={"campaign_id": "camp1", "node_id": "node1"})
        board_before = list(self.world.quest_board)
        with patch.object(qm, "replenish_board") as mock_replenish:
            qm.complete_quest(self.player, "q4")
        mock_replenish.assert_not_called()

    def test_syncs_party_quest_completion_when_server_present(self):
        qm = self.world.quest_manager
        self._active_quest("q5")
        fake_server = MagicMock()
        fake_server.sync_party_quest_completion.return_value = ["evt"]
        fake_server.pending_broadcasts = []
        self.world.server = fake_server
        try:
            qm.complete_quest(self.player, "q5")
            self.assertEqual(["evt"], fake_server.pending_broadcasts)
        finally:
            del self.world.server

    def test_syncs_party_quest_completion_without_pending_broadcasts_attribute(self):
        qm = self.world.quest_manager
        self._active_quest("q5b")

        class _BareServer:
            def sync_party_quest_completion(self, player, quest_data):
                return ["evt"]

        self.world.server = _BareServer()
        try:
            result = qm.complete_quest(self.player, "q5b")  # must not raise
            self.assertIsNotNone(result)
        finally:
            del self.world.server

    def test_campaign_context_present_but_manager_missing_skips_update(self):
        qm = self.world.quest_manager
        self._active_quest("q6", campaign_context={"campaign_id": "camp1", "node_id": "node1"})
        original = self.world.campaign_manager
        self.world.campaign_manager = None
        try:
            result = qm.complete_quest(self.player, "q6")
        finally:
            self.world.campaign_manager = original
        self.assertNotIn("\n", result)


class TestGrantRewards(GameTestBase):
    def test_item_rewards_are_added_with_quantity(self):
        qm = self.world.quest_manager
        text = qm._grant_rewards(
            self.player, {"items": [{"item_id": "item_starter_dagger", "quantity": 2}]}
        )
        self.assertIn("2x", text)

    def test_generated_item_data_reward_is_added(self):
        qm = self.world.quest_manager
        generated = {
            "obj_id": "quest_generated_item",
            "name": "Quest-Made Trinket",
            "description": "Forged for a quest.",
            "type": "Item",
        }
        text = qm._grant_rewards(self.player, {"generated_item_data": generated})
        self.assertIn("Quest-Made Trinket", text)

    def test_no_rewards_returns_empty_string(self):
        qm = self.world.quest_manager
        self.assertEqual("", qm._grant_rewards(self.player, {}))

    def test_server_present_delegates_to_grant_party_rewards(self):
        qm = self.world.quest_manager
        fake_server = MagicMock()
        fake_server.grant_party_rewards.return_value = "Party rewards text"
        self.world.server = fake_server
        try:
            text = qm._grant_rewards(self.player, {"xp": 5})
            self.assertEqual("Party rewards text", text)
        finally:
            del self.world.server


class TestAdvanceQuestStage(GameTestBase):
    def test_unknown_quest_id_returns_none(self):
        qm = self.world.quest_manager
        self.assertIsNone(qm.advance_quest_stage(self.player, "not_a_real_quest"))

    def test_index_already_beyond_stages_returns_quest_complete(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["over_index"] = {
            "current_stage_index": 5, "stages": [{"objective": {}}],
        }
        result = qm.advance_quest_stage(self.player, "over_index")
        self.assertEqual("QUEST_COMPLETE", result)

    def test_dialogue_choice_routes_to_named_next_stage(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["choice_quest"] = {
            "current_stage_index": 0,
            "stages": [
                {
                    "objective": {
                        "type": "dialogue_choice",
                        "choices": {
                            "peaceful": {"next_stage": 2, "description": "You chose peace."},
                        },
                    },
                },
                {"objective": {"type": "talk"}},
                {"objective": {"type": "final"}},
            ],
        }
        result = qm.advance_quest_stage(self.player, "choice_quest", choice_id="peaceful")
        self.assertEqual("You chose peace.", result)
        self.assertEqual(2, self.player.runtime_state.quests.active["choice_quest"]["current_stage_index"])

    def test_dialogue_choice_beyond_stages_completes_quest(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["choice_quest2"] = {
            "current_stage_index": 0,
            "stages": [
                {
                    "objective": {
                        "type": "negotiate",
                        "choices": {"end": {"next_stage": 99}},
                    },
                },
            ],
        }
        result = qm.advance_quest_stage(self.player, "choice_quest2", choice_id="end")
        self.assertEqual("QUEST_COMPLETE", result)

    def test_unrecognized_choice_id_falls_back_to_linear_next_stage(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["choice_quest3"] = {
            "current_stage_index": 0,
            "stages": [
                {"objective": {"type": "dialogue_choice", "choices": {"a": {"next_stage": 1}}}},
                {"objective": {"type": "final"}},
            ],
        }
        result = qm.advance_quest_stage(self.player, "choice_quest3", choice_id="not_a_real_choice")
        self.assertEqual(1, self.player.runtime_state.quests.active["choice_quest3"]["current_stage_index"])


class TestSetupStageMechanics(GameTestBase):
    def test_procedural_item_skipped_when_target_region_is_missing(self):
        qm = self.world.quest_manager
        objective = {
            "is_procedural_item": True,
            "procedural_item_data": {"template_id": "item_starter_dagger", "name": "Never Placed"},
        }
        with patch.object(self.world, "get_region", return_value=None):
            qm._setup_stage_mechanics({"instance_id": "proc_quest_no_region"}, {"objective": objective})
        for region in self.world.regions.values():
            for room in region.rooms.values():
                self.assertFalse(any(getattr(i, "name", "") == "Never Placed" for i in room.items))

    def test_procedural_item_skipped_when_template_is_unknown(self):
        qm = self.world.quest_manager
        objective = {
            "is_procedural_item": True,
            "procedural_item_data": {"template_id": "not_a_real_item_template", "name": "Never Placed"},
        }
        qm._setup_stage_mechanics({"instance_id": "proc_quest_bad_template"}, {"objective": objective})
        for region in self.world.regions.values():
            for room in region.rooms.values():
                self.assertFalse(any(getattr(i, "name", "") == "Never Placed" for i in room.items))

    def test_escort_with_no_spawn_config_is_a_no_op(self):
        qm = self.world.quest_manager
        objective = {"type": "escort"}
        qm._setup_stage_mechanics({"instance_id": "escort_quest_noconf"}, {"objective": objective})
        self.assertNotIn("target_npc_instance_id", objective)

    def test_escort_with_failed_npc_creation_leaves_no_instance_id(self):
        qm = self.world.quest_manager
        objective = {
            "type": "escort",
            "spawn_config": {
                "template_id": "not_a_real_template", "name": "Ghost Escort",
                "region_id": "town", "room_id": "town_square",
            },
        }
        qm._setup_stage_mechanics({"instance_id": "escort_quest_fail"}, {"objective": objective})
        self.assertNotIn("target_npc_instance_id", objective)

    def test_spawn_on_start_with_missing_fields_is_a_no_op(self):
        qm = self.world.quest_manager
        stage_data = {"objective": {}, "spawn_on_start": {"template_id": "goblin"}}  # no region/room
        count_before = len(self.world.npcs)
        qm._setup_stage_mechanics({"instance_id": "spawn_quest_missing"}, stage_data)
        self.assertEqual(count_before, len(self.world.npcs))

    def test_spawn_on_start_with_failed_npc_creation_is_a_no_op(self):
        qm = self.world.quest_manager
        stage_data = {
            "objective": {},
            "spawn_on_start": {"template_id": "not_a_real_template", "region_id": "town", "room_id": "town_square"},
        }
        count_before = len(self.world.npcs)
        qm._setup_stage_mechanics({"instance_id": "spawn_quest_fail"}, stage_data)
        self.assertEqual(count_before, len(self.world.npcs))

    def test_procedural_item_placement_skips_regions_with_no_rooms(self):
        # A room-less region (like the real "dynamic_themes" theme-definition
        # entry in world.regions) must never be a candidate for random.choice,
        # or this crashes with IndexError roughly 1-in-N times in the real game.
        qm = self.world.quest_manager
        from engine.world.region import Region
        empty_region = Region("Empty", "No rooms.", obj_id="truly_empty_region")
        self.world.add_region("truly_empty_region", empty_region)
        objective = {
            "is_procedural_item": True,
            "procedural_item_data": {"template_id": "item_starter_dagger", "name": "Survivor Dagger"},
        }
        quest_data = {"instance_id": "proc_quest_survives"}
        for _ in range(30):  # exercise random.choice enough to hit the empty region if unfiltered
            qm._setup_stage_mechanics(quest_data, {"objective": objective})  # must not raise

    def test_procedural_item_is_placed_in_a_room(self):
        qm = self.world.quest_manager
        objective = {
            "is_procedural_item": True,
            "procedural_item_data": {"template_id": "item_starter_dagger", "name": "The Special Dagger"},
        }
        quest_data = {"instance_id": "proc_quest"}
        qm._setup_stage_mechanics(quest_data, {"objective": objective})
        found = False
        for region in self.world.regions.values():
            for room in region.rooms.values():
                if any(getattr(i, "name", "") == "The Special Dagger" for i in room.items):
                    found = True
        self.assertTrue(found)

    def test_escort_spawns_stationary_npc_and_records_instance_id(self):
        qm = self.world.quest_manager
        objective = {
            "type": "escort",
            "spawn_config": {
                "template_id": "village_elder", "name": "Escort Target",
                "region_id": "town", "room_id": "town_square",
            },
        }
        quest_data = {"instance_id": "escort_quest"}
        qm._setup_stage_mechanics(quest_data, {"objective": objective})
        self.assertIn("target_npc_instance_id", objective)
        npc = self.world.get_npc(objective["target_npc_instance_id"])
        self.assertIsNotNone(npc)
        self.assertEqual("stationary", npc.behavior_type)
        self.assertTrue(npc.properties.get("is_escort_target"))

    def test_spawn_on_start_creates_boss_when_absent(self):
        qm = self.world.quest_manager
        stage_data = {
            "objective": {},
            "spawn_on_start": {
                "template_id": "goblin", "region_id": "town", "room_id": "town_square",
                "name_override": "Boss Goblin",
            },
        }
        before = sum(1 for n in self.world.npcs.values() if n.name == "Boss Goblin")
        qm._setup_stage_mechanics({"instance_id": "spawn_quest"}, stage_data)
        after = sum(1 for n in self.world.npcs.values() if n.name == "Boss Goblin")
        self.assertEqual(before + 1, after)

    def test_spawn_on_start_without_name_override_uses_template_name(self):
        qm = self.world.quest_manager
        stage_data = {
            "objective": {},
            "spawn_on_start": {"template_id": "goblin", "region_id": "town", "room_id": "town_square"},
        }
        count_before = len(self.world.npcs)
        qm._setup_stage_mechanics({"instance_id": "spawn_quest_no_override"}, stage_data)
        self.assertEqual(count_before + 1, len(self.world.npcs))

    def test_spawn_on_start_skips_when_boss_already_alive(self):
        qm = self.world.quest_manager
        existing = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="already_here")
        existing.current_region_id = "town"
        existing.is_alive = True
        self.world.add_npc(existing)
        stage_data = {
            "objective": {},
            "spawn_on_start": {"template_id": "goblin", "region_id": "town", "room_id": "town_square"},
        }
        count_before = len(self.world.npcs)
        qm._setup_stage_mechanics({"instance_id": "spawn_quest2"}, stage_data)
        self.assertEqual(count_before, len(self.world.npcs))


class TestHandleRoomEntry(GameTestBase):
    def test_quests_state_none_returns_empty_list(self):
        qm = self.world.quest_manager
        original = self.player.runtime_state.quests
        self.player.runtime_state.quests = None
        try:
            self.assertEqual([], qm.handle_room_entry(self.player))
        finally:
            self.player.runtime_state.quests = original

    def test_non_active_quest_state_is_skipped(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["inactive_q"] = {"state": "ready_to_complete"}
        result = qm.handle_room_entry(self.player)
        self.assertEqual([], result)

    def test_spawn_on_entry_dialog_override_merges_onto_base_template(self):
        """A spawn_on_entry `dialog` override (e.g. a negotiation-specific
        greeting) must merge onto the base template's dialog, not replace
        it outright -- otherwise a quest boss loses its other lines
        (threat/flee) just for having a custom greeting authored."""
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["spawn_dialog_q"] = {
            "state": "active",
            "current_stage_index": 0,
            "stages": [
                {
                    "objective": {},
                    "spawn_on_entry": {
                        "template_id": "bandit",
                        "region_id": self.player.current_region_id,
                        "room_id": self.player.current_room_id,
                        "name_override": "Negotiator",
                        "behavior_type": "stationary",
                        "dialog": {"greeting": "Let's talk business."},
                    },
                }
            ],
        }
        qm.handle_room_entry(self.player)
        spawned = next(n for n in self.world.npcs.values() if n.name == "Negotiator")
        self.assertEqual("Let's talk business.", spawned.dialog.get("greeting"))
        # The base "bandit" template's other dialog lines survive the merge.
        self.assertIn("threat", spawned.dialog)
        self.assertIn("flee", spawned.dialog)

    def test_spawn_on_entry_triggers_when_location_matches(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["spawn_entry_q"] = {
            "state": "active",
            "current_stage_index": 0,
            "stages": [
                {
                    "objective": {},
                    "spawn_on_entry": {
                        "template_id": "goblin",
                        "region_id": self.player.current_region_id,
                        "room_id": self.player.current_room_id,
                        "name_override": "Ambush Goblin",
                        "behavior_type": "aggressive",
                    },
                }
            ],
        }
        result = qm.handle_room_entry(self.player)
        self.assertTrue(any("Ambush Goblin" in m for m in result))
        stage = self.player.runtime_state.quests.active["spawn_entry_q"]["stages"][0]
        self.assertTrue(stage["_spawn_on_entry_triggered"])

    def test_spawn_on_entry_without_template_id_skips_boss_creation(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["spawn_entry_no_tid"] = {
            "state": "active",
            "current_stage_index": 0,
            "stages": [
                {
                    "objective": {},
                    "spawn_on_entry": {
                        "region_id": self.player.current_region_id,
                        "room_id": self.player.current_room_id,
                    },
                }
            ],
        }
        result = qm.handle_room_entry(self.player)
        self.assertEqual([], result)

    def test_spawn_on_entry_without_overrides_uses_template_defaults(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["spawn_entry_no_overrides"] = {
            "state": "active",
            "current_stage_index": 0,
            "stages": [
                {
                    "objective": {},
                    "spawn_on_entry": {
                        "template_id": "goblin",
                        "region_id": self.player.current_region_id,
                        "room_id": self.player.current_room_id,
                    },
                }
            ],
        }
        result = qm.handle_room_entry(self.player)
        self.assertTrue(any("steps out from the shadows" in m for m in result))

    def test_spawn_on_entry_with_unknown_template_yields_no_boss_message(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["spawn_entry_bad_template"] = {
            "state": "active",
            "current_stage_index": 0,
            "stages": [
                {
                    "objective": {},
                    "spawn_on_entry": {
                        "template_id": "not_a_real_template",
                        "region_id": self.player.current_region_id,
                        "room_id": self.player.current_room_id,
                    },
                }
            ],
        }
        result = qm.handle_room_entry(self.player)
        self.assertEqual([], result)

    def test_spawn_on_entry_does_not_trigger_twice(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["spawn_entry_q2"] = {
            "state": "active",
            "current_stage_index": 0,
            "stages": [
                {
                    "objective": {},
                    "_spawn_on_entry_triggered": True,
                    "spawn_on_entry": {
                        "template_id": "goblin",
                        "region_id": self.player.current_region_id,
                        "room_id": self.player.current_room_id,
                    },
                }
            ],
        }
        result = qm.handle_room_entry(self.player)
        self.assertEqual([], result)

    def test_spawn_on_entry_location_mismatch_does_not_trigger(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["spawn_entry_q3"] = {
            "state": "active",
            "current_stage_index": 0,
            "stages": [
                {
                    "objective": {},
                    "spawn_on_entry": {
                        "template_id": "goblin", "region_id": "nowhere", "room_id": "nowhere_room",
                    },
                }
            ],
        }
        result = qm.handle_room_entry(self.player)
        self.assertEqual([], result)

    def test_scout_objective_reports_reached_target(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["scout_q"] = {
            "state": "active",
            "title": "Scout the Ruins",
            "current_stage_index": 0,
            "stages": [
                {
                    "objective": {
                        "type": "scout",
                        "target_region": self.player.current_region_id,
                        "target_room_id": self.player.current_room_id,
                    },
                }
            ],
        }
        result = qm.handle_room_entry(self.player)
        self.assertTrue(any("reached the target location" in m for m in result))
        self.assertEqual("ready_to_complete", self.player.runtime_state.quests.active["scout_q"]["state"])

    def test_no_objective_is_skipped(self):
        qm = self.world.quest_manager
        self.player.runtime_state.quests.active["no_obj_q"] = {
            "state": "active",
            "current_stage_index": 0,
            "stages": [{}],
        }
        result = qm.handle_room_entry(self.player)
        self.assertEqual([], result)


if __name__ == "__main__":
    import unittest
    unittest.main()
