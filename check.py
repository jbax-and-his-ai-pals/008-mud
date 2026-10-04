#!/usr/bin/env python3
"""Run the project's gates together, or only the ones a change can affect.

    python check.py                  # all four gates at once (unit, content, editor, client)
    python check.py --quick          # what the uncommitted change can affect, found from `git diff`
    python check.py --gates unit,content
    python check.py --staged         # also refuse if a protected file is staged (see PROTECTED)

The gates are independent processes, so they run side by side: the whole set takes about as long as the
slowest (the editor's Godot checks, under a minute). Each one's output goes to `tmp/check/<gate>.log`; a gate that
fails has the tail of its log printed here.

`--quick` is for iterating. It reads the changed files (`git diff HEAD` and untracked), finds the unit-test modules
and editor/client checks that name what changed, and runs those plus the content gate, which is cheap. A passing
quick run says the change did not break what points at it; run the full set before committing.

Exit codes: 0 everything passed, 1 a gate failed, 2 a protected file is staged.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
LOG_DIR = REPO_ROOT / "tmp" / "check"
PYTHON = sys.executable

# Files the owner keeps hands-on or a gate depends on staying as authored; a commit that stages one is refused.
PROTECTED = (
    "content_sets/fantasy_frontier_test/",
    "mud-world-editor/scripts/data/RegionManager.gd",
    "mud-world-editor/tests/room_item_placement_smoke.gd",
)

NOISE = ("[DEBUG]", "[INFO]", "[WARNING]", "PluginManager", "Test mod setup")


def git_lines(*args: str) -> list[str]:
    done = subprocess.run(["git", *args], cwd=str(REPO_ROOT), capture_output=True, text=True, errors="replace")
    return [line.strip().replace("\\", "/") for line in done.stdout.splitlines() if line.strip()]


def staged_protected() -> list[str]:
    staged = git_lines("diff", "--cached", "--name-only")
    return [path for path in staged if any(path == p or path.startswith(p) for p in PROTECTED)]


def changed_files() -> list[str]:
    changed = set(git_lines("diff", "--name-only", "HEAD"))
    changed.update(git_lines("ls-files", "--others", "--exclude-standard"))
    return sorted(changed)


def _mentions(path: Path, word: str) -> bool:
    try:
        return re.search(r"\b%s\b" % re.escape(word), path.read_text(encoding="utf-8", errors="replace")) is not None
    except OSError:
        return False


def affected(changed: list[str]) -> dict[str, list[str]]:
    """Which unit modules and editor/client checks point at what changed."""
    unit_dir = REPO_ROOT / "server" / "tests"
    unit_files = [p for suite in ("singles", "batch", "current") for p in sorted((unit_dir / suite).rglob("test_*.py"))]
    editor_tests = sorted((REPO_ROOT / "mud-world-editor" / "tests").glob("*.gd"))
    client_tests = sorted((REPO_ROOT / "client" / "tests").glob("*_smoke.gd"))

    unit: set[str] = set()
    editor: set[str] = set()
    client: set[str] = set()
    engine_changed = False

    def dotted(path: Path) -> str:
        return ".".join(path.relative_to(REPO_ROOT / "server").with_suffix("").parts)

    for name in changed:
        path = Path(name)
        stem = path.stem
        if name.startswith("server/tests/") and stem.startswith("test_") and name.endswith(".py"):
            unit.add(".".join(Path(name[len("server/"):]).with_suffix("").parts))
            continue
        if name.startswith("mud-world-editor/tests/") and name.endswith(".gd"):
            editor.add(stem)
            continue
        if name.startswith("client/tests/") and name.endswith(".gd"):
            client.add(stem)
            continue
        words: list[str] = []
        if name.startswith(("server/engine/", "toolkit/")) and name.endswith(".py"):
            engine_changed = True
            if stem != "__init__":
                words.append(stem)
        elif name.startswith("content_sets/"):
            engine_changed = True
            parts = name.split("/")
            if len(parts) > 1:
                words.append(parts[1])
        elif name.startswith("mud-world-editor/scripts/") and name.endswith(".gd"):
            words.append(stem)
        elif name.startswith("client/") and name.endswith(".gd"):
            words.append(stem)
        for word in words:
            for test in unit_files:
                if _mentions(test, word):
                    unit.add(dotted(test))
            for test in editor_tests:
                if _mentions(test, word):
                    editor.add(test.stem)
            for test in client_tests:
                if _mentions(test, word):
                    client.add(test.stem)
    if engine_changed:
        # What reads the engine's vocabulary and the shipped sets from the editor's side.
        editor.update({"schema_parity_smoke", "content_round_trip_smoke"})
    return {"unit": sorted(unit), "editor": sorted(editor), "client": sorted(client)}


def gate_commands(selection: dict[str, list[str]] | None, wanted: list[str]) -> dict[str, list[str]]:
    commands: dict[str, list[str]] = {}
    for gate in wanted:
        if gate == "unit":
            if selection is None:
                commands["unit"] = [PYTHON, "run_tests.py", "--suite", "all"]
            elif selection["unit"]:
                commands["unit"] = [PYTHON, "run_tests.py", "--modules", ",".join(selection["unit"])]
        elif gate == "content":
            commands["content"] = [PYTHON, "run_content_checks.py"]
        elif gate == "editor":
            if selection is None:
                commands["editor"] = [PYTHON, "run_editor_checks.py"]
            elif selection["editor"]:
                only: list[str] = []
                for stem in selection["editor"]:
                    only += ["--only", stem]
                commands["editor"] = [PYTHON, "run_editor_checks.py", *only]
        elif gate == "client":
            if selection is None:
                commands["client"] = [PYTHON, "run_client_checks.py"]
            elif selection["client"]:
                commands["client"] = [PYTHON, "run_client_checks.py", *[stem for stem in selection["client"]]]
    return commands


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gates", default="unit,content,editor,client", help="comma separated: unit, content, editor, client")
    parser.add_argument("--quick", action="store_true", help="only what the uncommitted change can affect")
    parser.add_argument("--staged", action="store_true", help="refuse when a protected file is staged")
    args = parser.parse_args()

    if args.staged:
        bad = staged_protected()
        if bad:
            print("Refusing: these protected files are staged (see PROTECTED in check.py):")
            for path in bad:
                print("  " + path)
            return 2

    wanted = [gate.strip() for gate in args.gates.split(",") if gate.strip()]
    selection = None
    if args.quick:
        changed = changed_files()
        selection = affected(changed)
        print("==> %d changed files -> %d unit modules, %d editor checks, %d client checks" % (
            len(changed), len(selection["unit"]), len(selection["editor"]), len(selection["client"])))
    commands = gate_commands(selection, wanted)
    if not commands:
        print("Nothing to run.")
        return 0

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    started = time.time()
    running = {}
    for gate, argv in commands.items():
        log = open(LOG_DIR / ("%s.log" % gate), "w", encoding="utf-8")
        running[gate] = (subprocess.Popen(argv, cwd=str(REPO_ROOT), env=env, stdout=log, stderr=subprocess.STDOUT), log, time.time())

    failed: list[str] = []
    pending = dict(running)
    while pending:
        for gate, (process, log, began) in list(pending.items()):
            code = process.poll()
            if code is None:
                continue
            log.close()
            del pending[gate]
            print("%s %-8s %3.0fs" % ("OK  " if code == 0 else "FAIL", gate, time.time() - began))
            if code != 0:
                failed.append(gate)
        time.sleep(0.2)
    for gate in failed:
        path = LOG_DIR / ("%s.log" % gate)
        lines = [line.rstrip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
                 if line.strip() and not any(marker in line for marker in NOISE)]
        interesting = [line for line in lines if re.search(r"FAIL|Error|error|Traceback|assert", line)] or lines
        print("\n--- %s (%s)" % (gate, path.relative_to(REPO_ROOT).as_posix()))
        print("\n".join(interesting[-40:]))
    print("\n==> %s in %.0f seconds" % ("all passed" if not failed else "FAILED: " + ", ".join(failed), time.time() - started))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
