# tests/singles/test_triggers.py
"""Something can happen when the player walks into a room.

Until now the only event hook was a quest stage that spawned a boss. A scripted scene, a
door that seals behind you, a warning as you cross a threshold: none could be written. A
trigger is `{on, when, once, effects}` in `data/triggers/*.json`, keyed by id, running the
same effect vocabulary a conversation does.

Three rules are worth pinning:

* It fires **before the room is described**, so an exit it reveals is in the room text.
* `once` is `player` (the default, a flag on the player), `world` (a latch in the world's
  own state, which the snapshot keeps) or `false` (every time).
* A loop of triggers that teleport into each other stops, and a trigger whose effect
  fails does not stop the player arriving.
"""

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from engine.dialogue.effects import KNOWN_EFFECTS, apply_effects
from engine.world import world_snapshot
from engine.world.triggers import TRIGGER_EVENTS, TriggerRunner
from tests.fixtures import GameTestBase

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import content_set_validator as validator  # noqa: E402


class _Scenes(GameTestBase):
    def setUp(self):
        super().setUp()
        room = self.world.get_current_room(self.player)
        self.direction, destination = next(
            (d, dest) for d, dest in sorted(room.exits.items())
            if ":" not in dest and self.world.get_region(self.player.current_region_id).get_room(dest)
        )
        self.origin = (self.player.current_region_id, self.player.current_room_id)
        self.destination = (self.player.current_region_id, destination)

    def scene(self, trigger_id="probe", **more):
        definition = {"on": {"event": "on_enter", "region": self.destination[0], "room": self.destination[1]},
                      "effects": {"message": "A chill settles over the room."}}
        definition.update(more)
        self.world.trigger_runner.add(trigger_id, definition)
        return trigger_id

    def walk(self):
        self.player.current_region_id, self.player.current_room_id = self.origin
        return self.world.change_room(self.direction, self.player)


class TestTheVocabulary(unittest.TestCase):
    def test_the_events_and_the_effect_are_known(self):
        self.assertIn("on_enter", TRIGGER_EVENTS)
        self.assertIn("seal_exit", KNOWN_EFFECTS)


class TestFiring(_Scenes):
    def test_walking_into_the_room_fires_it(self):
        self.scene()
        self.assertIn("A chill settles", self.walk())

    def test_other_rooms_do_not(self):
        self.scene()
        self.player.current_region_id, self.player.current_room_id = self.destination
        back = next(d for d, dest in self.world.get_current_room(self.player).exits.items() if ":" not in dest)
        self.assertNotIn("A chill settles", self.world.change_room(back, self.player))

    def test_it_reads_after_the_room_and_before_the_quest_updates(self):
        self.scene()
        from unittest import mock
        with mock.patch.object(self.world.quest_manager, "handle_room_entry", return_value=["[Quest] done."]):
            text = self.walk()
        room = self.world.get_region(self.destination[0]).get_room(self.destination[1]).name.upper()
        self.assertLess(text.index(room), text.index("A chill settles"))
        self.assertLess(text.index("A chill settles"), text.index("[Quest] done."))

    def test_it_fires_before_the_room_is_described_so_a_revealed_exit_is_listed(self):
        room = self.world.get_region(self.destination[0]).get_room(self.destination[1])
        room.properties["hidden_exits"] = {"secret": "%s:%s" % self.origin}
        self.scene(effects={"reveal_exit": {"room": "%s:%s" % self.destination, "direction": "secret"}})
        self.assertIn("secret", self.walk().split("Exits:")[-1])

    def test_a_condition_gates_it(self):
        self.scene(when={"kind": "flag", "flag": "cursed"})
        self.assertNotIn("A chill settles", self.walk())
        self.player.flags["cursed"] = True
        self.assertIn("A chill settles", self.walk())

    def test_a_teleport_arrival_fires_it_too(self):
        self.scene()
        report = apply_effects({"teleport": {"region": self.destination[0], "room": self.destination[1]}},
                               {"player": self.player, "world": self.world})
        self.assertIn("A chill settles", report.message())


class TestOnce(_Scenes):
    def test_by_default_once_per_player(self):
        self.scene()
        self.assertIn("A chill settles", self.walk())
        self.assertNotIn("A chill settles", self.walk())
        self.assertTrue(self.player.flags.get("_trigger.probe"))

    def test_once_per_world_is_a_latch_in_the_worlds_own_state(self):
        self.scene(once="world")
        self.assertIn("A chill settles", self.walk())
        self.assertNotIn("A chill settles", self.walk())
        self.assertTrue(self.world.world_state["triggers"]["probe"])
        self.assertNotIn("_trigger.probe", self.player.flags)

    def test_a_world_latch_survives_a_snapshot(self):
        self.scene(once="world")
        self.walk()
        snapshot = copy.deepcopy(world_snapshot.capture(self.world))
        json.loads(json.dumps(snapshot))
        self.world.world_state.clear()
        world_snapshot.restore(self.world, snapshot)
        self.assertNotIn("A chill settles", self.walk(), "it does not play again after a restart")

    def test_false_fires_every_time(self):
        self.scene(once=False)
        self.assertIn("A chill settles", self.walk())
        self.assertIn("A chill settles", self.walk())


