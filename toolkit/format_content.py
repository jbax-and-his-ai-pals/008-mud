#!/usr/bin/env python3
"""Put hand-written content into the form the world editor writes.

The editor's round-trip check (`mud-world-editor/tests/content_round_trip_smoke.gd`) loads every shipped set's
`data/` through the editor and saves it back, and fails on any byte difference: a trailing newline, `1.0` where the
editor writes `1`, the wrong indent, a key in a different place. Content written by hand or by a script has to match,
and the way to know the form exactly is to ask the editor, so this does: it runs that check (which writes the editor's
version of every set under `tmp/content_round_trip/`) and then compares.

    python toolkit/format_content.py                  # list the files that are not in the editor's form
    python toolkit/format_content.py --apply          # rewrite them
    python toolkit/format_content.py --set ff4_slice --apply

Exit codes: 0 nothing to change (or changed with --apply), 1 files differ (without --apply), 2 Godot not found.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from run_editor_checks import EDITOR_ROOT, find_godot  # noqa: E402

SCRATCH = REPO_ROOT / "tmp" / "content_round_trip"
SHIPPED = REPO_ROOT / "content_sets"


def differing(set_id: str) -> list[Path]:
    """Files under a set's `data/` whose editor-written copy is not byte-identical."""
    original = SHIPPED / set_id / "data"
    canonical = SCRATCH / set_id / "data"
    found: list[Path] = []
    if not canonical.is_dir():
        return found
    for path in sorted(canonical.rglob("*.json")):
        relative = path.relative_to(canonical)
        source = original / relative
        if source.is_file() and source.read_bytes() != path.read_bytes():
            found.append(relative)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", action="append", default=[], dest="sets", help="a content set id (default: every set the editor check covers)")
    parser.add_argument("--apply", action="store_true", help="rewrite the files that differ")
    parser.add_argument("--godot", help="path to the Godot executable")
    args = parser.parse_args()

    godot = find_godot(args.godot)
    if not godot:
        print("Godot was not found (pass --godot or set GODOT_EXE).")
        return 2
    # The check's own verdict is not wanted here, only the copies it writes.
    subprocess.run(
        [godot, "--headless", "--path", str(EDITOR_ROOT), "--script", "tests/content_round_trip_smoke.gd",
         "--", "--python", sys.executable],
        cwd=str(REPO_ROOT), capture_output=True, text=True, errors="replace", timeout=300,
    )

    sets = args.sets or sorted(path.name for path in SCRATCH.iterdir() if path.is_dir()) if SCRATCH.is_dir() else []
    total = 0
    for set_id in sets:
        for relative in differing(set_id):
            total += 1
            print("%s %s/data/%s" % ("rewrote" if args.apply else "differs", set_id, relative.as_posix()))
            if args.apply:
                shutil.copyfile(SCRATCH / set_id / "data" / relative, SHIPPED / set_id / "data" / relative)
    if total == 0:
        print("every file is already in the editor's form")
        return 0
    return 0 if args.apply else 1


if __name__ == "__main__":
    sys.exit(main())
