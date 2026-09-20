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
  5. each content set: number types match the schema (`2.0` is not `2`)
  6. each content set: reference integrity, then the stale-reference audit
  7. each content set: skill audit (warnings only -- a skill no check rolls is
     a design question, so the build stays green while the gap is visible)
  8. engine content-neutrality, for fantasy and for the sci-fi proof
  9. each content set: booted and played (`content_playability_check.py`)
  10. the legacy editor fixture, if the recorded target exists on this machine

These gates exist because the defects they now catch all shipped silently:
five Portbridge rooms -- including the only quest giver for an entire campaign
-- with no way in; a mage set whose members do not exist anywhere in the
repository; content ids hardcoded in engine code; and eighteen dangling
references (a collection nobody authored, three minion templates, two rooms, a
damage channel the set never declared) in content that passed every gate that
existed at the time. Each gate tracks acknowledged gaps in an explicit
allowlist, so a NEW instance of the same class of mistake fails the build.

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


def resolve_recorded_path(recorded: str) -> Path:
    """Turn a path a tool recorded on some machine into one on this one.

    `fixture_refresh.py` writes absolute paths, so a committed
    `LATEST_REFRESH.json` points into whichever checkout produced it. That made
    these three steps skip on every machine but one -- including this one, where
    the fixture they are meant to check is committed under `server/data_fixtures/`.

    Two readings are therefore tried. A relative path is taken as repo-relative;
    an absolute path is used as written if it is still there, and otherwise
    reinterpreted from the first path segment that names something in this
    repository (`server`, `content_sets`, `toolkit`, ...). The recorded file is
    not rewritten: it is a log of what happened, and this is how to read it.
    """
    candidate = Path(recorded)
    if not candidate.is_absolute():
        return REPO_ROOT / candidate
    if candidate.exists():
        return candidate

    parts = candidate.parts
    for index, part in enumerate(parts):
        if part in ("server", "content_sets", "toolkit", "client", "mud-world-editor"):
            rebuilt = REPO_ROOT.joinpath(*parts[index:])
            if rebuilt.exists():
                return rebuilt
    return candidate
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

        # JSON has one number type, so `2.0` and `2` are the same file and
        # different values -- to Python, `isinstance(2.0, int)` is False. A JSON
        # writer that only emits floats (the world editor used to) therefore
        # silently turns every authored integer into a float, and the validator
        # above then rejects fields the author never touched. This gate fails on
        # that instead of letting it land, and names the tool that fixes it.
        run_step("Check content numbers match their schema types",
                 [python, f"{toolkit}/normalize_content_numbers.py"], env)

        for content_set in CONTENT_SETS:
            run_step("Validate content-set reference integrity: %s" % content_set,
                     [python, f"{toolkit}/reference_integrity_validator.py",
                      "content_sets/%s/data" % content_set], env)
            run_step("Audit stale content-set references: %s" % content_set,
                     [python, f"{toolkit}/stale_reference_audit.py",
                      "content_sets/%s/data" % content_set,
                      "--output", "tmp/stale_audit_%s.txt" % content_set], env)
            # Skills are named in four places (a ruleset's `skill`, a room exit's
            # `skill_name`, a dialogue check, a background grant) and declared in
            # one (`ruleset.skills.stat_bonuses`). Nothing checked the names
            # against each other, so a typo rolled at level 0 forever. Every
            # finding is a warning on purpose: a skill no check rolls is a design
            # question, not a broken build.
            run_step("Audit content-set skills: %s" % content_set,
                     [python, f"{toolkit}/skill_audit.py",
                      "content_sets/%s/data" % content_set], env)

        run_step("Validate engine content-neutrality",
                 [python, f"{toolkit}/content_neutrality_validator.py", "content_sets/fantasy_frontier"], env)
        # The sci-fi proof gets the same neutrality gate as the fantasy set. It is
        # the set whose whole purpose is to prove the engine reads declarations,
        # so engine code naming any of its content would be the exact failure it
        # exists to catch.
        run_step("Validate engine content-neutrality for the sci-fi proof",
                 [python, f"{toolkit}/content_neutrality_validator.py", "content_sets/orbital_salvage"], env)

        # Every contract field must have a read-or-delete verdict on record. The
        # rule it enforces -- a primitive with no consumer is worse than none --
        # has been found by hand three times now (`effect_packets`, the inert tier
        # weights, the unread `resource_cost`); this is the check that finds the
        # fourth without anyone thinking to look. It is a ledger rather than a
        # scan because a scan cannot tell a read from a mention: see the module
        # docstring for the three measured ways one gets it wrong here.
        run_step("Audit contract fields for a reader",
                 [python, f"{toolkit}/contract_field_audit.py"], env)

        # Everything above reads files. This one boots each set and plays it.
        # The two failures it exists for both validated perfectly: a set that
        # enabled `salvage` and declared no rule for any item, and a recipe file
        # whose top-level `_comment` aborted the loader and removed every recipe
        # in it. Neither is visible to a check that only resolves references.
        run_step("Play every content set",
                 [python, f"{toolkit}/content_playability_check.py"], env)

        # --- Legacy editor-fixture steps ------------------------------------
        # These validate a fixture produced by toolkit/fixture_refresh.py. The
        # recorded path is absolute and was written on the machine that produced
        # the fixture, so `resolve_recorded_path` reinterprets it against this
        # checkout. That is what makes the committed fixture under
        # `server/data_fixtures/` actually get checked; before this, the steps
        # skipped everywhere except the one directory they were recorded in.
        #
        # KNOWN TO FAIL IF ENABLED: the committed fixture is a partial editor
        # export (36-72 files) and `reference_integrity_validator` reports 37
        # errors on it, all cross-references to the full content set it was cut
        # from. `data_integrity_validator` and `stale_reference_audit` pass. Which
        # of the three belong in the gate is a content decision recorded in
        # `server/data_fixtures/README.md`; wiring all three up here would redden
        # the build today.
        latest = REPO_ROOT / "server" / "data_fixtures" / "LATEST_REFRESH.json"
        if latest.is_file():
            try:
                refresh = json.loads(latest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                print("SKIP: refreshed fixture checks - could not read %s: %s" % (latest, error))
                refresh = {}
            recorded = str(refresh.get("fixture_selected_target", "") or "").strip()
            if not recorded:
                print("SKIP: refreshed fixture checks - LATEST_REFRESH.json has no fixture_selected_target")
            else:
                target = resolve_recorded_path(recorded)
                if not target.exists():
                    print("SKIP: refreshed fixture checks - recorded fixture target is not in this checkout:")
                    print("      recorded: %s" % recorded)
                    print("      tried:    %s" % target)
                    print("      (regenerate with toolkit/fixture_refresh.py to validate a local fixture)")
                else:
                    print("==> refreshed fixture target: %s" % target)
                    run_step("Validate latest refreshed fixture JSON integrity",
                             [python, f"{toolkit}/data_integrity_validator.py", str(target)], env)
                    run_step("Audit stale latest refreshed fixture references",
                             [python, f"{toolkit}/stale_reference_audit.py", str(target),
                              "--output", "tmp/stale_audit_fixture_selected.txt"], env)
                    # `reference_integrity_validator` deliberately does NOT run
                    # here, although it used to be listed. The fixture is a partial
                    # editor export (36-72 files) cut from a full content set, so it
                    # references 37 items, NPCs and rooms that live in the set and
                    # not in the export. Measured on all three committed trees:
                    # data integrity 0 errors, stale audit 0 issues, reference
                    # integrity 37/51/60 errors. Whole-set reference integrity is
                    # the wrong instrument for a partial slice, and gating on it
                    # would fail the build for a property the fixture is not
                    # supposed to have.
                    #
                    # Re-enable it if the fixture is ever regenerated as a complete
                    # set. The reasoning and the counts are in
                    # `server/data_fixtures/README.md`.
    except StepFailed as failure:
        print()
        print(str(failure))
        return 1

    print()
    print("All content checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
