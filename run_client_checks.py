#!/usr/bin/env python3
"""Run every headless check in `client/tests/` against a real server.

The Godot client has behaviour no Python test can see: text revealed a few characters
at a time, panels dragged between docks, bars that drain, links that send commands. Those
used to be checked by hand, or by throwaway scripts. Each `client/tests/*_smoke.gd` here
boots the real client scene headlessly, connected to a real `poc_ws_server.py` playing
the story fixture in memory, and prints `ok`/`FAIL` lines; this runner starts a fresh server per
check (so no check inherits another's world), runs them, and reports.

    python3 run_client_checks.py
    python3 run_client_checks.py --godot /path/to/godot
    python3 run_client_checks.py dock          # only checks whose file name contains "dock"

Exit codes: 0 everything passed, 1 a check failed, 2 Godot was not found.

The client writes preferences, dock layouts and a session marker under Godot's per-user
folder; the checks run with that folder pointed at a temporary directory, so they never
touch (or are fooled by) a real player's settings.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from run_editor_checks import find_godot

REPO_ROOT = Path(__file__).resolve().parent
CLIENT_ROOT = REPO_ROOT / "client"
TESTS_DIR = CLIENT_ROOT / "tests"
# A frozen copy of the FF4 slice (server/tests/sets/README.md): the checks are of the client, not of the story, so the story is free to change.
CONTENT_SET = REPO_ROOT / "server" / "tests" / "sets" / "story_fixture"
TIMEOUT_SECONDS = 120


def client_tests(selection: list[str]) -> list[Path]:
    tests = sorted(TESTS_DIR.glob("*_smoke.gd"))
    if selection:
        tests = [t for t in tests if any(word in t.name for word in selection)]
    return tests


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def start_server(port: int) -> subprocess.Popen:
    command = [
        sys.executable, str(REPO_ROOT / "server" / "poc_ws_server.py"),
        "--content-set", str(CONTENT_SET), "--host", "127.0.0.1", "--port", str(port), "--ephemeral",
    ]
    server = subprocess.Popen(
        command, cwd=str(REPO_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 60
    while time.time() < deadline:
        if server.poll() is not None:
            raise RuntimeError("the test server exited at once (exit code %s)" % server.returncode)
        with socket.socket() as probe:
            probe.settimeout(0.5)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return server
        time.sleep(0.25)
    server.kill()
    raise RuntimeError("the test server did not start listening within 60 seconds")


def isolated_environment(port: int, user_dir: Path) -> dict[str, str]:
    environment = dict(os.environ)
    for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "HOME"):
        environment[name] = str(user_dir)
    environment["CLIENT_TEST_PORT"] = str(port)
    return environment


def run_check(godot: str, test: Path) -> tuple[bool, str]:
    port = free_port()
    user_dir = Path(tempfile.mkdtemp(prefix="client_check_"))
    server = None
    try:
        server = start_server(port)
        command = [godot, "--headless", "--path", str(CLIENT_ROOT), "--script", "res://tests/%s" % test.name]
        try:
            completed = subprocess.run(
                command, cwd=str(REPO_ROOT), capture_output=True, text=True, errors="replace",
                timeout=TIMEOUT_SECONDS, env=isolated_environment(port, user_dir),
            )
        except subprocess.TimeoutExpired:
            return False, "timed out after %d seconds" % TIMEOUT_SECONDS
        output = (completed.stdout or "") + (completed.stderr or "")
        failed = completed.returncode != 0 or "FAIL" in output or "SCRIPT ERROR" in output
        return (not failed), output
    except RuntimeError as problem:
        return False, str(problem)
    finally:
        if server is not None:
            server.kill()
            server.wait(timeout=10)
        shutil.rmtree(user_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Godot client's headless smoke checks.")
    parser.add_argument("--godot", help="path to the Godot executable")
    parser.add_argument("only", nargs="*", help="run only checks whose file name contains one of these words")
    args = parser.parse_args()

    godot = find_godot(args.godot)
    if not godot:
        print("Godot was not found. Pass --godot /path/to/godot or set GODOT_EXE.")
        return 2
    tests = client_tests(args.only)
    if not tests:
        print("No client checks found in %s" % TESTS_DIR)
        return 0

    failures = 0
    for test in tests:
        ok, output = run_check(godot, test)
        print("%s %s" % ("OK  " if ok else "FAIL", test.name))
        for line in output.splitlines():
            if not ok or line.strip().startswith(("ok ", "FAIL")):
                print("    " + line)
        failures += 0 if ok else 1
    if failures:
        print("%d of %d client checks failed." % (failures, len(tests)))
    else:
        print("All %d client checks passed." % len(tests))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
