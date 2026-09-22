"""Container template validation: authored contents must survive into play."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
for candidate in (REPO_ROOT, REPO_ROOT / "server"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from engine.server import content_set as cs  # noqa: E402


class ContainerTemplateValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="container-template-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.items = self.root / "items"
        self.items.mkdir()

    def _write(self, payload: dict) -> None:
        (self.items / "items.json").write_text(json.dumps(payload), encoding="utf-8")

    def _messages(self) -> list[str]:
        issues: list[cs.ContentSetIssue] = []
        cs._validate_container_templates(self.root, issues)
        return [issue.message for issue in issues]

    def test_valid_container_with_contents_and_key_is_accepted(self) -> None:
        self._write({
            "item_key": {"name": "Key", "type": "Key"},
            "item_coin": {"name": "Coin", "type": "Item"},
            "item_chest": {"name": "Chest", "type": "Container", "properties": {
                "capacity": 40, "locked": True, "is_open": False, "key_id": "item_key",
                "contains": [{"item_id": "item_coin", "quantity": 3}],
            }},
        })
        self.assertEqual([], self._messages())

    def test_bad_nested_references_and_shapes_are_specific_errors(self) -> None:
        self._write({
            "item_chest": {"name": "Chest", "type": "Container", "properties": {
                "capacity": -1, "locked": "yes", "key_id": "missing_key",
                "contains": [{"item_id": "missing_coin", "quantity": 0, "properties_override": []}],
            }},
        })
        messages = self._messages()
        self.assertTrue(any("capacity must be a non-negative number" in message for message in messages))
        self.assertTrue(any("locked must be a boolean" in message for message in messages))
        self.assertTrue(any("key_id references a missing item template" in message for message in messages))
        self.assertTrue(any("item_id references a missing item template" in message for message in messages))
        self.assertTrue(any("quantity must be a positive integer" in message for message in messages))
        self.assertTrue(any("properties_override must be an object" in message for message in messages))

    def test_recipe_station_must_be_provided_by_an_item(self) -> None:
        self._write({
            "item_fabricator": {"name": "Fabricator", "type": "Interactive", "properties": {
                "crafting_station_type": "fabricator",
            }},
        })
        crafting = self.root / "crafting"
        crafting.mkdir()
        (crafting / "recipes.json").write_text(json.dumps({
            "recipe_valid": {"name": "Valid", "station_required": "fabricator"},
            "recipe_missing": {"name": "Missing", "station_required": "missing_bench"},
        }), encoding="utf-8")
        issues: list[cs.ContentSetIssue] = []
        cs._validate_crafting_station_references(self.root, issues)
        messages = [issue.message for issue in issues]
        self.assertFalse(any("recipe_valid" in message for message in messages))
        self.assertTrue(any("recipe_missing" in message and "no authored crafting station" in message for message in messages))

    def test_resource_node_availability_fields_have_a_checked_shape(self) -> None:
        self._write({
            "item_ore": {"name": "Ore", "type": "Item"},
            "item_node": {"name": "Vein", "type": "ResourceNode", "properties": {
                "resource_item_id": "item_ore", "charges": -1, "respawn_days": 1.5,
                "tool_required": 7, "seasons": ["winter", ""], "weather_blocked_by": "rain",
            }},
        })
        issues: list[cs.ContentSetIssue] = []
        cs._validate_resource_node_yields(self.root, issues)
        messages = [issue.message for issue in issues]
        self.assertTrue(any("tool_required must be a string" in message for message in messages))
        self.assertTrue(any("charges must be a non-negative integer" in message for message in messages))
        self.assertTrue(any("respawn_days must be a non-negative integer" in message for message in messages))
        self.assertTrue(any("seasons must be an array of non-empty strings" in message for message in messages))
        self.assertTrue(any("weather_blocked_by must be an array of non-empty strings" in message for message in messages))
