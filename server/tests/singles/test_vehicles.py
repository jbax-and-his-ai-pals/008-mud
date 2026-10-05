# tests/singles/test_vehicles.py
"""Vehicles (`data/vehicles/`): boarded, ridden, set down, and what a way that needs one asks.

A vehicle waits where it starts or where it was set down; `board` and `disembark` are the player's commands; an exit
requirement `{"type": "vehicle"}` is open only to someone aboard; it goes where its rider goes; it may be set down only
in some biomes (or a room that names it in `properties.docks`); a rider who dies leaves it where it was; the story can
`place_vehicle` and `board_vehicle`, and ask `aboard`.
"""

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from engine import conditions
from engine.dialogue.effects import apply_effects
from engine.server import content_set
from engine.server.headless_server import HeadlessServer
from engine.world import world_snapshot
from tests.fixtures import STORY_FIXTURE

VEHICLES = {"skimmer": {
    "name": "the skimmer", "description": "A flat craft that rides the sand.", "start": {"region": "hazevale", "room": "village_square"},
    "board_text": "You climb aboard the skimmer.", "disembark_text": "You climb down.", "lands_in_biomes": ["desert"],
}}


def package(mutate=None):
    tmp = Path(tempfile.mkdtemp())
    pkg = tmp / "story_fixture"
    shutil.copytree(STORY_FIXTURE, pkg)
    (pkg / "data" / "vehicles").mkdir()
    (pkg / "data" / "vehicles" / "craft.json").write_text(json.dumps(copy.deepcopy(VEHICLES)), encoding="utf-8")
    path = pkg / "data" / "regions" / "hazevale.json"
    region = json.loads(path.read_text(encoding="utf-8"))
    rooms = region["rooms"]
    rooms["village_square"].setdefault("properties", {})["exit_requirements"] = {"east": {"type": "vehicle", "vehicle": "skimmer"}}
    rooms["shrine"].setdefault("properties", {})["docks"] = ["skimmer"]
    path.write_text(json.dumps(region), encoding="utf-8")
    if mutate:
        mutate(pkg)
    return tmp, pkg


class _Ride(unittest.TestCase):
    def setUp(self):
        tmp, pkg = package()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(pkg), deterministic_test_mode=True,
                                     default_presentation_mode="player")
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="hero").session_id
        self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world
        self.player.current_region_id, self.player.current_room_id = "hazevale", "village_square"

    def say(self, command):
        return " ".join(str(e["payload"]) for e in self.server.execute_command(self.sid, command) if e["type"] == "text")

    def where(self):
        return "%s:%s" % (self.player.current_region_id, self.player.current_room_id)


