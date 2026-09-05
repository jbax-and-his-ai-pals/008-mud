# tests/singles/test_content_set_direct.py
"""Coverage for engine/server/content_set.py's validation error paths that
the existing content-set validator tests (which mostly exercise the happy
path plus a handful of specific rejections) don't reach: malformed ruleset
systems, _parse_version/_load_json edge cases, region/room/exit/npc/item
structural errors, unreachable-room BFS edge cases, manifest field errors,
engine-API-range errors, paths/opening/capabilities/start structural errors,
and the validate_content_set() wrapper."""

import json
import shutil
import unittest
import uuid
from pathlib import Path

from engine.server import content_set as cs

REPO_ROOT = Path(__file__).resolve().parents[3]


class ContentSetDirectTestBase(unittest.TestCase):
    def _case_root(self) -> Path:
        root = REPO_ROOT / "tmp" / f"content_set_direct_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _write_package(self, root: Path, *, room_id: str = "square", manifest_overrides: dict | None = None) -> Path:
        package = root / "sample_game"
        content_root = package / "data"
        for directory in ("regions", "items", "npcs"):
            (content_root / directory).mkdir(parents=True, exist_ok=True)
        (content_root / "regions" / "town.json").write_text(
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
                "content_root": "data",
                "ruleset": "rules/ruleset.json",
                "presentation": "presentation/default.json",
            },
            "start": {"scenario_id": "start", "region_id": "town", "room_id": "square"},
            "capabilities": ["inventory", "dialogue"],
        }
        if manifest_overrides:
            manifest.update(manifest_overrides)
        (package / cs.CONTENT_SET_MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
        return package

    def _region_path(self, package: Path) -> Path:
        return package / "data" / "regions" / "town.json"

    def _write_region(self, package: Path, payload: dict) -> None:
        self._region_path(package).write_text(json.dumps(payload), encoding="utf-8")


class TestParseVersionAndRuntimeRange(unittest.TestCase):
    def test_empty_string_returns_none(self):
        self.assertIsNone(cs._parse_version(""))

    def test_non_digit_component_returns_none(self):
        self.assertIsNone(cs._parse_version("1.x.0"))

    def test_valid_version_parses(self):
        self.assertEqual((1, 2), cs._parse_version("1.2"))

    def test_runtime_in_range_true(self):
        self.assertTrue(cs._runtime_in_range("1.5", "1.0", "2.0"))

    def test_runtime_out_of_range_false(self):
        self.assertFalse(cs._runtime_in_range("3.0", "1.0", "2.0"))

    def test_runtime_in_range_with_unparseable_bound_false(self):
        self.assertFalse(cs._runtime_in_range("1.0", "abc", "2.0"))


class TestLoadJson(unittest.TestCase):
    def test_directory_path_raises_oserror_branch(self):
        root = Path(REPO_ROOT / "tmp" / f"load_json_dir_{uuid.uuid4().hex}")
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        issues: list = []
        result = cs._load_json(root, issues, "test label")
        self.assertIsNone(result)
        self.assertTrue(any("unable to read" in i.message for i in issues))

    def test_malformed_json_raises_decode_error_branch(self):
        root = Path(REPO_ROOT / "tmp" / f"load_json_bad_{uuid.uuid4().hex}")
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        bad_file = root / "bad.json"
        bad_file.write_text("{not valid json", encoding="utf-8")
        issues: list = []
        result = cs._load_json(bad_file, issues, "test label")
        self.assertIsNone(result)
        self.assertTrue(any("invalid test label JSON" in i.message for i in issues))


class TestLoadDefinitionIds(unittest.TestCase):
    def test_non_dict_payload_is_skipped(self):
        root = Path(REPO_ROOT / "tmp" / f"defs_{uuid.uuid4().hex}")
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        (root / "list_payload.json").write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
        issues: list = []
        ids = cs._load_definition_ids(root, "label", issues)
        self.assertEqual(set(), ids)

    def test_underscore_prefixed_entries_are_skipped(self):
        root = Path(REPO_ROOT / "tmp" / f"defs2_{uuid.uuid4().hex}")
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        (root / "defs.json").write_text(
            json.dumps({"_comment": {"note": "skip me"}, "real_item": {"name": "Real"}}), encoding="utf-8",
        )
        issues: list = []
        ids = cs._load_definition_ids(root, "label", issues)
        self.assertEqual({"real_item"}, ids)


class TestBuildGameContractErrors(ContentSetDirectTestBase):
    def test_ruleset_systems_not_dict_reports_error(self):
        package = self._write_package(self._case_root())
        (package / "rules" / "ruleset.json").write_text(json.dumps({"systems": "not_a_dict"}), encoding="utf-8")
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("ruleset.systems must be an object" in i.message for i in issues))

    def test_system_config_missing_enabled_key_is_skipped(self):
        package = self._write_package(self._case_root())
        (package / "rules" / "ruleset.json").write_text(
            json.dumps({"systems": {"inventory": {"some_other_key": True}}}), encoding="utf-8",
        )
        _definition, issues = cs.load_content_set(package)
        self.assertFalse(any("enabled must be a boolean" in i.message for i in issues))

    def test_system_enabled_not_boolean_reports_error(self):
        package = self._write_package(self._case_root())
        (package / "rules" / "ruleset.json").write_text(
            json.dumps({"systems": {"inventory": {"enabled": "yes"}}}), encoding="utf-8",
        )
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("enabled must be a boolean" in i.message for i in issues))

    def test_progression_conflict_reports_error(self):
        package = self._write_package(self._case_root())
        (package / "rules" / "ruleset.json").write_text(
            json.dumps({"progression_model": "none", "systems": {"progression": {"enabled": True}}}),
            encoding="utf-8",
        )
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("progression_model" in i.message for i in issues))

    def test_unrecognized_explicit_system_is_carried_through(self):
        package = self._write_package(self._case_root())
        (package / "rules" / "ruleset.json").write_text(
            json.dumps({"systems": {"custom_extension": {"enabled": True}}}), encoding="utf-8",
        )
        definition, issues = cs.load_content_set(package)
        self.assertIsNotNone(definition)
        self.assertTrue(definition.game_contract.system_enabled("custom_extension"))


