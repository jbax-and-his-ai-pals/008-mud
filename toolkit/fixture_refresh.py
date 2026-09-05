from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import time
from pathlib import Path
from typing import Any

from editor_export_shim import shim_editor_export


def _on_rm_error(func: Any, path: str, _exc_info: Any) -> None:
    Path(path).chmod(stat.S_IWRITE)
    func(path)


def _safe_rmtree(path: Path) -> None:
    if not path.exists():
        return
    shutil.rmtree(path, onerror=_on_rm_error)


def _copy_tree(src: Path, dst: Path) -> None:
    _safe_rmtree(dst)
    shutil.copytree(src, dst)


def refresh_fixture(
    *,
    source_root: Path,
    latest_root: Path,
    fixture_root: Path,
    fixture_name: str,
    tmp_root: Path,
    strict: bool = True,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    latest_root = latest_root.resolve()
    fixture_root = fixture_root.resolve()
    tmp_root = tmp_root.resolve()
    fixture_name = str(fixture_name).strip()
    if fixture_name == "":
        raise ValueError("fixture_name is required")

    work_dir = tmp_root / f"fixture_refresh_{int(time.time())}"
    target_data = work_dir / "server_data"
    report_path = work_dir / "report.json"
    work_dir.mkdir(parents=True, exist_ok=True)

    report = shim_editor_export(
        source_root,
        target_data,
        validate=True,
        latest_root=latest_root,
    )
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    warnings = len(report.get("warnings", []))
    missing = len(report.get("missing", []))
    migration = report.get("migration", {})
    unresolved = len(migration.get("missing_item_ids", [])) + len(migration.get("missing_npc_ids", []))
    validation = report.get("validation", {})
    validation_errors = int(validation.get("data_errors", 0)) + int(validation.get("reference_errors", 0))
    if strict and (warnings > 0 or missing > 0 or unresolved > 0 or validation_errors > 0):
        raise RuntimeError("Strict refresh failed; see report for warnings/errors.")

    fixture_target = fixture_root / fixture_name
    fixture_root.mkdir(parents=True, exist_ok=True)
    selected_target = fixture_target
    replaced_primary = False
    replacement_error = ""
    try:
        _copy_tree(target_data, fixture_target)
        replaced_primary = True
    except Exception as exc:  # pragma: no cover - lock contention path
        replacement_error = str(exc)
        fallback = fixture_root / f"{fixture_name}__refresh_{int(time.time())}"
        _copy_tree(target_data, fallback)
        selected_target = fallback

    meta = {
        "status": "ok",
        "source_root": str(source_root),
        "latest_root": str(latest_root),
        "work_dir": str(work_dir),
        "report_path": str(report_path),
        "fixture_primary_target": str(fixture_target),
        "fixture_selected_target": str(selected_target),
        "replaced_primary_target": replaced_primary,
    }
    if replacement_error:
        meta["replacement_error"] = replacement_error
    marker = fixture_root / "LATEST_REFRESH.json"
    marker.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh a server data fixture from mud-world-editor export using latest-format hydration."
    )
    parser.add_argument("--source", default="mud-world-editor/data")
    parser.add_argument("--latest-root", default="content_sets/fantasy_frontier/data")
    parser.add_argument("--fixture-root", default="tmp/content_fixtures")
    parser.add_argument("--fixture-name", default="fantasy_editor_migrated_latest")
    parser.add_argument("--tmp-root", default="tmp")
    parser.add_argument("--no-strict", action="store_true")
    args = parser.parse_args()

    result = refresh_fixture(
        source_root=Path(args.source),
        latest_root=Path(args.latest_root),
        fixture_root=Path(args.fixture_root),
        fixture_name=args.fixture_name,
        tmp_root=Path(args.tmp_root),
        strict=(not args.no_strict),
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
