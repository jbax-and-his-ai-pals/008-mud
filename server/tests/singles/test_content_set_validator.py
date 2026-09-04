import io
import json
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

from toolkit import content_set_validator as validator


class TestContentSetValidator(unittest.TestCase):
    def _case_root(self) -> Path:
        root = REPO_ROOT / "tmp" / f"content_set_validator_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _write_package(self, root: Path, *, room_id: str = "square") -> Path:
        package = root / "sample_game"
        data_root = package / "data"
        for directory in ("regions", "items", "npcs", "quests", "campaigns"):
            (data_root / directory).mkdir(parents=True, exist_ok=True)
        (data_root / "regions" / "town.json").write_text(
            json.dumps({"region_id": "town", "rooms": {room_id: {"name": "Square"}}}),
            encoding="utf-8",
        )
        (package / "rules").mkdir(parents=True, exist_ok=True)
        (package / "presentation").mkdir(parents=True, exist_ok=True)
        (package / "rules" / "ruleset.json").write_text("{}", encoding="utf-8")
        (package / "presentation" / "default.json").write_text("{}", encoding="utf-8")
        manifest = {
            "id": "sample_game",
            "title": "Sample Game",
            "version": "0.1.0",
            "manifest_schema_version": "1",
            "engine_api_min": "1.0",
            "engine_api_max": "1.0",
            "paths": {
                "data_root": "data",
                "ruleset": "rules/ruleset.json",
                "presentation": "presentation/default.json",
            },
            "start": {"scenario_id": "start", "region_id": "town", "room_id": "square"},
            "capabilities": ["inventory", "dialogue"],
        }
        (package / validator.CONTENT_SET_MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
        return package

    def test_fantasy_frontier_package_is_valid(self) -> None:
        definition, issues = validator.load_content_set(REPO_ROOT / "content_sets" / "fantasy_frontier")
        self.assertFalse([issue for issue in issues if issue.severity == "error"])
        self.assertIsNotNone(definition)
        assert definition is not None
        self.assertEqual("fantasy_frontier", definition.content_set_id)
        self.assertEqual(REPO_ROOT / "content_sets" / "fantasy_frontier" / "data", definition.data_root)
        self.assertEqual("town", definition.start_region_id)
        self.assertEqual("town_square", definition.start_room_id)
        self.assertTrue(definition.game_contract.system_enabled("magic"))
        self.assertTrue(definition.game_contract.system_enabled("progression"))
        self.assertIn("mana", definition.game_contract.status_fields)

    def test_modern_capsule_package_is_semantically_valid(self) -> None:
        definition, issues = validator.load_content_set(REPO_ROOT / "content_sets" / "modern_capsule")
        self.assertFalse([issue for issue in issues if issue.severity == "error"])
        self.assertIsNotNone(definition)
        self.assertFalse(any("missing NPC template" in issue.message for issue in issues))

    def test_missing_exit_target_is_rejected(self) -> None:
        package = self._write_package(self._case_root())
        region_path = package / "data" / "regions" / "town.json"
        region_path.write_text(
            json.dumps({"region_id": "town", "rooms": {"square": {"name": "Square", "exits": {"north": "missing"}}}}),
            encoding="utf-8",
        )
        _definition, issues = validator.load_content_set(package)
        self.assertTrue(any("targets missing room 'missing'" in issue.message for issue in issues))

    def test_missing_room_npc_and_item_references_are_rejected(self) -> None:
        package = self._write_package(self._case_root())
        region_path = package / "data" / "regions" / "town.json"
        region_path.write_text(
            json.dumps({
                "region_id": "town",
                "rooms": {"square": {"name": "Square", "initial_npcs": [{"template_id": "ghost"}], "items": [{"item_id": "missing_map"}]}},
            }),
            encoding="utf-8",
        )
        _definition, issues = validator.load_content_set(package)
        messages = [issue.message for issue in issues]
        self.assertTrue(any("missing NPC template 'ghost'" in message for message in messages))
        self.assertTrue(any("missing item 'missing_map'" in message for message in messages))

    def test_ruleset_cannot_contradict_manifest_capabilities(self) -> None:
        package = self._write_package(self._case_root())
        (package / "rules" / "ruleset.json").write_text(
            json.dumps({"systems": {"inventory": {"enabled": False}}}),
            encoding="utf-8",
        )
        _definition, issues = validator.load_content_set(package)
        self.assertTrue(any("conflicts with manifest capability 'inventory'" in issue.message for issue in issues))

    def test_valid_minimal_package_loads(self) -> None:
        definition, issues = validator.load_content_set(self._write_package(self._case_root()))
        self.assertFalse([issue for issue in issues if issue.severity == "error"])
        self.assertIsNotNone(definition)

    def test_missing_start_room_is_rejected(self) -> None:
        package = self._write_package(self._case_root(), room_id="elsewhere")
        _definition, issues = validator.load_content_set(package)
        self.assertTrue(any("start.room_id 'square'" in issue.message for issue in issues))

    def test_duplicate_capabilities_are_rejected(self) -> None:
        package = self._write_package(self._case_root())
        manifest_path = package / validator.CONTENT_SET_MANIFEST_NAME
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["capabilities"].append("dialogue")
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        _definition, issues = validator.load_content_set(package)
        self.assertTrue(any("must be unique" in issue.message for issue in issues))


class TestContentSetValidatorMain(unittest.TestCase):
    def test_valid_content_set_prints_success_and_does_not_exit(self) -> None:
        argv = ["content_set_validator.py", str(REPO_ROOT / "content_sets" / "fantasy_frontier")]
        buf = io.StringIO()
        with patch.object(sys, "argv", argv), redirect_stdout(buf):
            validator.main()  # must not raise
        self.assertIn("is valid", buf.getvalue())

    def test_invalid_content_set_exits_one(self) -> None:
        argv = ["content_set_validator.py", str(REPO_ROOT / "tmp" / f"no_such_content_set_{uuid.uuid4().hex}")]
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                validator.main()
        self.assertEqual(1, cm.exception.code)


if __name__ == "__main__":
    unittest.main()
