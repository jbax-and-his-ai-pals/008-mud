# tests/singles/test_p5_dialogue.py
"""P5 dialogue system: authored graphs, conditions, effects, negotiation.

The model this replaces: `data/dialogue/` was never loaded (the content loader
globs regions/npcs/items/crafting and nothing else), so the only branching
conversation in the game was dead code that also referenced two ids that did not
exist. What worked was a flat `dialog` keyword dict, and even that only worked
for its `greeting` key -- nothing called `npc.talk(topic)`, so ten of a smith's
eleven authored lines were unreachable.
"""

import json
import tempfile
import unittest
from pathlib import Path

from engine.conditions import evaluate
from engine.dialogue import effects as dialogue_effects
from engine.dialogue.manager import DialogueManager, parse_graph, structural_issues
from engine.dialogue import runner as dialogue_runner
from engine.npcs.npc_factory import NPCFactory
from engine.player import Player
from engine.server.content_set import load_content_set, validate_content_set
from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER, make_test_server


def _graph(payload, graph_id="probe"):
    graph, issues = parse_graph(payload, graph_id, "probe.json")
    return graph, issues


class _FakeWorld:
    """Minimal world for manager unit tests."""

    def __init__(self, content_root=None):
        self.content_root = content_root
        self.item_templates = {}
        self.npcs = {}
        self.regions = {}
        self.server = None
        self.game = None

    def ruleset_section(self, name):
        return {}

    def has_capability(self, capability):
        return True

    def get_region(self, region_id):
        return self.regions.get(region_id)

    def get_npc(self, npc_id):
        return self.npcs.get(npc_id)


# -- graph parsing ------------------------------------------------------------

class TestGraphParsing(unittest.TestCase):
    def test_nodes_choices_and_string_shorthand(self):
        graph, issues = _graph({
            "root": "greeting",
            "nodes": {
                "greeting": {
                    "text": "Well met.",
                    "choices": [
                        {"text": "Hello.", "next_node": "more"},
                        {"text": "Goodbye.", "end": True},
                    ],
                },
                "more": "That is all.",
            },
        })
        self.assertEqual([], issues)
        self.assertEqual(["greeting", "more"], graph.node_ids())
        greeting = graph.node("greeting")
        self.assertEqual("Well met.", greeting.text)
        self.assertEqual(2, len(greeting.choices))
        self.assertTrue(greeting.choices[1].ends_conversation)
        # A bare string node is a line with no choices; conversations end.
        self.assertEqual([], graph.node("more").choices)

    def test_root_defaults_with_a_reported_assumption(self):
        graph, issues = _graph({"nodes": {"opening": "Hello."}})
        self.assertEqual("opening", graph.root)
        self.assertTrue(any("does not declare 'root'" in issue for issue in issues))

    def test_missing_root_is_reported(self):
        graph, issues = _graph({"root": "nowhere", "nodes": {"a": "Hi."}})
        self.assertTrue(any("root 'nowhere' is not a node" in issue for issue in issues))

    def test_dangling_next_node_is_reported(self):
        graph, issues = _graph({
            "root": "a",
            "nodes": {"a": {"text": "Hi.", "choices": [{"text": "On.", "next_node": "gone"}]}},
        })
        self.assertTrue(any("'gone' is not a node" in issue for issue in issues))

    def test_choice_that_goes_nowhere_is_reported(self):
        graph, issues = _graph({
            "root": "a",
            "nodes": {"a": {"text": "Hi.", "choices": [{"text": "Hm."}]}},
        })
        self.assertTrue(any("goes nowhere" in issue for issue in issues))

    def test_unknown_effect_is_reported(self):
        graph, issues = _graph({
            "root": "a",
            "nodes": {"a": {"text": "Hi.", "choices": [
                {"text": "Take this.", "effects": {"give_pony": "item_pony"}, "end": True},
            ]}},
        })
        self.assertTrue(any("unknown effect 'give_pony'" in issue for issue in issues))

    def test_skill_check_needs_both_branches(self):
        graph, issues = _graph({
            "root": "a",
            "nodes": {"a": {"text": "Hi.", "choices": [
                {"text": "Try.", "check": {"skill": "diplomacy", "difficulty": 5, "success_node": "b"}},
            ]}, "b": "Won."},
        })
        self.assertTrue(any("has no fail_node" in issue for issue in issues))

    def test_a_graph_with_no_nodes_is_unusable(self):
        graph, issues = _graph({"root": "a"})
        self.assertIsNone(graph)
        self.assertTrue(any("has no nodes" in issue for issue in issues))

    def test_structural_issues_can_be_called_on_a_built_graph(self):
        graph, _issues = _graph({"root": "a", "nodes": {"a": "Hi."}})
        self.assertEqual([], structural_issues(graph))


