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

from stale_reference_audit import audit_stale_references


class TestStaleReferenceAudit(unittest.TestCase):
    def _case_root(self) -> Path:
        root = _REPO_ROOT / "server" / "tests" / "_tmp" / f"stale_audit_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _seed_minimal_tree(self, root: Path) -> None:
        for rel in ("items", "npcs", "regions", "quests", "campaigns"):
            (root / rel).mkdir(parents=True, exist_ok=True)
        (root / "quests" / "quests.json").write_text("{}", encoding="utf-8")
        (root / "regions" / "town.json").write_text(
            json.dumps({"region_id": "town", "rooms": {"square": {"exits": {}}}}), encoding="utf-8"
        )
        (root / "items" / "base.json").write_text(
            json.dumps({"item_ok": {"type": "Item", "name": "ok", "description": "ok", "properties": {}}}), encoding="utf-8"
        )
        (root / "npcs" / "base.json").write_text(
            json.dumps({"npc_ok": {"name": "ok", "faction": "friendly"}}), encoding="utf-8"
        )

    def test_ignores_loot_table_scalar_fields(self) -> None:
        root = self._case_root()
        self._seed_minimal_tree(root)
        (root / "npcs" / "hostiles.json").write_text(
            json.dumps(
                {
                    "goblin": {
                        "name": "Goblin",
                        "loot_table": {
                            "gold_value": {"min": 1, "max": 3},
                            "item_ok": {"chance": 0.25},
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        lines = audit_stale_references(root)
        self.assertFalse(any("gold_value" in line for line in lines))

    def test_flags_missing_item_in_npc_inventory(self) -> None:
        root = self._case_root()
        self._seed_minimal_tree(root)
        (root / "npcs" / "vendors.json").write_text(
            json.dumps({"vendor": {"name": "Vendor", "initial_inventory": [{"item_id": "item_missing"}]}}),
            encoding="utf-8",
        )
        lines = audit_stale_references(root)
        self.assertTrue(any("item_missing" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
