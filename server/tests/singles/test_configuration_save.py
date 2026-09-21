"""Configuration applies use the engine's verdict and never truncate originals."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from toolkit.configuration_save import save_configuration
import run_editor_checks


class ConfigurationSaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "modern_capsule"
        shutil.copytree(REPO / "content_sets/modern_capsule", self.root,
                        ignore=shutil.ignore_patterns("editor", "*.bak"))
        self.path = self.root / "rules/ruleset.json"
        self.before = self.path.read_bytes()
        self.expected = hashlib.sha256(self.before).hexdigest()
        self.draft = json.loads(self.before)

    def test_noop_preserves_bytes(self):
        self.assertTrue(save_configuration(self.path, self.draft, self.expected)["unchanged"])
        self.assertEqual(self.before, self.path.read_bytes())
        self.assertFalse(self.path.with_suffix(".json.bak").exists())

    def test_engine_refusal_preserves_file(self):
        self.draft["systems"]["combat"]["enabled"] = True
        result = save_configuration(self.path, self.draft, self.expected)
        self.assertFalse(result["ok"], result)
        self.assertIn("combat", result["error"])
        self.assertEqual(self.before, self.path.read_bytes())

    def test_edit_is_validated_saved_and_backed_up(self):
        self.draft["ruleset_id"] = "edited_modern"
        result = save_configuration(self.path, self.draft, self.expected)
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.draft, json.loads(self.path.read_bytes()))
        self.assertEqual(self.before, self.path.with_suffix(".json.bak").read_bytes())

    def test_external_change_is_not_overwritten(self):
        changed = self.before + b"\n"
        self.path.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "outside this dialog"):
            save_configuration(self.path, self.draft, self.expected)
        self.assertEqual(changed, self.path.read_bytes())

    def test_failed_replace_preserves_original(self):
        self.draft["ruleset_id"] = "edited_modern"
        with patch("toolkit.configuration_save.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaisesRegex(OSError, "disk failure"):
                save_configuration(self.path, self.draft, self.expected)
        self.assertEqual(self.before, self.path.read_bytes())
        self.assertEqual([], list(self.path.parent.glob("*.tmp")))

    def test_validator_failure_does_not_write(self):
        self.draft["ruleset_id"] = "edited_modern"
        with patch("toolkit.configuration_save.validate_content_set", side_effect=RuntimeError("unavailable")):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                save_configuration(self.path, self.draft, self.expected)
        self.assertEqual(self.before, self.path.read_bytes())

    def test_change_during_validation_does_not_write(self):
        self.draft["ruleset_id"] = "edited_modern"
        def mutate(_root):
            self.path.write_bytes(self.before + b"\n")
            return []
        with patch("toolkit.configuration_save.validate_content_set", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "during validation"):
                save_configuration(self.path, self.draft, self.expected)
        self.assertEqual(self.before + b"\n", self.path.read_bytes())

    def test_external_manifest_path_is_refused(self):
        manifest_path = self.root / "content_set.manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        manifest["paths"]["content_root"] = "../outside"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.draft["ruleset_id"] = "edited_modern"
        with self.assertRaisesRegex(ValueError, "outside this content set"):
            save_configuration(self.path, self.draft, self.expected)
        self.assertEqual(self.before, self.path.read_bytes())


class EditorRunnerTests(unittest.TestCase):
    def test_script_error_is_failure_even_when_godot_exits_zero(self):
        completed = subprocess.CompletedProcess([], 0, "OK first check\n", "SCRIPT ERROR: Invalid call\n")
        with patch("run_editor_checks.subprocess.run", return_value=completed):
            ok, detail = run_editor_checks.run_check("godot", Path("probe.gd"))
        self.assertFalse(ok)
        self.assertIn("SCRIPT ERROR", detail)

    def test_hung_check_is_failure(self):
        with patch("run_editor_checks.subprocess.run", side_effect=subprocess.TimeoutExpired("godot", 120)):
            ok, detail = run_editor_checks.run_check("godot", Path("probe.gd"))
        self.assertFalse(ok)
        self.assertIn("Timed out", detail)


if __name__ == "__main__":
    unittest.main()
