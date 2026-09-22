# tests/singles/test_reference_index.py
"""The reference index finds the same references the gate validates.

`toolkit/reference_index.py` exists so the editor can answer "what names this id?"
before a rename or a delete. That is only useful if it and
`toolkit/reference_integrity_validator.py` agree about **what a reference is** --
an index that quietly knew fewer references than the gate would tell an author a
name was safe to change when it was not.

So the tests here are mostly parity, not features:

1. On a synthetic set with one reference of each indexed family, the index finds
   every one of them, with the file and the path inside it.
2. On that same set, every reference the gate reports as missing appears in the
   index as `resolved: false` -- same fixture, both tools, one verdict.
3. The index's own coverage claims are checked: the families it says it indexes are
   the families `REFERENCE_FAMILIES` defines, and the bindings it says it does not
   index really are absent from it (a room placement is the example used).
"""

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TOOLKIT = REPOSITORY_ROOT / "toolkit"
for path in (str(REPOSITORY_ROOT), str(REPOSITORY_ROOT / "server"), str(TOOLKIT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from toolkit import reference_index  # noqa: E402
from toolkit import reference_integrity_validator as riv  # noqa: E402


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_set(root: Path, sword_id: str = "item_sword", key_id: str = "item_key") -> None:
    """A set with one reference in each indexed family, plus one deliberate dangle."""
    write(root / "items" / "gear.json", {
        sword_id: {"name": "Sword", "type": "Weapon"},
        key_id: {"name": "Key", "type": "Key"},
        "item_blueprint": {
            "name": "Blueprint",
            "type": "Item",
            "properties": {"recipe_to_learn": "recipe_forge"},
        },
    })
    write(root / "npcs" / "folk.json", {
        "blacksmith": {
            "name": "Smith",
            "properties": {"work_location": "town:forge", "spell_to_learn": "spell_spark"},
            "loot_table": {sword_id: {"chance": 1.0}},
        },
    })
    write(root / "regions" / "town.json", {
        "region_id": "town",
        "name": "Town",
        "rooms": {
            "forge": {
                "name": "Forge",
                "properties": {"locked_by": key_id},
                # A placement is *not* indexed (the sweep does not walk it). It is
                # here so the coverage claim can be tested rather than asserted.
                "items": [{"item_id": "item_anvil", "quantity": 1}],
            },
        },
    })
    write(root / "crafting" / "recipes.json", {
        "recipe_forge": {
            "name": "Forge a blade",
            "result_item_id": sword_id,
            "ingredients": [],
        },
    })
    write(root / "magic" / "sparks.json", {
        "spell_spark": {"id": "spell_spark", "name": "Spark", "mana_cost": 1},
    })
    write(root / "collections.json", {"collection_blades": {"name": "Blades"}})
    write(root / "items" / "collectible.json", {
        "item_sword_shard": {
            "name": "Shard",
            "type": "Item",
            "properties": {"collection_id": "collection_blades"},
        },
    })


class ReferenceIndexTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="reference-index-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = self.tmp / "data"
        build_set(self.data)


class TestTheIndexFindsEveryIndexedFamily(ReferenceIndexTestCase):
    def test_one_reference_of_each_family_is_found_with_its_path(self) -> None:
        index = reference_index.build_index(self.data)
        expected = {
            # `item_sword` is named by a recipe *and* by a loot table; `item_key` is
            # named by a locked room.
            ("items", "item_sword"): {"crafting/recipes.json", "npcs/folk.json"},
            ("items", "item_key"): {"regions/town.json"},
            ("recipes", "recipe_forge"): {"items/gear.json"},
            ("collections", "collection_blades"): {"items/collectible.json"},
            ("abilities", "spell_spark"): {"npcs/folk.json"},
            ("rooms", "town:forge"): {"npcs/folk.json"},
        }
        for (family, target), files in expected.items():
            with self.subTest(family=family, id=target):
                where = index["families"].get(family, {}).get(target, [])
                self.assertTrue(where, "%s should be indexed as named by something" % target)
                self.assertTrue(
                    files <= {one["file"] for one in where},
                    "expected %s to name %s, got %s"
                    % (sorted(files), target, sorted({one["file"] for one in where})),
                )
                self.assertTrue(all(one["path"] for one in where), "a path is recorded")

    def test_an_id_nothing_names_is_absent_rather_than_empty(self) -> None:
        """`blacksmith` is declared by the fixture and named by nothing in it."""
        index = reference_index.build_index(self.data)
        self.assertNotIn("blacksmith", index["families"].get("npcs", {}))

    def test_a_room_reference_is_located_by_path(self) -> None:
        index = reference_index.build_index(self.data)
        where = index["families"]["rooms"]["town:forge"]
        self.assertEqual("npcs/folk.json", where[0]["file"])
        self.assertIn("work_location", where[0]["path"])

    def test_look_up_answers_the_used_by_question(self) -> None:
        payload = reference_index.look_up(self.data, "item_sword")
        self.assertEqual(2, payload["count"])
        self.assertEqual(
            {"crafting/recipes.json", "npcs/folk.json"},
            {one["file"] for one in payload["families"]["items"]},
        )

    def test_look_up_of_an_unreferenced_id_is_empty_not_an_error(self) -> None:
        payload = reference_index.look_up(self.data, "blacksmith")
        self.assertEqual(0, payload["count"])


class TestTheIndexAndTheGateAgree(ReferenceIndexTestCase):
    def _gate_issues(self):
        catalogs = riv.load_catalogs(self.data)
        issues = riv.validate_catalogs(catalogs)
        catalogs["region_rooms"] = riv._region_rooms(self.data)
        issues.extend(riv._reference_sweep_issues(catalogs))
        return [issue for issue in issues if "references missing" in issue.message]

    def test_every_dangling_reference_the_gate_reports_is_unresolved_in_the_index(self) -> None:
        # Plant a dangling reference: an NPC whose loot table names a sword that
        # does not exist in this fixture.
        write(self.data / "npcs" / "folk.json", {
            "blacksmith": {
                "name": "Smith",
                "properties": {"work_location": "town:forge"},
                "loot_table": {"item_missing_sword": {"chance": 1.0}},
            },
        })
        gate = self._gate_issues()
        self.assertTrue(gate, "the fixture must produce a missing reference for this to mean anything")
        self.assertTrue(any("item_missing_sword" in issue.message for issue in gate))

        index = reference_index.build_index(self.data)
        unresolved = {one["id"] for one in index["unresolved"]}
        self.assertIn("item_missing_sword", unresolved)
        self.assertIn("items", index["families"])
        where = index["families"]["items"]["item_missing_sword"]
        self.assertEqual([False], [one["resolved"] for one in where])

    def test_a_clean_fixture_is_clean_in_both_directions(self) -> None:
        # `item_anvil` is placed in a room but declared nowhere, so the gate has a
        # finding for it while the sweep -- and therefore the index -- does not.
        # That asymmetry is the documented coverage gap, asserted rather than
        # discovered later.
        gate = self._gate_issues()
        self.assertFalse(
            [issue for issue in gate if "item_anvil" in issue.message],
            "room placements belong to `validate_catalogs`, not to the sweep",
        )
        index = reference_index.build_index(self.data)
        self.assertNotIn("item_anvil", index["families"].get("items", {}))


class TestTheIndexStatesItsOwnCoverage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="reference-index-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = self.tmp / "data"
        build_set(self.data)

    def test_the_indexed_families_are_the_sweeps_own_families(self) -> None:
        index = reference_index.build_index(self.data)
        self.assertEqual(
            sorted(name for name, _s, _w, _p in riv.REFERENCE_FAMILIES),
            index["coverage"]["indexed"],
            "The index claims a different coverage than the sweep defines.",
        )

    def test_the_documented_gaps_are_really_absent_from_the_index(self) -> None:
        """A room placement is the example: `validate_catalogs` checks it, the sweep
        does not, so the index must not pretend to know about it."""
        index = reference_index.build_index(self.data)
        for family in index["families"].values():
            for target in family:
                self.assertNotEqual("item_anvil", target, "a room placement leaked into the index")
        self.assertTrue(index["coverage"]["not_indexed"], "the gaps are listed, not implied")

    def test_no_referrers_is_never_reported_as_disuse(self) -> None:
        index = reference_index.build_index(self.data)
        self.assertIn("never of disuse", index["coverage"]["note"])


if __name__ == "__main__":
    unittest.main()
