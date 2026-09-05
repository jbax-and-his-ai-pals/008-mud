"""Coverage for toolkit/data_integrity_validator.py.

Note: two branches are left untested as unreachable:
- validate_tree()'s `else: continue` arm for an unrecognized file suffix --
  the file-collection walk immediately above it only ever appends paths
  whose suffix is already one of ".json"/".yaml"/".yml"/".svg", so by the
  time a path reaches this dispatch, one of the preceding branches always
  matches.
- the module's `if __name__ == "__main__": main()` guard, which only runs
  when the file is invoked directly as a script (consistent with this
  codebase's established precedent for such guards, e.g.
  toolkit/content_set_validator.py)."""

import io
import shutil
import sys
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import data_integrity_validator as validator


class TestDataIntegrityValidator(unittest.TestCase):
    def test_looks_like_item_template_rejects_non_dict_values(self) -> None:
        self.assertFalse(validator._looks_like_item_template("not a dict"))
        self.assertFalse(validator._looks_like_item_template(["also", "not", "a", "dict"]))

    def test_valid_reward_items_pass(self) -> None:
        payload = {
            "quest_a": {
                "rewards": {
                    "items": [{"item_id": "item_apple", "quantity": 1}],
                }
            }
        }
        issues = validator.validate_payload(payload, "collections.json")
        self.assertFalse(any(issue.severity == "error" for issue in issues))

    def test_invalid_reward_items_fail(self) -> None:
        payload = {
            "quest_a": {
                "rewards": {
                    "items": [{"item_id": "", "quantity": 0}],
                }
            }
        }
        issues = validator.validate_payload(payload, "collections.json")
        self.assertTrue(any(issue.severity == "error" for issue in issues))

    def test_item_template_missing_name_type_warns_by_default(self) -> None:
        payload = {"item_x": {"description": "x", "properties": {}}}
        issues = validator.validate_payload(payload, "content/items/items.json", strict_templates=False)
        self.assertTrue(any(issue.severity == "warn" for issue in issues))
        self.assertFalse(any(issue.severity == "error" for issue in issues))

    def test_item_template_missing_name_type_errors_in_strict_mode(self) -> None:
        payload = {"item_x": {"description": "x", "properties": {}}}
        issues = validator.validate_payload(payload, "content/items/items.json", strict_templates=True)
        self.assertTrue(any(issue.severity == "error" for issue in issues))

    def test_validate_tree_counts_files(self) -> None:
        checked, errors, _warnings = validator.validate_tree(REPO_ROOT / "content_sets" / "fantasy_frontier" / "data")
        self.assertGreater(checked, 0)
        self.assertEqual(0, errors)

    def test_reward_items_must_be_a_list(self) -> None:
        payload = {"quest_a": {"rewards": {"items": "not-a-list"}}}
        issues = validator.validate_payload(payload, "collections.json")
        self.assertTrue(any("must be a list" in i.message for i in issues))

    def test_reward_entry_must_be_an_object(self) -> None:
        payload = {"quest_a": {"rewards": {"items": ["not-a-dict"]}}}
        issues = validator.validate_payload(payload, "collections.json")
        self.assertTrue(any("must be an object" in i.message for i in issues))

    def test_reward_quantity_must_be_a_positive_integer(self) -> None:
        payload = {"quest_a": {"rewards": {"items": [{"item_id": "item_x", "quantity": -1}]}}}
        issues = validator.validate_payload(payload, "collections.json")
        self.assertTrue(any("positive integer" in i.message for i in issues))

    def test_empty_string_key_is_an_error(self) -> None:
        payload = {"": {"a": 1}}
        issues = validator.validate_payload(payload, "collections.json")
        self.assertTrue(any("empty-string key" in i.message for i in issues))

    def test_sets_json_is_excluded_from_item_template_checks(self) -> None:
        payload = {"set_x": {"description": "x", "properties": {}}}
        issues = validator.validate_payload(payload, "content/items/sets.json")
        self.assertEqual([], issues)

    def test_item_template_non_dict_properties_is_an_error(self) -> None:
        payload = {"item_x": {"name": "X", "type": "Item", "description": "x", "properties": "not-a-dict"}}
        issues = validator.validate_payload(payload, "content/items/items.json")
        self.assertTrue(any("must be an object when present" in i.message for i in issues))

    def test_top_level_must_be_object_or_array(self) -> None:
        issues = validator.validate_payload("just a string", "collections.json")
        self.assertEqual(1, len(issues))
        self.assertEqual("error", issues[0].severity)

    def test_validate_json_file_reports_parse_errors(self) -> None:
        root = self._case_root()
        bad = root / "bad.json"
        bad.write_text("{not valid", encoding="utf-8")
        issues = validator.validate_json_file(bad)
        self.assertEqual(1, len(issues))
        self.assertIn("failed to parse JSON", issues[0].message)

    def test_validate_yaml_file_accepts_valid_yaml(self) -> None:
        root = self._case_root()
        good = root / "good.yaml"
        good.write_text("item_x:\n  name: X\n  type: Item\n  description: d\n  properties: {}\n", encoding="utf-8")
        issues = validator.validate_yaml_file(good)
        self.assertEqual([], issues)

    def test_validate_yaml_file_reports_parse_errors(self) -> None:
        root = self._case_root()
        bad = root / "bad.yaml"
        bad.write_text("key: [unclosed", encoding="utf-8")
        issues = validator.validate_yaml_file(bad)
        self.assertEqual(1, len(issues))
        self.assertIn("failed to parse YAML", issues[0].message)

    def test_validate_yaml_file_empty_document_has_no_issues(self) -> None:
        root = self._case_root()
        empty = root / "empty.yaml"
        empty.write_text("", encoding="utf-8")
        self.assertEqual([], validator.validate_yaml_file(empty))

    def test_validate_svg_file_accepts_well_formed_xml(self) -> None:
        root = self._case_root()
        good = root / "icon.svg"
        good.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8")
        self.assertEqual([], validator.validate_svg_file(good))

    def test_validate_svg_file_reports_malformed_xml(self) -> None:
        root = self._case_root()
        bad = root / "icon.svg"
        bad.write_text("<svg><unclosed>", encoding="utf-8")
        issues = validator.validate_svg_file(bad)
        self.assertEqual(1, len(issues))
        self.assertIn("failed to parse SVG XML", issues[0].message)

    def _case_root(self) -> Path:
        root = Path("tmp") / f"data_integrity_test_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def test_validate_tree_processes_yaml_and_svg_files(self) -> None:
        root = self._case_root()
        (root / "good.yaml").write_text("key: value\n", encoding="utf-8")
        (root / "bad.svg").write_text("<svg><unclosed>", encoding="utf-8")

        with redirect_stdout(io.StringIO()):
            checked, errors, _warnings = validator.validate_tree(root)

        self.assertEqual(2, checked)
        self.assertEqual(1, errors)  # only the malformed svg

    def test_validate_tree_prints_warnings(self) -> None:
        root = self._case_root()
        (root / "items").mkdir()
        (root / "items" / "items.json").write_text(
            '{"item_x": {"description": "x", "properties": {}}}', encoding="utf-8"
        )

        buf = io.StringIO()
        with redirect_stdout(buf):
            checked, errors, warnings = validator.validate_tree(root)

        self.assertEqual(0, errors)
        self.assertEqual(1, warnings)
        self.assertIn("[WARN]", buf.getvalue())

    def test_validate_tree_counts_errors_and_ignores_dot_and_save_dirs(self) -> None:
        root = self._case_root()
        (root / "items").mkdir()
        (root / "items" / "bad.json").write_text("{not valid", encoding="utf-8")
        (root / "saves").mkdir()
        (root / "saves" / "player.json").write_text("{not valid", encoding="utf-8")
        (root / "__pycache__").mkdir()
        (root / "__pycache__" / "x.json").write_text("{not valid", encoding="utf-8")

        with redirect_stdout(io.StringIO()):
            checked, errors, _warnings = validator.validate_tree(root)
        self.assertEqual(1, checked)
        self.assertEqual(1, errors)


