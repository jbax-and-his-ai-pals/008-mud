import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class RefIssue:
    severity: str
    path: str
    message: str


def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _collect_templates(dir_path: Path) -> set[str]:
    ids: set[str] = set()
    for p in sorted(dir_path.glob("*.json")):
        try:
            payload = _load_json(p)
        except Exception:
            continue
        if isinstance(payload, dict):
            for k in payload.keys():
                if isinstance(k, str) and k.strip():
                    ids.add(k.strip())
    return ids


def load_catalogs(root: Path) -> dict[str, Any]:
    content_root = root
    items = _collect_templates(content_root / "items")
    npcs = _collect_templates(content_root / "npcs")
    quests_payload = _load_json(content_root / "quests" / "quests.json")
    campaigns_dir = content_root / "campaigns"
    region_files = sorted((content_root / "regions").glob("*.json"))
    return {
        "root": content_root,
        "item_ids": items,
        "npc_template_ids": npcs,
        "quest_ids": set(quests_payload.keys()) if isinstance(quests_payload, dict) else set(),
        "quests_payload": quests_payload,
        "campaign_files": campaigns_dir,
        "region_files": region_files,
    }


def _is_known_room_ref(ref: str, region_id: str, region_rooms: dict[str, set[str]]) -> bool:
    if ":" in ref:
        region, room = ref.split(":", 1)
        return room in region_rooms.get(region, set())
    return ref in region_rooms.get(region_id, set())


