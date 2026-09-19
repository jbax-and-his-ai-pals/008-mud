#!/usr/bin/env python3
"""Run every headless check in `mud-world-editor/tests/`.

The editor has its own test suite, but nothing ran it except by hand, one Godot
invocation per file. This is the same shape as `run_tests.py`: probe, run, report,
and say clearly when the toolchain is missing rather than failing obscurely.

    python3 run_editor_checks.py
    python3 run_editor_checks.py --godot /path/to/godot

Exit codes: 0 everything passed, 1 a check failed, 2 Godot was not found.

Godot is not vendored in this repository and the executable is named differently
on every platform, so `--godot`, then `$GODOT_EXE`, then a short list of likely
names and locations are tried in that order. When none is found the message says
what was tried and what to do, because "command not found" from a test runner is
not a useful answer.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
EDITOR_ROOT = REPO_ROOT / "mud-world-editor"
TESTS_DIR = EDITOR_ROOT / "tests"

# Names Godot ships under, most specific first.
GODOT_NAMES = (
    "godot", "godot4", "Godot", "godot.exe",
    "Godot_v4.7.2-stable_win64_console.exe", "Godot_v4.7.2-stable_win64.exe",
)

# Places a downloaded Godot tends to sit, relative to the user's home.
GODOT_LOCATIONS = (
    "Downloads", "Downloads/Godot", "Applications", "bin", ".local/bin",
    "scoop/apps/godot/current", "AppData/Local/Programs/Godot",
)


def find_godot(explicit: str | None) -> str:
    if explicit:
        return explicit if Path(explicit).exists() else ""
    from_env = os.environ.get("GODOT_EXE", "").strip()
    if from_env and Path(from_env).exists():
        return from_env
    for name in GODOT_NAMES:
        found = shutil.which(name)
        if found:
            return found
    home = Path.home()
    for location in GODOT_LOCATIONS:
        directory = home / location
        if not directory.is_dir():
            continue
        for name in GODOT_NAMES:
            for candidate in sorted(directory.glob(f"*{name}*")) + [directory / name]:
                if candidate.is_file():
                    return str(candidate)
    return ""


def editor_tests() -> list[Path]:
    return sorted(TESTS_DIR.glob("*.gd"))


def run_check(godot: str, test: Path) -> tuple[bool, str]:
    # The interpreter running this script is passed through, so a check that
    # needs Python (the engine-validation one) uses the same one the rest of the
    # build uses rather than probing for its own.
    command = [
        godot, "--headless", "--path", str(EDITOR_ROOT),
        "--script", "tests/%s" % test.name,
        "--", "--python", sys.executable,
    ]
    completed = subprocess.run(
        command, cwd=str(REPO_ROOT), capture_output=True, text=True, errors="replace",
    )
    detail = ""
    if completed.returncode != 0:
        tail = (completed.stdout + completed.stderr).strip().splitlines()[-12:]
        detail = "\n".join("    " + line for line in tail)
    return completed.returncode == 0, detail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--godot", help="path to the Godot executable")
    args = parser.parse_args()

    godot = find_godot(args.godot)
    if not godot:
        print("Godot was not found, so the editor checks cannot run.")
        print("Looked for: %s" % ", ".join(GODOT_NAMES))
        print("Looked in:  %s" % ", ".join(str(Path.home() / p) for p in GODOT_LOCATIONS))
        print("Pass --godot <path>, or set GODOT_EXE.")
        return 2

    print("==> Godot: %s" % godot)
    tests = editor_tests()
    if not tests:
        print("No tests found under %s." % TESTS_DIR)
        return 2

    failures: list[Path] = []
    for test in tests:
        ok, detail = run_check(godot, test)
        print("%s %s" % ("OK  " if ok else "FAIL", test.name))
        if detail:
            print(detail)
        if not ok:
            failures.append(test)

    print()
    if failures:
        print("%d of %d editor checks failed." % (len(failures), len(tests)))
        return 1
    print("All %d editor checks passed." % len(tests))
    return 0


if __name__ == "__main__":
    sys.exit(main())
