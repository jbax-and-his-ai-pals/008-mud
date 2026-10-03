# tests/singles/test_dialogue_scenes.py
"""Leaving ends a conversation, and a scene insists on an answer.

A conversation used to stay open for ever: you could walk away from the king and still `reply` to
him from the road. Now walking away (or being taken away, or the other party going) ends it, and a
node marked `"must_answer": true` is a scene: until you answer, anything that acts on the world is
refused and the question is asked again. Looking, the pack, the journal and help still work.
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.server import content_set as validator
from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


class _Game:
    def __init__(self, case):
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(REPO_ROOT / "content_sets" / "ff4_slice"),
            deterministic_test_mode=True, default_presentation_mode="player",
        )
        case.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="scene").session_id
        self.server.execute_command(self.sid, "char create Cecil")
        self.player = self.server.get_player_for_session(self.sid)

    def say(self, command):
        events = self.server.execute_command(self.sid, command)
        return "\n".join(_MARKUP.sub("", str(e["payload"])) for e in events if e["type"] == "text")

    def where(self):
        return f"{self.player.current_region_id}:{self.player.current_room_id}"


class TestTheKingInsistsOnAnAnswer(unittest.TestCase):
    def setUp(self):
        self.game = _Game(self)
        self.game.say("talk king")

    def test_walking_away_is_refused_and_the_question_is_asked_again(self):
        said = self.game.say("go south")
        self.assertIn("King Aldous awaits your answer", said)
        self.assertIn("1. At once, my king.", said)
        self.assertEqual("varenholt:throne_room", self.game.where())

    def test_a_bare_exit_word_is_refused_too(self):
        self.assertIn("awaits your answer", self.game.say("south"))
        self.assertEqual("varenholt:throne_room", self.game.where())

    def test_acting_on_the_world_is_refused(self):
        for command in ("attack king", "cast dark wave", "drop dark blade", "use potion"):
            self.assertIn("awaits your answer", self.game.say(command), command)

    def test_reading_is_allowed(self):
        for command in ("look", "inventory", "status", "journal", "help"):
            self.assertNotIn("awaits your answer", self.game.say(command), command)

    def test_answering_releases_him(self):
        self.game.say("reply 1")
        self.assertNotIn("awaits your answer", self.game.say("go south"))
        self.assertNotEqual("varenholt:throne_room", self.game.where())

    def test_if_he_is_no_longer_there_nothing_holds_the_player(self):
        king = next(n for n in self.game.server.world.npcs.values() if n.template_id == "king_aldous" or "Aldous" in n.name)
        king.current_room_id = "barracks"
        self.assertNotIn("awaits your answer", self.game.say("go south"))


class TestADismissedCourierStaysOut(unittest.TestCase):
    def test_the_guards_keep_him_out_of_the_throne_room(self):
        game = _Game(self)
        game.say("talk king")
        game.say("reply 2")
        self.assertEqual("varenholt:courtyard", game.where())
        said = game.say("go north")
        self.assertIn("guards", said)
        self.assertEqual("varenholt:courtyard", game.where())

    def test_whatever_he_answers_the_guards_walk_him_out_and_shut_the_door(self):
        for choice in ("reply 1", "reply 2", "reply 4"):
            game = _Game(self)
            game.say("talk king")
            said = game.say(choice)
            self.assertEqual("varenholt:courtyard", game.where(), choice)
            self.assertIn("guards", said.lower(), choice)
            self.assertIn("guards", game.say("go north"), choice)
            self.assertEqual("varenholt:courtyard", game.where(), choice)

    def test_what_follows_is_in_order_and_spaced_apart(self):
        game = _Game(self)
        game.say("talk king")
        said = game.say("reply 1")
        nl = chr(10)
        king = said.index("King Aldous speaks")
        seal = said.index("The king presses his seal", king)
        guards = said.index("Two guards fall in", seal)
        banner = said.index("[VARENHOLT - CASTLE COURTYARD]", guards)
        self.assertTrue(said[king:seal].endswith(nl + nl), "a blank line between the king's words and what he does")
        self.assertTrue(said[seal:guards].endswith(nl + nl), "a blank line between his seal and the guards")
        self.assertTrue(said[guards:banner].endswith(nl + nl + nl), "two blank lines before the room you are taken to")

    def test_two_guards_stand_in_the_courtyard(self):
        game = _Game(self)
        game.say("talk king")
        game.say("reply 1")
        guards = [n for n in game.server.world.npcs.values()
                  if n.template_id == "castle_guard" and (n.current_region_id, n.current_room_id) == ("varenholt", "courtyard")]
        self.assertEqual(2, len(guards))
        self.assertIn("a castle guard, a castle guard", game.say("look"))


class TestKessaRidesAheadInView(unittest.TestCase):
    def setUp(self):
        self.game = _Game(self)
        self.game.player.current_region_id, self.game.player.current_room_id = "varenholt", "barracks"
        self.game.player.flags["obeyed_king"] = True

    def test_her_words_are_read_slowly_like_the_kings(self):
        raw = " ".join(str(e["payload"]) for e in self.game.server.execute_command(self.game.sid, "talk kessa") if e["type"] == "text")
        self.assertIn("[[PACE:70]]", raw)

    def test_saying_not_yet_does_not_leave_a_reply_hanging(self):
        self.game.say("talk kessa")
        said = self.game.say("reply 2")
        self.assertIn("Captain Kessa speaks", said)
        self.assertIn("The king does not like to be kept waiting", said)

    def test_we_see_her_leave(self):
        self.game.say("talk kessa")
        said = self.game.say("reply 1")
        self.assertIn("strides out the west door", said)
        self.assertLess(said.index("I will ride ahead"), said.index("strides out"), "she says it, then goes")
        self.assertNotIn("Kessa", self.game.say("look"), "and she is gone from the room")


class TestRosalindHealsOnRequest(unittest.TestCase):
    def setUp(self):
        self.game = _Game(self)
        self.player = self.game.player
        self.player.current_region_id, self.player.current_room_id = "varenholt", "chapel"
        self.player.health = 20
        self.player.runtime_state.gold = 100

    def test_fleet_members_are_tended_for_nothing(self):
        said = self.game.say("talk rosalind")
        self.assertIn("1. Tend my wounds.", said)
        self.assertNotIn("30 gil", said)
        self.game.say("reply 1")
        self.assertEqual(self.player.max_health, self.player.health)
        self.assertEqual(100, self.player.runtime_state.gold)

    def test_one_without_a_seal_pays(self):
        self.player.inventory.slots = [s for s in self.player.inventory.slots if not (s.item and s.item.obj_id == "item_commander_seal")]
        said = self.game.say("talk rosalind")
        self.assertIn("(30 gil)", said)
        self.game.say("reply 1")
        self.assertEqual(self.player.max_health, self.player.health)
        self.assertEqual(70, self.player.runtime_state.gold)

    def test_one_without_a_seal_or_the_coins_is_not_offered_it(self):
        self.player.inventory.slots = [s for s in self.player.inventory.slots if not (s.item and s.item.obj_id == "item_commander_seal")]
        self.player.runtime_state.gold = 5
        said = self.game.say("talk rosalind")
        self.assertNotIn("Tend my wounds", said)


class TestAgreeingToGoStartsTheErrand(unittest.TestCase):
    def test_i_will_go_is_an_answer_the_king_acknowledges_and_it_sets_the_errand_going(self):
        game = _Game(self)
        game.say("talk king")
        said = game.say("reply 4")
        self.assertIn("King Aldous speaks", said)
        self.assertIn("The King's Package", ", ".join(q.get("title", "") for q in game.player.runtime_state.quests.active.values()))
        self.assertNotIn("awaits your answer", game.say("go south"))


class TestNoEmptyReplies(unittest.TestCase):
    """A reply that only ends the conversation, with nothing said back, is a click for nothing."""

    def test_no_slice_node_is_just_one_plain_goodbye(self):
        import glob

        for path in sorted(glob.glob(str(REPO_ROOT / "content_sets" / "*_slice" / "data" / "dialogue" / "*.json"))):
            graph = json.loads(Path(path).read_text(encoding="utf-8"))
            for node_id, node in graph["nodes"].items():
                if node.get("end"):
                    continue
                choices = node.get("choices", [])
                only_a_goodbye = (
                    len(choices) == 1 and choices[0].get("end") and not choices[0].get("next_node")
                    and not choices[0].get("effects") and not choices[0].get("condition") and not choices[0].get("check")
                )
                self.assertFalse(only_a_goodbye, f"{Path(path).name} node '{node_id}': say it and end (\"end\": true) instead of asking for a reply")


class TestLeavingEndsAConversation(unittest.TestCase):
    def test_a_reply_after_walking_away_is_not_a_reply(self):
        game = _Game(self)
        game.say("talk chancellor")
        game.say("go south")
        self.assertIn("not in the middle of a conversation", game.say("reply 1"))

    def test_a_reply_when_the_other_has_gone_says_so(self):
        game = _Game(self)
        game.say("talk chancellor")
        chancellor = next(n for n in game.server.world.npcs.values() if "chancellor" in n.name)
        chancellor.current_room_id = "barracks"
        self.assertIn("not here", game.say("reply 1"))


class TestTheValidator(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "ff4_slice"
        shutil.copytree(REPO_ROOT / "content_sets" / "ff4_slice", self.package, ignore=shutil.ignore_patterns("saves", "editor"))

    def errors_with(self, node_id, **changes):
        path = self.package / "data" / "dialogue" / "king_orders.json"
        graph = json.loads(path.read_text(encoding="utf-8"))
        graph["nodes"][node_id].update(changes)
        path.write_text(json.dumps(graph, indent=4), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return [i.message for i in issues if i.severity == "error"]

    def test_the_shipped_set_is_clean(self):
        _definition, issues = validator.load_content_set(self.package)
        self.assertEqual([], [i.message for i in issues if i.severity == "error"])

    def test_it_must_be_a_boolean(self):
        self.assertTrue(any("must_answer must be true or false" in m for m in self.errors_with("greeting", must_answer="yes")))

    def test_a_scene_with_nothing_to_answer_is_refused(self):
        self.assertTrue(any("nothing to answer" in m for m in self.errors_with("obey", must_answer=True)))


if __name__ == "__main__":
    unittest.main()