# -- loading ------------------------------------------------------------------

class TestDialogueLoading(unittest.TestCase):
    def test_shipped_content_loads_without_issues(self):
        server = make_test_server()
        try:
            manager = server.dialogue_manager
            self.assertEqual([], manager.issues, "dialogue content has problems")
            self.assertIn("grenda_forge", manager.graphs)
        finally:
            server.shutdown()

    def test_loader_reads_every_json_file_in_the_directory(self):
        with tempfile.TemporaryDirectory() as root:
            dialogue_dir = Path(root) / "dialogue"
            dialogue_dir.mkdir(parents=True)
            (dialogue_dir / "one.json").write_text(
                json.dumps({"nodes": {"a": "First."}}), encoding="utf-8"
            )
            (dialogue_dir / "two.json").write_text(
                json.dumps({"id": "second", "nodes": {"a": "Second."}}), encoding="utf-8"
            )
            manager = DialogueManager(_FakeWorld(content_root=root))
            self.assertEqual(["one", "second"], sorted(manager.graphs))
            # id wins over the filename
            self.assertIsNotNone(manager.get("second"))
            self.assertIsNone(manager.get("two"))

    def test_a_missing_directory_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as root:
            manager = DialogueManager(_FakeWorld(content_root=root))
            self.assertEqual({}, manager.graphs)
            self.assertEqual([], manager.issues)

    def test_broken_json_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as root:
            dialogue_dir = Path(root) / "dialogue"
            dialogue_dir.mkdir(parents=True)
            (dialogue_dir / "broken.json").write_text("{not json", encoding="utf-8")
            manager = DialogueManager(_FakeWorld(content_root=root))
            self.assertEqual({}, manager.graphs)
            self.assertTrue(manager.issues)

    def test_graph_for_npc_reads_the_template_property(self):
        server = make_test_server()
        try:
            npc = server.world.get_npc("blacksmith_grenda_forge")
            self.assertIsNotNone(npc)
            graph = server.dialogue_manager.graph_for_npc(npc)
            self.assertIsNotNone(graph)
            self.assertEqual("grenda_forge", graph.graph_id)

            plain = NPCFactory.create_npc_from_template("villager", server.world)
            self.assertIsNone(server.dialogue_manager.graph_for_npc(plain))
        finally:
            server.shutdown()


# -- validation ---------------------------------------------------------------

def _write_content_set(root: Path, **overrides) -> Path:
    """A copy of the shipped content set, with files replaced for the test.

    `validate_content_set` walks a whole data root, so the honest way to test a
    validator is to hand it a real content set and break one thing.
    """
    source = Path(FANTASY_FRONTIER)
    target = root / "content_set"
    import shutil

    shutil.copytree(source, target)
    for relative, payload in overrides.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


