#!/usr/bin/env python3
"""Read and change a content-set JSON file by path, keeping it in the form the editor writes.

    python toolkit/content_edit.py get    ff4_slice data/npcs/people.json ilmaran_acolyte.attack_power
    python toolkit/content_edit.py set    ff4_slice data/npcs/people.json ilmaran_acolyte.attack_power 3
    python toolkit/content_edit.py set    ff4_slice data/scenes/story.json ilmara_falls.beats.0.pace '"slow"'
    python toolkit/content_edit.py append ff4_slice data/triggers/scenes.json some_trigger.effects.list '{"a": 1}'
    python toolkit/content_edit.py delete ff4_slice data/regions/ilmara.json rooms.crystal_chamber.initial_npcs.2
    python toolkit/content_edit.py get    ff4_slice data/npcs/people.json          # no path: the top-level keys

A path is dot-separated keys and array indexes (`rooms.crystal_chamber.initial_npcs.2`); a key that itself holds a dot
is not reachable this way (edit the file directly). A value is JSON: `3`, `true`, `"text"`, `{"k": 1}`; a bare word that
is not JSON is taken as a string. The file keeps its key order and indent, a whole number stays whole, and there is no
trailing newline, which is the editor's form; `toolkit/format_content.py` confirms it against the editor itself.

`--dry` prints what would be written instead of writing it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def locate(root: Any, parts: list[str]) -> tuple[Any, str]:
    """The container holding the last step of a path, and that step's key (an index for a list)."""
    node = root
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node, parts[-1]


def key_for(container: Any, part: str) -> Any:
    return int(part) if isinstance(container, list) else part


def parse_value(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return text


def whole(value: Any) -> Any:
    """A whole-number float is the integer it means (the editor writes `1`, not `1.0`)."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [whole(item) for item in value]
    if isinstance(value, dict):
        return {key: whole(item) for key, item in value.items()}
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("get", "set", "append", "delete"))
    parser.add_argument("content_set", help="a content set id (under content_sets/) or the path of a set")
    parser.add_argument("file", help="a path inside the set, e.g. data/npcs/people.json")
    parser.add_argument("path", nargs="?", default="", help="dot-separated keys and indexes")
    parser.add_argument("value", nargs="?", help="JSON (for set and append)")
    parser.add_argument("--dry", action="store_true", help="show the result instead of writing it")
    args = parser.parse_args()

    given = Path(args.content_set)
    base = given if given.is_dir() else REPO_ROOT / "content_sets" / args.content_set
    target = base / args.file
    if not target.is_file():
        print("No such file: %s" % target)
        return 2
    raw = target.read_text(encoding="utf-8")
    data = json.loads(raw)
    parts = [part for part in args.path.split(".") if part != ""]

    if args.action == "get":
        node = data
        for part in parts:
            node = node[int(part)] if isinstance(node, list) else node[part]
        print(json.dumps(list(node) if isinstance(node, dict) and not parts else node, indent=2, ensure_ascii=False))
        return 0

    if not parts:
        print("%s needs a path" % args.action)
        return 2
    container, last = locate(data, parts)
    if args.action in ("set", "append") and args.value is None:
        print("%s needs a value" % args.action)
        return 2
    if args.action == "set":
        container[key_for(container, last)] = whole(parse_value(args.value))
    elif args.action == "append":
        target_list = container[key_for(container, last)]
        if not isinstance(target_list, list):
            print("%s is not a list" % args.path)
            return 2
        target_list.append(whole(parse_value(args.value)))
    else:
        del container[key_for(container, last)]

    indent = 2 if raw.startswith('{\n  "') else 4
    text = json.dumps(data, indent=indent, ensure_ascii=False)
    if args.dry:
        print(text)
        return 0
    newline = "\r\n" if "\r\n" in raw else "\n"
    target.write_text(text.replace("\n", newline), encoding="utf-8", newline="")
    print("wrote %s" % target.relative_to(REPO_ROOT).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
