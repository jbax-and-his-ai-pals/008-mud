import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

# The weapon-vs-armour vocabulary is engine-side, so one check reads it rather
# than restating it: a list copied into two places is a list that disagrees with
# itself eventually.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVER_ROOT = _REPO_ROOT / "server"
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))


@dataclass
class RefIssue:
    severity: str
    path: str
    message: str


# Known dangling references that are deliberately tolerated while the world is
# being built out. Each entry is (referencing path suffix, missing id). Keeping
# them listed here rather than suppressing the check means the gate still fails
# on any *new* dangling reference, and the list doubles as the to-do for content
# that was authored but never wired up.
KNOWN_DANGLING_REFERENCES: tuple[tuple[str, str], ...] = (
    # The mage set has no obtainable members. Content is planned; until then the
    # set is unreachable rather than silently broken.
    ("sets.json:mage_set.items", "item_wizard_hat"),
    ("sets.json:mage_set.items", "item_robe"),
)


def _is_known_dangling(path: str, missing_id: str) -> bool:
    normalized = str(path).replace("\\", "/")
    for path_fragment, known_id in KNOWN_DANGLING_REFERENCES:
        if known_id == missing_id and path_fragment in normalized:
            return True
    return False


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
    # Quest and campaign files are optional: a deliberately minimal content set
    # (modern_capsule, night_shift) ships only items, NPCs, and regions. Treating
    # the file as mandatory made this validator crash rather than report.
    quests_path = content_root / "quests" / "quests.json"
    quests_payload: Any = {}
    if quests_path.is_file():
        try:
            quests_payload = _load_json(quests_path)
        except Exception:
            quests_payload = {}
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
                objective_routes = []
                primary_objective = stage.get("objective")
                if isinstance(primary_objective, dict):
                    objective_routes.append(("objective", primary_objective))
                alternatives = stage.get("objectives_any", [])
                if isinstance(alternatives, list):
                    objective_routes.extend(
                        (f"objectives_any[{index}]", objective)
                        for index, objective in enumerate(alternatives)
                        if isinstance(objective, dict)
                    )
                for objective_path, objective in objective_routes:
                    for field in ("item_id", "item_template_id"):
                        item_id = str(objective.get(field, "")).strip()
                        if item_id and item_id not in item_ids:
                            issues.append(RefIssue("error", f"quests/{quest_id}.stages[{sidx}].{objective_path}.{field}", f"unknown item_id '{item_id}'"))
                    for field in ("target_template_id", "target_npc_id", "recipient_id"):
                        npc_id = str(objective.get(field, "")).strip()
                        if npc_id and npc_id not in npc_ids:
                            issues.append(RefIssue("error", f"quests/{quest_id}.stages[{sidx}].{objective_path}.{field}", f"unknown npc id '{npc_id}'"))
                    target_region = str(objective.get("target_region", "")).strip()
                    target_room = str(objective.get("target_room_id", "")).strip()
                    if target_region and target_region not in region_rooms:
                        issues.append(RefIssue("error", f"quests/{quest_id}.stages[{sidx}].{objective_path}.target_region", f"unknown region '{target_region}'"))
                    elif target_region and target_room and target_room not in region_rooms.get(target_region, set()):
                        issues.append(RefIssue("error", f"quests/{quest_id}.stages[{sidx}].{objective_path}.target_room_id", f"unknown room '{target_room}' in region '{target_region}'"))

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

    issues.extend(_validate_item_sets(catalogs))
    return issues


