# tests/singles/test_scenes.py
"""A scene is something the player watches: beats told a moment apart, with things happening between them.

Scenes (`data/scenes/*.json`, `engine/world/scenes.py`) are begun by the `play_scene` effect, so a trigger can start
one when a character first arrives or when an item is taken; they lock their spectator, survive a restart, and are
checked by the validator. `advance_time` lets a night pass.
"""

import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.server import content_set as validator
from engine.server.headless_server import HeadlessServer
from tests.fixtures import STORY_FIXTURE

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")
NL = chr(10)

OPENING = {
    "the_watch": {
        "beats": [
            {"text": "The bell tolls once."},
            {"after": 3, "text": "A second bell.", "pace": "slow", "effects": {"set_flag": "heard_two"}},
            {"after": 3, "effects": {"set_flag": "heard_three"}, "text": "A third."},
        ]
    },
    "quick_free": {"lock": False, "beats": [{"text": "A breeze."}]},
}
TRIGGERS = {
    "start_scene": {"on": {"event": "on_enter", "region": "varenholt", "room": "throne_room"}, "effects": {"play_scene": "the_watch"}},
    "seal_taken": {"on": {"event": "item_taken", "item": "item_commander_seal"}, "once": "world", "effects": {"play_scene": "quick_free"}},
}


def _plain(text):
    return _MARKUP.sub("", text)


class _Set:
    def __init__(self, case, scenes=None, triggers=None):
        tmp = Path(tempfile.mkdtemp())
        case.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.package = tmp / "story_fixture"
        shutil.copytree(STORY_FIXTURE, self.package)
        data = self.package / "data"
        if scenes is not None:
            (data / "scenes").mkdir(exist_ok=True)
            (data / "scenes" / "test.json").write_text(json.dumps(scenes, indent=2), encoding="utf-8")
        if triggers is not None:
            (data / "triggers" / "extra.json").write_text(json.dumps(triggers, indent=2), encoding="utf-8")

    def boot(self, case, db=":memory:"):
        server = HeadlessServer(db_path=db, content_set_path=str(self.package), deterministic_test_mode=True,
                                default_presentation_mode="player")
        case.addCleanup(server.shutdown)
        return server


def _run(server, sid, seconds):
    told = []
    for _ in range(seconds):
        server.world.clock.advance(1.0)
        events = server.tick(sid) + server._flush_background_batch(sid)   # as the transports do
        told += [str(e["payload"]) for e in events if e["type"] == "text"]
    return NL.join(told)


def _hero(server, name="Aldric"):
    sid = server.create_session(player_id="hero").session_id
    created = server.execute_command(sid, "char create %s" % name)
    return sid, server.get_player_for_session(sid), created


