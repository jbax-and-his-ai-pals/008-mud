from __future__ import annotations

import argparse
import json
import stat
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from data_integrity_validator import validate_tree
from reference_integrity_validator import load_catalogs, validate_catalogs


@dataclass(frozen=True)
class CopyRule:
    source_rel: str
    target_rel: str
    required: bool = False


_COPY_RULES: tuple[CopyRule, ...] = (
    CopyRule("items", "items"),
    CopyRule("npcs", "npcs"),
    CopyRule("regions", "regions"),
    CopyRule("magic", "magic"),
    CopyRule("quests/instances.json", "quests/instances.json"),
    CopyRule("quests.json", "quests/quests.json"),
    CopyRule("world_layout.json", "world/world_layout.editor.json"),
)

def _normalize_region_payload(payload: Any) -> tuple[Any, dict[str, int]]:
    stats = {
        "region_editor_keys_removed": 0,
        "room_editor_keys_removed": 0,
        "rooms_with_properties_added": 0,
    }
    if not isinstance(payload, dict):
        return payload, stats

    normalized = dict(payload)
    for key in list(normalized.keys()):
        if str(key).startswith("_editor_"):
            normalized.pop(key, None)
            stats["region_editor_keys_removed"] += 1

    rooms = normalized.get("rooms")
    if not isinstance(rooms, dict):
        return normalized, stats

    fixed_rooms: dict[str, Any] = {}
    for room_id, room in rooms.items():
        if not isinstance(room, dict):
            fixed_rooms[str(room_id)] = room
            continue
        room_obj = dict(room)
        for key in list(room_obj.keys()):
            if str(key).startswith("_editor_"):
                room_obj.pop(key, None)
                stats["room_editor_keys_removed"] += 1
        if "properties" not in room_obj or not isinstance(room_obj.get("properties"), dict):
            room_obj["properties"] = {}
            stats["rooms_with_properties_added"] += 1
        exits = room_obj.get("exits")
        if isinstance(exits, dict):
            room_obj["exits"] = {str(k): str(v).strip() for k, v in exits.items()}
        fixed_rooms[str(room_id)] = room_obj
    normalized["rooms"] = fixed_rooms
    return normalized, stats


def _normalize_export_tree(target_root: Path) -> dict[str, int]:
    summary = {
        "regions_processed": 0,
        "region_editor_keys_removed": 0,
        "room_editor_keys_removed": 0,
        "rooms_with_properties_added": 0,
    }
    regions_dir = target_root / "regions"
    if not regions_dir.exists() or not regions_dir.is_dir():
        return summary
    for region_file in sorted(regions_dir.glob("*.json")):
        try:
            raw = region_file.read_text(encoding="utf-8")
            parsed = json.loads(raw)
        except Exception:
            continue
        normalized, stats = _normalize_region_payload(parsed)
        region_file.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
        summary["regions_processed"] += 1
        summary["region_editor_keys_removed"] += stats["region_editor_keys_removed"]
        summary["room_editor_keys_removed"] += stats["room_editor_keys_removed"]
        summary["rooms_with_properties_added"] += stats["rooms_with_properties_added"]
    return summary


def _normalize_quest_payload(path: Path, default_type: str) -> dict[str, int]:
    stats = {
        "templates_processed": 0,
        "types_added": 0,
        "stage_indexes_added": 0,
    }
    if not path.exists() or not path.is_file():
        return stats
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return stats
    if not isinstance(parsed, dict):
        return stats
    normalized: dict[str, Any] = {}
    for template_id, template in parsed.items():
        if not isinstance(template, dict):
            normalized[str(template_id)] = template
            continue
        obj = dict(template)
        stats["templates_processed"] += 1
        if str(obj.get("type", "")).strip() == "":
            obj["type"] = default_type
            stats["types_added"] += 1
        stages = obj.get("stages")
        if isinstance(stages, list):
            fixed_stages: list[Any] = []
            next_index = 0
            for stage in stages:
                if not isinstance(stage, dict):
                    fixed_stages.append(stage)
                    next_index += 1
                    continue
                stage_obj = dict(stage)
                if "stage_index" not in stage_obj:
                    stage_obj["stage_index"] = next_index
                    stats["stage_indexes_added"] += 1
                fixed_stages.append(stage_obj)
                next_index += 1
            obj["stages"] = fixed_stages
        normalized[str(template_id)] = obj
    path.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
    return stats