def _validate_item_sets(catalogs: dict[str, Any]) -> list[RefIssue]:
    """Validate `items/sets.json` against the item catalog.

    This check was missing, which is how the shipped `mage_set` came to
    reference `item_wizard_hat` and `item_robe` -- two items that exist nowhere
    in the repository -- while this validator reported zero issues. A set whose
    members cannot be obtained is dead content, and nothing caught it.
    """
    issues: list[RefIssue] = []
    root = catalogs["root"]
    item_ids = catalogs["item_ids"]
    sets_dir = root / "items"
    if not sets_dir.is_dir():
        return issues

    for path in sorted(sets_dir.glob("*.json")):
        try:
            payload = _load_json(path)
        except Exception as exc:
            issues.append(RefIssue("error", str(path), f"failed to parse json: {exc}"))
            continue
        if not isinstance(payload, dict):
            continue

        # A set file is recognised by its entries carrying an `items` list.
        for set_id, entry in payload.items():
            if not isinstance(entry, dict):
                continue
            members = entry.get("items")
            if not isinstance(members, list):
                continue
            for index, member in enumerate(members):
                if not isinstance(member, str) or not member.strip():
                    issues.append(RefIssue(
                        "error",
                        f"{path}:{set_id}.items[{index}]",
                        "set member must be a non-empty item id",
                    ))
                    continue
                if member not in item_ids:
                    if _is_known_dangling(f"{path}:{set_id}.items", member):
                        issues.append(RefIssue(
                            "warning",
                            f"{path}:{set_id}.items[{index}]",
                            f"set '{set_id}' references missing item '{member}' (known dangling; "
                            f"listed in KNOWN_DANGLING_REFERENCES)",
                        ))
                        continue
                    issues.append(RefIssue(
                        "error",
                        f"{path}:{set_id}.items[{index}]",
                        f"set '{set_id}' references missing item '{member}'",
                    ))
            if not members:
                issues.append(RefIssue(
                    "warning",
                    f"{path}:{set_id}",
                    f"set '{set_id}' has no members and can never be completed",
                ))
            bonuses = entry.get("bonuses")
            if isinstance(bonuses, dict):
                for threshold in bonuses.keys():
                    try:
                        count = int(threshold)
                    except (TypeError, ValueError):
                        issues.append(RefIssue(
                            "error",
                            f"{path}:{set_id}.bonuses.{threshold}",
                            f"set bonus threshold '{threshold}' must be an integer",
                        ))
                        continue
                    if count > len(members):
                        issues.append(RefIssue(
                            "error",
                            f"{path}:{set_id}.bonuses.{threshold}",
                            f"set '{set_id}' has a bonus at {count} pieces but only "
                            f"{len(members)} members, so it is unreachable",
                        ))
    return issues


# --- references no audit used to read -----------------------------------------
#
# An authored id the engine resolves but nothing checks is worse than a missing
# feature: the thirteen dangling references these find were shipping in content
# that passed every gate, because the gates simply did not open the files they
# live in.
#
# Each row is (which id table, what to call it, a walker, which files it reads).
# A walker takes `[(file name, parsed payload)]` and yields `(label, value)`,
# the label being `entry.path` so a finding names both what to search for and
# where inside it the reference sits.
#
# These are written out rather than described by a path expression on purpose. A
# compact DSL was tried first and two of its sigils were silently wrong, so a
# check that should have failed reported success -- which is the exact bug this
# file exists to prevent. Verbose and obviously correct beats clever here.


def _entries(payload: Any) -> list[tuple[str, dict]]:
    """Every authored entry of one file, as (id, object)."""
    if not isinstance(payload, dict):
        return []
    return [
        (str(key), entry) for key, entry in payload.items()
        if not str(key).startswith("_") and isinstance(entry, dict)
    ]


def _rooms(payload: Any) -> list[tuple[str, dict]]:
    """Every room of one region file, as (room_id, room)."""
    rooms = payload.get("rooms") if isinstance(payload, dict) else None
    if not isinstance(rooms, dict):
        return []
    return [(str(room_id), room) for room_id, room in rooms.items() if isinstance(room, dict)]


def _objectives(stage: Any) -> list[dict]:
    """Every objective a stage carries: the primary, and any alternatives."""
    if not isinstance(stage, dict):
        return []
    found: list[dict] = []
    primary = stage.get("objective")
    if isinstance(primary, dict):
        found.append(primary)
    for alternative in stage.get("objectives_any", []) or []:
        if isinstance(alternative, dict):
            found.append(alternative)
    return found


