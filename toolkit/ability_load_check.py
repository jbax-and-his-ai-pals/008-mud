"""Check that every authored ability is one the engine can actually build.

`data/abilities/*.json` (or `magic/`) is loaded by `spell_registry`, which builds
a whole *file* inside one `try` -- so a single ability the engine refuses stops
every remaining ability in that file from registering, and the only trace is a log
line at boot. Nothing validated these files: `content_set_validator` checks the
contract's ability *declarations*, not the entry files, so the world editor could
report "No issues found" for a set whose abilities the engine drops.

An authored entry is passed straight into `Spell(**data)`, which takes keywords
and no `**kwargs`: an unknown key (an editor-only annotation, a field from a
newer or older engine) is a `TypeError`, and a missing description or an empty
effects list is a `ValueError`. Both are content errors, and both are cheap to
name here with the file and the ability id.

Usage:
    python toolkit/ability_load_check.py <content-set or its data dir> [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "server"))

from engine.magic.spell import Spell  # noqa: E402


def _data_root(target: Path) -> Path:
    target = target.resolve()
    if target.name == "data":
        return target
    return target / "data"


def check(target: Path) -> dict:
    data_root = _data_root(target)
    findings: list[dict] = []
    loaded = 0

    abilities_dir = None
    for name in ("abilities", "magic"):
        candidate = data_root / name
        if candidate.is_dir():
            abilities_dir = candidate
            break

    if abilities_dir is None:
        return {
            "ok": True,
            "abilities_dir": "",
            "loaded": 0,
            "findings": [],
            "note": "this set declares no abilities directory",
        }

    for path in sorted(abilities_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            findings.append({"path": path.name, "ability": "", "message": "unreadable: %s" % error})
            continue
        if not isinstance(payload, dict):
            findings.append({"path": path.name, "ability": "", "message": "not an object of abilities"})
            continue
        for ability_id, entry in payload.items():
            if str(ability_id).startswith("_"):
                continue
            if not isinstance(entry, dict):
                findings.append({
                    "path": path.name, "ability": str(ability_id),
                    "message": "must be an object",
                })
                continue
            try:
                Spell.from_dict(str(ability_id), entry)
            except Exception as error:  # noqa: BLE001 - every refusal is the finding
                findings.append({
                    "path": path.name,
                    "ability": str(ability_id),
                    "message": "%s: %s" % (type(error).__name__, error),
                })
                continue
            loaded += 1

    return {
        "ok": not findings,
        "abilities_dir": abilities_dir.name,
        "loaded": loaded,
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check that authored abilities build.")
    parser.add_argument("content_set", help="Content-set directory, or its data directory.")
    parser.add_argument("--json", action="store_true", help="Print the report as one JSON object.")
    args = parser.parse_args()

    result = check(Path(args.content_set))

    if args.json:
        print(json.dumps(result))
        return 0 if result["ok"] else 1

    print("==> Check abilities build: %s" % Path(args.content_set).name)
    if not result["abilities_dir"]:
        print("SKIP: %s" % result["note"])
        return 0
    for finding in result["findings"]:
        print("[ERROR] %s/%s - %s" % (result["abilities_dir"], finding["path"], finding["message"]))
    if result["ok"]:
        print("OK: %d abilities in %s build" % (result["loaded"], result["abilities_dir"]))
        return 0
    print("%d of %d abilities would be dropped by the engine"
          % (len(result["findings"]), len(result["findings"]) + result["loaded"]))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