class TestDialogueValidation(unittest.TestCase):
    def test_shipped_content_set_validates(self):
        issues = validate_content_set(Path(FANTASY_FRONTIER))
        errors = [issue for issue in issues if issue.severity == "error"]
        self.assertEqual([], errors, [issue.message for issue in errors])

    def test_npc_pointing_at_a_missing_graph_is_an_error(self):
        with tempfile.TemporaryDirectory() as root:
            target = _write_content_set(Path(root))
            npc_path = target / "data" / "npcs" / "villagers.json"
            payload = json.loads(npc_path.read_text(encoding="utf-8"))
            payload["blacksmith"]["properties"]["dialogue"] = "no_such_graph"
            npc_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            issues = validate_content_set(target)
            messages = [issue.message for issue in issues if issue.severity == "error"]
            self.assertTrue(
                any("missing dialogue graph 'no_such_graph'" in message for message in messages),
                messages,
            )

    def test_a_graph_that_leads_nowhere_is_an_error(self):
        with tempfile.TemporaryDirectory() as root:
            target = _write_content_set(Path(root), **{
                "data/dialogue/broken.json": {
                    "id": "broken_graph",
                    "root": "a",
                    "nodes": {"a": {"text": "Hi.", "choices": [
                        {"text": "Onwards.", "next_node": "elsewhere"},
                    ]}},
                }
            })
            issues = validate_content_set(target)
            messages = [issue.message for issue in issues if issue.severity == "error"]
            self.assertTrue(any("'elsewhere' is not a node" in m for m in messages), messages)

    def test_an_effect_naming_a_missing_item_is_an_error(self):
        with tempfile.TemporaryDirectory() as root:
            target = _write_content_set(Path(root), **{
                "data/dialogue/gift.json": {
                    "id": "gift_graph",
                    "root": "a",
                    "nodes": {"a": {"text": "Take this.", "choices": [
                        {"text": "Thanks.", "end": True,
                         "effects": {"give_item": "item_nonexistent_thing"}},
                    ]}},
                }
            })
            issues = validate_content_set(target)
            messages = [issue.message for issue in issues if issue.severity == "error"]
            self.assertTrue(
                any("item_nonexistent_thing" in m and "not defined" in m for m in messages),
                messages,
            )

    def test_a_condition_with_an_unknown_kind_is_an_error(self):
        with tempfile.TemporaryDirectory() as root:
            target = _write_content_set(Path(root), **{
                "data/dialogue/gated.json": {
                    "id": "gated_graph",
                    "root": "a",
                    "nodes": {"a": {"text": "Hi.", "choices": [
                        {"text": "Secret.", "end": True,
                         "condition": {"kind": "has_vibes", "value": 3}},
                    ]}},
                }
            })
            issues = validate_content_set(target)
            messages = [issue.message for issue in issues if issue.severity == "error"]
            self.assertTrue(any("unknown condition kind 'has_vibes'" in m for m in messages), messages)

    def test_an_unreferenced_graph_is_only_a_warning(self):
        with tempfile.TemporaryDirectory() as root:
            target = _write_content_set(Path(root), **{
                "data/dialogue/orphan.json": {
                    "id": "orphan_graph",
                    "root": "a",
                    "nodes": {"a": "Nobody says this."},
                }
            })
            issues = validate_content_set(target)
            warnings = [issue for issue in issues if issue.severity == "warning"]
            errors = [issue for issue in issues if issue.severity == "error"]
            self.assertEqual([], errors, [issue.message for issue in errors])
            self.assertTrue(
                any("not referenced by any NPC template" in issue.message for issue in warnings),
                [issue.message for issue in warnings],
            )

    def test_a_negotiate_outcome_must_say_where_it_leads(self):
        """The rule that would have caught an unreachable campaign ending."""
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "content_set"
            import shutil

            shutil.copytree(Path(FANTASY_FRONTIER), target)
            quests_path = target / "data" / "quests" / "quests.json"
            payload = json.loads(quests_path.read_text(encoding="utf-8"))
            success = payload["quest_bandit_lieutenant"]["stages"][0]["objective"]["choices"]["success"]
            success.pop("complete", None)  # say nothing about what happens next
            quests_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            issues = validate_content_set(target)
            messages = [issue.message for issue in issues if issue.severity == "error"]
            self.assertTrue(
                any("must declare next_stage or complete: true" in m for m in messages),
                messages,
            )


# -- conditions and effects ---------------------------------------------------

