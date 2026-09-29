# tests/singles/test_hazard_bite.py
"""A hazard that a fresh hero shrugs off draws a validator warning.

Damage goes through the target's flat reduction first: the defence stat for a physical
channel, the contract's resistance stat for the rest. A hero starts with a resistance of 2
(and a defence of 3), so a 1- or 2-damage hazard in a room does nothing, silently, and the
author finds out in play. It is a warning, not an error: a background or gear can raise the
floor, and a set that means a harmless room can say so by ignoring it. The room's own number
overrides the declared one, and a weather multiplier below 1 can push a hazard under the floor.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import content_set_validator as validator  # noqa: E402


class TestHazardBite(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "zelda_slice"
        shutil.copytree(REPO_ROOT / "content_sets" / "zelda_slice", self.package, ignore=shutil.ignore_patterns("saves", "editor"))

    def warnings(self, hazard, declared=None):
        if declared is not None:
            path = self.package / "data" / "combat" / "elements.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["hazards"]["poison_gas"].update(declared)
            path.write_text(json.dumps(payload), encoding="utf-8")
        vault = self.package / "data" / "regions" / "drowned_vault.json"
        region = json.loads(vault.read_text(encoding="utf-8"))
        region["rooms"]["flooded_hall"]["properties"]["hazards"] = [hazard]
        vault.write_text(json.dumps(region), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return [i.message for i in issues if i.severity == "warning" and "flooded_hall" in i.message and "never hurts" in i.message]

    def test_a_hazard_below_the_resistance_is_a_warning(self):
        found = self.warnings({"type": "poison_gas", "damage": 1})
        self.assertEqual(1, len(found), found)
        self.assertIn("raise its damage above 2", found[0])

    def test_equal_to_the_resistance_is_still_absorbed(self):
        self.assertEqual(1, len(self.warnings({"type": "poison_gas", "damage": 2})))

    def test_one_that_bites_is_quiet(self):
        self.assertEqual([], self.warnings({"type": "poison_gas", "damage": 6}))

    def test_the_declared_damage_counts_when_the_room_states_none(self):
        self.assertEqual(1, len(self.warnings({"type": "poison_gas"}, declared={"damage": 1})))
        self.assertEqual([], self.warnings({"type": "poison_gas"}, declared={"damage": 9}))

    def test_a_weather_multiplier_can_push_it_under(self):
        found = self.warnings({"type": "poison_gas", "damage": 6, "weather_multipliers": {"rain": 0.25}})
        self.assertEqual(1, len(found), found)
        self.assertEqual([], self.warnings({"type": "poison_gas", "damage": 6, "weather_multipliers": {"rain": 3}}))

    def test_it_is_never_an_error(self):
        self.warnings({"type": "poison_gas", "damage": 1})
        _definition, issues = validator.load_content_set(self.package)
        self.assertEqual([], [i.message for i in issues if i.severity == "error"])

    def test_the_shipped_sets_have_none(self):
        for name in ("zelda_slice", "ff4_slice", "fantasy_frontier"):
            _definition, issues = validator.load_content_set(REPO_ROOT / "content_sets" / name)
            self.assertEqual([], [i.message for i in issues if "never hurts anyone" in i.message], name)


if __name__ == "__main__":
    unittest.main()