def _at(node: Any, *keys: str) -> Any:
    """Walk object keys, returning None the moment one is absent.

    Keys may be given separately or as one dotted string. Both are accepted
    because getting that wrong is silent: `_at(entry, "properties.collection_id")`
    looks for a literal key of that name, finds nothing, and reports no finding --
    which is how the reference check that was written to catch a dangling
    collection id passed over the one in shipped content.
    """
    current = node
    for key in keys:
        for part in str(key).split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
    return current


def _each(node: Any, *keys: str) -> list[Any]:
    """Walk object keys, then require a list, yielding its elements."""
    found = _at(node, *keys)
    return list(found) if isinstance(found, list) else []


def _one_or_many(node: Any, *keys: str) -> list[Any]:
    """A field the engine accepts either as one value or as a list of them.

    `collection_id` is spelled both ways in the engine: `get_property` returns
    the scalar, and `CollectionManager` immediately wraps it in a list before
    walking it. A walker that required a list found no scalar reference at all
    -- including the one the check was written to catch.
    """
    found = _at(node, *keys)
    if isinstance(found, list):
        return [value for value in found if isinstance(value, str) and value.strip()]
    if isinstance(found, str) and found.strip():
        return [found]
    return []


def _item_references(files: list[tuple[str, Any]]):
    """Items named by crafting, by other items, and by the world's furniture.

    Not every id in `properties` is an item, which is worth saying because three
    of them are not and this check reported all three as missing items the first
    time it read them: `recipe_to_learn` names a recipe, `collection_id` names a
    collection, and `spell_to_learn` names an ability. Each is checked against
    its own table by the family that owns it; this walker takes the item ones.
    """
    for name, payload in files:
        for entry_name, entry in _entries(payload):
            value = _at(entry, "result_item_id")
            if value:
                yield "%s.result_item_id" % entry_name, value
            value = _at(entry, "properties", "seed_item_id")
            if value:
                yield "%s.properties.seed_item_id" % entry_name, value
            for index, crop in enumerate(_each(entry, "properties", "plantable_crops")):
                if isinstance(crop, dict) and crop.get("seed_item_id"):
                    yield "%s.properties.plantable_crops[%d].seed_item_id" % (entry_name, index), crop["seed_item_id"]
            for index, item_id in enumerate(_each(entry, "properties", "gift_preferences", "preferred_item_ids")):
                yield "%s.properties.gift_preferences.preferred_item_ids[%d]" % (entry_name, index), item_id
            for key in ("key_item_id", "storage_item_id"):
                value = _at(entry, "properties", "house_offer", key)
                if value:
                    yield "%s.properties.house_offer.%s" % (entry_name, key), value
            tiers = _at(entry, "properties", "house_tiers")
            for tier_id, tier in (tiers.items() if isinstance(tiers, dict) else []):
                for index, option in enumerate(_each(tier, "options")):
                    if isinstance(option, dict) and option.get("room_item_id"):
                        yield "%s.properties.house_tiers.%s.options[%d].room_item_id" % (
                            entry_name, tier_id, index), option["room_item_id"]
            for index, kit in enumerate(_each(entry, "initial_inventory")):
                if isinstance(kit, dict) and kit.get("item_id"):
                    yield "%s.initial_inventory[%d].item_id" % (entry_name, index), kit["item_id"]
            for index, ware in enumerate(_each(entry, "properties", "sells_items")):
                if isinstance(ware, dict) and ware.get("item_id"):
                    yield "%s.properties.sells_items[%d].item_id" % (entry_name, index), ware["item_id"]
            loot = _at(entry, "loot_table")
            for template_id, drop in (loot.items() if isinstance(loot, dict) else []):
                if str(template_id).startswith("item_") or str(template_id).startswith("scroll_"):
                    yield "%s.loot_table.%s" % (entry_name, template_id), template_id
        # A region file is the region: its rooms carry `locked_by`, and their
        # exit requirements name the key that opens a door.
        for room_id, room in _rooms(payload):
            value = _at(room, "properties", "locked_by")
            if value:
                yield "%s.properties.locked_by" % room_id, value
            requirements = _at(room, "properties", "exit_requirements")
            for direction, requirement in (requirements.items() if isinstance(requirements, dict) else []):
                if isinstance(requirement, dict) and requirement.get("key_id"):
                    yield "%s.properties.exit_requirements.%s.key_id" % (room_id, direction), requirement["key_id"]