class TestChoiceConditions(unittest.TestCase):
    def setUp(self):
        self.server = make_test_server()
        self.manager = self.server.dialogue_manager
        self.session = self.server.create_session(player_id="conditions")
        self.server.execute_command(self.session.session_id, "char create Rowan")
        self.player = self.server.get_player_for_session(self.session.session_id)
        self.npc = self.server.world.get_npc("blacksmith_grenda_forge")
        self.graph = self.manager.graph_for_npc(self.npc)

    def tearDown(self):
        self.server.shutdown()

    def _labels(self, node_id):
        node = self.graph.node(node_id)
        return [choice.label for choice in self.manager.offered_choices(self.player, node)]

    def test_a_gated_reply_is_not_offered_until_its_condition_holds(self):
        self.assertNotIn("Show me how to make one.", self._labels("working"))

        from engine.items.item_factory import ItemFactory

        for _ in range(2):
            self.player.inventory.add_item(
                ItemFactory.create_item_from_template("item_iron_ingot", self.server.world)
            )
        self.assertIn("Show me how to make one.", self._labels("working"))

    def test_relationship_gates_a_reply(self):
        self.assertNotIn(
            "That shipment you were waiting on -- what happened to it?", self._labels("greeting")
        )
        self.player.npc_relationships["blacksmith"] = 5
        self.assertIn(
            "That shipment you were waiting on -- what happened to it?", self._labels("greeting")
        )

    def test_visited_region_gates_a_reply(self):
        forest_reply = "I've been up to the woods already."
        self.assertNotIn(forest_reply, self._labels("where"))
        self.manager.apply(self.player, self.npc, {})  # no-op, keeps the server wired
        self.server.advancement_manager.record(
            self.player, "region", "forest", payload={"region_id": "forest"}
        )
        self.assertIn(forest_reply, self._labels("where"))


