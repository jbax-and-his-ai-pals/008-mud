# tests/singles/test_scene_skip_and_checkpoints.py
"""Testing the later parts of a story without sitting through the opening.

`scene skip` tells what is left of a running scene at once (every remaining beat's words and effects); `scene play <id>`
and `scene end <id>` begin or finish one; `end_scene` is the effect that finishes a scene without telling it. A
*checkpoint* is a scene whose id starts with `checkpoint_` (its beats carry effects that stand in for the story so far),
and `checkpoint <name>` jumps to it: running scenes are ended, the checkpoint is told at once. These are debug commands
(a test session), allowed while a scene runs.
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.dialogue.effects import apply_effects
from engine.server.headless_server import HeadlessServer
from tests.fixtures import STORY_FIXTURE

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")
NL = chr(10)

SCENES = {
    "the_watch": {"beats": [
        {"text": "The bell tolls once."},
        {"after": 30, "text": "A second bell.", "effects": {"set_flag": "heard_two"}},
        {"after": 30, "text": "A third.", "effects": {"set_flag": "heard_three", "play_scene": "the_echo"}},
    ]},
    "the_echo": {"beats": [{"after": 5, "text": "An echo.", "effects": {"set_flag": "heard_echo"}}]},
    "checkpoint_hall": {"note": "For testing: in the hall, having heard it all.", "lock": False, "beats": [
        {"effects": {"end_scene": ["the_watch", "the_echo"], "set_flag": "arrived_by_checkpoint"}},
        {"after": 0, "effects": {"set_flag": "second_beat"}},
    ]},
}
TRIGGERS = {"start": {"on": {"event": "on_enter", "region": "varenholt", "room": "throne_room"}, "effects": {"play_scene": "the_watch"}}}


def plain(text):
    return _MARKUP.sub("", text)


class _Game(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        package = tmp / "story_fixture"
        shutil.copytree(STORY_FIXTURE, package)
        (package / "data" / "scenes").mkdir(exist_ok=True)
        (package / "data" / "scenes" / "test.json").write_text(json.dumps(SCENES), encoding="utf-8")
        (package / "data" / "triggers" / "extra.json").write_text(json.dumps(TRIGGERS), encoding="utf-8")
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(package), deterministic_test_mode=True,
                                     default_presentation_mode="test")
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="hero").session_id
        self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.runner = self.server.world.scene_runner

    def say(self, command):
        return plain(NL.join(str(e["payload"]) for e in self.server.execute_command(self.sid, command) if e["type"] == "text"))

    def tick(self, seconds=1):
        told = []
        for _ in range(seconds):
            self.server.world.clock.advance(1.0)
            told += [str(e["payload"]) for e in self.server.tick(self.sid) + self.server._flush_background_batch(self.sid) if e["type"] == "text"]
        return plain(NL.join(told))


class TestSkipping(_Game):
    def test_skip_tells_the_rest_at_once_with_its_effects_and_what_it_began(self):
        self.assertIn("_scene.the_watch", self.player.flags)
        self.assertFalse(self.player.flags.get("heard_two"))
        told = self.say("scene skip")
        self.assertIn("Skipped", told)
        self.assertIn("A second bell.", told)
        self.assertIn("A third.", told)
        self.assertIn("An echo.", told, "a scene a beat began is told at once as well")
        for flag in ("heard_two", "heard_three", "heard_echo"):
            self.assertTrue(self.player.flags.get(flag), flag)
        self.assertEqual([], self.runner.running(self.player))
        self.assertTrue(self.player.flags.get("_scene_done.the_watch"))
        self.assertIn("No scene is running", self.say("scene skip"))

    def test_nothing_is_told_twice_after_a_skip(self):
        first = self.say("scene skip")
        later = self.tick(70)
        self.assertEqual(1, (first + later).count("A second bell."))

    def test_ending_a_scene_says_and_does_nothing_more(self):
        self.assertTrue(self.runner.end(self.player, "the_watch"))
        told = self.tick(70)
        self.assertNotIn("A second bell.", told)
        self.assertFalse(self.player.flags.get("heard_two"))
        self.assertTrue(self.player.flags.get("_scene_done.the_watch"))
        self.assertFalse(self.runner.end(self.player, "no_such_scene"))

    def test_the_effect_ends_scenes_and_reports_an_unknown_one(self):
        report = apply_effects({"end_scene": ["the_watch", "nonsense"]}, {"player": self.player, "world": self.server.world})
        self.assertTrue(self.player.flags.get("_scene_done.the_watch"))
        self.assertTrue([f for f in report.failed if "nonsense" in f])


class TestTheCommands(_Game):
    def test_they_work_while_a_scene_locks_the_player(self):
        self.assertTrue(self.runner.running(self.player))
        self.assertIn("the_watch", self.say("scene"))
        self.assertIn("running", self.say("scene"))
        self.assertNotIn("A scene is playing", self.say("scene"))

    def test_play_and_end_by_name_and_a_wrong_name_is_refused(self):
        self.say("scene end the_watch")
        self.assertIn("seen", self.say("scene"))
        self.assertIn("Playing 'the_echo'", self.say("scene play the_echo"))
        self.assertIn("the_echo", self.runner.running(self.player))
        self.assertIn("No scene named 'nope'", self.say("scene play nope"))
        self.assertIn("Usage", self.say("scene frobnicate"))

    def test_they_are_not_a_player_s_commands(self):
        server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                                default_presentation_mode="player")
        self.addCleanup(server.shutdown)
        sid = server.create_session(player_id="p").session_id
        server.execute_command(sid, "char create Aldric")
        said = NL.join(str(e["payload"]) for e in server.execute_command(sid, "checkpoint hall") if e["type"] in ("text", "error"))
        self.assertIn("permission", said)


class TestCheckpoints(_Game):
    def test_they_are_listed_with_their_notes(self):
        listing = self.say("checkpoint")
        self.assertIn("hall", listing)
        self.assertIn("having heard it all", listing)
        self.assertNotIn("the_watch", listing, "only the checkpoint_ scenes")

    def test_jumping_ends_what_is_running_and_applies_the_checkpoint_at_once(self):
        self.assertTrue(self.runner.running(self.player))
        self.assertIn("Jumped to 'hall'", self.say("checkpoint hall"))
        self.assertEqual([], self.runner.running(self.player))
        self.assertTrue(self.player.flags.get("arrived_by_checkpoint") and self.player.flags.get("second_beat"), "every beat, at once")
        self.assertFalse(self.player.flags.get("heard_two"), "and the opening it stands in for was not told")
        self.assertTrue(self.player.flags.get("_scene_done.the_watch"))
        self.assertNotIn("A second bell.", self.tick(70))

    def test_an_unknown_name_says_what_there_is(self):
        said = self.say("checkpoint nowhere")
        self.assertIn("No checkpoint named 'nowhere'", said)
        self.assertIn("hall", said)


if __name__ == "__main__":
    unittest.main()