def _collection_references(files: list[tuple[str, Any]]):
    """Collections named by the items that belong to them."""
    for name, payload in files:
        for entry_name, entry in _entries(payload):
            for collection_id in _one_or_many(entry, "properties", "collection_id"):
                yield "%s.properties.collection_id" % entry_name, collection_id


def _recipe_references(files: list[tuple[str, Any]]):
    """Recipes a pattern or book teaches."""
    for name, payload in files:
        for entry_name, entry in _entries(payload):
            value = _at(entry, "properties", "recipe_to_learn")
            if value:
                yield "%s.properties.recipe_to_learn" % entry_name, value


def _npc_references(files: list[tuple[str, Any]]):
    """NPC templates named by regions, quests and summoning spells."""
    for name, payload in files:
        if "regions/" in name:
            for field in ("monster_types", "npc_types"):
                # A spawner lists template id to spawn weight, so the reference
                # is the key rather than the value.
                types = _at(payload, "spawner", field)
                for template_id in (types if isinstance(types, dict) else {}):
                    yield "%s.%s.%s" % (name, field, template_id), template_id
            continue
        if "abilities/" in name or "magic/" in name:
            for ability_name, ability in _entries(payload):
                for index, effect in enumerate(_each(ability, "effects")):
                    if isinstance(effect, dict) and effect.get("summon_template_id"):
                        yield "%s.effects[%d].summon_template_id" % (ability_name, index), effect["summon_template_id"]
            continue
        for quest_id, quest in _entries(payload):
            for index, stage in enumerate(_each(quest, "stages")):
                for objective in _objectives(stage):
                    for field in ("recipient_template_id", "completion_npc_template_id",
                                  "target_npc_template_id", "npc_template_id"):
                        if objective.get(field):
                            yield "%s.stages[%d].objective.%s" % (quest_id, index, field), objective[field]
                    spawn = _at(objective, "spawn_config")
                    if isinstance(spawn, dict) and spawn.get("template_id"):
                        yield "%s.stages[%d].objective.spawn_config.template_id" % (quest_id, index), spawn["template_id"]
            for index, relationship in enumerate(_each(quest, "rewards", "relationships")):
                if isinstance(relationship, dict) and relationship.get("npc_template_id"):
                    yield "%s.rewards.relationships[%d].npc_template_id" % (quest_id, index), relationship["npc_template_id"]
            for field in ("giver_npc_template_id", "recipient_template_id"):
                if quest.get(field):
                    yield "%s.%s" % (quest_id, field), quest[field]


def _ability_references(files: list[tuple[str, Any]]):
    """Abilities named by items, by NPCs, and by the backgrounds that grant them."""
    for name, payload in files:
        if "backgrounds" in name:
            # One background per key, each naming the abilities it starts you with.
            for background_id, background in _entries(payload):
                for index, ability_id in enumerate(_each(background, "spells")):
                    yield "%s.spells[%d]" % (background_id, index), ability_id
            continue
        for entry_name, entry in _entries(payload):
            value = _at(entry, "properties", "spell_to_learn")
            if value:
                yield "%s.properties.spell_to_learn" % entry_name, value
            for index, ability_id in enumerate(_each(entry, "usable_spells")):
                yield "%s.usable_spells[%d]" % (entry_name, index), ability_id
            for index, ability_id in enumerate(_each(entry, "properties", "required_spells")):
                yield "%s.properties.required_spells[%d]" % (entry_name, index), ability_id
            for index, ability_id in enumerate(_each(entry, "properties", "random_spells", "pool")):
                yield "%s.properties.random_spells.pool[%d]" % (entry_name, index), ability_id


