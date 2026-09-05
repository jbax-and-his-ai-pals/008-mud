"""Coverage for toolkit/stale_reference_audit.py.

Note: the module's `if __name__ == "__main__": main()` guard (line 95) is
never executed under import-based testing -- it only runs when the file is
invoked directly as a script. Left untested as unreachable boilerplate,
consistent with this codebase's established precedent (e.g.
toolkit/content_set_validator.py's equivalent guard)."""

import io
import json
import shutil
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

from stale_reference_audit import audit_stale_references, main
from reference_integrity_validator import RefIssue


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

    def test_flags_missing_npc_template_id_reference(self) -> None:
        root = self._case_root()
        self._seed_minimal_tree(root)
        (root / "npcs" / "summoners.json").write_text(
            json.dumps({"summoner": {"name": "Summoner", "summon": {"template_id": "npc_missing"}}}),
            encoding="utf-8",
        )
        lines = audit_stale_references(root)
        self.assertTrue(any("npc_missing" in line for line in lines))

    def test_malformed_npc_file_is_reported_as_a_parse_failure(self) -> None:
        root = self._case_root()
        self._seed_minimal_tree(root)
        (root / "npcs" / "broken.json").write_text("{not valid", encoding="utf-8")
        lines = audit_stale_references(root)
        self.assertTrue(any("parse failure" in line for line in lines))

    def test_blank_item_id_value_is_ignored(self) -> None:
        root = self._case_root()
        self._seed_minimal_tree(root)
        (root / "npcs" / "blank_item.json").write_text(
            json.dumps({"vendor": {"name": "Vendor", "initial_inventory": [{"item_id": ""}]}}),
            encoding="utf-8",
        )
        lines = audit_stale_references(root)
        self.assertFalse(any("unknown item_id" in line for line in lines))

    def test_blank_template_id_value_is_ignored(self) -> None:
        root = self._case_root()
        self._seed_minimal_tree(root)
        (root / "npcs" / "blank_template.json").write_text(
            json.dumps({"summoner": {"name": "Summoner", "summon": {"template_id": ""}}}),
            encoding="utf-8",
        )
        lines = audit_stale_references(root)
        self.assertFalse(any("unknown npc template_id" in line for line in lines))

    def test_includes_baseline_reference_integrity_issues(self) -> None:
        root = self._case_root()
        self._seed_minimal_tree(root)
        (root / "regions" / "town.json").write_text(
            json.dumps({"region_id": "town", "rooms": {"square": {"exits": {"north": "nowhere"}}}}),
            encoding="utf-8",
        )
        lines = audit_stale_references(root)
        self.assertTrue(any("unknown exit target" in line for line in lines))


class TestStaleReferenceAuditMain(unittest.TestCase):
    def _case_root(self) -> Path:
        root = _REPO_ROOT / "server" / "tests" / "_tmp" / f"stale_audit_main_{uuid.uuid4().hex}"
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

    def _run_main(self, argv: list) -> int:
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                main()
        return cm.exception.code

    def test_missing_root_exits_two(self) -> None:
        code = self._run_main(["stale_reference_audit.py", str(self._case_root() / "missing")])
        self.assertEqual(2, code)

    def test_clean_root_exits_zero(self) -> None:
        root = self._case_root()
        self._seed_minimal_tree(root)
        code = self._run_main(["stale_reference_audit.py", str(root)])
        self.assertEqual(0, code)

    def test_root_with_issues_exits_one(self) -> None:
        root = self._case_root()
        self._seed_minimal_tree(root)
        (root / "regions" / "town.json").write_text(
            json.dumps({"region_id": "town", "rooms": {"square": {"exits": {"north": "nowhere"}}}}),
            encoding="utf-8",
        )
        code = self._run_main(["stale_reference_audit.py", str(root)])
        self.assertEqual(1, code)

    def test_non_error_lines_do_not_count_toward_error_total(self) -> None:
        root = self._case_root()
        self._seed_minimal_tree(root)
        with patch(
            "stale_reference_audit.validate_catalogs",
            return_value=[RefIssue("warning", "test/path", "a non-fatal warning")],
        ):
            code = self._run_main(["stale_reference_audit.py", str(root)])
        self.assertEqual(0, code)

    def test_output_flag_writes_report_file(self) -> None:
        root = self._case_root()
        self._seed_minimal_tree(root)
        out_path = root / "report.txt"
        code = self._run_main(["stale_reference_audit.py", str(root), "--output", str(out_path)])
        self.assertEqual(0, code)
        self.assertTrue(out_path.exists())


if __name__ == "__main__":
    unittest.main()
