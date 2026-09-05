from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from reference_integrity_validator import load_catalogs, validate_catalogs


def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _walk_refs(payload: Any, path: str, out: list[tuple[str, str, str]]) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_name = str(key).strip().lower()
            here = f"{path}.{key}" if path else str(key)
            if key_name in {"item_id", "item_template_id"}:
                val = str(value).strip()
                if val:
                    out.append(("item", here, val))
            elif key_name in {"template_id", "target_template_id", "target_npc_id", "npc_template_id"}:
                val = str(value).strip()
                if val:
                    out.append(("npc", here, val))
            elif key_name in {"loot_table", "loot"} and isinstance(value, dict):
                for loot_id in value.keys():
                    val = str(loot_id).strip()
                    if val and (val.startswith("item_") or val.startswith("scroll_")):
                        out.append(("item", f"{here}.{loot_id}", val))
            _walk_refs(value, here, out)
    elif isinstance(payload, list):
        for idx, entry in enumerate(payload):
            _walk_refs(entry, f"{path}[{idx}]", out)


def audit_stale_references(root: Path) -> list[str]:
    catalogs = load_catalogs(root)
    issues = validate_catalogs(catalogs)
    item_ids: set[str] = catalogs["item_ids"]
    npc_ids: set[str] = catalogs["npc_template_ids"]
    extra: list[str] = []

    npcs_dir = root / "npcs"
    for p in sorted(npcs_dir.glob("*.json")):
        try:
            payload = _load_json(p)
        except Exception as exc:
            extra.append(f"[ERROR] {p}: parse failure: {exc}")
            continue
        refs: list[tuple[str, str, str]] = []
        _walk_refs(payload, f"npcs/{p.name}", refs)
        for ref_type, ref_path, ref_id in refs:
            if ref_type == "item" and ref_id not in item_ids:
                extra.append(f"[ERROR] {ref_path}: unknown item_id '{ref_id}'")
            if ref_type == "npc" and ref_id not in npc_ids:
                extra.append(f"[ERROR] {ref_path}: unknown npc template_id '{ref_id}'")

    lines: list[str] = []
    for issue in issues:
        prefix = "[ERROR]" if issue.severity == "error" else "[WARN]"
        lines.append(f"{prefix} {issue.path}: {issue.message}")
    lines.extend(extra)
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit stale content references beyond baseline integrity checks.")
    parser.add_argument("root", nargs="?", default="content_sets/fantasy_frontier/data", help="Content-set data root")
    parser.add_argument("--output", default="", help="Optional output report path")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists() or not root.is_dir():
        print(f"[ERROR] Root directory not found: {root}")
        raise SystemExit(2)
    lines = audit_stale_references(root)
    error_count = 0
    for line in lines:
        print(line)
        if line.startswith("[ERROR]"):
            error_count += 1
    print(f"Stale reference audit issues: {len(lines)} (errors: {error_count})")
    if str(args.output).strip():
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    raise SystemExit(1 if error_count > 0 else 0)


if __name__ == "__main__":
    main()
