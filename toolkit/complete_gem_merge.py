"""Finish the gem merge: make the recovered gems obtainable and collectable.

`merge_editor_gems.py` brought ten gems across from the editor's mirror. Two
content invariants then failed, correctly:

* every Gem template that is not crafted must appear in an authored ambient loot
  pool (`test_fantasy_gem_catalogue_has_authored_ambient_sources`), otherwise it
  exists but can never be found;
* the gem catalogue must equal the `riverside_gem_ledger` collection's items
  (`test_fantasy_gem_catalogue_is_a_static_collection`), because the museum set
  is the record of them.

So this adds each new gem to a pool that matches its rarity and to the ledger,
rather than relaxing the tests.

    python toolkit/complete_gem_merge.py --check
    python toolkit/complete_gem_merge.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTENT = REPOSITORY_ROOT / "content_sets" / "fantasy_frontier" / "data"
RULESET = REPOSITORY_ROOT / "content_sets" / "fantasy_frontier" / "rules" / "ruleset.json"
COLLECTIONS = CONTENT / "collections.json"
COLLECTION_ID = "riverside_gem_ledger"

# Which pool takes which rarity, and the weight to give it. Pools are ordered by
# scarcity in the ruleset (0.18 living, 0.10, 0.10, 0.04).
POOL_FOR_RARITY = {"common": 1, "uncommon": 2, "rare": 3, "legendary": 3}
WEIGHT_FOR_RARITY = {"common": 12, "uncommon": 8, "rare": 4, "legendary": 2}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def found_gem_ids() -> set[str]:
    """Gem templates a player can find -- i.e. not the crafted ones."""
    templates: dict[str, dict] = {}
    for path in sorted((CONTENT / "items").glob("*.json")):
        payload = load(path)
        if isinstance(payload, dict):
            templates.update({k: v for k, v in payload.items() if isinstance(v, dict)})
    crafted: set[str] = set()
    for path in sorted((CONTENT / "crafting").glob("*.json")):
        payload = load(path)
        if not isinstance(payload, dict):
            continue
        for recipe in payload.values():
            if not isinstance(recipe, dict):
                continue
            result = recipe.get("result_item_id")
            if result and templates.get(result, {}).get("type") == "Gem":
                crafted.add(str(result))
    return {i for i, t in templates.items() if t.get("type") == "Gem" and i not in crafted}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report, change nothing")
    args = parser.parse_args()

    ruleset = load(RULESET)
    pools = ruleset["loot"]["ambient_pools"]
    gem_ids = found_gem_ids()
    ambient = {entry["item_id"] for pool in pools for entry in pool["entries"]}
    collections = load(COLLECTIONS)
    ledger = collections[COLLECTION_ID]
    ledger_items = [str(i) for i in ledger.get("items", [])]

    templates: dict[str, dict] = {}
    for path in sorted((CONTENT / "items").glob("*.json")):
        payload = load(path)
        if isinstance(payload, dict):
            templates.update({k: v for k, v in payload.items() if isinstance(v, dict)})

    missing_from_pools = sorted(gem_ids - ambient)
    missing_from_ledger = sorted(gem_ids - set(ledger_items))
    extra_in_ledger = sorted(set(ledger_items) - gem_ids)

    print("found gems: %d   in a loot pool: %d   in the ledger: %d"
          % (len(gem_ids), len(gem_ids & ambient), len(gem_ids & set(ledger_items))))
    print("\nto add to a loot pool: %d" % len(missing_from_pools))
    for gem_id in missing_from_pools:
        rarity = str(templates[gem_id].get("rarity", "common"))
        print("    %-24s rarity=%-9s -> pool %d weight %d"
              % (gem_id, rarity, POOL_FOR_RARITY.get(rarity, 1), WEIGHT_FOR_RARITY.get(rarity, 10)))
    print("\nto add to the ledger: %d" % len(missing_from_ledger))
    if extra_in_ledger:
        print("in the ledger but not a found gem: %s" % ", ".join(extra_in_ledger))

    if args.check:
        print("\n--check: nothing written.")
        return 0

    for gem_id in missing_from_pools:
        rarity = str(templates[gem_id].get("rarity", "common"))
        pools[POOL_FOR_RARITY.get(rarity, 1)]["entries"].append({
            "item_id": gem_id,
            "weight": WEIGHT_FOR_RARITY.get(rarity, 10),
        })
    RULESET.write_text(json.dumps(ruleset, indent=2) + "\n", encoding="utf-8")

    ledger["items"] = ledger_items + missing_from_ledger
    COLLECTIONS.write_text(json.dumps(collections, indent=2) + "\n", encoding="utf-8")

    print("\nWrote %s and %s" % (RULESET.name, COLLECTIONS.name))
    print("  pools now hold %d entries; ledger now holds %d items"
          % (sum(len(p["entries"]) for p in pools), len(ledger["items"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
