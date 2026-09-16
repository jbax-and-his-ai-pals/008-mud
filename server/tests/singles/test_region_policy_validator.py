# tests/singles/test_region_policy_validator.py
"""Coverage for engine/server/content_set.py's validate_region_policy() --
the standalone, no-manifest-required region-authoring policy check added
for the Godot world editor's fast "validate before it's wired into the
world" feedback, and its toolkit/region_policy_validator.py CLI wrapper."""

import json
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

from engine.server import content_set as cs

REPO_ROOT = Path(__file__).resolve().parents[3]


class TestValidateRegionPolicy(unittest.TestCase):
    def _case_root(self) -> Path:
        root = REPO_ROOT / "tmp" / f"region_policy_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _ruleset(self, root: Path, regions_config: dict) -> Path:
        ruleset_path = root / "ruleset.json"
        ruleset_path.write_text(json.dumps({"world": {"regions": regions_config}}), encoding="utf-8")
        return ruleset_path

    def _region(self, content_root: Path, region_id: str, properties: dict, rooms: dict | None = None) -> None:
        (content_root / "regions").mkdir(parents=True, exist_ok=True)
        (content_root / "regions" / f"{region_id}.json").write_text(
            json.dumps({"region_id": region_id, "properties": properties, "rooms": rooms or {}}),
            encoding="utf-8",
        )

    def test_passes_against_real_fantasy_frontier_content(self):
        issues = cs.validate_region_policy(
            REPO_ROOT / "content_sets" / "fantasy_frontier" / "data",
            REPO_ROOT / "content_sets" / "fantasy_frontier" / "rules" / "ruleset.json",
        )
        self.assertFalse([i for i in issues if i.severity == "error"])

    def test_missing_classification_and_level_band_are_reported(self):
        root = self._case_root()
        ruleset_path = self._ruleset(root, {
            "require_level_bands": True, "require_classification": True,
            "biomes": ["forest"], "region_types": ["wilderness"],
        })
        self._region(root, "bare", {})
        issues = cs.validate_region_policy(root, ruleset_path)
        messages = {i.message for i in issues}
        self.assertIn("region 'bare' requires properties.level_band", messages)
        self.assertIn("region 'bare' requires properties.biome", messages)
        self.assertIn("region 'bare' requires properties.region_type", messages)

    def test_biome_outside_vocabulary_is_reported(self):
        root = self._case_root()
        ruleset_path = self._ruleset(root, {
            "require_classification": True, "biomes": ["forest"], "region_types": ["wilderness"],
        })
        self._region(root, "odd", {"biome": "not_a_real_biome", "region_type": "wilderness"})
        issues = cs.validate_region_policy(root, ruleset_path)
        self.assertTrue(any("not in the ruleset vocabulary" in i.message for i in issues))

    def test_unknown_hazard_type_is_reported(self):
        root = self._case_root()
        ruleset_path = self._ruleset(root, {"require_hazard_coverage": True})
        (root / "combat").mkdir(parents=True, exist_ok=True)
        (root / "combat" / "elements.json").write_text(
            json.dumps({"hazards": {"mapping": {"poison_gas": "poison"}}}), encoding="utf-8",
        )
        self._region(root, "hazardous", {}, rooms={"room_a": {"properties": {"hazard_type": "not_real"}}})
        issues = cs.validate_region_policy(root, ruleset_path)
        self.assertTrue(any("unknown hazard_type" in i.message for i in issues))

    def test_valid_region_produces_no_issues(self):
        root = self._case_root()
        ruleset_path = self._ruleset(root, {
            "require_level_bands": True, "require_classification": True,
            "require_hazard_coverage": True, "biomes": ["forest"], "region_types": ["wilderness"],
        })
        (root / "combat").mkdir(parents=True, exist_ok=True)
        (root / "combat" / "elements.json").write_text(
            json.dumps({"hazards": {"mapping": {"poison_gas": "poison"}}}), encoding="utf-8",
        )
        self._region(
            root, "good",
            {"biome": "forest", "region_type": "wilderness", "level_band": {"min": 1, "max": 3}},
            rooms={"room_a": {"properties": {"hazard_type": "poison_gas", "hazard_damage": 5}}},
        )
        issues = cs.validate_region_policy(root, ruleset_path)
        self.assertEqual([], issues)

    def test_ruleset_only_flags_bad_json_is_reported(self):
        root = self._case_root()
        ruleset_path = root / "ruleset.json"
        ruleset_path.write_text("not json", encoding="utf-8")
        issues = cs.validate_region_policy(root, ruleset_path)
        self.assertTrue(any("invalid ruleset JSON" in i.message for i in issues))


class TestRegionPolicyValidatorCli(unittest.TestCase):
    def test_cli_reports_pass_for_real_content_via_json(self):
        result = subprocess.run(
            [
                sys.executable, str(REPO_ROOT / "toolkit" / "region_policy_validator.py"),
                str(REPO_ROOT / "content_sets" / "fantasy_frontier" / "data"),
                "--ruleset", str(REPO_ROOT / "content_sets" / "fantasy_frontier" / "rules" / "ruleset.json"),
                "--json",
            ],
            capture_output=True, text=True, cwd=str(REPO_ROOT / "server"),
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertTrue(payload["ok"])
        self.assertEqual(0, payload["error_count"])


if __name__ == "__main__":
    unittest.main()
