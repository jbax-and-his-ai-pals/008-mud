"""Bring the editor's gem authoring into the canonical content set.

The Gems tab work (`abd3175`) tagged gems with an intrinsic `rarity`, which
`GemGenerator.template_rarity` reads and falls back from only for legacy
templates. That authoring went to the editor's mirror, which the game does not
read, so every gem in play has been generated off the fallback path.

This merge is deliberately **additive**:

* gems in both trees gain `rarity` (and `weight`/`stackable`, which canonical gem
  templates never had, so they currently default to a 1.0-weight non-stackable
  item);
* the ten gems that exist only in the editor are added whole;
* canonical names, descriptions and values are left exactly as they are. The
  editor also renamed and re-priced the shared gems ("agate" -> "banded agate",
  30 -> 4.0), which may well be right now that rarity, size and quality
  multiply the base value -- but rewriting shipped text and prices is an
  editorial decision, not a migration, so it is reported rather than applied.

    python toolkit/merge_editor_gems.py --check
    python toolkit/merge_editor_gems.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CANONICAL = REPOSITORY_ROOT / "content_sets" / "fantasy_frontier" / "data" / "items" / "gems.json"
MIRROR = REPOSITORY_ROOT / "mud-world-editor" / "data" / "items" / "gems.json"

# Fields taken from the editor's copy when canonical has none of its own.
ADDITIVE_FIELDS = ("rarity", "weight", "stackable")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report, change nothing")
    args = parser.parse_args()

    canonical = load(CANONICAL)
    mirror = load(MIRROR)
    shared = sorted(set(canonical) & set(mirror))
    only_mirror = sorted(set(mirror) - set(canonical))
    only_canonical = sorted(set(canonical) - set(mirror))

    print("canonical gems: %d   editor gems: %d" % (len(canonical), len(mirror)))
    print("shared: %d   editor-only: %d   canonical-only: %d"
          % (len(shared), len(only_mirror), len(only_canonical)))

    tagged: list[str] = []
    for gem_id in shared:
        source, target = mirror[gem_id], canonical[gem_id]
        added = [field for field in ADDITIVE_FIELDS if field in source and field not in target]
        if not added:
            continue
        tagged.append("%s (%s)" % (gem_id, ", ".join(added)))
    print("\nwould gain authored fields: %d" % len(tagged))
    for line in tagged[:6]:
        print("    " + line)
    if len(tagged) > 6:
        print("    ... and %d more" % (len(tagged) - 6))

    print("\nwould be added whole: %d" % len(only_mirror))
    for gem_id in only_mirror:
        print("    %-24s rarity=%s value=%s" % (gem_id, mirror[gem_id].get("rarity", "-"), mirror[gem_id].get("value", "-")))

    editorial = [
        gem_id for gem_id in shared
        if mirror[gem_id].get("name") != canonical[gem_id].get("name")
        or mirror[gem_id].get("value") != canonical[gem_id].get("value")
        or mirror[gem_id].get("description") != canonical[gem_id].get("description")
    ]
    print("\neditorial differences NOT applied (name/description/value): %d" % len(editorial))
    for gem_id in editorial[:5]:
        print("    %-20s %r value %s -> %s" % (
            gem_id, canonical[gem_id].get("name"), canonical[gem_id].get("value"),
            mirror[gem_id].get("value")))

    if args.check:
        print("\n--check: nothing written.")
        return 0

    changed = 0
    for gem_id in shared:
        source, target = mirror[gem_id], canonical[gem_id]
        for field in ADDITIVE_FIELDS:
            if field in source and field not in target:
                target[field] = source[field]
                changed += 1
    for gem_id in only_mirror:
        canonical[gem_id] = dict(mirror[gem_id])

    CANONICAL.write_text(json.dumps(canonical, indent=2) + "\n", encoding="utf-8")
    print("\nWrote %s" % CANONICAL.relative_to(REPOSITORY_ROOT))
    print("  %d fields added, %d gems added, %d gems total" % (changed, len(only_mirror), len(canonical)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
