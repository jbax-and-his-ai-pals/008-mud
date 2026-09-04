import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TOOLKIT_DIR = _REPO_ROOT / "toolkit"
if str(_TOOLKIT_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLKIT_DIR))

from editor_export_shim import shim_editor_export


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

    def test_ignores_legacy_templates_path_without_warning(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