class TestAScenePlays(unittest.TestCase):
    def test_a_new_character_watches_the_scene_on_the_first_room(self):
        server = _Set(self, OPENING, TRIGGERS).boot(self)
        sid, player, _created = _hero(server)
        self.assertIn("_scene.the_watch", player.flags, "it began with the character")
        told = _run(server, sid, 12)
        plain = _plain(told)
        self.assertLess(plain.index("The bell tolls once."), plain.index("A second bell."))
        self.assertLess(plain.index("A second bell."), plain.index("A third."))
        self.assertIn("[[PACE:70]]A second bell.[[/PACE]]", told, "a beat's pace is marked for the client")
        self.assertTrue(player.flags.get("heard_two") and player.flags.get("heard_three"), "the beats' effects happened")
        self.assertNotIn("_scene.the_watch", player.flags)
        self.assertTrue(player.flags.get("_scene_done.the_watch"))

    def test_the_beats_are_a_moment_apart(self):
        server = _Set(self, OPENING, TRIGGERS).boot(self)
        sid, player, _created = _hero(server)
        _run(server, sid, 2)
        self.assertFalse(player.flags.get("heard_two"), "the second beat waits its 3 seconds")
        _run(server, sid, 3)
        self.assertTrue(player.flags.get("heard_two"))
        self.assertFalse(player.flags.get("heard_three"))

    def test_the_spectator_is_locked_until_it_ends_and_may_still_look(self):
        server = _Set(self, OPENING, TRIGGERS).boot(self)
        sid, player, _created = _hero(server)
        refused = _plain(NL.join(str(e["payload"]) for e in server.execute_command(sid, "go south") if e["type"] == "text"))
        self.assertIn("not yours to interrupt", refused)
        self.assertEqual("throne_room", player.current_room_id)
        looked = NL.join(str(e["payload"]) for e in server.execute_command(sid, "look") if e["type"] == "text")
        self.assertNotIn("not yours to interrupt", looked)
        _run(server, sid, 12)
        moved = _plain(NL.join(str(e["payload"]) for e in server.execute_command(sid, "go south") if e["type"] == "text"))
        self.assertNotIn("not yours to interrupt", moved)

    def test_a_scene_that_does_not_lock_leaves_the_player_free(self):
        server = _Set(self, OPENING, TRIGGERS).boot(self)
        sid, player, _created = _hero(server)
        _run(server, sid, 12)
        server.world.scene_runner.play(player, "quick_free")
        self.assertFalse(server.world.scene_runner.blocking(player))

    def test_asking_twice_does_not_tell_it_twice(self):
        server = _Set(self, OPENING, TRIGGERS).boot(self)
        sid, player, _created = _hero(server)
        server.world.scene_runner.play(player, "the_watch")
        told = _plain(_run(server, sid, 12))
        self.assertEqual(1, told.count("The bell tolls once."))

    def test_an_unknown_scene_is_refused_not_ignored(self):
        server = _Set(self, OPENING, TRIGGERS).boot(self)
        _sid, player, _created = _hero(server)
        self.assertFalse(server.world.scene_runner.play(player, "no_such_scene"))

    def test_a_beat_that_carries_the_player_away_is_told_where_they_arrive(self):
        scenes = {"carried": {"beats": [
            {"text": "You are taken from the hall.", "effects": {"teleport": {"region": "varenholt", "room": "courtyard"}}},
            {"after": 1, "text": "The courtyard is cold."},
        ]}}
        triggers = {"go": {"on": {"event": "on_enter", "region": "varenholt", "room": "throne_room"}, "effects": {"play_scene": "carried"}}}
        server = _Set(self, scenes, triggers).boot(self)
        sid, player, _created = _hero(server)
        told = _plain(_run(server, sid, 5))
        self.assertEqual("courtyard", player.current_room_id)
        self.assertIn("CASTLE COURTYARD", told)
        self.assertIn("The courtyard is cold.", told)


class TestItemTaken(unittest.TestCase):
    def test_taking_an_item_sets_off_its_trigger(self):
        triggers = {"seal_taken": {"on": {"event": "item_taken", "item": "item_commander_seal"}, "effects": {"set_flag": "took_the_seal"}}}
        server = _Set(self, OPENING, triggers).boot(self)
        sid, player, _created = _hero(server)
        _run(server, sid, 12)
        server.execute_command(sid, "drop commander's seal")
        self.assertFalse(player.flags.get("took_the_seal"))
        server.execute_command(sid, "take commander's seal")
        self.assertTrue(player.flags.get("took_the_seal"))

    def test_a_room_can_narrow_it(self):
        triggers = {"narrow": {"on": {"event": "item_taken", "item": "item_commander_seal", "region": "varenholt", "room": "courtyard"}, "once": False, "effects": {"set_flag": "took_it_there"}}}
        server = _Set(self, OPENING, triggers).boot(self)
        sid, player, _created = _hero(server)
        _run(server, sid, 12)
        server.execute_command(sid, "drop commander's seal")
        server.execute_command(sid, "take commander's seal")
        self.assertFalse(player.flags.get("took_it_there"), "not taken in the courtyard")


class TestASceneSurvivesARestart(unittest.TestCase):
    def test_a_part_told_scene_carries_on(self):
        package = _Set(self, OPENING, TRIGGERS)
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        db = os.path.join(tmp, "story.sqlite3")
        first = HeadlessServer(db_path=db, content_set_path=str(package.package), deterministic_test_mode=True, default_presentation_mode="player")
        sid, player, _created = _hero(first)
        _run(first, sid, 4)   # the first two beats
        self.assertEqual(2, player.flags["_scene.the_watch"])
        first.persist_player_snapshot(sid)
        first.shutdown()

        second = HeadlessServer(db_path=db, content_set_path=str(package.package), deterministic_test_mode=True, default_presentation_mode="player")
        self.addCleanup(second.shutdown)
        sid2 = second.create_session(player_id="hero").session_id
        second.execute_command(sid2, "char create Aldric")
        player2 = second.get_player_for_session(sid2)
        told = _plain(_run(second, sid2, 8))
        self.assertIn("A third.", told)
        self.assertNotIn("The bell tolls once.", told, "what was already told is not told again")
        self.assertTrue(player2.flags.get("_scene_done.the_watch"))


