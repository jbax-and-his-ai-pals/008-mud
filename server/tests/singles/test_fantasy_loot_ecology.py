"""Every fantasy_frontier hostile is placed in the gem ecology on purpose.

The ruleset's ambient loot pools select creatures by `properties.loot_tags`
(`npc.py::_matches_ambient_loot_pool`). Tags were given to the first dozen
hostiles when the pools shipped, and the thirty written after them had none, so
a cave bear or a sand raider could never drop a gem. Untagged is silent, so
this names it: each hostile declares its tags, and a living one lands in at
least one pool while the undead, constructs, elementals and the like land in
none.
"""

import json
from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


def _hostiles() -> dict:
    out = {}
    for path in sorted((FANTASY_FRONTIER / "data" / "npcs").glob("*.json")):
        for npc_id, npc in json.loads(path.read_text(encoding="utf-8")).items():
            if isinstance(npc, dict) and npc.get("faction") == "hostile":
                out[npc_id] = npc
    return out


def _pools_for(npc_id: str, tags: set, pools: list) -> list:
    matched = []
    for index, pool in enumerate(pools):
        ids = set(pool.get("npc_template_ids") or [])
        if ids and npc_id not in ids:
            continue
        if pool.get("npc_tags_any") and not tags & set(pool["npc_tags_any"]):
            continue
        if not set(pool.get("npc_tags_all") or []) <= tags:
            continue
        if tags & set(pool.get("npc_tags_none") or []):
            continue
        matched.append(index)
    return matched


class TestFantasyLootEcology(unittest.TestCase):
    def setUp(self):
        ruleset = json.loads((FANTASY_FRONTIER / "rules" / "ruleset.json").read_text(encoding="utf-8"))
        self.pools = ruleset["loot"]["ambient_pools"]
        self.hostiles = _hostiles()

    def test_every_hostile_declares_its_loot_tags(self):
        untagged = sorted(npc_id for npc_id, npc in self.hostiles.items() if not npc.get("properties", {}).get("loot_tags"))
        self.assertEqual([], untagged)

    def test_living_hostiles_roll_a_pool_and_the_rest_do_not(self):
        for npc_id, npc in self.hostiles.items():
            tags = set(npc.get("properties", {}).get("loot_tags", []))
            with self.subTest(npc_id):
                if "living" in tags:
                    self.assertTrue(_pools_for(npc_id, tags, self.pools), f"{npc_id} is living but no pool selects it")
                else:
                    self.assertEqual([], _pools_for(npc_id, tags, self.pools))


if __name__ == "__main__":
    unittest.main()