def _room_references(files: list[tuple[str, Any]]):
    """`region:room` strings, which an NPC's schedule and a quest spawn use."""
    for name, payload in files:
        for entry_name, entry in _entries(payload):
            value = _at(entry, "properties", "work_location")
            if value:
                yield "%s.properties.work_location" % entry_name, value
            for index, point in enumerate(_each(entry, "properties", "spawn_points")):
                if isinstance(point, dict) and point.get("room_id"):
                    yield "%s.properties.spawn_points[%d].room_id" % (entry_name, index), point["room_id"]
        for room_id, room in _rooms(payload):
            value = _at(room, "properties", "release_destination")
            if value:
                yield "%s.properties.release_destination" % room_id, value


# (id table, what to call it, walker, which file globs it reads)
REFERENCE_FAMILIES: tuple[tuple[str, str, Any, tuple[str, ...]], ...] = (
    ("items", "item", _item_references,
     ("crafting/*.json", "items/*.json", "npcs/*.json", "regions/*.json")),
    ("npcs", "NPC template", _npc_references,
     ("regions/*.json", "quests/*.json", "abilities/*.json", "magic/*.json")),
    ("abilities", "ability", _ability_references,
     ("items/*.json", "npcs/*.json", "player/backgrounds.json")),
    ("rooms", "room", _room_references, ("npcs/*.json", "regions/*.json")),
    ("collections", "collection", _collection_references, ("items/*.json",)),
    ("recipes", "recipe", _recipe_references, ("items/*.json",)),
)


def _reference_sweep_issues(catalogs: dict[str, Any]) -> list[RefIssue]:
    """Ids the engine resolves out of files no audit used to read."""
    issues: list[RefIssue] = []
    root: Path = catalogs["root"]
    tables: dict[str, set[str]] = {
        "items": catalogs["item_ids"],
        "npcs": catalogs["npc_template_ids"],
        "recipes": _collect_templates(root / "crafting"),
        # `collections.json` and `discoveries.json` are single files, not
        # folders, and each one's own field names it.
        "collections": _single_file_ids(root / "collections.json", "collection_id"),
        "discoveries": _single_file_ids(root / "discoveries.json", "discovery_id"),
        "abilities": _collect_ids_by_field(root, "abilities", "id")
        | _collect_ids_by_field(root, "magic", "id"),
        "campaigns": _collect_ids_by_field(root, "campaigns", "campaign_id"),
        # Rooms are `region:room`, which is how the engine spells them.
        "rooms": {
            "%s:%s" % (region_id, room_id)
            for region_id, room_ids in catalogs.get("region_rooms", {}).items()
            for room_id in room_ids
        },
    }

    for table_name, singular, walker, patterns in REFERENCE_FAMILIES:
        known = tables[table_name]
        files = _family_files(root, patterns)
        for label, value in walker(files):
            if not isinstance(value, str) or not value.strip():
                continue
            if value in known:
                continue
            issues.append(RefIssue(
                "error",
                "%s(%s)" % (_file_of(label, files), label),
                "references missing %s '%s'%s" % (
                    singular,
                    value,
                    "" if known else " (no %s are declared at all)" % table_name,
                ),
            ))
    return issues


def _family_files(root: Path, patterns: tuple[str, ...]) -> list[tuple[str, Any]]:
    """Every file a walker reads, as (name, payload), for one family."""
    loaded: list[tuple[str, Any]] = []
    for pattern in patterns:
        folder, _, name = pattern.partition("/")
        matches = sorted((root / folder).glob(name)) if name else sorted(root.glob(folder))
        for path in matches:
            try:
                payload = _load_json(path)
            except Exception:
                continue
            if isinstance(payload, dict):
                loaded.append((path.relative_to(root).as_posix(), payload))
    return loaded