class TestRiding(_Ride):
    def test_a_parked_vehicle_is_in_the_room_text(self):
        self.assertIn("The skimmer waits here.", self.say("look"))

    def test_the_way_is_shut_until_you_are_aboard(self):
        self.assertIn("would need the skimmer", self.say("go east"))
        self.assertEqual("hazevale:village_square", self.where())
        self.assertIn("climb aboard", self.say("embark"))
        self.say("go east")
        self.assertEqual("hazevale:ruined_lane", self.where())

    def test_it_goes_where_its_rider_goes(self):
        self.say("embark")
        self.say("go east")
        self.assertNotIn("skimmer waits", self.say("look"), "it is under you, not parked")
        self.say("go west")
        self.assertNotIn("skimmer waits", self.say("look"))
        self.assertEqual(("hazevale", "village_square"), (self.world.world_state["vehicles"]["skimmer"]["region"], self.world.world_state["vehicles"]["skimmer"]["room"]))

    def test_it_can_be_boarded_by_name_and_only_where_it_waits(self):
        self.assertIn("nothing like 'raft'", self.say("embark raft"))
        self.assertIn("climb aboard", self.say("embark skimmer"))
        self.assertIn("already aboard", self.say("embark"))
        self.say("go east")

    def test_it_is_set_down_only_where_it_may_land(self):
        self.say("embark")
        self.say("go east")
        self.assertIn("cannot set the skimmer down here", self.say("disembark"), "a lane in a region with no desert")
        self.say("go west")
        self.say("go south")
        self.assertEqual("hazevale:shrine", self.where())
        self.assertIn("climb down", self.say("disembark"), "the shrine names it in its docks")
        self.assertIn("The skimmer waits here.", self.say("look"))
        self.assertIn("not aboard anything", self.say("disembark"))

    def test_the_story_can_move_it_and_board_the_player(self):
        context = {"player": self.player, "world": self.world}
        apply_effects({"place_vehicle": {"vehicle": "skimmer", "region": "hazevale", "room": "shrine"}}, context)
        self.assertNotIn("skimmer waits", self.say("look"))
        apply_effects({"board_vehicle": "skimmer"}, context)
        self.assertEqual("skimmer", self.world.vehicles.aboard(self.player), "it came to where they stand")
        apply_effects({"place_vehicle": {"vehicle": "skimmer", "region": "hazevale", "room": "inn"}}, context)
        self.assertIsNone(self.world.vehicles.aboard(self.player), "whoever rode it is put ashore")

    def test_the_condition_asks_whether_they_are_aboard(self):
        self.assertFalse(conditions.evaluate({"kind": "aboard"}, self.player).satisfied)
        self.say("embark")
        self.assertTrue(conditions.evaluate({"kind": "aboard"}, self.player).satisfied)
        self.assertTrue(conditions.evaluate({"kind": "aboard", "vehicle_id": "skimmer"}, self.player).satisfied)
        self.assertFalse(conditions.evaluate({"kind": "aboard", "vehicle_id": "raft"}, self.player).satisfied)

    def test_a_rider_who_dies_leaves_it_where_they_fell(self):
        self.say("embark")
        self.say("go east")
        self.player.take_damage(10 ** 6, "physical")
        self.say("respawn")
        self.assertIsNone(self.world.vehicles.aboard(self.player))
        record = self.world.world_state["vehicles"]["skimmer"]
        self.assertEqual(("hazevale", "ruined_lane", None), (record["region"], record["room"], record["aboard"]))

    def test_where_it_is_survives_a_restart(self):
        self.say("embark")
        self.say("go east")
        snapshot = copy.deepcopy(world_snapshot.capture(self.world))
        self.world.world_state.clear()
        world_snapshot.restore(self.world, snapshot)
        self.assertEqual("ruined_lane", self.world.world_state["vehicles"]["skimmer"]["room"])
        self.assertEqual("skimmer", self.world.vehicles.aboard(self.player), "and what they ride is on the character")


class TestTheValidator(unittest.TestCase):
    def errors(self, mutate):
        tmp, pkg = package(mutate)
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        return [i.message for i in content_set.validate_content_set(pkg) if i.severity == "error"]

    def vehicles(self, change):
        def mutate(pkg):
            path = pkg / "data" / "vehicles" / "craft.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            change(data)
            path.write_text(json.dumps(data), encoding="utf-8")
        return mutate

    def test_the_good_set_has_no_vehicle_errors(self):
        self.assertEqual([], [m for m in self.errors(None) if "vehicle" in m])

    def test_bad_vehicles_are_refused(self):
        cases = {
            "name is required": lambda d: d["skimmer"].pop("name"),
            "unknown key 'wheels'": lambda d: d["skimmer"].update(wheels=4),
            "which this content set does not have": lambda d: d["skimmer"].update(start={"region": "hazevale", "room": "nowhere"}),
            "lands_in_biomes must be a list": lambda d: d["skimmer"].update(lands_in_biomes="desert"),
            "must be text": lambda d: d["skimmer"].update(board_text=3),
        }
        for expected, change in cases.items():
            self.assertTrue([m for m in self.errors(self.vehicles(change)) if expected in m], expected)

    def test_a_requirement_must_name_a_vehicle_the_set_has(self):
        def mutate(pkg):
            path = pkg / "data" / "regions" / "hazevale.json"
            region = json.loads(path.read_text(encoding="utf-8"))
            region["rooms"]["village_square"]["properties"]["exit_requirements"]["east"]["vehicle"] = "raft"
            path.write_text(json.dumps(region), encoding="utf-8")
        self.assertTrue([m for m in self.errors(mutate) if "names vehicle 'raft'" in m])

    def test_an_effect_must_name_a_vehicle_the_set_has(self):
        def mutate(pkg):
            path = pkg / "data" / "scenes"
            path.mkdir(exist_ok=True)
            (path / "launch.json").write_text(json.dumps({"launch": {"beats": [{"text": "Off.", "effects": {
                "place_vehicle": {"vehicle": "raft", "region": "hazevale", "room": "shrine"}, "board_vehicle": "boat"}}]}}), encoding="utf-8")
        found = self.errors(mutate)
        self.assertTrue([m for m in found if "place_vehicle names vehicle 'raft'" in m], found)
        self.assertTrue([m for m in found if "board_vehicle" in m and "boat" in m], found)


if __name__ == "__main__":
    unittest.main()
