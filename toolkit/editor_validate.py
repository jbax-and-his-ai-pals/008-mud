#!/usr/bin/env python3
"""One validation pass over a content set, as JSON, for the world editor.

The editor needs the *engine's* verdict, not a second opinion. This runs the
content checks that apply to one content set, in a single interpreter, and prints
one machine-readable document:

    {"ok": false, "counts": {"error": 1, "warning": 2},
     "issues": [{"severity": "error", "path": "...", "message": "...",
                 "source": "engine" | "references" | "templates" | "stale" | "json"}],
     "ran": ["engine", "references", ...], "skipped": ["json: PyYAML is not installed"],
     "not_run": {"playability": "boots and plays all four sets, ..."}}

**Which checks, and why that is not decided here.** The list lives in
`toolkit/content_check_steps.py`, shared with `run_content_checks.py`. It used to
be decided here and in prose: this file claimed to run "the same checks
`run_content_checks.py` runs" while running five of its fourteen, so the editor
could report "No issues found" for a set the build refuses -- and the ones it was
missing first were the number gate and the contract-field audit, both of which
exist specifically to catch defects the editor produces.

A check this cannot run is now *reported* in `not_run` with its reason, so the
editor shows its gaps instead of the author inferring there are none.

Why a separate entry point rather than `--json` on fourteen scripts: the editor
makes one subprocess call instead of fourteen interpreter starts, and every
validator keeps its own CLI for the cases where one of them is what you want.

Exit codes: 0 no errors (warnings allowed), 1 errors found, 2 the content set
could not be read at all.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_SERVER_ROOT = _REPO_ROOT / "server"
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))
# The toolkit's own modules import each other by bare name (that is how their
# CLIs run them), so `toolkit/` goes on the path too.
_TOOLKIT_ROOT = _REPO_ROOT / "toolkit"
if str(_TOOLKIT_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOLKIT_ROOT))

from toolkit import content_check_steps as steps_module  # noqa: E402

# Directories that hold no authored content, so a JSON-integrity walk skips them.
_IGNORED_DIR_NAMES = {"__pycache__", ".git", ".tmp", "saves", "editor", "unit_data_validator"}


def _issue(severity: str, path: str, message: str, source: str) -> dict:
    return {"severity": str(severity), "path": str(path), "message": str(message), "source": source}


def _resolve(content_set: Path) -> tuple[Path, Path]:
    """The content-set root and its data root, accepting either as the argument."""
    content_set = content_set.resolve()
    if content_set.name == "data" and (content_set.parent / "content_set.manifest.json").is_file():
        return content_set.parent, content_set
    return content_set, content_set / "data"


def validate(content_set: Path) -> dict:
    root, data_root = _resolve(content_set)
    issues: list[dict] = []
    ran: list[str] = []
    skipped: list[str] = []

    if not root.is_dir():
        return {
            "ok": False, "counts": {"error": 1, "warning": 0},
            "issues": [_issue("error", str(root), "content set directory does not exist", "setup")],
            "ran": [], "skipped": [],
        }

    # 1. The engine's own view: schema, references, dialogue, quests, contracts.
    try:
        from engine.server.content_set import validate_content_set

        ran.append("engine")
        for issue in validate_content_set(root):
            issues.append(_issue(issue.severity, issue.path, issue.message, "engine"))
    except Exception as error:  # noqa: BLE001 - a broken validator must not hide the rest
        skipped.append("engine: %s" % error)

    # 2. Reference integrity across items, NPCs, regions, quests and sets.
    try:
        from toolkit import reference_integrity_validator as riv

        ran.append("references")
        catalogs = riv.load_catalogs(data_root)
        for issue in riv.validate_catalogs(catalogs):
            issues.append(_issue(issue.severity, issue.path, issue.message, "references"))
    except Exception as error:  # noqa: BLE001
        skipped.append("references: %s" % error)

    # 3. Template placeholders in NPC dialogue, ability messages and item names.
    try:
        from toolkit import template_placeholder_validator as tpv

        ran.append("templates")
        for issue in tpv.validate_content_set(root):
            issues.append(_issue(issue.severity, issue.path, issue.message, "templates"))
    except Exception as error:  # noqa: BLE001
        skipped.append("templates: %s" % error)

    # 3b. Abilities the engine would refuse to build. `spell_registry` builds a
    #     whole file inside one `try`, so one bad entry drops the rest of that
    #     file -- and nothing else validated these files, which let "Validate
    #     Content" stay green for a set whose abilities never registered.
    try:
        from toolkit import ability_load_check as alc

        ran.append("abilities")
        ability_report = alc.check(root)
        for finding in ability_report["findings"]:
            issues.append(_issue(
                "error",
                str(Path("data") / ability_report["abilities_dir"] / finding["path"]),
                "%s: %s" % (finding["ability"] or "file", finding["message"]),
                "abilities",
            ))
    except Exception as error:  # noqa: BLE001
        skipped.append("abilities: %s" % error)

    # 4. References that point at ids nothing declares any more.
    try:
        from toolkit import stale_reference_audit as sra

        ran.append("stale")
        for line in sra.audit_stale_references(data_root):
            severity = "warning" if line.startswith("[WARN]") else "error"
            body = line
            for prefix in ("[ERROR] ", "[WARN]  ", "[WARN] "):
                if body.startswith(prefix):
                    body = body[len(prefix):]
                    break
            # "<path>:<pointer>: <message>" (or "<path>: <message>"). Splitting on
            # ": " keeps Windows drive letters intact, and gives the dedupe pass a
            # message that matches the reference validator's wording.
            location, separator, message = body.partition(": ")
            issues.append(_issue(severity, location if separator else "", message if separator else body, "stale"))
    except Exception as error:  # noqa: BLE001
        skipped.append("stale: %s" % error)

    # 5. Raw JSON integrity, including duplicate keys and template-shaped data.
    try:
        from toolkit import data_integrity_validator as div

        ran.append("json")
        for path in _json_files(data_root):
            for issue in div.validate_json_file(path):
                issues.append(_issue(issue.severity, issue.path, issue.message, "json"))
    except Exception as error:  # noqa: BLE001
        skipped.append("json: %s" % error)

    # 6. The number gate. This is the one the editor most needs: a JSON writer that
    #    only emits floats turns every authored integer into a float, and the
    #    editor used to be exactly that writer. Report-only here -- the fix is a
    #    deliberate `--apply`, never something a Validate button does behind the
    #    author's back.
    try:
        from toolkit import normalize_content_numbers as ncn

        ran.append("numbers")
        _total, offenders = ncn.normalize_content_set(root, apply=False)
        for offender in offenders:
            issues.append(_issue(
                "error", offender,
                "a number here is written as a float where the schema declares an "
                "integer; run `python toolkit/normalize_content_numbers.py --apply`",
                "numbers",
            ))
    except Exception as error:  # noqa: BLE001
        skipped.append("numbers: %s" % error)

    # 7. Every contract field needs a read-or-delete verdict on record. Repo-wide
    #    rather than per set, but it is cheap and it is about the schema this set's
    #    content is written against, so an editor session is the right moment to
    #    hear about a field nobody reads.
    try:
        from toolkit import contract_field_audit as cfa

        ran.append("contracts")
        unclassified, _unread, orphaned = cfa.audit()
        for section, field in unclassified:
            issues.append(_issue(
                "error", "%s.%s" % (section, field),
                "declared contract field with no read-or-delete verdict in "
                "toolkit/contract_field_audit.py", "contracts",
            ))
        for section, field in orphaned:
            issues.append(_issue(
                "error", "%s.%s" % (section, field),
                "the audit ledger names this field but no schema declares it", "contracts",
            ))
    except Exception as error:  # noqa: BLE001
        skipped.append("contracts: %s" % error)

    # 8. Skills are named in four places and declared in one; a typo rolls at
    #    level 0 forever. Warnings only, exactly as the gate treats them.
    try:
        from toolkit import skill_audit as sa

        ran.append("skills")
        ruleset_path = root / "rules" / "ruleset.json"
        findings, _inventory = sa.audit(
            data_root, ruleset_path if ruleset_path.is_file() else None, root,
        )
        for finding in findings:
            issues.append(_issue(finding.severity, finding.path, finding.message, "skills"))
    except Exception as error:  # noqa: BLE001
        skipped.append("skills: %s" % error)

    # 9. Engine content-neutrality, for the sets it is declared over. An editor
    #    session should not be how content ids get into engine code.
    set_id = root.name
    if set_id in steps_module.NEUTRALITY_SETS:
        try:
            from toolkit import content_neutrality_validator as cnv

            ran.append("neutrality")
            for found in cnv.validate(_REPO_ROOT, root):
                severity = getattr(found, "severity", "error")
                issues.append(_issue(
                    severity, getattr(found, "path", ""), getattr(found, "message", str(found)),
                    "neutrality",
                ))
        except Exception as error:  # noqa: BLE001
            skipped.append("neutrality: %s" % error)

    # 10. Boot and exercise the world currently being authored. The release gate
    # boots *every* shipped set, which is not suitable for an interactive button;
    # booting this one closes the more important gap where a set can validate as
    # JSON yet fail the first time a player creates a character or uses a command.
    try:
        from toolkit import content_playability_check as cpc

        ran.append("playability")
        for finding in cpc.check_one(root):
            issues.append(_issue(
                "error" if finding.fatal else "warning",
                "runtime/%s" % finding.command,
                finding.message,
                "playability",
            ))
    except Exception as error:  # noqa: BLE001
        skipped.append("playability: %s" % error)

    counts = {
        "error": sum(1 for i in issues if i["severity"] == "error"),
        "warning": sum(1 for i in issues if i["severity"] != "error"),
    }
    # Paths are reported relative to the content set: an editor showing an author
    # their own content should not lead with an absolute path from this machine.
    for issue in issues:
        issue["path"] = _relative(issue["path"], root)
    # Counted *after* dedupe, so the summary line and the list under it agree.
    # They did not: the validators overlap on purpose (the stale audit re-derives
    # some of what the reference validator finds), so fantasy_frontier reported
    # seven warnings above five rows. The `--only` path already recomputed its
    # counts; the unfiltered path -- the one the editor's modal shows -- did not.
    reported = _dedupe(issues)
    not_run = {
        check_id: reason
        for check_id, reason in steps_module.editor_coverage(set_id).items()
        if reason != "ran"
    }
    # `editor_coverage` describes the shared release-gate table, where
    # playability means every shipped set. Above we deliberately run the fast,
    # useful subset: the one the author has open. Say so directly rather than
    # claiming that a green editor report proved the other worlds too.
    not_run.pop("playability", None)
    not_run["playability_other_sets"] = (
        "the open content set was booted and exercised; run run_content_checks.py "
        "before release to play every shipped set"
    )
    return {
        "ok": counts["error"] == 0,
        "counts": {
            "error": sum(1 for i in reported if i["severity"] == "error"),
            "warning": sum(1 for i in reported if i["severity"] != "error"),
        },
        "issues": reported,
        "ran": ran,
        "skipped": skipped,
        # What this deliberately does not check, and why. An author reading a
        # green light deserves to know its scope.
        "not_run": not_run,
    }


def _relative(path: str, root: Path) -> str:
    text = str(path or "")
    for prefix in (str(root), str(root).replace("\\", "/")):
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip("\\/")
            break
    return text.replace("\\", "/")


def _dedupe(issues: list[dict]) -> list[dict]:
    """One entry per distinct problem.

    The validators overlap deliberately -- the stale audit re-derives some of what
    the reference validator already found -- so the same mage_set warning arrives
    from two sources. An author reading a list wants it once; the `sources` field
    records that both agree rather than hiding one.
    """
    merged: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for issue in issues:
        message = issue["message"]
        for prefix in ("[ERROR] ", "[WARN]  ", "[WARN] "):
            if message.startswith(prefix):
                message = message[len(prefix):]
        # The absolute path is part of the message for the stale audit only.
        message = message.replace(str(_REPO_ROOT), "")
        key = (issue["severity"], message)
        if key not in merged:
            entry = dict(issue)
            entry["message"] = message
            entry["sources"] = [issue["source"]]
            merged[key] = entry
            order.append(key)
        elif issue["source"] not in merged[key]["sources"]:
            merged[key]["sources"].append(issue["source"])
    return [merged[key] for key in order]


def _json_files(data_root: Path) -> list[Path]:
    files: list[Path] = []
    if not data_root.is_dir():
        return files
    for path in sorted(data_root.rglob("*.json")):
        if any(part in _IGNORED_DIR_NAMES for part in path.parts):
            continue
        files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one content set and print JSON.")
    parser.add_argument("content_set", help="Content-set directory, or its data/ directory.")
    parser.add_argument("--json", action="store_true", help="print the JSON document (always, for now)")
    parser.add_argument("--output", help="also write the JSON document here")
    parser.add_argument(
        "--only",
        help="limit the reported issues to these sources (comma-separated), for a caller "
             "that asks one specific question and would otherwise wade through the rest",
    )
    args = parser.parse_args()

    result = validate(Path(args.content_set))
    if args.only:
        wanted = {name.strip() for name in args.only.split(",") if name.strip()}
        result["issues"] = [
            issue for issue in result["issues"]
            if wanted & set(issue.get("sources", [issue.get("source", "")]))
        ]
        # The counts describe what is being reported, so they have to be recomputed
        # rather than left describing the full run.
        result["counts"] = {
            "error": sum(1 for i in result["issues"] if i["severity"] == "error"),
            "warning": sum(1 for i in result["issues"] if i["severity"] != "error"),
        }
        result["ok"] = result["counts"]["error"] == 0
        result["filtered_to"] = sorted(wanted)

    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)

    if not result["ran"]:
        return 2
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
