# tests/singles/test_reference_coverage.py
"""References the engine reads that no audit used to open the file for.

Eighteen dangling references were shipping in content that passed every gate.
None of them was exotic: seven items named a collection nobody authored, three
summon spells named minion templates nobody authored, two NPCs were scheduled to
walk to rooms that do not exist, and one spell dealt `cold` in a set whose channel
is `ice`. They survived because the audits read four families and the engine reads
about fifty, so the checks were not wrong -- they were absent.

The families were added to `toolkit/reference_integrity_validator.py` as a table.
These tests are about the table staying honest: that it catches a dangling id, and
that it does not invent one.
"""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONTENT_SETS = ("fantasy_frontier", "modern_capsule", "night_shift", "orbital_salvage")
PYTHON = sys.executable


def _copy_set(name: str, case: unittest.TestCase) -> Path:
    scratch = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
    target = scratch / name
    shutil.copytree(REPO_ROOT / "content_sets" / name, target)
    return target / "data"


def _run_validator(data_root: Path) -> tuple[int, str]:
    completed = subprocess.run(
        [PYTHON, str(REPO_ROOT / "toolkit" / "reference_integrity_validator.py"), str(data_root)],
        capture_output=True, text=True, encoding="utf-8", cwd=str(REPO_ROOT),
    )
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


class TestEveryShippedSetPasses(unittest.TestCase):
    def test_no_dangling_references(self):
        for content_set in CONTENT_SETS:
            code, output = _run_validator(REPO_ROOT / "content_sets" / content_set / "data")
            self.assertEqual(0, code, "%s: %s" % (content_set, output))
            self.assertIn("errors: 0", output)


class TestTheFamiliesItNowChecks(unittest.TestCase):
    """One case per family that the audit found nobody was checking."""

    def _break(self, content_set: str, relative: str, mutate) -> str:
        data_root = _copy_set(content_set, self)
        path = data_root / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        mutate(payload)
        path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
        code, output = _run_validator(data_root)
        self.assertEqual(1, code, output)
        return output

    def test_a_recipe_that_produces_a_missing_item(self):
        def mutate(payload):
            payload["tie_wildflower_posy"]["result_item_id"] = "item_absent"

        output = self._break("fantasy_frontier", "crafting/basic_recipes.json", mutate)
        self.assertIn("item_absent", output)

    def test_a_collection_that_does_not_exist(self):
        def mutate(payload):
            payload["item_goblin_bead_red"]["properties"]["collection_id"] = "absent_collection"

        output = self._break("fantasy_frontier", "items/collection_items.json", mutate)
        self.assertIn("absent_collection", output)

    def test_a_recipe_to_learn_that_does_not_exist(self):
        def mutate(payload):
            payload["item_smithing_pattern_hatchet"]["properties"]["recipe_to_learn"] = "absent_recipe"

        output = self._break("fantasy_frontier", "items/consumables.json", mutate)
        self.assertIn("absent_recipe", output)

    def test_a_summon_naming_a_minion_that_does_not_exist(self):
        def mutate(payload):
            payload["summon_spirit_wolf"]["effects"][0]["summon_template_id"] = "absent_minion"

        output = self._break("fantasy_frontier", "magic/summoning_spells.json", mutate)
        self.assertIn("absent_minion", output)

    def test_a_work_location_in_a_room_that_does_not_exist(self):
        def mutate(payload):
            payload["blacksmith"]["properties"]["work_location"] = "town:nowhere"

        output = self._break("fantasy_frontier", "npcs/villagers.json", mutate)
        self.assertIn("town:nowhere", output)

    def test_a_region_spawning_a_monster_that_does_not_exist(self):
        def mutate(payload):
            # `monster_types` is a map of template id to spawn weight, so the
            # reference is the key.
            payload["spawner"]["monster_types"] = {"absent_monster": 2}

        output = self._break("fantasy_frontier", "regions/caves.json", mutate)
        self.assertIn("absent_monster", output)

    def test_an_ability_a_background_grants_that_does_not_exist(self):
        def mutate(payload):
            payload["apprentice"]["spells"] = ["absent_ability"]

        output = self._break("fantasy_frontier", "player/backgrounds.json", mutate)
        self.assertIn("absent_ability", output)

    def test_a_damage_type_the_set_does_not_declare(self):
        def mutate(payload):
            payload["ice_shard"]["effects"][0]["damage_type"] = "lukewarm"

        output = self._break("fantasy_frontier", "magic/offensive_spells.json", mutate)
        self.assertIn("lukewarm", output)

    def test_a_weapon_damage_type_outside_the_engine_vocabulary(self):
        """A different axis from the damage channels, checked against its own list."""
        def mutate(payload):
            payload["wolf"]["properties"]["weapon_damage_type"] = "biting"

        output = self._break("fantasy_frontier", "npcs/hostiles.json", mutate)
        self.assertIn("biting", output)
        self.assertIn("slashing", output, "the message names the values it wants")

    def test_a_default_damage_type_the_set_does_not_declare(self):
        """The fallback channel a spell with no `damage_type` of its own deals.

        `default_damage_type` is read at world construction and cannot be
        reported at runtime: the engine looks it up in the flavour map, misses,
        and uses the generic text, so a typo here is invisible in play.
        """
        def mutate(payload):
            payload["default_damage_type"] = "lukewarm"

        output = self._break("fantasy_frontier", "combat/elements.json", mutate)
        self.assertIn("lukewarm", output)
        self.assertIn("default_damage_type", output)


