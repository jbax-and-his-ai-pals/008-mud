#!/usr/bin/env python3
"""Where every id is named -- the reverse of the reference sweep.

`reference_integrity_validator.py` asks "does this id exist?" by walking the files
that may name one. This asks the question an author asks before a rename or a
delete: **what names this id, and where?**

Both share `REFERENCE_FAMILIES` and `reference_tables()`, deliberately. An index
that knew a different set of references than the gate would be a second opinion
about what a reference *is*, which is the defect class this project keeps paying
for. The index locates; the gate judges.

What it does not claim
----------------------
A family is only indexed where the sweep already walks it: items, NPCs, abilities,
rooms, collections and recipes. A binding the sweep does not know about -- an NPC's
dialogue graph, a title's guild `place`, a quest's `spawn_on_entry.room_id` -- is
**not** in this index, so "no referrers" here means "none in the indexed families",
never "unused". Widening the index means widening `REFERENCE_FAMILIES` first, so
the gate and the index move together.

A referrer whose target is missing is reported `"resolved": false` rather than as
an error: whether a missing target fails the build is the gate's call, and it has
an allowlist for the ones that are deliberate (`KNOWN_DANGLING_REFERENCES`).

Usage:
    python toolkit/reference_index.py content_sets/fantasy_frontier/data
    python toolkit/reference_index.py <data-root> --json
    python toolkit/reference_index.py <data-root> --id item_iron_sword
    python toolkit/reference_index.py <data-root> --family items --limit 25
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_SERVER_ROOT = _REPO_ROOT / "server"
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))
# `toolkit/` modules import each other by bare name, which is how their CLIs run.
_TOOLKIT_ROOT = _REPO_ROOT / "toolkit"
if str(_TOOLKIT_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOLKIT_ROOT))

from toolkit import reference_integrity_validator as riv  # noqa: E402

# What the index does *not* see, stated in the payload as well as in this docstring.
# Each entry names where the reference is really enforced, so widening the index
# means moving that check into `REFERENCE_FAMILIES` first -- not adding a walker
# here, which would give the gate and the index different opinions.
NOT_INDEXED: Tuple[str, ...] = (
    "room placements (`rooms[].items[].item_id`, `rooms[].initial_npcs[].template_id`) "
    "-- enforced inline in `validate_catalogs`, not in the sweep",
    "room exits (`region:room` strings) -- enforced inline in `validate_catalogs`",
    "an NPC's dialogue graph binding (`properties.dialogue`) -- enforced by `content_set.py`",
    "a title's guild `place` and a quest's `spawn_on_entry.room_id` -- enforced by "
    "`content_set.py` and the quest validator",
    "contract references (family -> profile, ability -> effect packet) -- enforced by "
    "`contracts/registry.py`",
)

# Why "no referrers" is not "unused", quoted into the payload for the same reason.
PARTIAL_COVERAGE_NOTE = (
    "A family is indexed only where the reference sweep walks it. An id with no "
    "referrers here may still be named by a binding listed in `coverage.not_indexed`, "
    "so the index is evidence of *use*, never of disuse."
)


def _resolve_file(label: str, files: List[Tuple[str, Any]]) -> str:
    """Which file a walker's label came from.

    Most walkers label with `entry.path`, and an entry id is unique within a
    family, so `_file_of` can find the file again. Region walkers label with the
    *file* first (`regions/town.json.spawner.monster_types.goblin`), which
    `_file_of` would read as an entry id -- so that case is answered directly.
    """
    for name, _payload in files:
        if label.startswith(name + "."):
            return name
    return riv._file_of(label, files)


def _path_in_file(label: str, file_name: str) -> str:
    """The label with its file prefix removed, so it addresses the file's payload.

    A caller that wants to *apply* a change -- the editor's rename, or a
    `--rename` run -- needs a path relative to the file, not a label that
    sometimes repeats the file name. `regions/town.json.spawner.monster_types.goblin`
    becomes `spawner.monster_types.goblin`; every other walker already labels that
    way.
    """
    prefix = file_name + "."
    return label[len(prefix):] if label.startswith(prefix) else label


def references(root: Path) -> Iterator[Tuple[str, str, str, str, str, bool]]:
    """Every indexed reference: `(family, id, file, json_path, label, resolved)`."""
    catalogs = riv.load_catalogs(root)
    catalogs["region_rooms"] = riv._region_rooms(root)
    tables = riv.reference_tables(catalogs)
    for table_name, _singular, walker, patterns in riv.REFERENCE_FAMILIES:
        known = tables.get(table_name, set())
        files = riv._family_files(root, patterns)
        for label, value in walker(files):
            if not isinstance(value, str) or not value.strip():
                continue
            target = value.strip()
            file_name = _resolve_file(label, files)
            bare_label = _path_in_file(label, file_name)
            # `path` is where an edit goes; `label` is what a person reads. They
            # differ only for region files, and the walker's own grammar decides
            # which is which -- see `reference_json_path`.
            json_path = riv.reference_json_path(table_name, file_name, bare_label)
            yield table_name, target, file_name, json_path, bare_label, target in known


def build_index(root: Path) -> Dict[str, Any]:
    """The whole index: `families[family][id] = [{file, path, label, resolved}]`."""
    families: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    references_seen = 0
    unresolved: List[Dict[str, str]] = []
    for family, target, file_name, json_path, label, resolved in references(root):
        references_seen += 1
        families.setdefault(family, {}).setdefault(target, []).append(
            {"file": file_name, "path": json_path, "label": label, "resolved": resolved}
        )
        if not resolved:
            unresolved.append({"family": family, "id": target, "file": file_name})
    summary = {
        "families": {
            family: {
                "ids": len(entries),
                "references": sum(len(where) for where in entries.values()),
                "unresolved": sum(
                    1 for where in entries.values() for one in where if not one["resolved"]
                ),
            }
            for family, entries in sorted(families.items())
        },
        "ids": sum(len(entries) for entries in families.values()),
        "references": references_seen,
        "unresolved": len(unresolved),
    }
    return {
        "root": root.as_posix(),
        "families": families,
        "unresolved": unresolved,
        "summary": summary,
        "coverage": {
            "indexed": sorted(name for name, _s, _w, _p in riv.REFERENCE_FAMILIES),
            "source": "toolkit/reference_integrity_validator.REFERENCE_FAMILIES",
            "not_indexed": list(NOT_INDEXED),
            "note": PARTIAL_COVERAGE_NOTE,
        },
    }


def look_up(root: Path, wanted: str, family: str = "") -> Dict[str, Any]:
    """Every indexed reference to one id, optionally restricted to one family."""
    hits: Dict[str, List[Dict[str, Any]]] = {}
    for found_family, target, file_name, json_path, label, resolved in references(root):
        if target != wanted:
            continue
        if family and found_family != family:
            continue
        hits.setdefault(found_family, []).append(
            {"file": file_name, "path": json_path, "label": label, "resolved": resolved}
        )
    return {"id": wanted, "families": hits, "count": sum(len(v) for v in hits.values())}


def _human_report(index: Dict[str, Any], limit: int, family: str = "") -> str:
    lines = ["Reference index for %s" % index["root"], ""]
    summary = index["summary"]
    for name, counts in summary["families"].items():
        if family and name != family:
            continue
        lines.append(
            "  %-12s %4d ids  %5d references  %d unresolved"
            % (name, counts["ids"], counts["references"], counts["unresolved"])
        )
    lines.append(
        "  %-12s %4d ids  %5d references  %d unresolved"
        % ("total", summary["ids"], summary["references"], summary["unresolved"])
    )

    ranked: List[Tuple[int, str, str]] = []
    for name, entries in index["families"].items():
        if family and name != family:
            continue
        for target, where in entries.items():
            ranked.append((len(where), name, target))
    ranked.sort(reverse=True)
    if ranked:
        lines += ["", "Most-referenced ids (a rename touches all of these):"]
        for count, name, target in ranked[:limit]:
            files = sorted({one["file"] for one in index["families"][name][target]})
            lines.append("  %-32s %-10s %2d  %s" % (target, name, count, ", ".join(files[:3])))

    if index["unresolved"]:
        lines += ["", "Referrers whose target is missing (the gate decides if that fails):"]
        for one in index["unresolved"][:limit]:
            lines.append("  %-32s %-10s %s" % (one["id"], one["family"], one["file"]))

    coverage = index["coverage"]
    lines += [
        "",
        "Indexed families: %s" % ", ".join(coverage["indexed"]),
        "Not indexed (so absence here is not evidence of disuse):",
    ]
    for missing in coverage["not_indexed"]:
        lines.append("  - %s" % missing)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Index which files name which content ids (the reverse of the reference sweep)."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default="content_sets/fantasy_frontier/data",
        help="Path to a content set's data root.",
    )
    parser.add_argument("--json", action="store_true", help="Print the index as one JSON object.")
    parser.add_argument("--id", default="", help="Only report the referrers of this id.")
    parser.add_argument("--family", default="", help="Restrict to one reference family.")
    parser.add_argument("--limit", type=int, default=15, help="Rows in the readable report.")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(json.dumps({"error": "not a directory: %s" % root}))
        return 2

    if args.id:
        payload = look_up(root, args.id, args.family)
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if not payload["count"]:
            print("No indexed reference names '%s'." % args.id)
            return 0
        print("%s is named %d time(s):" % (args.id, payload["count"]))
        for name, where in payload["families"].items():
            for one in where:
                # The path is what makes two references in one file tell apart:
                # four vendor lines in `villagers.json` are four different edits.
                suffix = "" if one["resolved"] else "  (target missing)"
                print("  %-12s %-32s %s%s" % (name, one["file"], one["path"], suffix))
        return 0

    index = build_index(root)
    if args.json:
        print(json.dumps(index, indent=2, sort_keys=True))
        return 0
    print(_human_report(index, args.limit, args.family))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