class TestSafety(_Scenes):
    def test_a_loop_of_triggers_that_teleport_into_each_other_stops(self):
        here, there = self.origin, self.destination
        self.world.trigger_runner.add("to_there", {
            "on": {"event": "on_enter", "region": here[0], "room": here[1]}, "once": False,
            "effects": {"teleport": {"region": there[0], "room": there[1]}}})
        self.world.trigger_runner.add("to_here", {
            "on": {"event": "on_enter", "region": there[0], "room": there[1]}, "once": False,
            "effects": {"teleport": {"region": here[0], "room": here[1]}}})
        self.world.change_room(self.direction, self.player)   # arriving there starts the ping-pong
        self.assertIn(self.where(), (here, there), "and it ended")
        self.assertEqual(0, self.world._teleport_depth)
        self.assertEqual(0, self.world.trigger_runner._depth)

    def where(self):
        return self.player.current_region_id, self.player.current_room_id

    def test_a_trigger_whose_effect_fails_does_not_stop_the_arrival(self):
        self.scene(effects={"take_gold": 10 ** 9, "message": "still here"})
        text = self.walk()
        self.assertEqual(self.destination, self.where())
        self.assertIn("still here", text)


class TestSealExit(_Scenes):
    def room(self):
        return self.world.get_region(self.origin[0]).get_room(self.origin[1])

    def seal(self, **more):
        return apply_effects({"seal_exit": {"region": self.origin[0], "room": self.origin[1],
                                            "direction": self.direction, **more}},
                             {"player": self.player, "world": self.world})

    def test_the_way_closes(self):
        report = self.seal()
        self.assertNotIn(self.direction, self.room().exits)
        self.assertTrue(report.applied, report.summary())
        self.assertIn("seals", report.message())
        self.assertIn("cannot go", self.world.change_room(self.direction, self.player))

    def test_it_is_remembered_as_a_hidden_exit_so_a_lever_can_open_it_again(self):
        self.seal()
        self.assertIn(self.direction, self.room().properties["hidden_exits"])
        apply_effects({"reveal_exit": {"room": "%s:%s" % self.origin, "direction": self.direction}},
                      {"player": self.player, "world": self.world})
        self.assertIn(self.direction, self.room().exits)

    def test_sealing_twice_does_nothing_more(self):
        self.seal()
        report = self.seal()
        self.assertEqual([], report.applied)
        self.assertTrue(report.unchanged, report.summary())

    def test_an_exit_the_room_does_not_have_is_reported(self):
        report = apply_effects({"seal_exit": {"region": self.origin[0], "room": self.origin[1], "direction": "sideways"}},
                               {"player": self.player, "world": self.world})
        self.assertTrue(any("seal_exit" in f for f in report.failed), report.summary())

    def test_a_sealed_exit_is_still_sealed_after_a_snapshot(self):
        self.seal()
        snapshot = copy.deepcopy(world_snapshot.capture(self.world))
        self.room().exits[self.direction] = "%s" % self.destination[1]   # the static room puts it back
        world_snapshot.restore(self.world, snapshot)
        self.assertNotIn(self.direction, self.room().exits)