class TestEffectInterpreter(unittest.TestCase):
    """The interpreter is shared: dialogue choices and topic responses."""

    def setUp(self):
        self.server = make_test_server()
        self.session = self.server.create_session(player_id="effects")
        self.server.execute_command(self.session.session_id, "char create Rowan")
        self.player = self.server.get_player_for_session(self.session.session_id)
        self.npc = self.server.world.get_npc("blacksmith_grenda_forge")

    def tearDown(self):
        self.server.shutdown()

    def _apply(self, block):
        return self.manager.apply(self.player, self.npc, block)

    @property
    def manager(self):
        return self.server.dialogue_manager

    def test_grant_recipe_teaches_and_records_it(self):
        self.assertNotIn("forge_travelers_hatchet", self.player.known_recipe_ids)
        report = self._apply({"grant_recipe": "forge_travelers_hatchet"})
        self.assertIn("forge_travelers_hatchet", self.player.known_recipe_ids)
        self.assertIn("grant_recipe forge_travelers_hatchet", report.applied)
        # Learning it is worth XP the first time (P4's `recipe` grant).
        self.assertGreater(self.player.total_experience(), 0)
        self.assertTrue(
            self.server.advancement_manager.has_entry(self.player, "recipe:forge_travelers_hatchet")
        )

    def test_teaching_twice_does_not_pay_twice(self):
        self._apply({"grant_recipe": "forge_travelers_hatchet"})
        experience = self.player.total_experience()
        second = self._apply({"grant_recipe": "forge_travelers_hatchet"})
        self.assertIn("already known", " ".join(second.applied))
        self.assertEqual(experience, self.player.total_experience())

    def test_set_flag_is_readable_by_the_flag_condition(self):
        self.assertFalse(evaluate({"kind": "flag", "flag": "grenda_asked_about_caravan"}, self.player))
        self._apply({"set_flag": "grenda_asked_about_caravan"})
        self.assertTrue(evaluate({"kind": "flag", "flag": "grenda_asked_about_caravan"}, self.player))

    def test_adjust_relationship_moves_the_ledger(self):
        report = self._apply({"adjust_relationship": {"amount": 5}})
        self.assertIn("relationship blacksmith +5", " ".join(report.applied))
        self.assertEqual(5, self.player.npc_relationships.get("blacksmith"))
        self._apply({"adjust_relationship": {"amount": -2}})
        self.assertEqual(3, self.player.npc_relationships.get("blacksmith"))

    def test_relationship_cannot_go_negative(self):
        self._apply({"adjust_relationship": {"amount": -50}})
        self.assertEqual(0, self.player.npc_relationships.get("blacksmith"))

    def test_give_and_take_items(self):
        report = self._apply({"give_item": {"item_id": "item_iron_ingot", "quantity": 2}})
        self.assertEqual(2, self.player.inventory.count_item("item_iron_ingot"))
        self.assertTrue(any("You receive" in message for message in report.messages))

        taken = self._apply({"take_item": {"item_id": "item_iron_ingot", "quantity": 1}})
        self.assertEqual(1, self.player.inventory.count_item("item_iron_ingot"))
        self.assertIn("took item_iron_ingot", taken.applied)

    def test_taking_what_the_player_does_not_have_fails_softly(self):
        report = self._apply({"take_item": "item_iron_ingot"})
        self.assertEqual([], report.applied)
        self.assertTrue(report.failed)

    def test_give_gold(self):
        before = self.player.runtime_state.gold
        self._apply({"give_gold": 7})
        self.assertEqual(before + 7, self.player.runtime_state.gold)

    def test_stacking_effects_apply_in_one_call(self):
        report = self._apply({
            "set_flag": "met_grenda",
            "adjust_relationship": {"amount": 2},
            "give_item": "item_leather_strip",
        })
        self.assertEqual(3, len(report.applied))
        self.assertTrue(self.player.flags.get("met_grenda"))
        self.assertEqual(1, self.player.inventory.count_item("item_leather_strip"))

    def test_unknown_effect_is_reported_not_obeyed(self):
        report = self._apply({"give_pony": "item_pony"})
        self.assertIn("give_pony", report.unknown)
        self.assertEqual([], report.applied)

    def test_teach_spell(self):
        # The default wanderer starts with no spells, which is the point.
        report = self._apply({"teach_spell": "minor_heal"})
        self.assertIn("minor_heal", self.player.runtime_state.magic.known_spells)
        self.assertTrue(any("learn" in message.lower() for message in report.messages), report.messages)

    def test_move_npc_moves_it(self):
        report = self._apply({"move_npc": {"npc": "blacksmith", "region": "forest", "room": "forest_edge"}})
        self.assertEqual("forest", self.npc.current_region_id)
        self.assertEqual("forest_edge", self.npc.current_room_id)
        self.assertIn("moved", " ".join(report.applied))

    def test_grant_discovery_records_it(self):
        self._apply({"grant_discovery": "rose_quartz"})
        self.assertIn("rose_quartz", self.player.discoveries)

    def test_reveal_exit_opens_a_declared_hidden_exit(self):
        """A no-op without a real hidden exit, and an error at validation time."""
        report = self._apply({"reveal_exit": {"room": "town:blacksmith_interior", "direction": "down"}})
        self.assertEqual([], report.applied)
        self.assertTrue(report.failed)

    def test_a_describe_helper_exists_for_test_mode(self):
        text = dialogue_effects.describe_effects({"grant_recipe": "x", "give_gold": 3})
        self.assertIn("grant_recipe=x", text)
        self.assertIn("give_gold=3", text)


# -- sessions: matching, modes, rendering -------------------------------------

