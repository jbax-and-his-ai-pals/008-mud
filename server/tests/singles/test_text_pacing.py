# tests/singles/test_text_pacing.py
"""A dialogue node can ask for its words to be revealed gradually.

The server only marks the passage (`[[PACE:70]]...[[/PACE]]`); a client that reveals gradually
types it out, one that does not shows it at once. Default is no pacing at all.
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.server import content_set as validator
from engine.server.headless_server import HeadlessServer
from engine.utils.pacing import PACE_RANGE, TEXT_PACES, pace_quest_text, paced, resolve_pace

from tests.fixtures import STORY_FIXTURE

REPO_ROOT = Path(__file__).resolve().parents[3]
_MARKUP = re.compile(r"\[\[[^\]]*\]\]")
NL = chr(10)


def _raw(events):
    return "\n".join(str(e["payload"]) for e in events if e["type"] == "text")


class TestResolvingAPace(unittest.TestCase):
    def test_a_name_is_characters_per_second(self):
        self.assertEqual(70, resolve_pace("slow"))
        self.assertEqual(70, resolve_pace(" Slow "))
        self.assertEqual(set(TEXT_PACES), {"brisk", "measured", "slow", "solemn"})

    def test_a_number_in_range_is_itself(self):
        self.assertEqual(30, resolve_pace(30))
        self.assertEqual(PACE_RANGE[0], resolve_pace(PACE_RANGE[0]))

    def test_anything_else_is_no_pace(self):
        for value in (None, "", "instant", "glacial", 0, 4, 201, True, [], {}):
            self.assertIsNone(resolve_pace(value), value)

    def test_unpaced_text_is_returned_unchanged(self):
        self.assertEqual("hello", paced("hello", None))
        self.assertEqual("hello", paced("hello", "glacial"))
        self.assertEqual("[[PACE:70]]hello[[/PACE]]", paced("hello", "slow"))


class TestTheKingSpeaksSlowly(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(STORY_FIXTURE),
            deterministic_test_mode=True, default_presentation_mode="player",
        )
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="pace").session_id
        self.server.execute_command(self.sid, "char create Aldric")

    def test_his_orders_are_marked_for_gradual_reveal(self):
        said = _raw(self.server.execute_command(self.sid, "talk king"))
        self.assertIn("[[PACE:70]]", said)
        self.assertIn("[[/PACE]]", said)
        self.assertIn("Carry this package", _MARKUP.sub("", said.split("[[PACE:70]]", 1)[1].split("[[/PACE]]", 1)[0]))

    def test_only_his_words_are_paced_not_the_replies_or_the_instructions(self):
        said = _raw(self.server.execute_command(self.sid, "talk king"))
        paced_part = said.split("[[PACE:70]]", 1)[1].split("[[/PACE]]", 1)[0]
        self.assertNotIn("reply <number>", paced_part)
        self.assertNotIn("At once, my king", paced_part)

    def test_his_answer_to_a_reply_is_paced_too(self):
        self.server.execute_command(self.sid, "talk king")
        said = _raw(self.server.execute_command(self.sid, "reply 1"))
        self.assertIn("[[PACE:70]]", said)
        self.assertIn("Good. Be quick.", _MARKUP.sub("", said.split("[[PACE:70]]", 1)[1].split("[[/PACE]]", 1)[0]))

    def test_a_node_with_no_pace_is_not_marked(self):
        from engine.dialogue.graph import DialogueNode
        from engine.utils.pacing import paced as _paced

        self.assertEqual("x", _paced("x", DialogueNode(node_id="n", text="x").pace))


class TestQuestTextIsPacedByDefault(unittest.TestCase):
    def test_a_quest_paragraph_is_marked_and_the_text_around_it_is_not(self):
        text = "You walk on." + NL + NL + "[[GREEN]][Quest Accepted] Deliver it[[/]]" + NL + "Take it to the mayor." + NL + NL + "A bird sings."
        marked = pace_quest_text(text)
        self.assertEqual("You walk on." + NL + NL + "[[PACE:70]][[GREEN]][Quest Accepted] Deliver it[[/]]" + NL + "Take it to the mayor.[[/PACE]]" + NL + NL + "A bird sings.", marked)

    def test_updates_and_new_objectives_are_quest_text_too(self):
        for line in ("[Quest Update] Wolves: (1/3)", "[Objective Complete]", "New Objective: Find the shrine."):
            self.assertIn("[[PACE:70]]", pace_quest_text(line), line)

    def test_text_that_already_has_a_pace_is_left_alone(self):
        text = "[[PACE:20]][Quest Accepted] x[[/PACE]]"
        self.assertEqual(text, pace_quest_text(text))

    def test_no_pace_means_all_at_once(self):
        self.assertEqual("[Quest Accepted] x", pace_quest_text("[Quest Accepted] x", None))
        self.assertEqual("[Quest Accepted] x", pace_quest_text("[Quest Accepted] x", "instant"))

    def test_a_players_text_is_paced_and_an_authoring_session_is_not(self):
        for mode, expect in (("player", True), ("test", False)):
            server = HeadlessServer(
                db_path=":memory:", content_set_path=str(STORY_FIXTURE),
                deterministic_test_mode=True, default_presentation_mode=mode,
            )
            self.addCleanup(server.shutdown)
            sid = server.create_session(player_id=mode).session_id
            event = server._event("text", sid, "[Quest Update] Wolves: (1/3)")
            self.assertEqual(expect, "[[PACE:" in event["payload"], mode)

    def test_a_server_can_turn_it_off(self):
        server = HeadlessServer(
            db_path=":memory:", content_set_path=str(STORY_FIXTURE),
            deterministic_test_mode=True, default_presentation_mode="player",
        )
        self.addCleanup(server.shutdown)
        server.quest_text_pace = None
        sid = server.create_session(player_id="off").session_id
        self.assertEqual("[Quest Update] x", server._event("text", sid, "[Quest Update] x")["payload"])


class TestTheValidator(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "story_fixture"
        shutil.copytree(STORY_FIXTURE, self.package, ignore=shutil.ignore_patterns("saves", "editor"))

    def errors_with_pace(self, value):
        path = self.package / "data" / "dialogue" / "king_orders.json"
        graph = json.loads(path.read_text(encoding="utf-8"))
        graph["nodes"]["greeting"]["pace"] = value
        path.write_text(json.dumps(graph, indent=4), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return [i.message for i in issues if i.severity == "error"]

    def test_names_numbers_and_instant_pass(self):
        for good in ("slow", "solemn", 30, "instant"):
            self.assertEqual([], self.errors_with_pace(good), good)

    def test_anything_else_is_refused_with_what_would_work(self):
        for bad in ("glacial", 2, 900, True, ["slow"]):
            errors = self.errors_with_pace(bad)
            self.assertTrue(any(".pace" in m and "solemn" in m for m in errors), (bad, errors))


if __name__ == "__main__":
    unittest.main()