class TestDataIntegrityValidatorMain(unittest.TestCase):
    def _case_root(self) -> Path:
        root = Path("tmp") / f"data_integrity_main_test_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _run_main(self, argv: list) -> int:
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                validator.main()
        return cm.exception.code

    def test_missing_root_exits_two(self) -> None:
        code = self._run_main(["data_integrity_validator.py", str(self._case_root() / "missing")])
        self.assertEqual(2, code)

    def test_clean_root_exits_zero(self) -> None:
        root = self._case_root()
        (root / "ok.json").write_text("{}", encoding="utf-8")
        code = self._run_main(["data_integrity_validator.py", str(root)])
        self.assertEqual(0, code)

    def test_root_with_errors_exits_one(self) -> None:
        root = self._case_root()
        (root / "bad.json").write_text("{not valid", encoding="utf-8")
        code = self._run_main(["data_integrity_validator.py", str(root)])
        self.assertEqual(1, code)

    def test_strict_templates_flag_is_wired_through(self) -> None:
        root = self._case_root()
        (root / "items").mkdir()
        (root / "items" / "items.json").write_text(
            '{"item_x": {"description": "x", "properties": {}}}', encoding="utf-8"
        )
        code = self._run_main(["data_integrity_validator.py", str(root), "--strict-templates"])
        self.assertEqual(1, code)


if __name__ == "__main__":
    unittest.main()
