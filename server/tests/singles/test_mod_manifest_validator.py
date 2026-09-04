import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import mod_manifest_validator as mmv
from engine.core.plugin_manager import validate_plugin_manifest


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


if __name__ == "__main__":
    unittest.main()
