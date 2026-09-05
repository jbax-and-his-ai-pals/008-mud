import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ValidationIssue:
    severity: str
    path: str
    message: str


def _looks_like_item_template(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    keys = set(value.keys())
    return bool({"type", "name", "description", "properties"} & keys)


def _validate_reward_items(node: Any, file_path: Path, pointer: str, issues: list[ValidationIssue]) -> None:
    if not isinstance(node, list):
        issues.append(
            ValidationIssue(
                "error",
                f"{file_path}:{pointer}",
                "rewards.items must be a list.",
            )
        )
        return
    for idx, entry in enumerate(node):
        entry_ptr = f"{pointer}[{idx}]"
        if not isinstance(entry, dict):
            issues.append(
                ValidationIssue(
                    "error",
                    f"{file_path}:{entry_ptr}",
                    "reward entry must be an object.",
                )
            )
            continue
        item_id = str(entry.get("item_id", "")).strip()
        if item_id == "":
            issues.append(
                ValidationIssue(
                    "error",
                    f"{file_path}:{entry_ptr}",
                    "reward entry requires non-empty item_id.",
                )
            )
        quantity = entry.get("quantity", 1)
        if not isinstance(quantity, int) or quantity <= 0:
            issues.append(
                ValidationIssue(
                    "error",
                    f"{file_path}:{entry_ptr}",
                    "reward quantity must be a positive integer.",
                )
            )


def _walk(value: Any, file_path: Path, pointer: str, issues: list[ValidationIssue], strict_templates: bool) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and key.strip() == "":
                issues.append(
                    ValidationIssue(
                        "error",
                        f"{file_path}:{pointer}",
                        "object contains an empty-string key.",
                    )
                )
            child_pointer = f"{pointer}.{key}" if pointer else str(key)
            if key == "items" and pointer.endswith("rewards"):
                _validate_reward_items(child, file_path, child_pointer, issues)
            _walk(child, file_path, child_pointer, issues, strict_templates)

        if (
            "items" in file_path.parts
            and file_path.name not in ("sets.json", "affixes.json")
            and _looks_like_item_template(value)
        ):
            name = str(value.get("name", "")).strip()
            item_type = str(value.get("type", "")).strip()
            if name == "" or item_type == "":
                severity = "error" if strict_templates else "warn"
                issues.append(
                    ValidationIssue(
                        severity,
                        f"{file_path}:{pointer or '<root>'}",
                        "item-like template should define non-empty 'name' and 'type'.",
                    )
                )
            properties = value.get("properties")
            if properties is not None and not isinstance(properties, dict):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"{file_path}:{pointer or '<root>'}",
                        "item-like template 'properties' must be an object when present.",
                    )
                )
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            child_pointer = f"{pointer}[{idx}]"
            _walk(child, file_path, child_pointer, issues, strict_templates)


def validate_payload(parsed: Any, source: str, strict_templates: bool = False) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(parsed, (dict, list)):
        issues.append(
            ValidationIssue(
                "error",
                source,
                "top-level JSON must be an object or array.",
            )
        )
        return issues
    _walk(parsed, Path(source), "", issues, strict_templates)
    return issues


def validate_json_file(file_path: Path, strict_templates: bool = False) -> list[ValidationIssue]:
    try:
        raw = file_path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
    except Exception as exc:
        return [ValidationIssue("error", str(file_path), f"failed to parse JSON: {exc}")]
    return validate_payload(parsed, str(file_path), strict_templates=strict_templates)


import yaml
import xml.etree.ElementTree as ET

def validate_yaml_file(file_path: Path, strict_templates: bool = False) -> list[ValidationIssue]:
    try:
        raw = file_path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(raw)
    except Exception as exc:
        return [ValidationIssue("error", str(file_path), f"failed to parse YAML: {exc}")]
    if parsed is None:
        return []
    return validate_payload(parsed, str(file_path), strict_templates=strict_templates)

def validate_svg_file(file_path: Path) -> list[ValidationIssue]:
    try:
        raw = file_path.read_text(encoding="utf-8")
        ET.fromstring(raw)
    except Exception as exc:
        return [ValidationIssue("error", str(file_path), f"failed to parse SVG XML: {exc}")]
    return []

def validate_tree(root: Path, strict_templates: bool = False) -> tuple[int, int, int]:
    ignored_dir_names = {
        "__pycache__",
        ".git",
        ".tmp",
        "saves",
        "unit_data_validator",
    }
    files: list[Path] = []
    for current_root, dir_names, file_names in os.walk(root, topdown=True):
        current_root = Path(current_root)
        dir_names[:] = [d for d in dir_names if d not in ignored_dir_names]
        for file_name in file_names:
            p = current_root / file_name
            if p.suffix in (".json", ".yaml", ".yml", ".svg"):
                files.append(p)
    files.sort()
    error_count = 0
    warn_count = 0
    checked = 0
    for path in files:
        checked += 1
        if path.suffix == ".json":
            issues = validate_json_file(path, strict_templates=strict_templates)
        elif path.suffix in (".yaml", ".yml"):
            issues = validate_yaml_file(path, strict_templates=strict_templates)
        elif path.suffix == ".svg":
            issues = validate_svg_file(path)
        else:
            continue
            
        for issue in issues:
            if issue.severity == "error":
                error_count += 1
                print(f"[ERROR] {issue.path} - {issue.message}")
            else:
                warn_count += 1
                print(f"[WARN]  {issue.path} - {issue.message}")
    print(f"Checked {checked} content files (JSON/YAML/SVG) under {root}")
    print(f"Errors: {error_count}  Warnings: {warn_count}")
    return checked, error_count, warn_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate content-set data JSON integrity.")
    parser.add_argument(
        "root",
        nargs="?",
        default="content_sets/fantasy_frontier/data",
        help="Root directory containing JSON content files.",
    )
    parser.add_argument(
        "--strict-templates",
        action="store_true",
        help="Treat missing item-template name/type as errors (default: warnings).",
    )
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists() or not root.is_dir():
        print(f"[ERROR] Root directory not found: {root}")
        raise SystemExit(2)

    _checked, error_count, _warn_count = validate_tree(root, strict_templates=args.strict_templates)
    raise SystemExit(1 if error_count > 0 else 0)


if __name__ == "__main__":
    main()
