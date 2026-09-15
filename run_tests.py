#!/usr/bin/env python3
"""Run the server test suites with the interpreter you are already using.

This is the cross-platform implementation. `run_tests.ps1` is a Windows
launcher that picks a versioned interpreter and calls this; on Linux or macOS
just run it directly:

    python3 run_tests.py                    # all three suites
    python3 run_tests.py --suite singles    # just tests/singles
    python3 run_tests.py --target tests.singles.test_p4_progression

Why it exists
-------------
The suites were being run through a bare `python`, and on a machine with more
than one interpreter that is a coin toss. On the Windows checkout it landed on
a Python 3.14 that had none of the three runtime dependencies, so whole test
modules failed to import, a pygame stub stood in for the real library, and 40
"failures" appeared that were not defects -- while the same commit was green in
CI on Python 3.11. This script runs under whatever interpreter invoked it (so
the choice is explicit and visible), checks the three dependencies before
running anything, and refuses to produce a misleading number.

Exit codes: 0 all suites passed, 1 a suite failed, 2 dependencies missing.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SERVER_ROOT = REPO_ROOT / "server"
RESULTS_DIR = REPO_ROOT / "tmp" / "test-results"

SUITES = ("singles", "batch", "current")

# Package -> what breaks without it. `importlib.util.find_spec` is used rather
# than a real import so probing cannot execute package code (pygame prints a
# banner on import) and cannot raise for an unrelated reason.
REQUIRED = {
    "yaml": "PyYAML -- toolkit/data_integrity_validator.py imports it at module scope",
    "msgpack": "msgpack -- the transport codec tests skip without it",
    "pygame": "pygame (or pygame-ce) -- engine/utils/text_formatter.py imports it at module scope",
}


def missing_dependencies() -> list[str]:
    return [name for name in REQUIRED if importlib.util.find_spec(name) is None]


def build_environment() -> dict[str, str]:
    """A run environment that cannot be broken by the host's temp directory."""
    env = dict(os.environ)
    temp = REPO_ROOT / "tmp" / "pytemp"
    temp.mkdir(parents=True, exist_ok=True)
    env["TMP"] = env["TEMP"] = env["TMPDIR"] = str(temp)
    # Real pygame prints a support banner on import; it is noise here.
    env["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    return env


def report_missing(missing: list[str]) -> int:
    executable = sys.executable
    print()
    print("MISSING for this interpreter (%s):" % sys.version.split()[0])
    print("    %s" % executable)
    for name in missing:
        print("    %-8s -> %s" % (name, REQUIRED[name]))
    print()
    print("Install them for THIS interpreter:")
    print("    %s -m pip install -r server/requirements.txt" % _quoted(executable))
    print()
    print("On Python 3.14 plain pygame has no wheel yet; pygame-ce provides the")
    print("same `pygame` module and does:")
    print("    %s -m pip install pygame-ce PyYAML msgpack" % _quoted(executable))
    print()
    print("Refusing to run: a suite without these reports failures that are not")
    print("defects. See README.md, 'Setting up'.")
    return 2


def _quoted(value: str) -> str:
    return '"%s"' % value if " " in value else value


def run(argv: list[str], label: str, log_path: Path, env: dict[str, str]) -> int:
    print()
    print("==> %s  (log: %s)" % (label, log_path.relative_to(REPO_ROOT)))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as log:
        completed = subprocess.run(
            argv, cwd=str(SERVER_ROOT), env=env, stdout=log, stderr=subprocess.STDOUT
        )
    # Echo the log minus engine chatter, so a failure is readable in place.
    noise = ("[DEBUG]", "[INFO]", "[WARNING]", "PluginManager", "Test mod setup")
    tail = [
        line.rstrip()
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip() and not any(marker in line for marker in noise)
    ][-40:]
    print("\n".join(tail))
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--suite",
        choices=SUITES + ("all",),
        default="all",
        help="which suite to run (default: all three)",
    )
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        metavar="DOTTED.TEST",
        help="run specific tests instead of a suite (repeatable)",
    )
    parser.add_argument(
        "--check-dependencies",
        action="store_true",
        help="report missing packages and exit without running anything",
    )
    args = parser.parse_args()

    print("==> Interpreter: Python %s" % sys.version.split()[0])
    print("    %s" % sys.executable)

    missing = missing_dependencies()
    if missing:
        return report_missing(missing)
    print("    dependencies: %s" % ", ".join(sorted(REQUIRED)))

    if args.check_dependencies:
        return 0

    env = build_environment()
    failures: list[str] = []

    if args.target:
        for index, target in enumerate(args.target):
            argv = [sys.executable, "-m", "unittest", target]
            label = "selected: %s" % target
            code = run(argv, label, RESULTS_DIR / ("selected-%d.log" % index), env)
            if code != 0:
                failures.append(target)
    else:
        wanted = SUITES if args.suite == "all" else (args.suite,)
        for suite in wanted:
            argv = [
                sys.executable, "-m", "unittest", "discover",
                "-s", "tests/%s" % suite, "-p", "test_*.py", "-t", ".",
            ]
            code = run(argv, "tests/%s" % suite, RESULTS_DIR / ("%s.log" % suite), env)
            if code != 0:
                failures.append(suite)

    print()
    if failures:
        print("FAILED: %s  (logs in tmp/test-results)" % ", ".join(failures))
        return 1
    print("All suites passed. Logs in tmp/test-results.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
