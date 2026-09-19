#!/usr/bin/env python3
"""One validation pass over a content set, as JSON, for the world editor.

The editor needs the *engine's* verdict, not a second opinion. This runs the same
checks `run_content_checks.py` runs -- the content-set schema and reference
validation, reference integrity, template placeholders, stale references and raw
JSON integrity -- in a single interpreter, and prints one machine-readable
document:

    {"ok": false, "counts": {"error": 1, "warning": 2},
     "issues": [{"severity": "error", "path": "...", "message": "...",
                 "source": "engine" | "references" | "templates" | "stale" | "json"}],
     "ran": ["engine", "references", ...], "skipped": ["json: PyYAML is not installed"]}

Why a separate entry point rather than `--json` on five scripts: the editor makes
one subprocess call instead of five interpreter starts, the editor and CI cannot
drift onto different checks, and every validator keeps its own CLI for the cases
where one of them is what you want.

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

    counts = {
        "error": sum(1 for i in issues if i["severity"] == "error"),
        "warning": sum(1 for i in issues if i["severity"] != "error"),
    }
    # Paths are reported relative to the content set: an editor showing an author
    # their own content should not lead with an absolute path from this machine.
    for issue in issues:
        issue["path"] = _relative(issue["path"], root)
    return {
        "ok": counts["error"] == 0,
        "counts": counts,
        "issues": _dedupe(issues),
        "ran": ran,
        "skipped": skipped,
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
    args = parser.parse_args()

    result = validate(Path(args.content_set))
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)

    if not result["ran"]:
        return 2
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