class TestAdvanceTime(unittest.TestCase):
    def test_the_clock_jumps_to_the_next_time_it_is_that_hour(self):
        from engine.dialogue.effects import apply_effects

        server = _Set(self, OPENING, TRIGGERS).boot(self)
        _sid, player, _created = _hero(server)
        clock = server.time_manager
        clock.initialize_time(float(20 * 3600))   # eight in the evening
        before_day = clock.day
        apply_effects({"advance_time": {"to_hour": 6}}, {"player": player, "world": server.world})
        self.assertEqual(6, clock.hour)
        self.assertEqual(before_day + 1, clock.day, "the next 6 o'clock is tomorrow's")
        clock.initialize_time(float(4 * 3600))   # four in the morning
        apply_effects({"advance_time": {"to_hour": 6}}, {"player": player, "world": server.world})
        self.assertEqual((6, 1), (clock.hour, clock.day), "from before dawn it is the same day's")


class TestTheValidator(unittest.TestCase):
    def issues_with(self, scenes=None, triggers=None):
        package = _Set(self, scenes if scenes is not None else OPENING, triggers if triggers is not None else TRIGGERS).package
        _definition, issues = validator.load_content_set(package)
        return [(i.severity, i.message) for i in issues]

    def errors(self, **kwargs):
        return [m for s, m in self.issues_with(**kwargs) if s == "error"]

    def test_good_scenes_pass(self):
        self.assertEqual([], self.errors())

    def test_bad_scenes_are_refused_and_say_what_would_work(self):
        def one(scene):
            return self.errors(scenes={"s": scene}, triggers={})

        self.assertTrue(any("non-empty list" in m for m in one({"beats": []})))
        self.assertTrue(any("non-empty list" in m for m in one({})))
        self.assertTrue(any("unknown key 'mood'" in m for m in one({"beats": [{"text": "x"}], "mood": "grim"})))
        self.assertTrue(any("lock must be true or false" in m for m in one({"beats": [{"text": "x"}], "lock": "yes"})))
        self.assertTrue(any("must be an object" in m for m in one({"beats": ["just text"]})))
        self.assertTrue(any("tells nothing" in m for m in one({"beats": [{"after": 1}]})))
        self.assertTrue(any(".text must be the words" in m for m in one({"beats": [{"text": ""}]})))
        self.assertTrue(any(".after must be a number" in m for m in one({"beats": [{"text": "x", "after": -1}]})))
        self.assertTrue(any(".after must be a number" in m for m in one({"beats": [{"text": "x", "after": 9999}]})))
        self.assertTrue(any("is not a pace" in m for m in one({"beats": [{"text": "x", "pace": "glacial"}]})))
        self.assertTrue(any("unknown effect 'teleportt'" in m for m in one({"beats": [{"effects": {"teleportt": 1}}]})))
        self.assertTrue(any("non-empty object" in m for m in one({"beats": [{"text": "x", "effects": {}}]})))

    def test_a_beats_effects_are_checked_like_a_conversations(self):
        errors = self.errors(scenes={"s": {"beats": [{"effects": {"give_item": "item_nobody_made"}}]}}, triggers={})
        self.assertTrue(any("item_nobody_made" in m for m in errors), errors)
        errors = self.errors(scenes={"s": {"beats": [{"effects": {"teleport": {"region": "varenholt", "room": "no_such_room"}}}]}}, triggers={})
        self.assertTrue(any("no_such_room" in m for m in errors), errors)

    def test_play_scene_must_name_a_scene_that_exists(self):
        errors = self.errors(triggers={"t": {"on": {"event": "on_enter", "region": "varenholt", "room": "courtyard"}, "effects": {"play_scene": "ghost"}}})
        self.assertTrue(any("play_scene names scene 'ghost'" in m for m in errors), errors)

    def test_item_taken_needs_an_item_that_exists(self):
        errors = self.errors(triggers={"t": {"on": {"event": "item_taken"}, "effects": {"message": "x"}}})
        self.assertTrue(any("needs a item" in m or "item" in m for m in errors), errors)

    def test_two_scenes_may_not_share_an_id(self):
        package = _Set(self, OPENING, TRIGGERS).package
        (package / "data" / "scenes" / "again.json").write_text(json.dumps({"the_watch": {"beats": [{"text": "x"}]}}), encoding="utf-8")
        _definition, issues = validator.load_content_set(package)
        self.assertTrue(any("defined twice" in i.message for i in issues if i.severity == "error"))


if __name__ == "__main__":
    unittest.main()
