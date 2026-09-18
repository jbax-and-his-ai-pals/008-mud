"""Lift editor state out of the legacy mirror into the shared content set.

One-time migration for docs/roadmap/editor-content-source.md. The editor used to
read and write `mud-world-editor/data/`; that tree is being retired, but it holds
work worth keeping: room graph positions, exit layouts, the world map layout,
magic library grouping and room templates -- none of which the game server knows
or wants.

What moves where (all under the content set's `editor/` directory):

    world_layout.json          -> editor/world_layout.json
    magic_groups.json          -> editor/magic_groups.json
    templates/*                -> editor/templates/*
    regions/*.json  _editor_*  -> editor/regions/<id>.editor.json
    quests/quests.json stages  -> editor/quest_layout.json

Content itself is *not* copied: the mirror's items and NPCs are a stale subset of
canonical (1 weapon against 23, 1 villager against 21), so copying it back would
destroy content. Only editor-only state moves.

    python toolkit/migrate_editor_state.py --check     # report, change nothing
    python toolkit/migrate_editor_state.py             # migrate
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MIRROR = REPOSITORY_ROOT / "mud-world-editor" / "data"
DEFAULT_CONTENT_SET = REPOSITORY_ROOT / "content_sets" / "fantasy_frontier"

POSITION_KEY = "_editor_pos"
EXIT_LAYOUT_KEY = "_editor_exit_layout"


def is_editor_key(key: str) -> bool:
    return str(key).startswith("_editor_")


def editor_keys_of(source: dict) -> dict:
    return {k: v for k, v in source.items() if is_editor_key(str(k))}


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def plan(mirror: Path, content_set: Path) -> dict:
    """What the migration would do. Reporting is the same computation."""
    editor_dir = content_set / "editor"
    result = {
        "editor_dir": editor_dir,
        "files": [],          # simple one-for-one file copies
        "regions": {},        # region_id -> sidecar payload
        "quest_layout": {},   # quest_id -> {stage_index: position}
        "warnings": [],
    }

    for name in ("world_layout.json", "magic_groups.json"):
        source = mirror / name
        if source.is_file():
            result["files"].append((source, editor_dir / name))

    templates = mirror / "templates"
    if templates.is_dir():
        for source in sorted(templates.glob("*.json")):
            result["files"].append((source, editor_dir / "templates" / source.name))

    regions_dir = mirror / "regions"
    if regions_dir.is_dir():
        for source in sorted(regions_dir.glob("*.json")):
            payload = load(source)
            if not isinstance(payload, dict):
                result["warnings"].append("unreadable region: %s" % source.name)
                continue
            region_id = str(payload.get("region_id") or source.stem)
            region_keys = editor_keys_of(payload)
            rooms: dict[str, dict] = {}
            for room_id, room in (payload.get("rooms") or {}).items():
                if not isinstance(room, dict):
                    continue
                keys = editor_keys_of(room)
                if keys:
                    rooms[room_id] = keys
            if region_keys or rooms:
                result["regions"][region_id] = {"region": region_keys, "rooms": rooms}

    quests_path = mirror / "quests" / "quests.json"
    payload = load(quests_path)
    if isinstance(payload, dict):
        for quest_id, quest in payload.items():
            if not isinstance(quest, dict):
                continue
            stages = quest.get("stages")
            if not isinstance(stages, list):
                continue
            positions = {
                str(index): stage[POSITION_KEY]
                for index, stage in enumerate(stages)
                if isinstance(stage, dict) and POSITION_KEY in stage
            }
            if positions:
                result["quest_layout"][str(quest_id)] = positions

    return result


def summarise(migration: dict) -> None:
    print("editor directory : %s" % migration["editor_dir"])
    print("plain files      : %d" % len(migration["files"]))
    for source, target in migration["files"]:
        print("    %-34s -> %s" % (source.name, target.relative_to(migration["editor_dir"].parent)))
    print("region sidecars  : %d regions, %d rooms with layout"
          % (len(migration["regions"]),
             sum(len(payload["rooms"]) for payload in migration["regions"].values())))
    print("quest layout     : %d quests" % len(migration["quest_layout"]))
    for warning in migration["warnings"]:
        print("WARNING: %s" % warning)


def apply(migration: dict, mirror: Path) -> None:
    editor_dir = migration["editor_dir"]
    (editor_dir / "regions").mkdir(parents=True, exist_ok=True)
    (editor_dir / "templates").mkdir(parents=True, exist_ok=True)

    for source, target in migration["files"]:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    for region_id, payload in migration["regions"].items():
        target = editor_dir / "regions" / ("%s.editor.json" % region_id)
        target.write_text(json.dumps(payload, indent="\t") + "\n", encoding="utf-8")

    if migration["quest_layout"]:
        target = editor_dir / "quest_layout.json"
        target.write_text(json.dumps(migration["quest_layout"], indent="\t") + "\n", encoding="utf-8")

    print("\nMigrated into %s" % editor_dir)
    print("The legacy mirror at %s is no longer read by anything." % mirror)
    print("Remove it with: git rm -r %s" % mirror.relative_to(REPOSITORY_ROOT).as_posix())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mirror", default=str(DEFAULT_MIRROR),
                        help="legacy editor tree to lift state from")
    parser.add_argument("--content-set", default=str(DEFAULT_CONTENT_SET),
                        help="content set whose editor/ directory receives the state")
    parser.add_argument("--check", action="store_true",
                        help="report what would move, change nothing")
    args = parser.parse_args()

    mirror = Path(args.mirror)
    content_set = Path(args.content_set)
    if not mirror.is_dir():
        print("No legacy mirror at %s -- nothing to migrate." % mirror)
        return 0
    if not content_set.is_dir():
        print("No content set at %s." % content_set)
        return 2

    migration = plan(mirror, content_set)
    summarise(migration)
    if args.check:
        print("\n--check: nothing written.")
        return 0
    apply(migration, mirror)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