def _load_template_payloads(dir_path: Path) -> dict[str, dict[str, Any]]:
    templates: dict[str, dict[str, Any]] = {}
    if not dir_path.exists() or not dir_path.is_dir():
        return templates
    for json_file in sorted(dir_path.glob("*.json")):
        try:
            parsed = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        for template_id, payload in parsed.items():
            if isinstance(template_id, str) and isinstance(payload, dict):
                templates[template_id] = payload
    return templates


def _collect_references_for_migration(target_root: Path) -> tuple[set[str], set[str]]:
    item_ids: set[str] = set()
    npc_ids: set[str] = set()
    regions_dir = target_root / "regions"
    if regions_dir.exists():
        for region_file in sorted(regions_dir.glob("*.json")):
            try:
                parsed = json.loads(region_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            rooms = parsed.get("rooms", {}) if isinstance(parsed, dict) else {}
            if not isinstance(rooms, dict):
                continue
            for room in rooms.values():
                if not isinstance(room, dict):
                    continue
                items = room.get("items", [])
                if isinstance(items, list):
                    for entry in items:
                        if isinstance(entry, dict):
                            iid = str(entry.get("item_id", "")).strip()
                            if iid:
                                item_ids.add(iid)
                npcs = room.get("initial_npcs", [])
                if isinstance(npcs, list):
                    for entry in npcs:
                        if isinstance(entry, dict):
                            nid = str(entry.get("template_id", "")).strip()
                            if nid:
                                npc_ids.add(nid)
    for qfile in (target_root / "quests" / "quests.json", target_root / "quests" / "instances.json"):
        if not qfile.exists():
            continue
        try:
            parsed = json.loads(qfile.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        for template in parsed.values():
            if not isinstance(template, dict):
                continue
            rewards = template.get("rewards", {})
            if isinstance(rewards, dict):
                ritems = rewards.get("items", [])
                if isinstance(ritems, list):
                    for entry in ritems:
                        if isinstance(entry, dict):
                            iid = str(entry.get("item_id", "")).strip()
                            if iid:
                                item_ids.add(iid)
            stages = template.get("stages", [])
            if isinstance(stages, list):
                for stage in stages:
                    if not isinstance(stage, dict):
                        continue
                    tid = str(stage.get("turn_in_id", "")).strip()
                    if tid:
                        npc_ids.add(tid)
                    spawn = stage.get("spawn_on_entry", {})
                    if isinstance(spawn, dict):
                        nid = str(spawn.get("template_id", "")).strip()
                        if nid:
                            npc_ids.add(nid)
                    objective = stage.get("objective", {})
                    if isinstance(objective, dict):
                        for field in ("item_id", "item_template_id"):
                            iid = str(objective.get(field, "")).strip()
                            if iid:
                                item_ids.add(iid)
                        for field in ("target_template_id", "target_npc_id", "recipient_id"):
                            nid = str(objective.get(field, "")).strip()
                            if nid:
                                npc_ids.add(nid)
    # NPC template-level references (vendor stock, loot tables, summon targets, etc.).
    npcs_dir = target_root / "npcs"
    if npcs_dir.exists():
        for npc_file in sorted(npcs_dir.glob("*.json")):
            try:
                parsed = json.loads(npc_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(parsed, dict):
                continue
            for payload in parsed.values():
                _collect_ids_from_payload(payload, item_ids, npc_ids)
    return item_ids, npc_ids


def _collect_ids_from_payload(payload: Any, item_ids: set[str], npc_ids: set[str]) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_name = str(key).strip().lower()
            if key_name in {"item_id", "item_template_id"}:
                text = str(value).strip()
                if text:
                    item_ids.add(text)
            elif key_name in {"template_id", "target_template_id", "target_npc_id", "npc_template_id"}:
                text = str(value).strip()
                if text:
                    npc_ids.add(text)
            elif key_name in {"loot_table", "loot"} and isinstance(value, dict):
                for item_key in value.keys():
                    text = str(item_key).strip()
                    if text:
                        item_ids.add(text)
            _collect_ids_from_payload(value, item_ids, npc_ids)
    elif isinstance(payload, list):
        for entry in payload:
            _collect_ids_from_payload(entry, item_ids, npc_ids)


def _hydrate_from_latest(target_root: Path, latest_root: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "latest_root": str(latest_root),
        "missing_item_ids": [],
        "missing_npc_ids": [],
        "hydrated_item_ids": [],
        "hydrated_npc_ids": [],
    }
    latest_items = _load_template_payloads(latest_root / "items")
    latest_npcs = _load_template_payloads(latest_root / "npcs")
    target_items = _load_template_payloads(target_root / "items")
    target_npcs = _load_template_payloads(target_root / "npcs")
    referenced_items, referenced_npcs = _collect_references_for_migration(target_root)
    need_items = sorted(i for i in referenced_items if i not in target_items)
    need_npcs = sorted(n for n in referenced_npcs if n not in target_npcs)

    add_items: dict[str, Any] = {}
    for item_id in need_items:
        payload = latest_items.get(item_id)
        if payload is None:
            summary["missing_item_ids"].append(item_id)
            continue
        add_items[item_id] = payload
        summary["hydrated_item_ids"].append(item_id)

    add_npcs: dict[str, Any] = {}
    for npc_id in need_npcs:
        payload = latest_npcs.get(npc_id)
        if payload is None:
            summary["missing_npc_ids"].append(npc_id)
            continue
        add_npcs[npc_id] = payload
        summary["hydrated_npc_ids"].append(npc_id)

    if add_items:
        out_path = target_root / "items" / "migrated_latest.items.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(add_items, indent=2) + "\n", encoding="utf-8")
    if add_npcs:
        out_path = target_root / "npcs" / "migrated_latest.npcs.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(add_npcs, indent=2) + "\n", encoding="utf-8")
        # Second-pass item hydration: newly hydrated NPC templates may reference
        # item IDs that were not visible in the original editor export.
        second_pass_item_ids: set[str] = set()
        second_pass_npc_ids: set[str] = set()
        for npc_payload in add_npcs.values():
            _collect_ids_from_payload(npc_payload, second_pass_item_ids, second_pass_npc_ids)
        for item_id in sorted(second_pass_item_ids):
            if item_id in target_items or item_id in add_items:
                continue
            payload = latest_items.get(item_id)
            if payload is None:
                if item_id not in summary["missing_item_ids"]:
                    summary["missing_item_ids"].append(item_id)
                continue
            add_items[item_id] = payload
            if item_id not in summary["hydrated_item_ids"]:
                summary["hydrated_item_ids"].append(item_id)
        if add_items:
            out_path = target_root / "items" / "migrated_latest.items.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(add_items, indent=2) + "\n", encoding="utf-8")
    return summary


def _copy_path(src: Path, dst: Path) -> None:
    if src.is_dir():
        def _on_rm_error(_func: Any, path: str, _exc_info: Any) -> None:
            Path(path).chmod(stat.S_IWRITE)
            _func(path)

        if dst.exists():
            shutil.rmtree(dst, onerror=_on_rm_error)
        shutil.copytree(src, dst)
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_quests_root_json(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    raw = src.read_text(encoding="utf-8")
    text = raw.strip()
    if text == "":
        dst.write_text("{}\n", encoding="utf-8")
        return
    try:
        parsed = json.loads(raw)
    except Exception:
        # Keep source bytes when parse fails; validator/report will surface the issue.
        shutil.copy2(src, dst)
        return
    if not isinstance(parsed, dict):
        dst.write_text("{}\n", encoding="utf-8")
        return
    dst.write_text(json.dumps(parsed, indent=2) + "\n", encoding="utf-8")


def shim_editor_export(
    source_root: Path,
    target_root: Path,
    validate: bool = True,
    latest_root: Path | None = None,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    target_root = target_root.resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    copied: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    warnings: list[str] = []

    for rule in _COPY_RULES:
        src = source_root / rule.source_rel
        dst = target_root / rule.target_rel
        if not src.exists():
            if rule.required:
                missing.append({"source": str(src), "target": str(dst), "severity": "error"})
            else:
                missing.append({"source": str(src), "target": str(dst), "severity": "warn"})
            continue
        if rule.source_rel == "quests.json":
            _copy_quests_root_json(src, dst)
        else:
            _copy_path(src, dst)
        copied.append({"source": str(src), "target": str(dst)})

    normalization = _normalize_export_tree(target_root)
    quest_norm = _normalize_quest_payload(target_root / "quests" / "quests.json", "quest")
    instance_norm = _normalize_quest_payload(target_root / "quests" / "instances.json", "instance")
    normalization.update(
        {
            "quest_templates_processed": quest_norm["templates_processed"],
            "quest_types_added": quest_norm["types_added"],
            "quest_stage_indexes_added": quest_norm["stage_indexes_added"],
            "instance_templates_processed": instance_norm["templates_processed"],
            "instance_types_added": instance_norm["types_added"],
            "instance_stage_indexes_added": instance_norm["stage_indexes_added"],
        }
    )
    migration = _hydrate_from_latest(target_root, (latest_root or Path("content_sets/fantasy_frontier/data")).resolve())

    report: dict[str, Any] = {
        "source_root": str(source_root),
        "target_root": str(target_root),
        "copied": copied,
        "missing": missing,
        "warnings": warnings,
        "normalization": normalization,
        "migration": migration,
    }

    if validate:
        checked, data_errors, data_warnings = validate_tree(target_root, strict_templates=False)
        ref_error_count = 0
        ref_issue_count = 0
        try:
            catalogs = load_catalogs(target_root)
            ref_issues = validate_catalogs(catalogs)
            ref_issue_count = len(ref_issues)
            ref_error_count = sum(1 for i in ref_issues if i.severity == "error")
        except Exception as exc:  # pragma: no cover - defensive path
            ref_error_count = 1
            ref_issue_count = 1
            warnings.append(f"reference validation failed to run: {exc}")
        report["validation"] = {
            "checked_files": int(checked),
            "data_errors": int(data_errors),
            "data_warnings": int(data_warnings),
            "reference_issue_count": int(ref_issue_count),
            "reference_errors": int(ref_error_count),
            "ok": bool(data_errors == 0 and ref_error_count == 0),
        }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate mud-world-editor export data into latest-format content-set data structure."
    )
    parser.add_argument("--source", default="mud-world-editor/data", help="Editor data root.")
    parser.add_argument("--target", default="tmp/editor_export_shim/content_data", help="Shim output root.")
    parser.add_argument("--report", default="tmp/editor_export_shim/report.json", help="Report JSON output path.")
    parser.add_argument("--no-validate", action="store_true", help="Skip data/reference validation pass.")
    parser.add_argument("--strict", action="store_true", help="Fail when warnings/missing/validation errors are present.")
    parser.add_argument("--latest-root", default="content_sets/fantasy_frontier/data", help="Canonical content-set data root for template hydration.")
    args = parser.parse_args()

    source_root = Path(args.source)
    target_root = Path(args.target)
    report_path = Path(args.report)

    if not source_root.exists() or not source_root.is_dir():
        raise SystemExit(f"Source root not found or not a directory: {source_root}")

    report = shim_editor_export(
        source_root,
        target_root,
        validate=(not args.no_validate),
        latest_root=Path(args.latest_root),
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "target_root": str(target_root), "report": str(report_path)}))
    if args.strict:
        warn_count = len(report.get("warnings", []))
        missing = report.get("missing", [])
        missing_count = len([m for m in missing if str(m.get("severity", "warn")) in {"warn", "error"}])
        migration = report.get("migration", {})
        unresolved_migration = len(migration.get("missing_item_ids", [])) + len(migration.get("missing_npc_ids", []))
        validation = report.get("validation", {})
        validation_errors = int(validation.get("data_errors", 0)) + int(validation.get("reference_errors", 0))
        if warn_count > 0 or missing_count > 0 or validation_errors > 0 or unresolved_migration > 0:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
