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
import toolkit.configuration_transaction as configuration_transaction
from toolkit.configuration_transaction import save_configuration_pair
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

    def _field_path(self) -> Path:
        path = self.root / "data/world/field_interactions.json"
        self.assertFalse(path.exists(), "modern_capsule ships no field interactions")
        return path

    def test_an_absent_optional_file_is_created_after_validation(self):
        path = self._field_path()
        config = {"default_field_id": "static", "polarities": {"static": "negative"}}
        result = save_configuration(path, config, "absent")
        self.assertTrue(result["ok"], result)
        self.assertEqual(config, json.loads(path.read_bytes()))
        self.assertFalse(path.with_name(path.name + ".bak").exists(), "there was nothing to back up")

    def test_an_invalid_new_file_is_not_created(self):
        path = self._field_path()
        result = save_configuration(path, {"polarities": {"static": "bad"}}, "absent")
        self.assertFalse(result["ok"], result)
        self.assertIn("polarities.static", result["error"])
        self.assertFalse(path.exists())

    def test_a_file_that_appeared_meanwhile_is_not_overwritten(self):
        path = self._field_path()
        path.parent.mkdir(parents=True)
        path.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            save_configuration(path, {"polarities": {}}, "absent")
        self.assertEqual("{}", path.read_text(encoding="utf-8"))

    def test_a_required_file_is_never_created(self):
        self.path.unlink()
        with self.assertRaises(ValueError):
            save_configuration(self.path, self.draft, "absent")
        self.assertFalse(self.path.exists())

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
        self.draft["label"] = "Edited modern rules"
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
        self.draft["label"] = "Edited modern rules"
        with patch("toolkit.configuration_save.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaisesRegex(OSError, "disk failure"):
                save_configuration(self.path, self.draft, self.expected)
        self.assertEqual(self.before, self.path.read_bytes())
        self.assertEqual([], list(self.path.parent.glob("*.tmp")))

    def test_validator_failure_does_not_write(self):
        self.draft["label"] = "Edited modern rules"
        with patch("toolkit.configuration_save.validate_content_set", side_effect=RuntimeError("unavailable")):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                save_configuration(self.path, self.draft, self.expected)
        self.assertEqual(self.before, self.path.read_bytes())

    def test_change_during_validation_does_not_write(self):
        self.draft["label"] = "Edited modern rules"
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
        self.draft["label"] = "Edited modern rules"
        with self.assertRaisesRegex(ValueError, "outside this content set"):
            save_configuration(self.path, self.draft, self.expected)
        self.assertEqual(self.before, self.path.read_bytes())


class ManifestSaveTests(unittest.TestCase):
    """The manifest is configuration too: batch 6B's "change the start or a
    capability after creation" needs the same staged engine verdict the other
    configuration files get."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "orbital_salvage"
        shutil.copytree(REPO / "content_sets/orbital_salvage", self.root,
                        ignore=shutil.ignore_patterns("editor", "*.bak"))
        self.path = self.root / "content_set.manifest.json"
        self.before = self.path.read_bytes()
        self.expected = hashlib.sha256(self.before).hexdigest()
        self.draft = json.loads(self.before)

    def test_the_manifest_is_a_supported_configuration_file(self):
        self.draft["title"] = "Orbital Salvage (edited)"
        result = save_configuration(self.path, self.draft, self.expected)
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.draft, json.loads(self.path.read_bytes()))
        self.assertEqual(self.before, self.path.with_name(self.path.name + ".bak").read_bytes())

    def test_moving_the_start_is_validated_and_saved(self):
        self.draft["start"]["room_id"] = "cargo_bay"
        result = save_configuration(self.path, self.draft, self.expected)
        # Whether that room exists is the engine's call, not this test's: what
        # matters is that the verdict came from the staged set either way.
        if result["ok"]:
            self.assertEqual("cargo_bay", json.loads(self.path.read_bytes())["start"]["room_id"])
        else:
            self.assertIn("cargo_bay", result["error"])
            self.assertEqual(self.before, self.path.read_bytes())

    def test_a_capability_that_contradicts_the_ruleset_is_refused(self):
        # `combat` is enabled in this set's ruleset; dropping the capability alone
        # is the contradiction the engine reports.
        self.draft["capabilities"] = [c for c in self.draft["capabilities"] if c != "combat"]
        result = save_configuration(self.path, self.draft, self.expected)
        self.assertFalse(result["ok"], result)
        self.assertIn("combat", result["error"])
        self.assertEqual(self.before, self.path.read_bytes())

    def test_a_draft_that_moves_its_own_paths_out_is_refused(self):
        self.draft["paths"]["content_root"] = "../outside"
        with self.assertRaisesRegex(ValueError, "may not point outside"):
            save_configuration(self.path, self.draft, self.expected)
        self.assertEqual(self.before, self.path.read_bytes())

    def test_paths_must_stay_an_object(self):
        self.draft["paths"] = ["data"]
        with self.assertRaisesRegex(ValueError, "paths must be an object"):
            save_configuration(self.path, self.draft, self.expected)
        self.assertEqual(self.before, self.path.read_bytes())


class CoordinatedConfigurationSaveTests(unittest.TestCase):
    """Capabilities and explicit ruleset systems must change as one decision."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "orbital_salvage"
        shutil.copytree(REPO / "content_sets/orbital_salvage", self.root,
                        ignore=shutil.ignore_patterns("editor", "*.bak"))
        self.manifest_path = self.root / "content_set.manifest.json"
        self.ruleset_path = self.root / "rules/ruleset.json"
        self.manifest_before = self.manifest_path.read_bytes()
        self.ruleset_before = self.ruleset_path.read_bytes()
        self.manifest = json.loads(self.manifest_before)
        self.ruleset = json.loads(self.ruleset_before)
        self.manifest["capabilities"].remove("combat")
        self.ruleset["systems"]["combat"]["enabled"] = False

    def _save(self):
        return save_configuration_pair(
            self.manifest_path, self.manifest, hashlib.sha256(self.manifest_before).hexdigest(),
            self.ruleset_path, self.ruleset, hashlib.sha256(self.ruleset_before).hexdigest(),
        )

    def test_capability_and_ruleset_save_together(self):
        result = self._save()
        self.assertTrue(result["ok"], result)
        self.assertNotIn("combat", json.loads(self.manifest_path.read_bytes())["capabilities"])
        self.assertFalse(json.loads(self.ruleset_path.read_bytes())["systems"]["combat"]["enabled"])
        self.assertEqual(self.manifest_before, self.manifest_path.with_name(self.manifest_path.name + ".bak").read_bytes())
        self.assertEqual(self.ruleset_before, self.ruleset_path.with_name(self.ruleset_path.name + ".bak").read_bytes())

    def test_engine_refusal_leaves_both_files_unchanged(self):
        # A manifest capability and `systems` must still agree after the pair is
        # staged; a coordinated write does not weaken the engine's verdict.
        self.ruleset["systems"]["combat"]["enabled"] = True
        result = self._save()
        self.assertFalse(result["ok"], result)
        self.assertEqual(self.manifest_before, self.manifest_path.read_bytes())
        self.assertEqual(self.ruleset_before, self.ruleset_path.read_bytes())

    def test_second_replace_failure_rolls_back_first_file(self):
        real_atomic = configuration_transaction._atomic_bytes

        def fail_only_second_destination(path, data):
            if Path(path) == self.ruleset_path and data != self.ruleset_before:
                raise OSError("second destination unavailable")
            return real_atomic(path, data)

        with patch("toolkit.configuration_transaction._atomic_bytes", side_effect=fail_only_second_destination):
            with self.assertRaisesRegex(OSError, "second destination unavailable"):
                self._save()
        self.assertEqual(self.manifest_before, self.manifest_path.read_bytes())
        self.assertEqual(self.ruleset_before, self.ruleset_path.read_bytes())


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