class TestConversationFlow(unittest.TestCase):
    def setUp(self):
        self.server = make_test_server()
        self.session = self.server.create_session(player_id="flow")
        self.server.execute_command(self.session.session_id, "char create Rowan")
        self.player = self.server.get_player_for_session(self.session.session_id)
        self.player.current_region_id = "town"
        self.player.current_room_id = "blacksmith_interior"
        self.npc = self.server.world.get_npc("blacksmith_grenda_forge")

    def tearDown(self):
        self.server.shutdown()

    def _command(self, text):
        return "\n".join(
            str(event["payload"])
            for event in self.server.execute_command(self.session.session_id, text)
            if event.get("type") == "text"
        )

    def test_talking_opens_the_authored_opening_line(self):
        output = self._command("talk grenda")
        self.assertIn("Well met", output)
        self.assertIn("What are you working on?", output)

    def test_a_reply_can_be_a_number_or_the_words(self):
        self._command("talk grenda")
        by_number = self._command("reply 1")
        self.assertIn("Hatchets", by_number)

        self._command("talk grenda")
        by_words = self._command("reply what are you working on")
        self.assertIn("Hatchets", by_words)

    def test_a_reply_can_use_an_authored_alias(self):
        self._command("talk grenda")
        output = self._command("reply the forge")
        self.assertIn("Hatchets", output)

    def test_an_unclear_reply_asks_again_instead_of_guessing(self):
        self._command("talk grenda")
        output = self._command("reply something entirely unrelated")
        self.assertIn("did not understand", output)
        # Still in the conversation, and shown the replies again.
        self.assertIn("What are you working on?", output)

    def test_a_gated_reply_cannot_be_chosen_by_number(self):
        self._command("talk grenda")
        self._command("reply 1")  # working
        output = self._command("reply 1")  # offered replies start at "Where would I get..."
        self.assertNotIn("Watch the hammer", output)
        self.assertNotIn("forge_travelers_hatchet", self.player.known_recipe_ids)

    def test_choosing_the_teaching_reply_grants_the_recipe(self):
        from engine.items.item_factory import ItemFactory

        for _ in range(2):
            self.player.inventory.add_item(
                ItemFactory.create_item_from_template("item_iron_ingot", self.server.world)
            )
        self._command("talk grenda")
        self._command("reply the forge")
        output = self._command("reply show me the pattern")
        self.assertIn("Watch the hammer", output)
        self.assertIn("forge_travelers_hatchet", self.player.known_recipe_ids)
        self.assertTrue(self.player.flags.get("grenda_taught_hatchet"))

    def test_ending_a_conversation_closes_it(self):
        self._command("talk grenda")
        self._command("reply 3")  # "No time. Goodbye."
        self.assertIsNone(self.server.dialogue_manager.current(self.player))
        self.assertIn("not in the middle of a conversation", self._command("reply 1"))

    def test_reply_outside_a_conversation_suggests_who_to_talk_to(self):
        self._command("talk grenda")
        self._command("reply 3")
        output = self._command("reply 1")
        self.assertIn("talk Grenda", output)

    def test_a_topic_typed_mid_conversation_reaches_the_flat_dialog_dict(self):
        """`talk <npc> <topic>` should answer the topic, not scold the player."""
        self._command("talk grenda")
        output = self._command("talk grenda patterns")
        self.assertIn("pattern", output.lower())
        self.assertNotIn("did not understand", output)

    def test_ask_reaches_the_flat_dialog_dict(self):
        """The flat dict's topics were unreachable: nothing called talk(topic)."""
        output = self._command("ask grenda about missing supplies")
        self.assertIn("crate of good iron", output)

    def test_flat_dialog_is_unreachable_for_an_unknown_topic(self):
        output = self._command("ask grenda about quadratic equations")
        self.assertIn("nothing to say", output)

    def test_test_mode_annotates_choices_and_player_mode_does_not(self):
        test_output = self._command("talk grenda")
        self.assertIn("[-> working]", test_output)
        self.assertIn("unavailable:", test_output)

        player_session = self.server.create_session("player_view", presentation_mode="player")
        self.server.execute_command(player_session.session_id, "char create Wren")
        player = self.server.get_player_for_session(player_session.session_id)
        player.current_region_id, player.current_room_id = "town", "blacksmith_interior"
        events = self.server.execute_command(player_session.session_id, "talk grenda")
        output = "\n".join(str(e["payload"]) for e in events if e.get("type") == "text")
        self.assertIn("Well met", output)
        self.assertNotIn("[->", output)
        self.assertNotIn("unavailable", output)
        self.assertNotIn("effects:", output)
        # The gated line is simply absent for a player.
        self.assertNotIn("what happened to it", output)

    def test_node_text_can_vary_by_mode(self):
        manager = self.server.dialogue_manager
        graph, issues = parse_graph({
            "root": "a",
            "nodes": {"a": {"text": {"player": "The forge roars.", "test": "node a"}}},
        }, "variant")
        self.assertEqual([], issues)
        node = graph.node("a")

        test_output = manager.render_node(self.player, self.npc, node)
        self.assertIn("node a", test_output)

        player_session = self.server.create_session("variant_view", presentation_mode="player")
        self.server.execute_command(player_session.session_id, "char create Wren")
        viewer = self.server.get_player_for_session(player_session.session_id)
        player_output = manager.render_node(viewer, self.npc, node)
        self.assertIn("The forge roars.", player_output)

    def test_match_choice_rejects_ambiguity(self):
        manager = self.server.dialogue_manager
        labels = ["Talk about the weather.", "Talk about the war."]
        self.assertEqual(0, manager.match_choice("talk about the weather", labels))
        self.assertIsNone(manager.match_choice("talk about", labels))
        self.assertIsNone(manager.match_choice("9", labels))


