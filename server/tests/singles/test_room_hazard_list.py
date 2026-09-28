# tests/singles/test_room_hazard_list.py
"""A room with more than one hazard.

A room used to name exactly one hazard (`hazard_type`, with optional
`hazard_damage`, `hazard_tick_interval` and `weather_hazard_multipliers`). It
may now name several as `hazards: [{type, damage?, tick_interval?,
weather_multipliers?}]`, each ticking on its own clock. The one-hazard keys
still read as a list of one, so every existing room behaves as it did.

A field reaction that suppresses hazards may name a `channel`: then only the
hazards dealing through it go quiet (frost quenches the heat and leaves the
poison). Without one it quiets them all, as it always has.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from engine.config import config_combat
from engine.world import environment
from engine.world.room import Room

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import content_set_validator as validator

HAZARDS = {
    "extreme_heat": {"channel": "fire", "flavor": "The heat bites.", "damage": 4, "tick_interval": 5.0},
    "poison_gas": {"channel": "poison", "flavor": "The fumes sting.", "damage": 2, "tick_interval": 2.0},
}


class _Entity:
    def __init__(self):
        self.obj_id = "hero"
        self.health = 100
        self.is_alive = True
        self.current_region_id = ""
        self.hits = []

    def take_damage(self, amount, damage_type=None):
        self.hits.append((int(amount), damage_type))
        self.health -= int(amount)
        return int(amount)


class _Fixture(unittest.TestCase):
    def setUp(self):
        saved = dict(config_combat.HAZARD_TYPES)
        config_combat.HAZARD_TYPES.clear()
        config_combat.HAZARD_TYPES.update({key: config_combat._normalize_hazard(value) for key, value in HAZARDS.items()})
        self.addCleanup(lambda: (config_combat.HAZARD_TYPES.clear(), config_combat.HAZARD_TYPES.update(saved)))


class TestReadingHazards(_Fixture):
    def test_the_one_hazard_keys_read_as_a_list_of_one(self):
        entries = environment.hazard_entries({"hazard_type": "extreme_heat", "hazard_damage": 9})
        self.assertEqual([("extreme_heat", 9)], [(e["type"], e["damage"]) for e in entries])

    def test_a_list_names_each_hazard_with_its_own_numbers(self):
        room = Room("Vent", "Hot and foul.", obj_id="vent")
        room.properties["hazards"] = [{"type": "extreme_heat", "damage": 7}, {"type": "poison_gas"}]
        hazards = environment.hazards_in(None, room)
        self.assertEqual(["extreme_heat", "poison_gas"], [h["id"] for h in hazards])
        self.assertEqual([7, 2], [h["damage"] for h in hazards])

    def test_each_hazard_ticks_on_its_own_clock(self):
        room = Room("Vent", "Hot and foul.", obj_id="vent")
        room.properties["hazards"] = [{"type": "extreme_heat"}, {"type": "poison_gas"}]
        hero = _Entity()
        first = room.apply_hazards(hero, 10.0)
        self.assertIn("The heat bites.", first)
        self.assertIn("The fumes sting.", first)
        self.assertEqual({"fire", "poison"}, {channel for _amount, channel in hero.hits})
        hero.hits.clear()
        room.apply_hazards(hero, 12.5)  # the gas's 2 s has passed; the heat's 5 s has not
        self.assertEqual([(2, "poison")], hero.hits)


class TestSuppressingByChannel(_Fixture):
    def _room(self, reaction):
        room = Room("Vent", "Hot and foul.", obj_id="vent")
        room.properties["hazards"] = [{"type": "extreme_heat"}, {"type": "poison_gas"}]
        room.properties["env_interactions"] = {"ice": dict({"type": "suppress_hazard", "duration": 5.0, "message": "Frost settles."}, **reaction)}
        return room

    def test_a_channel_quiets_only_the_matching_hazard_and_it_comes_back(self):
        room = self._room({"channel": "fire"})
        self.assertIn("Frost settles.", room.apply_elemental_interaction("ice"))
        self.assertEqual(["poison_gas"], [e["type"] for e in room.properties["hazards"]])
        messages = room.update(6.0)
        self.assertIn("hazard returns", messages[0])
        self.assertEqual({"extreme_heat", "poison_gas"}, {e["type"] for e in room.properties["hazards"]})

    def test_a_channel_no_hazard_uses_does_nothing(self):
        room = self._room({"channel": "lightning"})
        self.assertIsNone(room.apply_elemental_interaction("ice"))
        self.assertEqual(2, len(room.properties["hazards"]))

    def test_no_channel_quiets_every_hazard_as_before(self):
        room = self._room({})
        room.apply_elemental_interaction("ice")
        self.assertEqual([], room.properties["hazards"])

    def test_a_channel_also_narrows_a_one_hazard_room(self):
        room = Room("Oven", "Hot.", obj_id="oven")
        room.properties["hazard_type"] = "extreme_heat"
        room.properties["env_interactions"] = {"ice": {"type": "suppress_hazard", "channel": "poison"}}
        self.assertIsNone(room.apply_elemental_interaction("ice"))
        self.assertEqual("extreme_heat", room.properties["hazard_type"])


class TestValidatingHazardLists(unittest.TestCase):
    """Against a scratch copy of Fantasy Frontier, changing only the Quicksand Pit."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "fantasy_frontier"
        shutil.copytree(REPO_ROOT / "content_sets" / "fantasy_frontier", self.package,
                        ignore=shutil.ignore_patterns("saves", "editor"))
        self.swamp = self.package / "data" / "regions" / "swamp.json"

    def _pit(self, properties: dict) -> list:
        region = json.loads(self.swamp.read_text(encoding="utf-8"))
        region["rooms"]["quicksand_pit"]["properties"] = properties
        self.swamp.write_text(json.dumps(region), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return [issue.message for issue in issues if issue.severity == "error"]

    def test_a_list_of_declared_hazards_is_accepted(self):
        errors = self._pit({"hazards": [
            {"type": "quicksand", "damage": 9, "tick_interval": 5, "weather_multipliers": {"mist": 1.25}},
            {"type": "poison_gas", "damage": 3},
        ], "env_interactions": {"water": {"type": "suppress_hazard", "channel": "poison"}}})
        self.assertEqual([], [m for m in errors if "quicksand_pit" in m], errors)

    def test_both_forms_at_once_is_an_error(self):
        errors = self._pit({"hazard_type": "quicksand", "hazards": [{"type": "poison_gas"}]})
        self.assertTrue(any("both ways" in m for m in errors), errors)

    def test_an_unknown_hazard_in_the_list_is_an_error(self):
        errors = self._pit({"hazards": [{"type": "quicksand"}, {"type": "lava_lake"}]})
        self.assertTrue(any("hazards[1]" in m and "lava_lake" in m for m in errors), errors)

    def test_naming_a_hazard_twice_is_an_error(self):
        errors = self._pit({"hazards": [{"type": "quicksand"}, {"type": "quicksand"}]})
        self.assertTrue(any("second time" in m for m in errors), errors)

    def test_an_unread_key_in_an_entry_is_an_error(self):
        errors = self._pit({"hazards": [{"type": "quicksand", "dammage": 4}]})
        self.assertTrue(any("dammage" in m and "not read" in m for m in errors), errors)

    def test_a_suppressing_channel_no_hazard_uses_is_an_error(self):
        errors = self._pit({"hazards": [{"type": "quicksand"}],
                            "env_interactions": {"water": {"type": "suppress_hazard", "channel": "fire"}}})
        self.assertTrue(any("matches none of this room's hazards" in m for m in errors), errors)


if __name__ == "__main__":
    unittest.main()
