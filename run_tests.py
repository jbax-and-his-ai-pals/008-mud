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
import json
import time
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


TIMINGS_PATH = REPO_ROOT / "tmp" / "test-timings.json"


def test_modules(suites: tuple[str, ...]) -> list[str]:
    """Every test module in the suites, as the dotted names `unittest` takes from the server root."""
    names: list[str] = []
    for suite in suites:
        for path in sorted((SERVER_ROOT / "tests" / suite).rglob("test_*.py")):
            names.append(".".join(path.relative_to(SERVER_ROOT).with_suffix("").parts))
    return names


def balance(modules: list[str], jobs: int, timings: dict[str, float]) -> list[list[str]]:
    """Longest-first into the lightest shard, by how long each module took last time (an unseen module
    counts as the median), so the shards finish together."""
    known = sorted(timings.get(name, 0.0) for name in modules if name in timings)
    median = known[len(known) // 2] if known else 1.0
    weighted = sorted(((timings.get(name, median), name) for name in modules), reverse=True)
    shards: list[list[str]] = [[] for _ in range(jobs)]
    loads = [0.0] * jobs
    for seconds, name in weighted:
        lightest = loads.index(min(loads))
        shards[lightest].append(name)
        loads[lightest] += seconds
    return [shard for shard in shards if shard]


def run_sharded(suites: tuple[str, ...], jobs: int, env: dict[str, str]) -> list[str]:
    """All the suites at once, as `jobs` processes that each run a share of the modules. Returns what failed."""
    modules = test_modules(suites)
    try:
        timings = json.loads(TIMINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        timings = {}
    shards = balance(modules, jobs, timings)
    print()
    print("==> %d test modules in %d shards%s" % (len(modules), len(shards), "" if timings else " (no timings yet: evenly spread)"))
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()
    running = []
    for index, shard in enumerate(shards):
        shard_env = dict(env)
        temp = REPO_ROOT / "tmp" / "pytemp" / ("shard-%d" % index)
        temp.mkdir(parents=True, exist_ok=True)
        shard_env["TMP"] = shard_env["TEMP"] = shard_env["TMPDIR"] = str(temp)
        log_path = RESULTS_DIR / ("shard-%d.log" % index)
        report_path = RESULTS_DIR / ("shard-%d.json" % index)
        if report_path.exists():
            report_path.unlink()
        log = open(log_path, "w", encoding="utf-8")
        process = subprocess.Popen(
            [sys.executable, "-m", "tests.shard_worker", "--report", str(report_path), *shard],
            cwd=str(SERVER_ROOT), env=shard_env, stdout=log, stderr=subprocess.STDOUT,
        )
        running.append((index, process, log, log_path, report_path))

    failures: list[str] = []
    ran = 0
    seconds: dict[str, float] = dict(timings)
    for index, process, log, log_path, report_path in running:
        code = process.wait()
        log.close()
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            report = None
        if report is None:
            failures.append("shard %d did not finish (exit %s; see %s)" % (index, code, log_path.relative_to(REPO_ROOT)))
            continue
        ran += report["ran"]
        seconds.update(report["seconds"])
        failures.extend(report["failed"])
        if code != 0:
            noise = ("[DEBUG]", "[INFO]", "[WARNING]", "PluginManager", "Test mod setup")
            tail = [line.rstrip() for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    if line.strip() and not any(marker in line for marker in noise)][-30:]
            print("\n--- shard %d (%s)" % (index, log_path.relative_to(REPO_ROOT)))
            print("\n".join(tail))
    TIMINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TIMINGS_PATH.write_text(json.dumps(seconds, indent=1, sort_keys=True), encoding="utf-8")
    print()
    print("==> %d tests in %.0f seconds" % (ran, time.time() - started))
    return failures


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
        "--jobs",
        type=int,
        default=min(16, max(1, (os.cpu_count() or 2) // 2)),
        help="run the suites as this many parallel shards (default: half the cores, at most 16; 1 runs them one "
             "after another, as before)",
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
    elif args.jobs > 1:
        wanted = SUITES if args.suite == "all" else (args.suite,)
        failures.extend(run_sharded(wanted, args.jobs, env))
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