class TestManifestFieldErrors(ContentSetDirectTestBase):
    def test_manifest_top_level_not_object_reports_error(self):
        package = self._write_package(self._case_root())
        (package / cs.CONTENT_SET_MANIFEST_NAME).write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
        definition, issues = cs.load_content_set(package)
        self.assertIsNone(definition)
        self.assertTrue(any("must be a JSON object" in i.message for i in issues))

    def test_missing_required_string_field_reports_error(self):
        package = self._write_package(self._case_root(), manifest_overrides={"title": ""})
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("missing/invalid string field 'title'" in i.message for i in issues))

    def test_invalid_id_pattern_reports_error(self):
        package = self._write_package(self._case_root(), manifest_overrides={"id": "Not-Valid-ID"})
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("id must match" in i.message for i in issues))

    def test_unsupported_schema_version_reports_error(self):
        package = self._write_package(self._case_root(), manifest_overrides={"manifest_schema_version": "99"})
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("unsupported manifest_schema_version" in i.message for i in issues))

    def test_blank_engine_api_bounds_skip_range_validation(self):
        package = self._write_package(self._case_root(), manifest_overrides={"engine_api_min": "", "engine_api_max": ""})
        _definition, issues = cs.load_content_set(package)
        self.assertFalse(any("dotted numeric" in i.message or "outside supported range" in i.message for i in issues))

    def test_non_numeric_engine_api_bounds_reports_error(self):
        package = self._write_package(self._case_root(), manifest_overrides={"engine_api_min": "abc"})
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("dotted numeric versions" in i.message for i in issues))

    def test_engine_api_min_greater_than_max_reports_error(self):
        package = self._write_package(
            self._case_root(), manifest_overrides={"engine_api_min": "2.0", "engine_api_max": "1.0"},
        )
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("must be <= engine_api_max" in i.message for i in issues))

    def test_runtime_outside_supported_range_reports_error(self):
        package = self._write_package(
            self._case_root(), manifest_overrides={"engine_api_min": "0.1", "engine_api_max": "0.5"},
        )
        _definition, issues = cs.load_content_set(package, runtime_api="1.0")
        self.assertTrue(any("outside supported range" in i.message for i in issues))

    def test_paths_not_object_reports_error_and_returns_none(self):
        package = self._write_package(self._case_root(), manifest_overrides={"paths": "not_an_object"})
        definition, issues = cs.load_content_set(package)
        self.assertIsNone(definition)
        self.assertTrue(any("paths must be an object" in i.message for i in issues))

    def test_blank_path_entry_reports_error(self):
        package = self._write_package(self._case_root())
        manifest_path = package / cs.CONTENT_SET_MANIFEST_NAME
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["paths"]["ruleset"] = ""
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("paths.ruleset must be a non-empty string" in i.message for i in issues))

    def test_blank_opening_path_reports_error(self):
        package = self._write_package(self._case_root())
        manifest_path = package / cs.CONTENT_SET_MANIFEST_NAME
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["paths"]["opening"] = "   "
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("paths.opening must be a non-empty string" in i.message for i in issues))

    def test_opening_scenario_load_failure_leaves_opening_payload_empty(self):
        package = self._write_package(self._case_root())
        manifest_path = package / cs.CONTENT_SET_MANIFEST_NAME
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["paths"]["opening"] = "opening.json"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        (package / "opening.json").write_text("{not valid json", encoding="utf-8")
        definition, issues = cs.load_content_set(package)
        self.assertIsNone(definition)
        self.assertTrue(any("invalid opening scenario JSON" in i.message for i in issues))

    def test_opening_scenario_not_object_reports_error(self):
        package = self._write_package(self._case_root())
        manifest_path = package / cs.CONTENT_SET_MANIFEST_NAME
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["paths"]["opening"] = "opening.json"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        (package / "opening.json").write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("opening scenario must be a JSON object" in i.message for i in issues))

    def test_opening_scenario_blank_scenario_id_reports_error(self):
        package = self._write_package(self._case_root())
        manifest_path = package / cs.CONTENT_SET_MANIFEST_NAME
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["paths"]["opening"] = "opening.json"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        (package / "opening.json").write_text(json.dumps({"scenario_id": ""}), encoding="utf-8")
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("requires a non-empty 'scenario_id'" in i.message for i in issues))

    def test_opening_scenario_id_mismatch_reports_error(self):
        package = self._write_package(self._case_root())
        manifest_path = package / cs.CONTENT_SET_MANIFEST_NAME
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["paths"]["opening"] = "opening.json"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        (package / "opening.json").write_text(json.dumps({"scenario_id": "not_start"}), encoding="utf-8")
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("must match start.scenario_id" in i.message for i in issues))

    def test_opening_scenario_matching_id_loads_successfully(self):
        package = self._write_package(self._case_root())
        manifest_path = package / cs.CONTENT_SET_MANIFEST_NAME
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["paths"]["opening"] = "opening.json"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        (package / "opening.json").write_text(json.dumps({"scenario_id": "start"}), encoding="utf-8")
        definition, issues = cs.load_content_set(package)
        self.assertFalse([i for i in issues if i.severity == "error"])
        self.assertEqual({"scenario_id": "start"}, definition.opening)

    def test_content_root_not_a_directory_reports_error(self):
        package = self._write_package(self._case_root())
        manifest_path = package / cs.CONTENT_SET_MANIFEST_NAME
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["paths"]["content_root"] = "does_not_exist_dir"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("does not resolve to a directory" in i.message for i in issues))

    def test_missing_required_data_directory_reports_error(self):
        package = self._write_package(self._case_root())
        shutil.rmtree(package / "data" / "npcs")
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("missing required data directory 'npcs'" in i.message for i in issues))

    def test_missing_content_root_key_skips_directory_checks(self):
        package = self._write_package(self._case_root())
        manifest_path = package / cs.CONTENT_SET_MANIFEST_NAME
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        del payload["paths"]["content_root"]
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        definition, issues = cs.load_content_set(package)
        self.assertIsNone(definition)  # still an error (missing path), but no crash reaching content_root logic
        self.assertTrue(any("paths.content_root must be a non-empty string" in i.message for i in issues))

    def test_ruleset_not_object_reports_error(self):
        package = self._write_package(self._case_root())
        (package / "rules" / "ruleset.json").write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("ruleset must be a JSON object" in i.message for i in issues))

    def test_capabilities_not_list_reports_error(self):
        package = self._write_package(self._case_root(), manifest_overrides={"capabilities": "inventory"})
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("capabilities must be an array" in i.message for i in issues))

    def test_blank_capability_entry_reports_error(self):
        package = self._write_package(self._case_root(), manifest_overrides={"capabilities": ["inventory", "  "]})
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("capabilities entries must be non-empty strings" in i.message for i in issues))

    def test_start_not_object_reports_error(self):
        package = self._write_package(self._case_root(), manifest_overrides={"start": "not_an_object"})
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("start must be an object" in i.message for i in issues))

    def test_start_field_blank_reports_error(self):
        package = self._write_package(
            self._case_root(),
            manifest_overrides={"start": {"scenario_id": "start", "region_id": "", "room_id": "square"}},
        )
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("start.region_id must be a non-empty string" in i.message for i in issues))

    def test_missing_start_ids_skips_start_room_and_world_validation(self):
        package = self._write_package(
            self._case_root(),
            manifest_overrides={"start": {"scenario_id": "start", "region_id": "", "room_id": ""}},
        )
        definition, issues = cs.load_content_set(package)
        self.assertIsNone(definition)
        # Still reports the blank-field errors, but doesn't crash trying to
        # validate a start room / authored world with empty ids.
        self.assertTrue(any("start.region_id" in i.message for i in issues))

    def test_start_region_file_not_a_dict_skips_room_check(self):
        package = self._write_package(self._case_root())
        (package / "data" / "regions" / "town.json").write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
        # Not a dict -> the isinstance(region_payload, dict) guard skips the
        # room-membership check without raising; _validate_authored_world's
        # own region loader also just skips a non-dict region payload.
        definition, issues = cs.load_content_set(package)  # must not raise
        self.assertIsNotNone(definition)


