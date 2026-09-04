import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import data_integrity_validator as validator


class TestDataIntegrityValidator(unittest.TestCase):
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
        issues = validator.validate_payload(payload, "server/data/items/items.json", strict_templates=False)
        self.assertTrue(any(issue.severity == "warn" for issue in issues))
        self.assertFalse(any(issue.severity == "error" for issue in issues))

    def test_item_template_missing_name_type_errors_in_strict_mode(self) -> None:
        payload = {"item_x": {"description": "x", "properties": {}}}
        issues = validator.validate_payload(payload, "server/data/items/items.json", strict_templates=True)
        self.assertTrue(any(issue.severity == "error" for issue in issues))

    def test_validate_tree_counts_files(self) -> None:
        checked, errors, _warnings = validator.validate_tree(REPO_ROOT / "server" / "data")
        self.assertGreater(checked, 0)
        self.assertEqual(0, errors)


if __name__ == "__main__":
    unittest.main()