def _file_of(label: str, files: list[tuple[str, Any]]) -> str:
    """The file a finding came from, recovered from the walker's own label.

    Walkers label with `entry.path`, and an entry id is enough to find its file
    again because ids are unique within a family.
    """
    entry_id = label.split(".", 1)[0]
    for name, payload in files:
        if isinstance(payload, dict) and entry_id in payload:
            return name
        if any(room_id == entry_id for room_id, _room in _rooms(payload)):
            return name
    return files[0][0] if files else "?"


# Two vocabularies share the words `damage_type`, and they are not the same
# list. `damage_type` is the damage *channel* (`ice`, `kinetic`): the set's own
# `combat/elements.json` declares it, and it feeds resistance maths and flavour
# text. `weapon_damage_type` is edge geometry against body armour (`slashing`,
# `piercing`, `crushing`): it is engine physics, hardcoded in
# `config_combat.WEAPON_DAMAGE_TYPES`, and no content set declares it. Checking
# the second against the first reported 41 working weapons as broken.
_DAMAGE_CHANNEL_FIELDS = (
    "damage_type",
    "dot_damage_type",
)
_DAMAGE_TYPE_FILE_PATTERNS = (
    "items/*.json",
    "npcs/*.json",
    "magic/*.json",
    "abilities/*.json",
    "contracts/*.json",
)


def _suffix_matches(keys: list[str], wanted: tuple[str, ...]) -> bool:
    """Does one walked key path end in the path we are looking for?

    A suffix match makes a bare `damage_type` mean "at any depth", so a rule
    does not have to know that one NPC spells it `on_hit_effect.damage_type`.
    """
    if len(keys) < len(wanted):
        return False
    return keys[-len(wanted):] == list(wanted)


def _walk_named_path(node: Any, wanted: tuple[str, ...]) -> Iterator[tuple[str, Any]]:
    """Every value reached at one key path, matching as deep as the key goes.

    A path is matched literally, so a bare `damage_type` and a
    `weapon_damage_type` are different fields. An intervening array costs
    nothing, because `effects[0].damage_type` is the same authoring decision as
    `effects[3].damage_type`.

    A match yields once and keeps walking past itself, so a longer path written
    as `on_hit_effect.damage_type` finds the same value the bare rule already
    found -- the long form says where to descend, not what to report twice.
    """
    def visit(current: Any, keys: list[str], label: str) -> Iterator[tuple[str, Any]]:
        if isinstance(current, dict):
            for key, value in current.items():
                text = str(key)
                if text.startswith("_"):
                    continue
                child = "%s.%s" % (label, text) if label else text
                walked = keys + [text]
                if _suffix_matches(walked, wanted):
                    yield child, value
                if isinstance(value, (dict, list)):
                    yield from visit(value, walked, child)
        elif isinstance(current, list):
            # An array is not a path segment: it is the same authoring slot
            # repeated, so `effects[2].damage_type` matches `effects.damage_type`.
            for index, element in enumerate(current):
                if isinstance(element, (dict, list)):
                    yield from visit(element, keys, "%s[%d]" % (label, index))

    yield from visit(node, [], "")


def _damage_type_references(
    files: list[tuple[str, Any]], field: str
) -> Iterator[tuple[str, Any]]:
    """Every authored value of one damage-type field.

    Written as a path walk rather than a fixed shape because the same field is
    reached four different ways in shipped content: an npc's `properties`, an
    item's `properties`, a spell's `effects[]`, and a contract's
    `attack_profiles[]`. A reader that knew only one of those would pass a set
    that typed `cold` somewhere it does not happen to look.
    """
    wanted = tuple(field.split("."))
    for name, payload in files:
        for entry_name, entry in _entries(payload):
            for path, value in _walk_named_path(entry, wanted):
                yield "%s(%s.%s)" % (name, entry_name, path), value


