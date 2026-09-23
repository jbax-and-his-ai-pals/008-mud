"""Apply a small, coherent group of configuration files as one checked change.

The editor uses this for the manifest capability toggle + its matching ruleset
system declaration.  Each candidate is validated in one copied content set;
only then are the originals replaced.  A write failure restores every file that
was already replaced, rather than leaving the manifest and ruleset disagreeing.

This is intentionally narrow.  It is a safe configuration transaction, not a
general migration runner: all files must be supported configuration files inside
one ordinary content set.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
# A Godot-launched script inherits the editor directory as its working
# directory, not the repository root.  Make both project packages importable
# from the script's own location rather than depending on the caller's cwd.
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "server"))
from engine.server.content_set import validate_content_set
from toolkit.configuration_save import _atomic_bytes


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _root_for(path: Path) -> Path:
    resolved = path.resolve()
    return next((parent for parent in resolved.parents if (parent / "content_set.manifest.json").is_file()), None)


def _supported_paths(root: Path, manifest: dict[str, Any]) -> set[Path]:
    content = Path(manifest.get("paths", {}).get("content_root", "data"))
    return {
        Path("content_set.manifest.json"),
        Path(manifest.get("paths", {}).get("ruleset", "rules/ruleset.json")),
        content / "contracts/world_contracts.json",
        content / "combat/elements.json",
    }


def save_configuration_pair(
    first_path: Path,
    first_candidate: dict[str, Any],
    first_expected: str,
    second_path: Path,
    second_candidate: dict[str, Any],
    second_expected: str,
) -> dict[str, Any]:
    """Validate and replace exactly two configuration files together.

    Raises for stale files, unsafe roots, disk errors, and a failed rollback. A
    validation refusal returns ``ok: false`` and changes neither destination.
    """
    entries = [(Path(first_path).resolve(), first_candidate, first_expected),
               (Path(second_path).resolve(), second_candidate, second_expected)]
    if entries[0][0] == entries[1][0]:
        raise ValueError("A configuration transaction needs two different files.")
    root = _root_for(entries[0][0])
    if root is None or _root_for(entries[1][0]) != root:
        raise ValueError("Configuration transaction files must belong to one content set.")
    if not all(isinstance(candidate, dict) for _, candidate, _ in entries):
        raise ValueError("Configuration transaction candidates must be JSON objects.")
    manifest = json.loads((root / "content_set.manifest.json").read_text(encoding="utf-8"))
    for value in manifest.get("paths", {}).values():
        if isinstance(value, str) and not (root / value).resolve().is_relative_to(root):
            raise ValueError("Configuration transactions do not support manifest paths outside this content set.")
    for entry in root.rglob("*"):
        if entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
            raise ValueError("Configuration transactions do not support linked content directories or files.")
    allowed = _supported_paths(root, manifest)
    for path, _, expected in entries:
        if path.relative_to(root) not in allowed:
            raise ValueError(f"{path.relative_to(root)} is not a supported configuration file.")
        if _digest(path.read_bytes()) != expected:
            raise ValueError("A configuration file changed outside this dialog. Reopen it before saving; no files were written.")

    originals = {path: path.read_bytes() for path, _, _ in entries}
    candidates = {
        path: json.dumps(candidate, indent=4, ensure_ascii=False, allow_nan=False).encode("utf-8")
        for path, candidate, _ in entries
    }
    if all(candidates[path] == originals[path] for path, _, _ in entries):
        return {"ok": True, "unchanged": True}

    with tempfile.TemporaryDirectory(prefix="mud-config-transaction-") as temporary:
        staged = Path(temporary) / root.name
        shutil.copytree(root, staged, ignore=shutil.ignore_patterns(".git", "editor", "saves", "__pycache__", "*.bak"))
        for path, _, _ in entries:
            (staged / path.relative_to(root)).write_bytes(candidates[path])
        issues = validate_content_set(staged)
        errors = [f"{issue.path}: {issue.message}".replace(str(staged), str(root))
                  for issue in issues if issue.severity == "error"]
        if errors:
            return {"ok": False, "error": "Engine validation refused this coordinated draft:\n" + "\n".join(errors)}

    # Validate did not hold the files open, but another program could have
    # changed either while it ran.  Re-check both before touching backups.
    for path, _, expected in entries:
        if _digest(path.read_bytes()) != expected:
            raise ValueError("A configuration file changed during validation. Nothing was saved; reopen and reconcile the changes.")

    for path, _, _ in entries:
        _atomic_bytes(path.with_name(path.name + ".bak"), originals[path])
    replaced: list[Path] = []
    try:
        for path, _, _ in entries:
            if candidates[path] == originals[path]:
                continue
            _atomic_bytes(path, candidates[path])
            replaced.append(path)
    except Exception:
        rollback_errors: list[str] = []
        for path in reversed(replaced):
            try:
                _atomic_bytes(path, originals[path])
            except Exception as error:  # pragma: no cover - catastrophic disk path
                rollback_errors.append(f"{path}: {error}")
        if rollback_errors:
            raise RuntimeError("Configuration apply failed and rollback also failed: " + "; ".join(rollback_errors))
        raise
    return {"ok": True, "unchanged": False}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first_path", type=Path)
    parser.add_argument("first_candidate", type=Path)
    parser.add_argument("first_expected")
    parser.add_argument("second_path", type=Path)
    parser.add_argument("second_candidate", type=Path)
    parser.add_argument("second_expected")
    args = parser.parse_args()
    try:
        result = save_configuration_pair(
            args.first_path, json.loads(args.first_candidate.read_text(encoding="utf-8")), args.first_expected,
            args.second_path, json.loads(args.second_candidate.read_text(encoding="utf-8")), args.second_expected,
        )
    except Exception as error:
        result = {"ok": False, "error": str(error)}
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