# -- negotiation (absorbed) ---------------------------------------------------

class TestNegotiationThroughDialogue(unittest.TestCase):
    def setUp(self):
        self.server = make_test_server()
        self.session = self.server.create_session(player_id="negotiation")
        self.server.execute_command(self.session.session_id, "char create Rowan")
        self.player = self.server.get_player_for_session(self.session.session_id)

    def tearDown(self):
        self.server.shutdown()

    def _command(self, text):
        return "\n".join(
            str(event["payload"])
            for event in self.server.execute_command(self.session.session_id, text)
            if event.get("type") == "text"
        )

    def _start_bandit_quest_with_boss(self):
        self.server.world.quest_manager.start_quest("quest_bandit_lieutenant", self.player)
        boss = NPCFactory.create_npc_from_template(
            "bandit_leader", self.server.world, instance_id="bandit_lieutenant_test",
            name="Bandit Lieutenant",
        )
        boss.current_region_id, boss.current_room_id = "forest", "forest_edge"
        self.server.world.npcs[boss.obj_id] = boss
        self.player.current_region_id = "forest"
        self.player.current_room_id = "forest_edge"
        return boss

    def test_a_pending_negotiation_is_detected_for_the_right_npc(self):
        boss = self._start_bandit_quest_with_boss()
        pending = dialogue_runner.pending_negotiation(self.player, boss)
        self.assertIsNotNone(pending)
        quest_id, objective = pending
        self.assertEqual("negotiate", objective.get("type"))
        self.assertTrue(quest_id.startswith("quest_bandit_lieutenant"))

        other = NPCFactory.create_npc_from_template("villager", self.server.world)
        self.assertIsNone(dialogue_runner.pending_negotiation(self.player, other))

    def test_talking_opens_the_negotiation_as_a_conversation(self):
        self._start_bandit_quest_with_boss()
        output = self._command("talk bandit")
        # The authored approach is offered as a reply, not resolved behind the
        # player's back.
        self.assertIn("village sent me", output)
        self.assertIn("Say nothing more", output)

    def test_successful_negotiation_completes_the_peaceful_ending(self):
        """The campaign's PEACEFUL_SUCCESS branch must be reachable.

        Its success outcome used to advance to the *next* stage -- "Kill the
        Lieutenant" -- so a truce turned into an order to commit murder and the
        two-ending campaign had one ending.
        """
        self._start_bandit_quest_with_boss()
        self._command("talk bandit")
        # Diplomacy 10 is winnable but not guaranteed; practice until it lands,
        # which also proves the check trains the skill (P4).
        for _ in range(12):
            if "success" in self._command("reply 1").lower():
                break
            if not self.server.dialogue_manager.current(self.player):
                self._command("talk bandit")
        self.assertEqual([], list(self.player.runtime_state.quests.active.keys()))
        self.assertTrue(self.player.runtime_state.quests.completed)

    def test_walking_away_leaves_the_negotiation_open(self):
        self._start_bandit_quest_with_boss()
        self._command("talk bandit")
        self._command("reply 2")
        self.assertIsNone(self.server.dialogue_manager.current(self.player))
        self.assertTrue(self.player.runtime_state.quests.active)


if __name__ == "__main__":
    unittest.main()
