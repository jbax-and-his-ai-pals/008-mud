# tests/singles/test_dialogue_entries.py
"""A conversation can open somewhere else the second time, and tells you how to answer.

A graph's `root` is where it always opened, so an NPC repeated their whole greeting however
often you came back. A graph may now list `entries`: [{"node", "condition"}], tried in order, the
first whose condition holds is where the conversation opens; `root` is what is left. Every
numbered list of replies also ends with how to pick one (`reply <number>`).
"""

import unittest

from engine.dialogue.manager import parse_graph
from tests.fixtures import GameTestBase


def _graph(entries=None):
    payload = {
        "id": "probe", "root": "first",
        "nodes": {
            "first": {"text": "Welcome.", "choices": [{"text": "Bye.", "end": True}]},
            "again": {"text": "Back so soon?", "choices": [{"text": "Bye.", "end": True}]},
            "grudge": {"text": "You again.", "choices": [{"text": "Bye.", "end": True}]},
        },
    }
    if entries is not None:
        payload["entries"] = entries
    return parse_graph(payload, "probe", "probe.json")


FLAG = lambda name: {"kind": "flag", "flag": name}  # noqa: E731


class TestEntries(GameTestBase):
    def setUp(self):
        super().setUp()
        self.manager = self.world.dialogue_manager if hasattr(self.world, "dialogue_manager") else None
        if self.manager is None:
            from engine.dialogue.manager import manager_for
            self.manager = manager_for(self.world)
        self.npc = next(iter(self.world.npcs.values()))

    def opens_at(self, graph):
        return self.manager.open(self.player, self.npc, graph).node_id

    def test_without_entries_it_opens_at_the_root(self):
        graph, issues = _graph()
        self.assertEqual([], issues)
        self.assertEqual("first", self.opens_at(graph))

    def test_the_first_entry_whose_condition_holds_is_where_it_opens(self):
        graph, issues = _graph([
            {"node": "grudge", "condition": FLAG("insulted")},
            {"node": "again", "condition": FLAG("met")},
        ])
        self.assertEqual([], issues)
        self.assertEqual("first", self.opens_at(graph), "no condition holds yet")
        self.player.flags["met"] = True
        self.assertEqual("again", self.opens_at(graph))
        self.player.flags["insulted"] = True
        self.assertEqual("grudge", self.opens_at(graph), "the earlier entry wins")

    def test_an_entry_with_no_condition_always_applies(self):
        graph, _issues = _graph([{"node": "again"}])
        self.assertEqual("again", self.opens_at(graph))

    def test_an_explicit_node_still_beats_the_entries(self):
        graph, _issues = _graph([{"node": "again"}])
        self.assertEqual("first", self.manager.open(self.player, self.npc, graph, node_id="first").node_id)

    def test_a_bad_entry_is_reported(self):
        _graph_obj, issues = _graph([{"condition": FLAG("x")}])
        self.assertTrue(any("entries[0] needs a 'node'" in i for i in issues), issues)
        _graph_obj, issues = _graph([{"node": "nowhere"}])
        self.assertTrue(any("'nowhere' is not a node" in i for i in issues), issues)
        _graph_obj, issues = _graph("everything")
        self.assertTrue(any("entries must be a list" in i for i in issues), issues)

    def test_every_list_of_replies_says_how_to_answer(self):
        graph, _issues = _graph()
        node = self.manager.open(self.player, self.npc, graph)
        text = self.manager.render_node(self.player, self.npc, node, self.manager.current(self.player))
        self.assertIn("reply <number>", text)


class TestEndingNodes(GameTestBase):
    """`"end": true` on a node: the NPC has the last word and the conversation closes."""

    def setUp(self):
        super().setUp()
        self.manager = self.world.dialogue_manager
        self.npc = next(iter(self.world.npcs.values()))

    def graph(self, node_extra=None):
        payload = {
            "id": "probe", "root": "first",
            "nodes": {
                "first": {"text": "Choose.", "choices": [{"text": "Go on.", "next_node": "last"}]},
                "last": {"text": "Farewell.", **(node_extra or {"end": True})},
            },
        }
        return parse_graph(payload, "probe", "probe.json")

    def test_an_ending_node_offers_nothing_and_closes_the_conversation(self):
        graph, issues = self.graph()
        self.assertEqual([], issues)
        node = self.manager.open(self.player, self.npc, graph)
        session = self.manager.current(self.player)
        session.node_id = "last"
        text = self.manager.render_node(self.player, self.npc, graph.node("last"), session, reply=True)
        self.assertIn("speaks:", text)
        self.assertNotIn("1.", text)
        self.assertNotIn("That seems to be all", text)
        self.assertTrue(graph.node("last").ends_conversation)
        self.assertIsNotNone(node)

    def test_an_ending_node_that_also_offers_replies_is_refused(self):
        _graph, issues = self.graph({"end": True, "choices": [{"text": "Wait.", "end": True}]})
        self.assertTrue(any("could never be chosen" in i for i in issues), issues)

    def test_end_must_be_true_or_false(self):
        _graph, issues = self.graph({"end": "yes"})
        self.assertTrue(any("end must be true or false" in i for i in issues), issues)


if __name__ == "__main__":
    unittest.main()
