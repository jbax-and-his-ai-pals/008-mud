# tests/singles/test_npc_max_health.py
"""A template can say how much health its creature has at most.

The factory derived `max_health` from level and constitution and read a value only from a
saved or placed override; a template's own `max_health` was silently ignored (its `health`
is where it starts, clamped to the derived maximum). An author who wanted a 250-hit-point
boss had to solve for the constitution that produced it.

Precedence now: a saved or placed value, then the template's `max_health`, then the derived
figure. `health` stays the starting figure, clamped to the maximum. An elite promotion
scales an authored maximum too, because it boosts constitution, which an authored maximum
does not read.
"""

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from engine.npcs.elite import compute_elite_overrides
from engine.npcs.npc_factory import NPCFactory
from tests.fixtures import GameTestBase

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import content_set_validator as validator  # noqa: E402

TEMPLATE = "zombie"


class TestPrecedence(GameTestBase):
    def setUp(self):
        super().setUp()
        self.template = self.world.npc_templates[TEMPLATE]
        self.saved = {key: self.template.get(key) for key in ("max_health", "health")}
        self.addCleanup(self._restore_template)
        self.where = dict(current_region_id=self.player.current_region_id, current_room_id=self.player.current_room_id)

    def _restore_template(self):
        for key, value in self.saved.items():
            if value is None:
                self.template.pop(key, None)
            else:
                self.template[key] = value

    def make(self, instance_id="probe", **more):
        return NPCFactory.create_npc_from_template(TEMPLATE, self.world, instance_id, **self.where, **more)

    def test_a_template_maximum_is_the_maximum(self):
        derived = self.make("derived").max_health
        self.template["max_health"] = derived + 500
        npc = self.make("authored")
        self.assertEqual(derived + 500, npc.max_health)

    def test_without_one_the_figure_is_still_derived(self):
        self.template.pop("max_health", None)
        first, second = self.make("a"), self.make("b")
        self.assertEqual(first.max_health, second.max_health)
        self.assertGreater(first.max_health, 0)

    def test_it_starts_at_full_unless_the_template_says_otherwise(self):
        self.template["max_health"] = 321
        self.template.pop("health", None)
        self.assertEqual(321, self.make().health)
        self.template["health"] = 100
        self.assertEqual(100, self.make("wounded").health, "`health` is where it starts")
        self.template["health"] = 9999
        self.assertEqual(321, self.make("clamped").health, "and never above the maximum")

    def test_a_placement_overrides_the_template(self):
        self.template["max_health"] = 321
        self.assertEqual(77, self.make(max_health=77).max_health)

    def test_a_saved_value_beats_the_template_too(self):
        self.template["max_health"] = 321
        npc = self.make()
        npc.max_health = 250
        state = copy.deepcopy(npc.to_dict())
        template_id = state.pop("template_id")
        again = NPCFactory.create_npc_from_template(template_id, self.world, "again", **state)
        self.assertEqual(250, again.max_health)

    def test_nonsense_in_a_template_is_ignored_rather_than_crashing(self):
        derived = self.make("derived").max_health
        for junk in (0, -5, "lots", True, None):
            self.template["max_health"] = junk
            self.assertEqual(derived, self.make("junk").max_health, repr(junk))


class TestElites(GameTestBase):
    def setUp(self):
        super().setUp()
        self.template = self.world.npc_templates[TEMPLATE]
        self.addCleanup(self.template.pop, "max_health", None)

    def test_an_elite_of_a_template_with_a_stated_maximum_is_scaled_from_it(self):
        self.template["max_health"] = 200
        multiplier = float(self.world.ruleset_section("elites").get("stat_multiplier", 1.5))
        self.assertEqual(int(200 * multiplier), compute_elite_overrides(self.template, self.world)["max_health"])

    def test_a_template_without_one_leaves_the_derived_figure_to_grow_with_its_stats(self):
        self.template.pop("max_health", None)
        self.assertNotIn("max_health", compute_elite_overrides(self.template, self.world))

    def test_the_promoted_creature_has_the_bigger_maximum(self):
        self.template["max_health"] = 200
        where = dict(current_region_id=self.player.current_region_id, current_room_id=self.player.current_room_id)
        plain = NPCFactory.create_npc_from_template(TEMPLATE, self.world, "plain", **where)
        elite = NPCFactory.create_npc_from_template(
            TEMPLATE, self.world, "elite", **where, **compute_elite_overrides(self.template, self.world))
        self.assertEqual(200, plain.max_health)
        self.assertGreater(elite.max_health, plain.max_health)


class TestValidating(unittest.TestCase):
    """Against a scratch copy of Zelda Slice with one template changed."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "zelda_slice"
        shutil.copytree(REPO_ROOT / "content_sets" / "zelda_slice", self.package, ignore=shutil.ignore_patterns("saves", "editor"))
        self.path = self.package / "data" / "npcs" / "hostiles.json"

    def issues(self, severity, **changes):
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        template = payload["slime_blob"]
        for key in ("max_health", "health"):
            template.pop(key, None)
        template.update(changes)
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        _definition, found = validator.load_content_set(self.package)
        return [i.message for i in found if i.severity == severity and "slime_blob" in i.message]

    def test_a_good_maximum_is_accepted(self):
        self.assertEqual([], self.issues("error", max_health=30, health=30))

    def test_a_maximum_must_be_a_whole_number_of_at_least_one(self):
        for bad in (0, -3, 12.5, "many", True):
            errors = self.issues("error", max_health=bad)
            self.assertTrue(any("max_health must be a whole number of at least 1" in m for m in errors), (bad, errors))

    def test_a_starting_health_above_the_maximum_is_a_warning(self):
        warnings = self.issues("warning", max_health=30, health=50)
        self.assertTrue(any("health 50 is above its max_health 30" in m for m in warnings), warnings)
        self.assertEqual([], self.issues("error", max_health=30, health=50))

    def test_a_starting_health_alone_draws_nothing(self):
        self.assertEqual([], self.issues("warning", health=400))


if __name__ == "__main__":
    unittest.main()