class TestAuthoredWorldValidation(ContentSetDirectTestBase):
    def test_region_payload_not_dict_is_skipped(self):
        package = self._write_package(self._case_root())
        (package / "data" / "regions" / "extra.json").write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
        definition, issues = cs.load_content_set(package)
        self.assertIsNotNone(definition)

    def test_region_generation_theme_file_is_skipped(self):
        package = self._write_package(self._case_root())
        (package / "data" / "regions" / "theme.json").write_text(json.dumps({"themes": {"a": {}}}), encoding="utf-8")
        definition, issues = cs.load_content_set(package)
        self.assertIsNotNone(definition)

    def test_region_missing_region_id_reports_error(self):
        package = self._write_package(self._case_root())
        (package / "data" / "regions" / "extra.json").write_text(
            json.dumps({"rooms": {"a_room": {}}}), encoding="utf-8",
        )
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("requires a non-empty region_id" in i.message for i in issues))

    def test_region_missing_rooms_object_reports_error(self):
        package = self._write_package(self._case_root())
        (package / "data" / "regions" / "extra.json").write_text(
            json.dumps({"region_id": "extra_region"}), encoding="utf-8",
        )
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("requires a rooms object" in i.message for i in issues))

    def test_duplicate_region_id_reports_error(self):
        package = self._write_package(self._case_root())
        (package / "data" / "regions" / "town_dup.json").write_text(
            json.dumps({"region_id": "town", "rooms": {"another": {}}}), encoding="utf-8",
        )
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("duplicate region_id 'town'" in i.message for i in issues))

    def test_room_not_object_reports_error(self):
        package = self._write_package(self._case_root())
        self._write_region(package, {"region_id": "town", "rooms": {"square": "not_an_object"}})
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("must be an object" in i.message for i in issues))

    def test_exits_not_object_reports_error(self):
        package = self._write_package(self._case_root())
        self._write_region(package, {"region_id": "town", "rooms": {"square": {"exits": "not_an_object"}}})
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("exits must be an object" in i.message for i in issues))

    def test_exit_destination_not_string_reports_error(self):
        package = self._write_package(self._case_root())
        self._write_region(package, {"region_id": "town", "rooms": {"square": {"exits": {"north": 123}}}})
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("must name a destination room" in i.message for i in issues))

    def test_invalid_initial_npcs_entry_reports_error(self):
        package = self._write_package(self._case_root())
        self._write_region(package, {"region_id": "town", "rooms": {"square": {"initial_npcs": ["not_a_dict"]}}})
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("invalid initial_npcs entry" in i.message for i in issues))

    def test_invalid_items_entry_reports_error(self):
        package = self._write_package(self._case_root())
        self._write_region(package, {"region_id": "town", "rooms": {"square": {"items": ["not_a_dict"]}}})
        _definition, issues = cs.load_content_set(package)
        self.assertTrue(any("invalid items entry" in i.message for i in issues))

    def test_unreachable_room_with_non_string_exit_is_handled_gracefully(self):
        package = self._write_package(self._case_root())
        self._write_region(package, {
            "region_id": "town",
            "rooms": {
                "square": {"exits": {"east": "town:annex"}},
                "annex": {"exits": {"weird": 123}},
            },
        })
        # "annex" is reachable via a valid exit from "square", and itself has
        # a malformed (non-string) exit destination that the BFS must skip
        # over gracefully rather than crashing.
        definition, issues = cs.load_content_set(package)
        self.assertIsNone(definition)  # the malformed exit is still a structural error
        self.assertTrue(any("must name a destination room" in i.message for i in issues))

    def test_unreachable_room_reports_warning(self):
        package = self._write_package(self._case_root())
        self._write_region(package, {
            "region_id": "town",
            "rooms": {
                "square": {},
                "isolated": {},
            },
        })
        definition, issues = cs.load_content_set(package)
        self.assertIsNotNone(definition)
        self.assertTrue(any(
            i.severity == "warning" and "isolated" in i.message and "not reachable" in i.message for i in issues
        ))


class TestValidateContentSetWrapper(ContentSetDirectTestBase):
    def test_returns_only_issues_for_valid_package(self):
        package = self._write_package(self._case_root())
        issues = cs.validate_content_set(package)
        self.assertFalse([i for i in issues if i.severity == "error"])

    def test_returns_issues_for_invalid_package(self):
        package = self._write_package(self._case_root(), manifest_overrides={"title": ""})
        issues = cs.validate_content_set(package)
        self.assertTrue(any(i.severity == "error" for i in issues))


if __name__ == "__main__":
    unittest.main()
