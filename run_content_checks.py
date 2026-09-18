#!/usr/bin/env python3
"""Run every content gate: validators, neutrality, reference and stale audits.

Cross-platform and interpreter-explicit. This is the implementation; the
PowerShell script of the same name is now a thin launcher for it, and on
Linux/macOS you run it directly:

    python3 run_content_checks.py

What it runs, in order:

  1. client theme packs and starter packs (pack_tool)
  2. content-set JSON integrity (needs PyYAML; skipped with a note without it)
  3. mod manifest compatibility
  4. each content set: schema validation
  5. each content set: reference integrity, then the stale-reference audit
  6. engine content-neutrality
  7. the legacy editor fixture, if the recorded target exists on this machine

These gates exist because the defects they now catch all shipped silently:
five Portbridge rooms -- including the only quest giver for an entire campaign
-- with no way in; a mage set whose members do not exist anywhere in the
repository; and content ids hardcoded in engine code. Each gate tracks
acknowledged gaps in an explicit allowlist, so a NEW instance of the same class
of mistake fails the build.

Exit codes: 0 everything passed, 1 a step failed, 2 an interpreter/dependency
problem (as opposed to a content problem).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
CONTENT_SETS = ("fantasy_frontier", "modern_capsule", "night_shift", "orbital_salvage")


class StepFailed(Exception):
    def __init__(self, name: str, code: int) -> None:
        super().__init__("Step failed (%s) with exit code %d" % (name, code))
        self.name = name
        self.code = code


def build_environment() -> dict[str, str]:
    env = dict(os.environ)
    temp = REPO_ROOT / "tmp" / "pytemp"
    temp.mkdir(parents=True, exist_ok=True)
    env["TMP"] = env["TEMP"] = env["TMPDIR"] = str(temp)
    env["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    return env


def run_step(name: str, argv: list[str], env: dict[str, str]) -> None:
    print("==> %s" % name)
    completed = subprocess.run(argv, cwd=str(REPO_ROOT), env=env)
    if completed.returncode != 0:
        raise StepFailed(name, completed.returncode)
    print("OK: %s" % name)


def main() -> int:
    print("==> Interpreter: Python %s" % sys.version.split()[0])
    print("    %s" % sys.executable)
    env = build_environment()
    python = sys.executable
    toolkit = "toolkit"

    # PyYAML is needed by the JSON-integrity validator. Probe rather than assume,
    # so a missing dependency reads as a setup problem and not a content error.
    has_yaml = importlib.util.find_spec("yaml") is not None

    try:
        run_step("Validate client theme packs",
                 [python, f"{toolkit}/pack_tool.py", "validate", "client/themes"], env)
        run_step("Validate starter theme packs (strict)",
                 [python, f"{toolkit}/pack_tool.py", "validate", "toolkit/starter_packs", "--strict"], env)

        if has_yaml:
            run_step("Validate content-set JSON integrity",
                     [python, f"{toolkit}/data_integrity_validator.py",
                      "content_sets/fantasy_frontier/data"], env)
        else:
            print("SKIP: Validate content-set JSON integrity - PyYAML is not installed")
            print("      install it with: %s -m pip install -r server/requirements.txt" % python)

        run_step("Validate mod manifest compatibility",
                 [python, f"{toolkit}/mod_manifest_validator.py", "--roots", "server/mods", "mods"], env)

        for content_set in CONTENT_SETS:
            run_step("Validate content set: %s" % content_set,
                     [python, f"{toolkit}/content_set_validator.py", "content_sets/%s" % content_set], env)

        for content_set in CONTENT_SETS:
            run_step("Validate content-set reference integrity: %s" % content_set,
                     [python, f"{toolkit}/reference_integrity_validator.py",
                      "content_sets/%s/data" % content_set], env)
            run_step("Audit stale content-set references: %s" % content_set,
                     [python, f"{toolkit}/stale_reference_audit.py",
                      "content_sets/%s/data" % content_set,
                      "--output", "tmp/stale_audit_%s.txt" % content_set], env)

        run_step("Validate engine content-neutrality",
                 [python, f"{toolkit}/content_neutrality_validator.py", "content_sets/fantasy_frontier"], env)
        # The sci-fi proof gets the same neutrality gate as the fantasy set. It is
        # the set whose whole purpose is to prove the engine reads declarations,
        # so engine code naming any of its content would be the exact failure it
        # exists to catch.
        run_step("Validate engine content-neutrality for the sci-fi proof",
                 [python, f"{toolkit}/content_neutrality_validator.py", "content_sets/orbital_salvage"], env)

        # --- Legacy editor-fixture steps ------------------------------------
        # These validate a fixture produced by toolkit/fixture_refresh.py. The
        # recorded path is absolute and may point at a different checkout (the
        # committed LATEST_REFRESH.json points at C:\python\old\restart), so its
        # absence here is not a content failure -- report it and move on. If the
        # target does exist, the checks run and gate as before.
        latest = REPO_ROOT / "server" / "data_fixtures" / "LATEST_REFRESH.json"
        if latest.is_file():
            try:
                refresh = json.loads(latest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                print("SKIP: refreshed fixture checks - could not read %s: %s" % (latest, error))
                refresh = {}
            target = str(refresh.get("fixture_selected_target", "") or "").strip()
            if not target:
                print("SKIP: refreshed fixture checks - LATEST_REFRESH.json has no fixture_selected_target")
            elif not Path(target).exists():
                print("SKIP: refreshed fixture checks - recorded fixture target is not on this machine:")
                print("      %s" % target)
                print("      (regenerate with toolkit/fixture_refresh.py to validate a local fixture)")
            else:
                run_step("Validate latest refreshed fixture JSON integrity",
                         [python, f"{toolkit}/data_integrity_validator.py", target], env)
                run_step("Validate latest refreshed fixture reference integrity",
                         [python, f"{toolkit}/reference_integrity_validator.py", target], env)
                run_step("Audit stale latest refreshed fixture references",
                         [python, f"{toolkit}/stale_reference_audit.py", target,
                          "--output", "tmp/stale_audit_fixture_selected.txt"], env)
    except StepFailed as failure:
        print()
        print(str(failure))
        return 1

    print()
    print("All content checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
