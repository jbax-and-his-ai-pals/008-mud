"""Coverage for toolkit/editor_export_shim.py.

Note: two branches are left untested as unreachable:
- _hydrate_from_latest()'s second-pass `if item_id not in
  summary["hydrated_item_ids"]:` guard -- add_items and
  summary["hydrated_item_ids"] are always updated together (in both the
  first pass and the second pass, immediately after each other, with no
  intervening reset), and the preceding `if item_id in target_items or
  item_id in add_items: continue` check already guarantees an item_id
  reaching this point was never in add_items before -- so it can never
  already be in hydrated_item_ids either.
- the module's `if __name__ == "__main__": main()` guard, which only runs
  when the file is invoked directly as a script (consistent with this
  codebase's established precedent for such guards)."""

import io
import json
import shutil
import stat
import sys
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TOOLKIT_DIR = _REPO_ROOT / "toolkit"
if str(_TOOLKIT_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLKIT_DIR))

from editor_export_shim import (
    CopyRule,
    _collect_ids_from_payload,
    _collect_references_for_migration,
    _copy_path,
    _copy_quests_root_json,
    _hydrate_from_latest,
    _load_template_payloads,
    _normalize_export_tree,
    _normalize_quest_payload,
    _normalize_region_payload,
    main,
    shim_editor_export,
)