def validate_catalogs(catalogs: dict[str, Any]) -> list[RefIssue]:
    issues: list[RefIssue] = []
    item_ids: set[str] = catalogs["item_ids"]
    npc_ids: set[str] = catalogs["npc_template_ids"]
    quest_ids: set[str] = catalogs["quest_ids"]
    quests_payload = catalogs["quests_payload"]
    region_files: list[Path] = catalogs["region_files"]
    campaigns_dir: Path = catalogs["campaign_files"]

    region_rooms: dict[str, set[str]] = {}
    region_payloads: dict[str, dict[str, Any]] = {}
    for rf in region_files:
        try:
            payload = _load_json(rf)
        except Exception as exc:
            issues.append(RefIssue("error", str(rf), f"failed to parse region json: {exc}"))
            continue
        if not isinstance(payload, dict):
            continue
        region_id = str(payload.get("region_id", "")).strip()
        rooms = payload.get("rooms", {})
        if region_id and isinstance(rooms, dict):
            region_rooms[region_id] = set(str(k) for k in rooms.keys())
            region_payloads[region_id] = payload

    # Region references
    for region_id, payload in region_payloads.items():
        rooms = payload.get("rooms", {})
        if not isinstance(rooms, dict):
            continue
        for room_id, room in rooms.items():
            if not isinstance(room, dict):
                continue
            exits = room.get("exits", {})
            if isinstance(exits, dict):
                for direction, ref in exits.items():
                    ref_text = str(ref).strip()
                    if ref_text and not _is_known_room_ref(ref_text, region_id, region_rooms):
                        issues.append(
                            RefIssue(
                                "error",
                                f"regions/{region_id}:{room_id}.exits.{direction}",
                                f"unknown exit target '{ref_text}'",
                            )
                        )
            items = room.get("items", [])
            if isinstance(items, list):
                for idx, entry in enumerate(items):
                    if not isinstance(entry, dict):
                        continue
                    item_id = str(entry.get("item_id", "")).strip()
                    if item_id and item_id not in item_ids:
                        issues.append(
                            RefIssue(
                                "error",
                                f"regions/{region_id}:{room_id}.items[{idx}]",
                                f"unknown item_id '{item_id}'",
                            )
                        )
            npcs = room.get("initial_npcs", [])
            if isinstance(npcs, list):
                for idx, entry in enumerate(npcs):
                    if not isinstance(entry, dict):
                        continue
                    template_id = str(entry.get("template_id", "")).strip()
                    if template_id and template_id not in npc_ids:
                        issues.append(
                            RefIssue(
                                "error",
                                f"regions/{region_id}:{room_id}.initial_npcs[{idx}]",
                                f"unknown npc template_id '{template_id}'",
                            )
                        )

    # Quest references
    if isinstance(quests_payload, dict):
        for quest_id, quest in quests_payload.items():
            if not isinstance(quest, dict):
                continue
            rewards = quest.get("rewards", {})
            if isinstance(rewards, dict):
                reward_items = rewards.get("items", [])
                if isinstance(reward_items, list):
                    for idx, entry in enumerate(reward_items):
                        if not isinstance(entry, dict):
                            continue
                        item_id = str(entry.get("item_id", "")).strip()
                        if item_id and item_id not in item_ids:
                            issues.append(
                                RefIssue("error", f"quests/{quest_id}.rewards.items[{idx}]", f"unknown item_id '{item_id}'")
                            )
            for sidx, stage in enumerate(quest.get("stages", [])):
                if not isinstance(stage, dict):
                    continue
                turn_in_id = str(stage.get("turn_in_id", "")).strip()
                if turn_in_id and turn_in_id not in npc_ids:
                    issues.append(RefIssue("error", f"quests/{quest_id}.stages[{sidx}].turn_in_id", f"unknown npc id '{turn_in_id}'"))
                spawn = stage.get("spawn_on_entry", {})
                if isinstance(spawn, dict):
                    template_id = str(spawn.get("template_id", "")).strip()
                    if template_id and template_id not in npc_ids:
                        issues.append(RefIssue("error", f"quests/{quest_id}.stages[{sidx}].spawn_on_entry.template_id", f"unknown npc template_id '{template_id}'"))
                    region_id = str(spawn.get("region_id", "")).strip()
                    room_id = str(spawn.get("room_id", "")).strip()
                    if region_id and region_id not in region_rooms:
                        issues.append(RefIssue("error", f"quests/{quest_id}.stages[{sidx}].spawn_on_entry.region_id", f"unknown region_id '{region_id}'"))
                    elif region_id and room_id and room_id not in region_rooms.get(region_id, set()):
                        issues.append(RefIssue("error", f"quests/{quest_id}.stages[{sidx}].spawn_on_entry.room_id", f"unknown room_id '{room_id}' in region '{region_id}'"))
                objective = stage.get("objective", {})
                if isinstance(objective, dict):
                    for field in ("item_id", "item_template_id"):
                        item_id = str(objective.get(field, "")).strip()
                        if item_id and item_id not in item_ids:
                            issues.append(RefIssue("error", f"quests/{quest_id}.stages[{sidx}].objective.{field}", f"unknown item_id '{item_id}'"))
                    for field in ("target_template_id", "target_npc_id", "recipient_id"):
                        npc_id = str(objective.get(field, "")).strip()
                        if npc_id and npc_id not in npc_ids:
                            issues.append(RefIssue("error", f"quests/{quest_id}.stages[{sidx}].objective.{field}", f"unknown npc id '{npc_id}'"))
                    target_region = str(objective.get("target_region", "")).strip()
                    target_room = str(objective.get("target_room_id", "")).strip()
                    if target_region and target_region not in region_rooms:
                        issues.append(RefIssue("error", f"quests/{quest_id}.stages[{sidx}].objective.target_region", f"unknown region '{target_region}'"))
                    elif target_region and target_room and target_room not in region_rooms.get(target_region, set()):
                        issues.append(RefIssue("error", f"quests/{quest_id}.stages[{sidx}].objective.target_room_id", f"unknown room '{target_room}' in region '{target_region}'"))

    # Campaign references
    for cfile in sorted(campaigns_dir.glob("*.json")):
        try:
            campaign = _load_json(cfile)
        except Exception as exc:
            issues.append(RefIssue("error", str(cfile), f"failed to parse campaign json: {exc}"))
            continue
        if not isinstance(campaign, dict):
            continue
        nodes = campaign.get("nodes", {})
        node_ids = set(nodes.keys()) if isinstance(nodes, dict) else set()
        start_node = str(campaign.get("start_node_id", "")).strip()
        if start_node and start_node not in node_ids:
            issues.append(RefIssue("error", f"{cfile}:start_node_id", f"unknown start_node_id '{start_node}'"))
        if isinstance(nodes, dict):
            for node_id, node in nodes.items():
                if not isinstance(node, dict):
                    continue
                qid = str(node.get("quest_template_id", "")).strip()
                if qid and qid not in quest_ids:
                    issues.append(RefIssue("error", f"{cfile}:nodes.{node_id}.quest_template_id", f"unknown quest_template_id '{qid}'"))
                transitions = node.get("transitions", [])
                if isinstance(transitions, list):
                    for tidx, trans in enumerate(transitions):
                        if not isinstance(trans, dict):
                            continue
                        target = str(trans.get("target_node_id", "")).strip()
                        if target and target not in node_ids:
                            issues.append(RefIssue("error", f"{cfile}:nodes.{node_id}.transitions[{tidx}].target_node_id", f"unknown node '{target}'"))

    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate cross-file reference integrity for content-set data.")
    parser.add_argument("root", nargs="?", default="content_sets/fantasy_frontier/data", help="Path to content-set data root.")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists() or not root.is_dir():
        print(f"[ERROR] Root directory not found: {root}")
        raise SystemExit(2)

    catalogs = load_catalogs(root)
    issues = validate_catalogs(catalogs)
    error_count = 0
    for issue in issues:
        if issue.severity == "error":
            error_count += 1
            print(f"[ERROR] {issue.path} - {issue.message}")
        else:
            print(f"[WARN]  {issue.path} - {issue.message}")
    print(f"Reference issues: {len(issues)} (errors: {error_count})")
    raise SystemExit(1 if error_count > 0 else 0)


if __name__ == "__main__":
    main()