def _damage_type_issues(root: Path) -> list[RefIssue]:
    """Every damage channel named must be one this set declares.

    The vocabulary is the set's own (`combat/elements.json`), so this checks
    against content rather than an engine list -- a set that adds `thermal` is
    not wrong, and a set that types `cold` where it declared `ice` is.
    """
    elements_path = root / "combat" / "elements.json"
    if not elements_path.is_file():
        return []
    try:
        payload = _load_json(elements_path)
    except Exception:
        return []
    declared = payload.get("valid_damage_types") if isinstance(payload, dict) else None
    if not isinstance(declared, list) or not declared:
        return []

    issues: list[RefIssue] = []
    known = {str(entry) for entry in declared}
    files = _family_files(root, _DAMAGE_TYPE_FILE_PATTERNS)
    for field in _DAMAGE_CHANNEL_FIELDS:
        for where, value in _damage_type_references(files, field):
            if not isinstance(value, str) or not value.strip() or value in known:
                continue
            issues.append(RefIssue(
                "error",
                where,
                "names damage type '%s', which combat/elements.json does not declare "
                "(it declares: %s)" % (value, ", ".join(sorted(known))),
            ))

    from engine.config.config_combat import WEAPON_DAMAGE_TYPES

    for where, value in _damage_type_references(files, "weapon_damage_type"):
        if not isinstance(value, str) or not value.strip() or value in WEAPON_DAMAGE_TYPES:
            continue
        issues.append(RefIssue(
            "error",
            where,
            "names weapon damage type '%s'; the engine compares this against armour "
            "materials, and its values are %s"
            % (value, ", ".join(WEAPON_DAMAGE_TYPES)),
        ))

    # The set's own fallback channel. A default no combatant can actually deal is
    # a typo the engine cannot report: it looks the fallback up in a flavour map,
    # misses, and uses the generic text.
    default = payload.get("default_damage_type")
    if isinstance(default, str) and default.strip() and default not in known:
        issues.append(RefIssue(
            "error",
            "combat/elements.json(default_damage_type)",
            "declares default damage type '%s', which valid_damage_types does not "
            "include (it declares: %s)" % (default, ", ".join(sorted(known))),
        ))
    return issues


def _region_rooms(root: Path) -> dict[str, set[str]]:
    """Every region's room ids, for checking `region:room` references."""
    rooms: dict[str, set[str]] = {}
    for path in sorted((root / "regions").glob("*.json")):
        try:
            payload = _load_json(path)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        region_id = str(payload.get("region_id") or path.stem)
        entries = payload.get("rooms")
        rooms[region_id] = set(entries.keys()) if isinstance(entries, dict) else set()
    return rooms


def _collect_ids_by_field(content_root: Path, directory: str, field: str) -> set[str]:
    """Ids a family declares under its own field, falling back to the file key.

    A campaign file names its campaign with `campaign_id`; an item file names the
    template with the map key. The engine resolves both ways, so a check that
    knew only one of them would report a working reference as dangling.
    """
    ids: set[str] = set()
    folder = content_root / directory
    if not folder.is_dir():
        return ids
    for path in sorted(folder.glob("*.json")):
        try:
            payload = _load_json(path)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        authored = payload.get(field)
        if isinstance(authored, str) and authored.strip():
            ids.add(authored.strip())
            continue
        for key, entry in payload.items():
            # `_`-prefixed keys are authoring notes. Counting one as an id makes
            # every typo'd reference to it resolve, which is how a table looks
            # populated while checking nothing.
            if str(key).startswith("_"):
                continue
            nested = entry.get(field) if isinstance(entry, dict) else None
            ids.add(str(nested) if isinstance(nested, str) and nested.strip() else str(key))
    return ids


def _single_file_ids(path: Path, id_field: str) -> set[str]:
    """Ids from a single authored file, under its own field or its map keys."""
    if not path.is_file():
        return set()
    try:
        payload = _load_json(path)
    except Exception:
        return set()
    if not isinstance(payload, dict):
        return set()
    authored = payload.get(id_field)
    if isinstance(authored, str) and authored.strip():
        return {authored.strip()}
    return {str(k) for k in payload if not str(k).startswith("_")}


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
    catalogs["region_rooms"] = _region_rooms(root)
    issues.extend(_reference_sweep_issues(catalogs))
    issues.extend(_damage_type_issues(root))
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
