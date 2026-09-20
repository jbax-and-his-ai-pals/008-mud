#!/usr/bin/env python3
"""Move three engine classes' behaviour into the templates that used them.

`Gem`, `Junk` and `Treasure` were `Item` subclasses that did three things
between them: default `stackable`, set `gift_tags: ["gem"]` on every gem, and
return one hardcoded sentence from `use()`. Each of those is a content decision
the template could not make, so a content set could not retag its stones, change
one sentence, or say that a particular curio stacks.

This tool materialises what those classes currently do into the templates, so
removing the classes changes no item's behaviour. It is a migration, not a
policy: run it once, and afterwards `use_text` / `gift_tags` / `stackable` are
ordinary authored fields with no engine default standing behind them.

    python3 toolkit/materialize_item_class_defaults.py [--apply]

Without `--apply` it prints what it would write. With it, the files are rewritten
and the same report is printed, followed by a check that re-running finds
nothing -- the same idempotency proof `normalize_content_numbers.py` uses.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT_SETS_DIR = REPO_ROOT / "content_sets"

# What each retiring class supplied, as the template key that now supplies it.
# `use_text` is the only one the engine reads at construction; `stackable` and
# `gift_tags` are read by the factory and by gift scoring respectively.
CLASS_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "Gem": {
        "stackable": True,
        "gift_tags": ["gem"],
        "use_text": "You hold the {name} up to the light. It sparkles brilliantly.",
    },
    "Junk": {
        "stackable": True,
        "use_text": "You examine the {name}, but can't find any immediate use for it.",
    },
    "Treasure": {
        "stackable": False,
        # `Treasure.__init__` also passed `treasure_type="generic"`. Nothing
        # reads that value -- `chest_loot_generator` looks for `"coin"` -- so it
        # is recorded here for the templates that already carry a treasure_type
        # and deliberately not invented onto the rest.
        "use_text": "You admire the {name}. It looks quite valuable.",
    },
}


def _item_files(content_set: Path) -> List[Path]:
    items_dir = content_set / "data" / "items"
    return sorted(items_dir.glob("*.json")) if items_dir.is_dir() else []


def materialize_document(payload: Dict[str, Any]) -> List[str]:
    """Add the missing keys to one items file in place. Returns what changed."""
    changes: List[str] = []
    for template_id, template in payload.items():
        if str(template_id).startswith("_") or not isinstance(template, dict):
            continue
        defaults = CLASS_DEFAULTS.get(str(template.get("type", "")))
        if defaults is None:
            continue
        for key, value in defaults.items():
            if key in template:
                continue
            if key == "gift_tags" and isinstance(template.get("properties"), dict):
                if "gift_tags" in template["properties"]:
                    continue
            template[key] = list(value) if isinstance(value, list) else value
            changes.append("%s.%s" % (template_id, key))
    return changes


def materialize_content_set(content_set: Path, apply: bool = False) -> List[str]:
    changes: List[str] = []
    for path in _item_files(content_set):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            changes.append("%s: unreadable (%s)" % (path.name, error))
            continue
        if not isinstance(payload, dict):
            continue
        written = materialize_document(payload)
        if written and apply:
            # No trailing newline, matching how these files are already written:
            # the whole file is reformatted by this tool, so keeping the ending
            # byte-identical keeps the resulting diff to the keys that moved.
            path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
        changes.extend("%s:%s" % (path.relative_to(content_set).as_posix(), entry) for entry in written)
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="rewrite the files instead of reporting")
    args = parser.parse_args()

    sets = sorted(path for path in CONTENT_SETS_DIR.iterdir() if path.is_dir()) if CONTENT_SETS_DIR.is_dir() else []
    total = 0
    for content_set in sets:
        changes = materialize_content_set(content_set, apply=args.apply)
        total += len(changes)
        for change in changes:
            print("%s  %s" % (content_set.name, change))

    print()
    if not args.apply:
        print("%d template field(s) would be written. Re-run with --apply." % total)
        return 0

    print("%d template field(s) written." % total)
    remaining = sum(len(materialize_content_set(path, apply=False)) for path in sets)
    if remaining:
        print("NOT IDEMPOTENT: %d field(s) still missing after writing." % remaining)
        return 1
    print("Idempotent: a second pass finds nothing left to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
