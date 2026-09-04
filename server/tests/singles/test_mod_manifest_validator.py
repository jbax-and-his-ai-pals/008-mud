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

from toolkit import mod_manifest_validator as mmv
from engine.core.plugin_manager import validate_plugin_manifest

VALID_MANIFEST = {
    "plugin_id": "sample_mod",
    "name": "Sample Mod",
    "version": "1.0.0",
    "manifest_schema_version": "1",
    "engine_api_min": "1.0",
    "engine_api_max": "1.0",
    "capabilities": ["command_registration"],
}


class TestModManifestValidator(unittest.TestCase):
    def test_manifest_payload_validation_passes(self) -> None:
        payload = {
            "plugin_id": "sample_mod",
            "name": "Sample Mod",
            "version": "1.0.0",
            "manifest_schema_version": "1",
            "engine_api_min": "1.0",
            "engine_api_max": "1.0",
            "capabilities": ["command_registration"],
        }
        issues = mmv.validate_manifest(payload, "sample")
        self.assertEqual([], [i for i in issues if i.severity == "error"])

    def test_manifest_payload_validation_rejects_unknown_capability(self) -> None:
        payload = {
            "plugin_id": "sample_mod",
            "name": "Sample Mod",
            "version": "1.0.0",
            "manifest_schema_version": "1",
            "engine_api_min": "1.0",
            "engine_api_max": "1.0",
            "capabilities": ["super_user_mode"],
        }
        issues = mmv.validate_manifest(payload, "sample")
        self.assertTrue(any(i.severity == "error" for i in issues))

    def test_plugin_manager_manifest_validation_guard(self) -> None:
        manifest = {
            "plugin_id": "bad_mod",
            "name": "Bad Mod",
            "version": "1.0.0",
            "manifest_schema_version": "1",
            "engine_api_min": "2.0",
            "engine_api_max": "2.1",
            "capabilities": ["command_registration"],
        }
        errors = validate_plugin_manifest(manifest)
        self.assertTrue(any("outside plugin supported range" in e for e in errors))

    def test_non_dict_payload_is_a_single_error(self) -> None:
        issues = mmv.validate_manifest(["not", "a", "dict"], "sample")
        self.assertEqual(1, len(issues))
        self.assertEqual("error", issues[0].severity)

    def test_missing_required_string_fields_are_reported(self) -> None:
        issues = mmv.validate_manifest({}, "sample")
        messages = [i.message for i in issues]
        for field in ("plugin_id", "name", "version", "manifest_schema_version", "engine_api_min", "engine_api_max"):
            self.assertTrue(any(field in m for m in messages), f"expected an issue mentioning '{field}'")

    def test_invalid_plugin_id_pattern_is_rejected(self) -> None:
        payload = dict(VALID_MANIFEST, plugin_id="Not Valid!")
        issues = mmv.validate_manifest(payload, "sample")
        self.assertTrue(any("plugin_id must match" in i.message for i in issues))

    def test_unsupported_schema_version_is_rejected(self) -> None:
        payload = dict(VALID_MANIFEST, manifest_schema_version="99")
        issues = mmv.validate_manifest(payload, "sample")
        self.assertTrue(any("unsupported manifest_schema_version" in i.message for i in issues))

    def test_non_numeric_engine_api_bounds_are_rejected(self) -> None:
        payload = dict(VALID_MANIFEST, engine_api_min="abc")
        issues = mmv.validate_manifest(payload, "sample")
        self.assertTrue(any("dotted numeric versions" in i.message for i in issues))

    def test_engine_api_min_greater_than_max_is_rejected(self) -> None:
        payload = dict(VALID_MANIFEST, engine_api_min="2.0", engine_api_max="1.0")
        issues = mmv.validate_manifest(payload, "sample")
        self.assertTrue(any("must be <= engine_api_max" in i.message for i in issues))

    def test_capabilities_must_be_a_list(self) -> None:
        payload = dict(VALID_MANIFEST, capabilities="command_registration")
        issues = mmv.validate_manifest(payload, "sample")
        self.assertTrue(any("capabilities must be an array" in i.message for i in issues))

    def test_empty_capability_string_is_rejected(self) -> None:
        payload = dict(VALID_MANIFEST, capabilities=["   "])
        issues = mmv.validate_manifest(payload, "sample")
        self.assertTrue(any("non-empty strings" in i.message for i in issues))

    def test_validate_manifest_file_reports_parse_errors(self) -> None:
        root = self._case_root()
        bad = root / "manifest.json"
        bad.write_text("{not valid", encoding="utf-8")
        issues = mmv.validate_manifest_file(bad)
        self.assertEqual(1, len(issues))
        self.assertIn("failed to parse JSON", issues[0].message)

    def _case_root(self) -> Path:
        root = Path("tmp") / f"mod_manifest_test_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def test_validate_mod_roots_scans_nested_manifests_across_multiple_roots(self) -> None:
        root_a = self._case_root()
        root_b = self._case_root()
        (root_a / "mod_one").mkdir()
        (root_a / "mod_one" / "manifest.json").write_text(json.dumps(VALID_MANIFEST), encoding="utf-8")
        (root_b / "mod_two").mkdir()
        (root_b / "mod_two" / "manifest.json").write_text(
            json.dumps(dict(VALID_MANIFEST, plugin_id="broken id!")), encoding="utf-8"
        )
        missing_root = root_a / "does_not_exist"

        with redirect_stdout(io.StringIO()):
            checked, errors = mmv.validate_mod_roots([root_a, root_b, missing_root])
        self.assertEqual(2, checked)
        self.assertEqual(1, errors)


class TestModManifestValidatorMain(unittest.TestCase):
    def _case_root(self) -> Path:
        root = Path("tmp") / f"mod_manifest_main_test_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _run_main(self, argv: list) -> int:
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                mmv.main()
        return cm.exception.code

    def test_clean_roots_exit_zero(self) -> None:
        root = self._case_root()
        (root / "mod_one").mkdir()
        (root / "mod_one" / "manifest.json").write_text(json.dumps(VALID_MANIFEST), encoding="utf-8")
        code = self._run_main(["mod_manifest_validator.py", "--roots", str(root)])
        self.assertEqual(0, code)

    def test_invalid_manifest_exits_one(self) -> None:
        root = self._case_root()
        (root / "mod_one").mkdir()
        (root / "mod_one" / "manifest.json").write_text(
            json.dumps(dict(VALID_MANIFEST, capabilities=["not_a_real_capability"])), encoding="utf-8"
        )
        code = self._run_main(["mod_manifest_validator.py", "--roots", str(root)])
        self.assertEqual(1, code)

    def test_no_manifests_found_exits_zero(self) -> None:
        root = self._case_root()
        code = self._run_main(["mod_manifest_validator.py", "--roots", str(root)])
        self.assertEqual(0, code)


if __name__ == "__main__":
    unittest.main()