class TestLoadingAndValidating(unittest.TestCase):
    """Against a scratch copy of Zelda Slice with a trigger file added."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "zelda_slice"
        shutil.copytree(REPO_ROOT / "content_sets" / "zelda_slice", self.package, ignore=shutil.ignore_patterns("saves", "editor"))
        self.folder = self.package / "data" / "triggers"
        self.folder.mkdir(exist_ok=True)

    GOOD = {"on": {"event": "on_enter", "region": "mossroot", "room": "boss_hall"},
            "effects": {"message": "The door grinds shut behind you."}}

    def _issues(self, triggers, name="scenes.json", extra=None):
        (self.folder / name).write_text(json.dumps(triggers), encoding="utf-8")
        for other, payload in (extra or {}).items():
            (self.folder / other).write_text(json.dumps(payload), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return issues

    def _errors(self, triggers, **kwargs):
        return [i.message for i in self._issues(triggers, **kwargs) if i.severity == "error"]

    def _warnings(self, triggers):
        return [i.message for i in self._issues(triggers) if i.severity == "warning"]

    def test_a_good_trigger_is_accepted(self):
        self.assertEqual([], self._errors({"boss_door": self.GOOD}))

    def test_an_unknown_event_is_refused(self):
        errors = self._errors({"t": {**self.GOOD, "on": {"event": "on_sneeze", "region": "mossroot", "room": "boss_hall"}}})
        self.assertTrue(any("on_sneeze" in m for m in errors), errors)

    def test_on_needs_an_event_a_region_and_a_room(self):
        for on in ({}, {"event": "on_enter"}, {"event": "on_enter", "region": "mossroot"}, "boss_hall"):
            errors = self._errors({"t": {**self.GOOD, "on": on}})
            self.assertTrue(any("'t'" in m and "on" in m for m in errors), (on, errors))

    def test_a_room_nobody_authored_is_refused(self):
        errors = self._errors({"t": {**self.GOOD, "on": {"event": "on_enter", "region": "mossroot", "room": "no_such_room"}}})
        self.assertTrue(any("no_such_room" in m for m in errors), errors)

    def test_once_must_be_player_world_or_false(self):
        for good in ("player", "world", False):
            self.assertEqual([], self._errors({"t": {**self.GOOD, "once": good}}), good)
        errors = self._errors({"t": {**self.GOOD, "once": "sometimes"}})
        self.assertTrue(any("once" in m for m in errors), errors)

    def test_effects_are_required_and_are_checked_like_a_conversations(self):
        errors = self._errors({"t": {"on": self.GOOD["on"]}})
        self.assertTrue(any("effects" in m for m in errors), errors)
        errors = self._errors({"t": {**self.GOOD, "effects": {"give_gold": 0, "summon_a_dragon": True, "give_item": "item_nobody_authored"}}})
        text = " ".join(errors)
        for needle in ("give_gold", "summon_a_dragon", "item_nobody_authored"):
            self.assertIn(needle, text)

    def test_a_condition_is_checked_like_a_conversations(self):
        errors = self._errors({"t": {**self.GOOD, "when": {"kind": "moon_is_full"}}})
        self.assertTrue(any("moon_is_full" in m for m in errors), errors)
        errors = self._errors({"t": {**self.GOOD, "when": {"all": [{"kind": "has_item", "item_id": "item_nobody_authored"}]}}})
        self.assertTrue(any("item_nobody_authored" in m for m in errors), errors)

    def test_an_unknown_key_is_refused(self):
        errors = self._errors({"t": {**self.GOOD, "whenever": True}})
        self.assertTrue(any("whenever" in m for m in errors), errors)

    def test_an_id_used_in_two_files_is_refused(self):
        errors = self._errors({"t": self.GOOD}, extra={"more.json": {"t": self.GOOD}})
        self.assertTrue(any("'t'" in m and "twice" in m for m in errors), errors)

    def test_seal_exit_must_name_an_exit_the_room_really_has(self):
        good = {"seal_exit": {"region": "mossroot", "room": "boss_hall", "direction": "east"}}
        self.assertEqual([], self._errors({"t": {**self.GOOD, "effects": good}}))
        bad = {"seal_exit": {"region": "mossroot", "room": "boss_hall", "direction": "sideways"}}
        errors = self._errors({"t": {**self.GOOD, "effects": bad}})
        self.assertTrue(any("seal_exit" in m and "sideways" in m for m in errors), errors)

    def test_a_repeating_trigger_that_raises_draws_a_warning(self):
        warnings = self._warnings({"t": {**self.GOOD, "once": False, "effects": {"raise": {"max_health": 5}}}})
        self.assertTrue(any("raise" in m and "repeat" in m for m in warnings), warnings)
        warnings = self._warnings({"t": {**self.GOOD, "effects": {"raise": {"max_health": 5}}}})
        self.assertEqual([], [m for m in warnings if "raise" in m])

    def test_a_set_with_no_triggers_folder_is_unchanged(self):
        shutil.rmtree(self.folder)
        _definition, issues = validator.load_content_set(self.package)
        self.assertEqual([], [i.message for i in issues if i.severity == "error"])


class TestFromDisk(unittest.TestCase):
    """The loader reads the folder and the runner fires it in a real server."""

    def test_a_trigger_on_disk_fires_when_the_player_walks_in(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        package = tmp / "zelda_slice"
        shutil.copytree(REPO_ROOT / "content_sets" / "zelda_slice", package, ignore=shutil.ignore_patterns("saves", "editor"))
        (package / "data" / "triggers").mkdir(exist_ok=True)
        (package / "data" / "triggers" / "scenes.json").write_text(json.dumps({
            "meadow_wind": {"on": {"event": "on_enter", "region": "aldermark", "room": "crossroads"},
                            "effects": {"message": "A cold wind pushes at your back."}}}), encoding="utf-8")
        from engine.server.headless_server import HeadlessServer
        server = HeadlessServer(db_path=":memory:", content_set_path=str(package),
                                deterministic_test_mode=True, default_presentation_mode="player")
        self.addCleanup(server.shutdown)
        self.assertIn("meadow_wind", server.world.trigger_runner.triggers)
        sid = server.create_session(player_id="t").session_id
        server.execute_command(sid, "char create Tester")
        player = server.get_player_for_session(sid)
        room = server.world.get_region("aldermark").get_room("crossroads")
        origin = next(dest.split(":")[-1] for dest in room.exits.values() if ":" not in dest)
        direction = next(d for d, dest in room.exits.items() if dest == origin)
        player.current_region_id, player.current_room_id = "aldermark", origin
        back = next(d for d, dest in server.world.get_region("aldermark").get_room(origin).exits.items()
                    if dest.split(":")[-1] == "crossroads")
        events = server.execute_command(sid, "go " + back)
        text = "\n".join(str(e.get("payload")) for e in events if e.get("type") in ("text", "error"))
        self.assertIn("cold wind", text)


if __name__ == "__main__":
    unittest.main()