class TestEditorExportShim(unittest.TestCase):
    def _case_root(self) -> Path:
        root = Path("tmp") / f"editor_export_shim_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def test_maps_core_editor_paths(self) -> None:
        root = self._case_root()
        src = root / "src"
        dst = root / "dst"
        (src / "items").mkdir(parents=True, exist_ok=True)
        (src / "npcs").mkdir(parents=True, exist_ok=True)
        (src / "regions").mkdir(parents=True, exist_ok=True)
        (src / "magic").mkdir(parents=True, exist_ok=True)
        (src / "quests").mkdir(parents=True, exist_ok=True)
        (src / "items" / "weapons.json").write_text("{}", encoding="utf-8")
        (src / "npcs" / "villagers.json").write_text("{}", encoding="utf-8")
        (src / "regions" / "town.json").write_text(
            json.dumps(
                {
                    "region_id": "town",
                    "_editor_graph": {"zoom": 1.0},
                    "rooms": {
                        "square": {
                            "_editor_pos": [1, 2],
                            "name": "Square",
                            "exits": {"north": " forest:glade "},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        (src / "magic" / "offensive_spells.json").write_text("{}", encoding="utf-8")
        (src / "quests" / "instances.json").write_text("{}", encoding="utf-8")
        (src / "quests.json").write_text("{}", encoding="utf-8")
        (src / "world_layout.json").write_text("{}", encoding="utf-8")

        report = shim_editor_export(src, dst, validate=False)
        self.assertTrue((dst / "items" / "weapons.json").exists())
        self.assertTrue((dst / "npcs" / "villagers.json").exists())
        self.assertTrue((dst / "regions" / "town.json").exists())
        self.assertTrue((dst / "magic" / "offensive_spells.json").exists())
        self.assertTrue((dst / "quests" / "quests.json").exists())
        self.assertTrue((dst / "world" / "world_layout.editor.json").exists())
        self.assertGreaterEqual(len(report.get("copied", [])), 6)
        normalized_region = json.loads((dst / "regions" / "town.json").read_text(encoding="utf-8"))
        room = normalized_region["rooms"]["square"]
        self.assertNotIn("_editor_graph", normalized_region)
        self.assertNotIn("_editor_pos", room)
        self.assertEqual("forest:glade", room["exits"]["north"])
        self.assertIsInstance(room["properties"], dict)
        normalization = report.get("normalization", {})
        self.assertGreaterEqual(int(normalization.get("regions_processed", 0)), 1)
        self.assertGreaterEqual(int(normalization.get("room_editor_keys_removed", 0)), 1)

    def test_missing_required_copy_rule_is_reported_as_an_error(self) -> None:
        root = self._case_root()
        src = root / "src"
        dst = root / "dst"
        src.mkdir(parents=True, exist_ok=True)
        required_rule = (CopyRule("must_exist", "must_exist", required=True),)
        with patch("editor_export_shim._COPY_RULES", required_rule):
            report = shim_editor_export(src, dst, validate=False)
        self.assertEqual(1, len(report["missing"]))
        self.assertEqual("error", report["missing"][0]["severity"])

    def test_ignores_deprecated_templates_path_without_warning(self) -> None:
        root = self._case_root()
        src = root / "src"
        dst = root / "dst"
        (src / "templates").mkdir(parents=True, exist_ok=True)
        report = shim_editor_export(src, dst, validate=False)
        self.assertEqual([], report.get("warnings", []))

    def test_normalizes_quest_and_instance_payloads(self) -> None:
        root = self._case_root()
        src = root / "src"
        dst = root / "dst"
        (src / "items").mkdir(parents=True, exist_ok=True)
        (src / "npcs").mkdir(parents=True, exist_ok=True)
        (src / "regions").mkdir(parents=True, exist_ok=True)
        (src / "magic").mkdir(parents=True, exist_ok=True)
        (src / "quests").mkdir(parents=True, exist_ok=True)
        (src / "items" / "stub.json").write_text("{}", encoding="utf-8")
        (src / "npcs" / "stub.json").write_text("{}", encoding="utf-8")
        (src / "regions" / "stub.json").write_text(json.dumps({"region_id": "x", "rooms": {}}), encoding="utf-8")
        (src / "magic" / "stub.json").write_text("{}", encoding="utf-8")
        (src / "world_layout.json").write_text("{}", encoding="utf-8")
        (src / "quests.json").write_text(
            json.dumps({"q1": {"title": "Quest 1", "stages": [{"description": "a"}, {"stage_index": 9, "description": "b"}]}}),
            encoding="utf-8",
        )
        (src / "quests" / "instances.json").write_text(
            json.dumps({"i1": {"title": "Instance 1", "stages": [{"description": "x"}]}}),
            encoding="utf-8",
        )
        report = shim_editor_export(src, dst, validate=False)
        quests = json.loads((dst / "quests" / "quests.json").read_text(encoding="utf-8"))
        instances = json.loads((dst / "quests" / "instances.json").read_text(encoding="utf-8"))
        self.assertEqual("quest", quests["q1"]["type"])
        self.assertEqual(0, quests["q1"]["stages"][0]["stage_index"])
        self.assertEqual(9, quests["q1"]["stages"][1]["stage_index"])
        self.assertEqual("instance", instances["i1"]["type"])
        self.assertEqual(0, instances["i1"]["stages"][0]["stage_index"])
        normalization = report.get("normalization", {})
        self.assertGreaterEqual(int(normalization.get("quest_types_added", 0)), 1)
        self.assertGreaterEqual(int(normalization.get("instance_types_added", 0)), 1)

    def test_hydrates_missing_templates_from_latest_root(self) -> None:
        root = self._case_root()
        src = root / "src"
        dst = root / "dst"
        latest = root / "latest"
        (src / "items").mkdir(parents=True, exist_ok=True)
        (src / "npcs").mkdir(parents=True, exist_ok=True)
        (src / "regions").mkdir(parents=True, exist_ok=True)
        (src / "magic").mkdir(parents=True, exist_ok=True)
        (src / "quests").mkdir(parents=True, exist_ok=True)
        (latest / "items").mkdir(parents=True, exist_ok=True)
        (latest / "npcs").mkdir(parents=True, exist_ok=True)
        (src / "items" / "stub.json").write_text("{}", encoding="utf-8")
        (src / "npcs" / "stub.json").write_text("{}", encoding="utf-8")
        (src / "magic" / "stub.json").write_text("{}", encoding="utf-8")
        (src / "world_layout.json").write_text("{}", encoding="utf-8")
        (src / "quests.json").write_text("{}", encoding="utf-8")
        (src / "quests" / "instances.json").write_text("{}", encoding="utf-8")
        (src / "regions" / "town.json").write_text(
            json.dumps(
                {
                    "region_id": "town",
                    "rooms": {
                        "square": {
                            "name": "Square",
                            "exits": {},
                            "items": [{"item_id": "item_missing"}],
                            "initial_npcs": [{"template_id": "npc_missing"}],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        (latest / "items" / "misc.json").write_text(
            json.dumps({"item_missing": {"type": "Item", "name": "x", "description": "x", "properties": {}}}),
            encoding="utf-8",
        )
        (latest / "npcs" / "misc.json").write_text(
            json.dumps({"npc_missing": {"name": "x", "faction": "friendly"}}),
            encoding="utf-8",
        )

        report = shim_editor_export(src, dst, validate=False, latest_root=latest)
        self.assertIn("item_missing", report.get("migration", {}).get("hydrated_item_ids", []))
        self.assertIn("npc_missing", report.get("migration", {}).get("hydrated_npc_ids", []))
        self.assertTrue((dst / "items" / "migrated_latest.items.json").exists())
        self.assertTrue((dst / "npcs" / "migrated_latest.npcs.json").exists())

    def test_hydrates_item_refs_found_inside_npc_templates(self) -> None:
        root = self._case_root()
        src = root / "src"
        dst = root / "dst"
        latest = root / "latest"
        (src / "items").mkdir(parents=True, exist_ok=True)
        (src / "npcs").mkdir(parents=True, exist_ok=True)
        (src / "regions").mkdir(parents=True, exist_ok=True)
        (src / "magic").mkdir(parents=True, exist_ok=True)
        (src / "quests").mkdir(parents=True, exist_ok=True)
        (latest / "items").mkdir(parents=True, exist_ok=True)
        (latest / "npcs").mkdir(parents=True, exist_ok=True)
        (src / "items" / "stub.json").write_text("{}", encoding="utf-8")
        (src / "npcs" / "vendors.json").write_text(
            json.dumps({"vendor": {"name": "Vendor", "vendor_inventory": [{"item_id": "item_only_in_latest"}]}}),
            encoding="utf-8",
        )
        (src / "regions" / "stub.json").write_text(json.dumps({"region_id": "x", "rooms": {}}), encoding="utf-8")
        (src / "magic" / "stub.json").write_text("{}", encoding="utf-8")
        (src / "world_layout.json").write_text("{}", encoding="utf-8")
        (src / "quests.json").write_text("{}", encoding="utf-8")
        (src / "quests" / "instances.json").write_text("{}", encoding="utf-8")
        (latest / "items" / "misc.json").write_text(
            json.dumps({"item_only_in_latest": {"type": "Item", "name": "x", "description": "x", "properties": {}}}),
            encoding="utf-8",
        )
        (latest / "npcs" / "misc.json").write_text("{}", encoding="utf-8")

        report = shim_editor_export(src, dst, validate=False, latest_root=latest)
        self.assertIn("item_only_in_latest", report.get("migration", {}).get("hydrated_item_ids", []))


class TestNormalizeRegionPayload(unittest.TestCase):
    def test_non_dict_payload_is_returned_unchanged(self) -> None:
        payload, stats = _normalize_region_payload(["not", "a", "dict"])
        self.assertEqual(["not", "a", "dict"], payload)
        self.assertEqual(0, stats["region_editor_keys_removed"])

    def test_missing_rooms_key_returns_after_top_level_cleanup(self) -> None:
        payload, stats = _normalize_region_payload({"_editor_graph": {}, "region_id": "x"})
        self.assertNotIn("_editor_graph", payload)
        self.assertEqual(1, stats["region_editor_keys_removed"])
        self.assertEqual(0, stats["room_editor_keys_removed"])

    def test_non_dict_rooms_value_returns_after_top_level_cleanup(self) -> None:
        payload, stats = _normalize_region_payload({"rooms": "not-a-dict"})
        self.assertEqual("not-a-dict", payload["rooms"])
        self.assertEqual(0, stats["room_editor_keys_removed"])

    def test_non_dict_room_entry_is_kept_verbatim(self) -> None:
        payload, stats = _normalize_region_payload({"rooms": {"broken": "not-a-dict"}})
        self.assertEqual("not-a-dict", payload["rooms"]["broken"])
        self.assertEqual(0, stats["rooms_with_properties_added"])

    def test_room_with_existing_properties_dict_is_not_flagged(self) -> None:
        payload, stats = _normalize_region_payload(
            {"rooms": {"square": {"properties": {"lit": True}, "exits": {}}}}
        )
        self.assertEqual({"lit": True}, payload["rooms"]["square"]["properties"])
        self.assertEqual(0, stats["rooms_with_properties_added"])

    def test_room_with_non_dict_exits_is_left_alone(self) -> None:
        payload, _stats = _normalize_region_payload({"rooms": {"square": {"exits": "north"}}})
        self.assertEqual("north", payload["rooms"]["square"]["exits"])

    def test_exit_values_are_stringified_and_trimmed(self) -> None:
        payload, _stats = _normalize_region_payload({"rooms": {"square": {"exits": {"north": "  town:gate  "}}}})
        self.assertEqual("town:gate", payload["rooms"]["square"]["exits"]["north"])


class TestNormalizeExportTree(unittest.TestCase):
    def _case_root(self) -> Path:
        root = Path("tmp") / f"editor_export_shim_helper_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def test_missing_regions_dir_returns_zeroed_summary(self) -> None:
        root = self._case_root()
        summary = _normalize_export_tree(root)
        self.assertEqual(0, summary["regions_processed"])

    def test_malformed_region_file_is_skipped_but_others_still_processed(self) -> None:
        root = self._case_root()
        regions = root / "regions"
        regions.mkdir()
        (regions / "broken.json").write_text("{not valid", encoding="utf-8")
        (regions / "ok.json").write_text(json.dumps({"_editor_graph": {}, "rooms": {}}), encoding="utf-8")

        summary = _normalize_export_tree(root)
        self.assertEqual(1, summary["regions_processed"])
        self.assertEqual(1, summary["region_editor_keys_removed"])


class TestNormalizeQuestPayload(unittest.TestCase):
    def _case_root(self) -> Path:
        root = Path("tmp") / f"editor_export_shim_helper_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def test_missing_file_returns_zeroed_stats(self) -> None:
        stats = _normalize_quest_payload(self._case_root() / "missing.json", "quest")
        self.assertEqual({"templates_processed": 0, "types_added": 0, "stage_indexes_added": 0}, stats)

    def test_malformed_json_returns_zeroed_stats(self) -> None:
        path = self._case_root() / "quests.json"
        path.write_text("{broken", encoding="utf-8")
        stats = _normalize_quest_payload(path, "quest")
        self.assertEqual(0, stats["templates_processed"])

    def test_non_dict_top_level_returns_zeroed_stats(self) -> None:
        path = self._case_root() / "quests.json"
        path.write_text("[]", encoding="utf-8")
        stats = _normalize_quest_payload(path, "quest")
        self.assertEqual(0, stats["templates_processed"])

    def test_non_dict_template_entry_is_kept_verbatim(self) -> None:
        path = self._case_root() / "quests.json"
        path.write_text(json.dumps({"broken": "not-a-dict"}), encoding="utf-8")
        _normalize_quest_payload(path, "quest")
        self.assertEqual({"broken": "not-a-dict"}, json.loads(path.read_text(encoding="utf-8")))

    def test_existing_type_is_not_overwritten(self) -> None:
        path = self._case_root() / "quests.json"
        path.write_text(json.dumps({"q1": {"type": "custom_type"}}), encoding="utf-8")
        stats = _normalize_quest_payload(path, "quest")
        self.assertEqual(0, stats["types_added"])
        self.assertEqual("custom_type", json.loads(path.read_text(encoding="utf-8"))["q1"]["type"])

    def test_non_list_stages_are_left_alone(self) -> None:
        path = self._case_root() / "quests.json"
        path.write_text(json.dumps({"q1": {"stages": "not-a-list"}}), encoding="utf-8")
        _normalize_quest_payload(path, "quest")
        self.assertEqual("not-a-list", json.loads(path.read_text(encoding="utf-8"))["q1"]["stages"])

    def test_non_dict_stage_is_kept_verbatim_and_still_indexed(self) -> None:
        path = self._case_root() / "quests.json"
        path.write_text(json.dumps({"q1": {"stages": ["not-a-dict"]}}), encoding="utf-8")
        _normalize_quest_payload(path, "quest")
        self.assertEqual(["not-a-dict"], json.loads(path.read_text(encoding="utf-8"))["q1"]["stages"])

    def test_existing_stage_index_is_not_overwritten(self) -> None:
        path = self._case_root() / "quests.json"
        path.write_text(json.dumps({"q1": {"stages": [{"stage_index": 9}]}}), encoding="utf-8")
        stats = _normalize_quest_payload(path, "quest")
        self.assertEqual(0, stats["stage_indexes_added"])
        self.assertEqual(9, json.loads(path.read_text(encoding="utf-8"))["q1"]["stages"][0]["stage_index"])


class TestLoadTemplatePayloads(unittest.TestCase):
    def _case_root(self) -> Path:
        root = Path("tmp") / f"editor_export_shim_helper_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def test_missing_directory_returns_empty_dict(self) -> None:
        self.assertEqual({}, _load_template_payloads(self._case_root() / "missing"))

    def test_malformed_file_is_skipped(self) -> None:
        root = self._case_root()
        (root / "broken.json").write_text("{not valid", encoding="utf-8")
        self.assertEqual({}, _load_template_payloads(root))

    def test_non_dict_top_level_is_skipped(self) -> None:
        root = self._case_root()
        (root / "list.json").write_text("[]", encoding="utf-8")
        self.assertEqual({}, _load_template_payloads(root))

    def test_non_dict_entry_values_are_skipped(self) -> None:
        root = self._case_root()
        (root / "mixed.json").write_text(json.dumps({"good": {"a": 1}, "bad": "not-a-dict"}), encoding="utf-8")
        self.assertEqual({"good": {"a": 1}}, _load_template_payloads(root))


class TestCollectIdsFromPayload(unittest.TestCase):
    def test_collects_item_and_npc_ids_from_nested_structures(self) -> None:
        item_ids: set[str] = set()
        npc_ids: set[str] = set()
        payload = {
            "vendor_inventory": [{"item_id": "item_potion"}],
            "loot_table": {"item_gold": 1, "item_gem": 2},
            "summon": {"template_id": "npc_wolf"},
            "irrelevant": 42,
        }
        _collect_ids_from_payload(payload, item_ids, npc_ids)
        self.assertEqual({"item_potion", "item_gold", "item_gem"}, item_ids)
        self.assertEqual({"npc_wolf"}, npc_ids)

    def test_ignores_non_dict_non_list_leaves(self) -> None:
        item_ids: set[str] = set()
        npc_ids: set[str] = set()
        _collect_ids_from_payload("just a string", item_ids, npc_ids)
        _collect_ids_from_payload(42, item_ids, npc_ids)
        self.assertEqual(set(), item_ids)
        self.assertEqual(set(), npc_ids)

    def test_blank_item_and_template_id_values_are_ignored(self) -> None:
        item_ids: set[str] = set()
        npc_ids: set[str] = set()
        payload = {"item_id": "   ", "nested": {"template_id": "  "}}
        _collect_ids_from_payload(payload, item_ids, npc_ids)
        self.assertEqual(set(), item_ids)
        self.assertEqual(set(), npc_ids)

    def test_blank_loot_table_key_is_ignored(self) -> None:
        item_ids: set[str] = set()
        npc_ids: set[str] = set()
        payload = {"loot_table": {"  ": 1, "item_real": 1}}
        _collect_ids_from_payload(payload, item_ids, npc_ids)
        self.assertEqual({"item_real"}, item_ids)


class TestCollectReferencesForMigration(unittest.TestCase):
    def _case_root(self) -> Path:
        root = Path("tmp") / f"editor_export_shim_helper_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def test_no_directories_returns_empty_sets(self) -> None:
        item_ids, npc_ids = _collect_references_for_migration(self._case_root())
        self.assertEqual(set(), item_ids)
        self.assertEqual(set(), npc_ids)

    def test_malformed_region_and_quest_files_are_skipped(self) -> None:
        root = self._case_root()
        (root / "regions").mkdir()
        (root / "regions" / "broken.json").write_text("{not valid", encoding="utf-8")
        (root / "quests").mkdir()
        (root / "quests" / "quests.json").write_text("{not valid", encoding="utf-8")
        item_ids, npc_ids = _collect_references_for_migration(root)
        self.assertEqual(set(), item_ids)
        self.assertEqual(set(), npc_ids)

    def test_room_items_and_npcs_are_collected(self) -> None:
        root = self._case_root()
        (root / "regions").mkdir()
        (root / "regions" / "town.json").write_text(
            json.dumps({
                "rooms": {
                    "square": {
                        "items": [{"item_id": "item_sword"}, "not-a-dict"],
                        "initial_npcs": [{"template_id": "npc_guard"}, "not-a-dict"],
                    },
                    "broken": "not-a-dict",
                }
            }),
            encoding="utf-8",
        )
        item_ids, npc_ids = _collect_references_for_migration(root)
        self.assertEqual({"item_sword"}, item_ids)
        self.assertEqual({"npc_guard"}, npc_ids)

    def test_quest_reward_and_stage_references_are_collected(self) -> None:
        root = self._case_root()
        (root / "quests").mkdir()
        (root / "quests" / "quests.json").write_text(
            json.dumps({
                "q1": {
                    "rewards": {"items": [{"item_id": "item_reward"}, "not-a-dict"]},
                    "stages": [
                        "not-a-dict",
                        {
                            "turn_in_id": "npc_giver",
                            "spawn_on_entry": {"template_id": "npc_spawned"},
                            "objective": {
                                "item_id": "item_objective",
                                "target_template_id": "npc_target",
                            },
                        },
                    ],
                },
                "q2": "not-a-dict",
            }),
            encoding="utf-8",
        )
        item_ids, npc_ids = _collect_references_for_migration(root)
        self.assertEqual({"item_reward", "item_objective"}, item_ids)
        self.assertEqual({"npc_giver", "npc_spawned", "npc_target"}, npc_ids)

    def test_npc_templates_contribute_nested_references(self) -> None:
        root = self._case_root()
        (root / "npcs").mkdir()
        (root / "npcs" / "broken.json").write_text("{not valid", encoding="utf-8")
        (root / "npcs" / "vendors.json").write_text(
            json.dumps({"npc_vendor": {"loot_table": {"item_from_npc": 1}}}),
            encoding="utf-8",
        )
        item_ids, _npc_ids = _collect_references_for_migration(root)
        self.assertEqual({"item_from_npc"}, item_ids)

    def test_non_dict_npc_json_top_level_is_skipped(self) -> None:
        root = self._case_root()
        (root / "npcs").mkdir()
        (root / "npcs" / "list.json").write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
        item_ids, npc_ids = _collect_references_for_migration(root)
        self.assertEqual(set(), item_ids)
        self.assertEqual(set(), npc_ids)

    def test_non_dict_rooms_value_is_skipped(self) -> None:
        root = self._case_root()
        (root / "regions").mkdir()
        (root / "regions" / "town.json").write_text(
            json.dumps({"rooms": "not-a-dict"}), encoding="utf-8",
        )
        item_ids, npc_ids = _collect_references_for_migration(root)
        self.assertEqual(set(), item_ids)
        self.assertEqual(set(), npc_ids)

    def test_non_list_room_items_and_npcs_are_skipped(self) -> None:
        root = self._case_root()
        (root / "regions").mkdir()
        (root / "regions" / "town.json").write_text(
            json.dumps({
                "rooms": {"square": {"items": "not-a-list", "initial_npcs": "not-a-list"}},
            }),
            encoding="utf-8",
        )
        item_ids, npc_ids = _collect_references_for_migration(root)
        self.assertEqual(set(), item_ids)
        self.assertEqual(set(), npc_ids)

    def test_blank_room_item_and_npc_ids_are_ignored(self) -> None:
        root = self._case_root()
        (root / "regions").mkdir()
        (root / "regions" / "town.json").write_text(
            json.dumps({
                "rooms": {
                    "square": {
                        "items": [{"item_id": "  "}, {"item_id": "item_real"}],
                        "initial_npcs": [{"template_id": "  "}, {"template_id": "npc_real"}],
                    },
                },
            }),
            encoding="utf-8",
        )
        item_ids, npc_ids = _collect_references_for_migration(root)
        self.assertEqual({"item_real"}, item_ids)
        self.assertEqual({"npc_real"}, npc_ids)

    def test_non_dict_quest_json_top_level_is_skipped(self) -> None:
        root = self._case_root()
        (root / "quests").mkdir()
        (root / "quests" / "quests.json").write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
        item_ids, npc_ids = _collect_references_for_migration(root)
        self.assertEqual(set(), item_ids)
        self.assertEqual(set(), npc_ids)

    def test_quest_rewards_and_stages_with_wrong_types_are_skipped(self) -> None:
        root = self._case_root()
        (root / "quests").mkdir()
        (root / "quests" / "quests.json").write_text(
            json.dumps({"q1": {"rewards": "not-a-dict", "stages": "not-a-list"}}), encoding="utf-8",
        )
        item_ids, npc_ids = _collect_references_for_migration(root)
        self.assertEqual(set(), item_ids)
        self.assertEqual(set(), npc_ids)

    def test_non_list_reward_items_is_skipped(self) -> None:
        root = self._case_root()
        (root / "quests").mkdir()
        (root / "quests" / "quests.json").write_text(
            json.dumps({"q1": {"rewards": {"items": "not-a-list"}}}), encoding="utf-8",
        )
        item_ids, _npc_ids = _collect_references_for_migration(root)
        self.assertEqual(set(), item_ids)

    def test_blank_reward_item_id_is_ignored(self) -> None:
        root = self._case_root()
        (root / "quests").mkdir()
        (root / "quests" / "quests.json").write_text(
            json.dumps({"q1": {"rewards": {"items": [{"item_id": "  "}, {"item_id": "item_real"}]}}}),
            encoding="utf-8",
        )
        item_ids, _npc_ids = _collect_references_for_migration(root)
        self.assertEqual({"item_real"}, item_ids)

    def test_spawn_and_objective_with_wrong_types_are_skipped(self) -> None:
        root = self._case_root()
        (root / "quests").mkdir()
        (root / "quests" / "quests.json").write_text(
            json.dumps({
                "q1": {"stages": [{"spawn_on_entry": "not-a-dict", "objective": "not-a-dict"}]},
            }),
            encoding="utf-8",
        )
        item_ids, npc_ids = _collect_references_for_migration(root)
        self.assertEqual(set(), item_ids)
        self.assertEqual(set(), npc_ids)


class TestHydrateFromLatest(unittest.TestCase):
    def _case_root(self) -> Path:
        root = Path("tmp") / f"editor_export_shim_helper_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def test_no_referenced_ids_writes_nothing(self) -> None:
        root = self._case_root()
        target = root / "target"
        (target / "regions").mkdir(parents=True)
        summary = _hydrate_from_latest(target, root / "latest")
        self.assertEqual([], summary["hydrated_item_ids"])
        self.assertFalse((target / "items" / "migrated_latest.items.json").exists())

    def test_referenced_id_missing_from_latest_is_reported(self) -> None:
        root = self._case_root()
        target = root / "target"
        (target / "regions").mkdir(parents=True)
        (target / "regions" / "town.json").write_text(
            json.dumps({"rooms": {"square": {"items": [{"item_id": "item_ghost"}]}}}), encoding="utf-8"
        )
        summary = _hydrate_from_latest(target, root / "latest")
        self.assertEqual(["item_ghost"], summary["missing_item_ids"])

    def test_referenced_npc_missing_from_latest_is_reported(self) -> None:
        root = self._case_root()
        target = root / "target"
        (target / "regions").mkdir(parents=True)
        (target / "regions" / "town.json").write_text(
            json.dumps({"rooms": {"square": {"initial_npcs": [{"template_id": "npc_ghost"}]}}}),
            encoding="utf-8",
        )
        summary = _hydrate_from_latest(target, root / "latest")
        self.assertEqual(["npc_ghost"], summary["missing_npc_ids"])

    def test_second_pass_skips_item_already_present_in_target(self) -> None:
        root = self._case_root()
        target = root / "target"
        latest = root / "latest"
        (target / "regions").mkdir(parents=True)
        (target / "regions" / "town.json").write_text(
            json.dumps({"rooms": {"square": {"initial_npcs": [{"template_id": "npc_vendor"}]}}}),
            encoding="utf-8",
        )
        (target / "items").mkdir(parents=True)
        (target / "items" / "existing.json").write_text(
            json.dumps({"item_already_present": {"type": "Item", "name": "x", "description": "x", "properties": {}}}),
            encoding="utf-8",
        )
        (latest / "npcs").mkdir(parents=True)
        (latest / "npcs" / "vendors.json").write_text(
            json.dumps({"npc_vendor": {"loot_table": {"item_already_present": 1}}}),
            encoding="utf-8",
        )

        summary = _hydrate_from_latest(target, latest)

        self.assertNotIn("item_already_present", summary["hydrated_item_ids"])
        self.assertFalse((target / "items" / "migrated_latest.items.json").exists())

    def test_second_pass_reports_item_missing_from_latest(self) -> None:
        root = self._case_root()
        target = root / "target"
        latest = root / "latest"
        (target / "regions").mkdir(parents=True)
        (target / "regions" / "town.json").write_text(
            json.dumps({"rooms": {"square": {"initial_npcs": [{"template_id": "npc_vendor"}]}}}),
            encoding="utf-8",
        )
        (latest / "npcs").mkdir(parents=True)
        (latest / "npcs" / "vendors.json").write_text(
            json.dumps({"npc_vendor": {"loot_table": {"item_only_via_npc_and_missing": 1}}}),
            encoding="utf-8",
        )

        summary = _hydrate_from_latest(target, latest)

        self.assertIn("item_only_via_npc_and_missing", summary["missing_item_ids"])

    def test_second_pass_does_not_duplicate_an_already_reported_missing_item(self) -> None:
        root = self._case_root()
        target = root / "target"
        latest = root / "latest"
        (target / "regions").mkdir(parents=True)
        (target / "regions" / "town.json").write_text(
            json.dumps({
                "rooms": {
                    "square": {
                        "items": [{"item_id": "item_shared_missing"}],
                        "initial_npcs": [{"template_id": "npc_vendor"}],
                    },
                },
            }),
            encoding="utf-8",
        )
        (latest / "npcs").mkdir(parents=True)
        (latest / "npcs" / "vendors.json").write_text(
            json.dumps({"npc_vendor": {"loot_table": {"item_shared_missing": 1}}}),
            encoding="utf-8",
        )

        summary = _hydrate_from_latest(target, latest)

        self.assertEqual(["item_shared_missing"], summary["missing_item_ids"])

    def test_second_pass_with_no_item_references_writes_no_items_file(self) -> None:
        root = self._case_root()
        target = root / "target"
        latest = root / "latest"
        (target / "regions").mkdir(parents=True)
        (target / "regions" / "town.json").write_text(
            json.dumps({"rooms": {"square": {"initial_npcs": [{"template_id": "npc_plain"}]}}}),
            encoding="utf-8",
        )
        (latest / "npcs").mkdir(parents=True)
        (latest / "npcs" / "plain.json").write_text(
            json.dumps({"npc_plain": {"name": "Plain Npc", "faction": "neutral"}}),
            encoding="utf-8",
        )

        summary = _hydrate_from_latest(target, latest)

        self.assertIn("npc_plain", summary["hydrated_npc_ids"])
        self.assertEqual([], summary["hydrated_item_ids"])
        self.assertFalse((target / "items" / "migrated_latest.items.json").exists())

    def test_second_pass_hydrates_items_referenced_only_by_a_hydrated_npc(self) -> None:
        root = self._case_root()
        target = root / "target"
        latest = root / "latest"
        (target / "regions").mkdir(parents=True)
        (target / "regions" / "town.json").write_text(
            json.dumps({"rooms": {"square": {"initial_npcs": [{"template_id": "npc_vendor"}]}}}),
            encoding="utf-8",
        )
        (latest / "npcs").mkdir(parents=True)
        (latest / "npcs" / "vendors.json").write_text(
            json.dumps({"npc_vendor": {"loot_table": {"item_only_via_npc": 1}}}),
            encoding="utf-8",
        )
        (latest / "items").mkdir(parents=True)
        (latest / "items" / "misc.json").write_text(
            json.dumps({"item_only_via_npc": {"type": "Item", "name": "x", "description": "x", "properties": {}}}),
            encoding="utf-8",
        )

        summary = _hydrate_from_latest(target, latest)

        self.assertIn("npc_vendor", summary["hydrated_npc_ids"])
        self.assertIn("item_only_via_npc", summary["hydrated_item_ids"])
        hydrated_items = json.loads((target / "items" / "migrated_latest.items.json").read_text(encoding="utf-8"))
        self.assertIn("item_only_via_npc", hydrated_items)


class TestCopyPathAndQuestsJson(unittest.TestCase):
    def _case_root(self) -> Path:
        root = Path("tmp") / f"editor_export_shim_helper_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def test_copy_path_copies_a_single_file(self) -> None:
        root = self._case_root()
        src = root / "src.json"
        src.write_text("{}", encoding="utf-8")
        dst = root / "nested" / "dst.json"
        _copy_path(src, dst)
        self.assertTrue(dst.exists())

    def test_copy_path_replaces_an_existing_readonly_destination_directory(self) -> None:
        root = self._case_root()
        src = root / "src"
        src.mkdir()
        (src / "new.txt").write_text("new", encoding="utf-8")
        dst = root / "dst"
        dst.mkdir()
        stale_file = dst / "stale.txt"
        stale_file.write_text("stale", encoding="utf-8")
        stale_file.chmod(stat.S_IREAD)  # exercise the readonly-cleanup path
        self.addCleanup(lambda: stale_file.chmod(stat.S_IWRITE) if stale_file.exists() else None)

        _copy_path(src, dst)

        self.assertTrue((dst / "new.txt").exists())
        self.assertFalse((dst / "stale.txt").exists())

    def test_copy_quests_root_json_writes_empty_object_for_blank_source(self) -> None:
        root = self._case_root()
        src = root / "quests.json"
        src.write_text("   ", encoding="utf-8")
        dst = root / "out.json"
        _copy_quests_root_json(src, dst)
        self.assertEqual("{}\n", dst.read_text(encoding="utf-8"))

    def test_copy_quests_root_json_preserves_bytes_on_malformed_source(self) -> None:
        root = self._case_root()
        src = root / "quests.json"
        src.write_text("{not valid", encoding="utf-8")
        dst = root / "out.json"
        _copy_quests_root_json(src, dst)
        self.assertEqual("{not valid", dst.read_text(encoding="utf-8"))

    def test_copy_quests_root_json_writes_empty_object_for_non_dict_source(self) -> None:
        root = self._case_root()
        src = root / "quests.json"
        src.write_text("[1, 2, 3]", encoding="utf-8")
        dst = root / "out.json"
        _copy_quests_root_json(src, dst)
        self.assertEqual("{}\n", dst.read_text(encoding="utf-8"))


class TestEditorExportShimMain(unittest.TestCase):
    def _case_root(self) -> Path:
        root = Path("tmp") / f"editor_export_shim_main_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _write_clean_source(self, src: Path) -> None:
        for sub in ("items", "npcs", "regions", "magic", "quests"):
            (src / sub).mkdir(parents=True, exist_ok=True)
        (src / "items" / "base.json").write_text("{}", encoding="utf-8")
        (src / "npcs" / "base.json").write_text("{}", encoding="utf-8")
        (src / "regions" / "town.json").write_text(
            json.dumps({"region_id": "town", "rooms": {"square": {"name": "Square", "exits": {}}}}),
            encoding="utf-8",
        )
        (src / "magic" / "base.json").write_text("{}", encoding="utf-8")
        (src / "quests" / "instances.json").write_text("{}", encoding="utf-8")
        (src / "quests.json").write_text("{}", encoding="utf-8")
        (src / "world_layout.json").write_text("{}", encoding="utf-8")

    def test_missing_source_root_raises_system_exit(self) -> None:
        root = self._case_root()
        argv = ["editor_export_shim.py", "--source", str(root / "missing")]
        with patch.object(sys, "argv", argv):
            with self.assertRaises(SystemExit):
                main()

    def test_no_validate_flag_omits_validation_report_key(self) -> None:
        root = self._case_root()
        src = root / "src"
        self._write_clean_source(src)
        argv = [
            "editor_export_shim.py",
            "--source", str(src),
            "--target", str(root / "target"),
            "--report", str(root / "report.json"),
            "--latest-root", str(root / "latest"),
            "--no-validate",
        ]
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            main()
        report = json.loads((root / "report.json").read_text(encoding="utf-8"))
        self.assertNotIn("validation", report)

    def test_strict_flag_raises_system_exit_when_issues_present(self) -> None:
        root = self._case_root()
        src = root / "src"
        src.mkdir()  # empty source: everything will be reported missing
        argv = [
            "editor_export_shim.py",
            "--source", str(src),
            "--target", str(root / "target"),
            "--report", str(root / "report.json"),
            "--latest-root", str(root / "latest"),
            "--no-validate",
            "--strict",
        ]
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(1, cm.exception.code)

    def test_clean_strict_run_does_not_raise(self) -> None:
        root = self._case_root()
        src = root / "src"
        self._write_clean_source(src)
        argv = [
            "editor_export_shim.py",
            "--source", str(src),
            "--target", str(root / "target"),
            "--report", str(root / "report.json"),
            "--latest-root", str(root / "latest"),
            "--strict",
        ]
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            main()  # must not raise
        report = json.loads((root / "report.json").read_text(encoding="utf-8"))
        self.assertTrue(report["validation"]["ok"])


if __name__ == "__main__":
    unittest.main()