class TestItDoesNotInventFindings(unittest.TestCase):
    """A check that reports working content is a check people learn to ignore."""

    def test_the_weapon_damage_type_check_accepts_the_engine_vocabulary(self):
        from engine.config.config_combat import WEAPON_DAMAGE_TYPES

        self.assertEqual(["slashing", "piercing", "crushing"], WEAPON_DAMAGE_TYPES)

    def test_an_absent_optional_reference_is_not_a_finding(self):
        """Most references are optional; only a present-but-dangling one is wrong."""
        data_root = _copy_set("fantasy_frontier", self)
        path = data_root / "npcs" / "villagers.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["blacksmith"]["properties"].pop("work_location", None)
        path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
        code, output = _run_validator(data_root)
        self.assertEqual(0, code, output)

    def test_an_authoring_note_is_not_read_as_a_reference(self):
        data_root = _copy_set("fantasy_frontier", self)
        path = data_root / "npcs" / "villagers.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["_comment"] = "a note, not an NPC"
        path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
        code, output = _run_validator(data_root)
        self.assertEqual(0, code, output)


class TestTheEmptyBucketMistake(unittest.TestCase):
    """An empty id set must not mean "skip the check".

    Two of these hid real defects: the campaign bucket was read from a directory
    no shipped set has, and the ability bucket was read from a registry that is
    empty until a `World` boots -- which happens after validation. Both reported
    success, and both meant every reference of that kind went unchecked.
    """

    def test_the_campaign_ids_come_from_where_the_engine_reads_them(self):
        from engine.server.content_set import _content_identifier_sets

        issues: list = []
        ids = _content_identifier_sets(REPO_ROOT / "content_sets" / "fantasy_frontier" / "data", issues)
        self.assertIn("bandit_rebellion", ids["campaigns"])
        self.assertIn("portbridge_smugglers", ids["campaigns"])

    def test_the_ability_ids_are_read_without_booting_a_world(self):
        """`SPELL_REGISTRY` is populated by world construction, after validation."""
        from engine.magic.spell_registry import SPELL_REGISTRY
        from engine.server.content_set import _content_identifier_sets

        SPELL_REGISTRY.clear()
        issues: list = []
        ids = _content_identifier_sets(REPO_ROOT / "content_sets" / "fantasy_frontier" / "data", issues)
        self.assertEqual(23, len(ids["spells"]))
        self.assertIn("magic_missile", ids["spells"])

    def test_a_content_set_without_abilities_reports_none_rather_than_failing(self):
        from engine.server.content_set import _content_identifier_sets

        issues: list = []
        ids = _content_identifier_sets(REPO_ROOT / "content_sets" / "modern_capsule" / "data", issues)
        self.assertEqual(set(), ids["spells"])


if __name__ == "__main__":
    unittest.main()
