"""Validate a staged configuration against the engine, then replace one file.

Not a multi-file migration service. External roots/symlinks are refused until an
overlay validator can safely resolve them; an unavailable validator fails closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from engine.server.content_set import validate_content_set


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


ABSENT = "absent"


def _creatable_paths(content: Path) -> set[Path]:
    """Optional configuration files a dialog may create; their absence is meaningful."""
    return {content / "world/field_interactions.json"}


def save_configuration(path: Path, candidate: dict, expected: str) -> dict:
    path = path.resolve()
    # ABSENT (not an empty string, which OS.execute drops on Windows) means the
    # dialog opened with no file: only an optional file may be created that
    # way, and only if it is still absent.
    before = path.read_bytes() if path.is_file() else None
    if (before is None and expected != ABSENT) or (before is not None and _digest(before) != expected):
        raise ValueError("This file changed outside this dialog. Reopen it before saving; your draft has not been written.")
    if not isinstance(candidate, dict):
        raise ValueError("Configuration must be a JSON object.")
    if before is not None and json.loads(before) == candidate:
        return {"ok": True, "unchanged": True}
    root = next((p for p in path.parents if (p / "content_set.manifest.json").is_file()), None)
    if root is None:
        raise ValueError("A content-set manifest is required to validate configuration changes.")
    manifest = json.loads((root / "content_set.manifest.json").read_text(encoding="utf-8"))
    for value in manifest.get("paths", {}).values():
        if isinstance(value, str) and not (root / value).resolve().is_relative_to(root):
            raise ValueError("Configuration saving does not yet support manifest paths outside this content set.")
    for entry in root.rglob("*"):
        if entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
            raise ValueError("Configuration saving does not yet support linked content directories or files.")
    relative = path.relative_to(root)
    content = Path(manifest.get("paths", {}).get("content_root", "data"))
    manifest_relative = Path("content_set.manifest.json")
    allowed = {Path(manifest.get("paths", {}).get("ruleset", "rules/ruleset.json")),
               content / "contracts/world_contracts.json", content / "combat/elements.json",
               manifest_relative} | _creatable_paths(content)
    opening = manifest.get("paths", {}).get("opening")
    if isinstance(opening, str) and opening.strip():
        allowed.add(Path(opening))
    if relative not in allowed:
        raise ValueError("This is not a supported configuration file.")
    if before is None and relative not in _creatable_paths(content):
        raise ValueError("This configuration file does not exist, and it is not one that may be created here.")
    if relative == manifest_relative:
        # The check above read the manifest on disk. A draft that moves its own
        # paths would make the staged validation read another tree -- and, once
        # saved, point the engine there for real. So the candidate is checked too,
        # before it is staged.
        if not isinstance(candidate.get("paths", {}), dict):
            raise ValueError("Manifest paths must be an object.")
        for key, value in candidate.get("paths", {}).items():
            if isinstance(value, str) and not (root / value).resolve().is_relative_to(root):
                raise ValueError(
                    "A manifest path may not point outside the content set: paths.%s = %s" % (key, value)
                )
    text = json.dumps(candidate, indent=4, ensure_ascii=False, allow_nan=False)
    with tempfile.TemporaryDirectory(prefix="mud-config-") as temporary:
        staged = Path(temporary) / root.name
        shutil.copytree(root, staged, ignore=shutil.ignore_patterns(".git", "editor", "saves", "__pycache__", "*.bak"))
        (staged / relative).parent.mkdir(parents=True, exist_ok=True)
        (staged / relative).write_text(text, encoding="utf-8")
        issues = validate_content_set(staged)
        errors = [f"{issue.path}: {issue.message}".replace(str(staged), str(root))
                  for issue in issues if issue.severity == "error"]
        if errors:
            return {"ok": False, "error": "Engine validation refused this draft:\n" + "\n".join(errors)}
    # Check again after validation, before either backup or destination is changed.
    now = path.read_bytes() if path.is_file() else None
    if (now is None) != (before is None) or (now is not None and _digest(now) != expected):
        raise ValueError("This file changed during validation. Nothing was saved; reopen and reconcile the changes.")
    if before is not None:
        _atomic_bytes(path.with_name(path.name + ".bak"), before)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_bytes(path, text.encode("utf-8"))
    return {"ok": True, "unchanged": False}


def _atomic_bytes(path: Path, data: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if Path(name).read_bytes() != data:
            raise OSError("Temporary write verification failed")
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("expected")
    args = parser.parse_args()
    try:
        result = save_configuration(args.path, json.loads(args.candidate.read_text(encoding="utf-8")), args.expected)
    except Exception as error:
        result = {"ok": False, "error": str(error)}
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
