import io
import json
import shutil
import sys
import tempfile
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
        content_root = package / "data"
        for directory in ("regions", "items", "npcs", "quests", "campaigns"):
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
        (package / validator.CONTENT_SET_MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
        return package

    def test_fantasy_frontier_package_is_valid(self) -> None:
        definition, issues = validator.load_content_set(REPO_ROOT / "content_sets" / "fantasy_frontier")
        self.assertFalse([issue for issue in issues if issue.severity == "error"])
        self.assertIsNotNone(definition)
        assert definition is not None
        self.assertEqual("fantasy_frontier", definition.content_set_id)
        self.assertEqual(REPO_ROOT / "content_sets" / "fantasy_frontier" / "data", definition.content_root)
        self.assertEqual("town", definition.start_region_id)
        self.assertEqual("town_square", definition.start_room_id)
        self.assertTrue(definition.game_contract.system_enabled("magic"))
        self.assertTrue(definition.game_contract.system_enabled("abilities"))
        self.assertTrue(definition.game_contract.system_enabled("progression"))
        # The status field says "this game shows an ability pool"; what the pool
        # is called travels in the payload, from the content set's `resources`.
        self.assertIn("ability_resource", definition.game_contract.status_fields)

    def test_modern_capsule_package_is_semantically_valid(self) -> None:
        definition, issues = validator.load_content_set(REPO_ROOT / "content_sets" / "modern_capsule")
        self.assertFalse([issue for issue in issues if issue.severity == "error"])
        self.assertIsNotNone(definition)
        self.assertFalse(any("missing NPC template" in issue.message for issue in issues))

    def test_orbital_salvage_package_is_semantically_valid(self) -> None:
        """The sci-fi proof validates through the same gate as the fantasy set."""
        definition, issues = validator.load_content_set(REPO_ROOT / "content_sets" / "orbital_salvage")
        self.assertFalse([issue for issue in issues if issue.severity == "error"], issues)
        self.assertIsNotNone(definition)
        assert definition is not None
        # Abilities without magic: the capability is its own thing.
        self.assertTrue(definition.game_contract.system_enabled("abilities"))
        self.assertFalse(definition.game_contract.system_enabled("magic"))
        self.assertIn("ability_resource", definition.game_contract.status_fields)

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


class TestQuestStageObjectives(unittest.TestCase):
    """A stage nothing can satisfy is an error, not a silence.

    The world editor used to write stages as `{id, description, type: "KILL",
    target, count, next}` while the engine reads `stage.objective.type`; such a
    stage passed validation with zero errors and stalled the quest forever. The
    inspector writes the engine's schema now, and this is the engine declining the
    old shape by name.
    """

    def _package_with_stage(self, stage: dict) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        package = root / "content_set"
        (package / "data" / "quests").mkdir(parents=True)
        (package / "data" / "regions").mkdir(parents=True)
        (package / "data" / "items").mkdir(parents=True)
        (package / "data" / "npcs").mkdir(parents=True)
        (package / "rules").mkdir(parents=True)
        (package / validator.CONTENT_SET_MANIFEST_NAME).write_text(json.dumps({
            "id": "stage_probe", "title": "Stage Probe", "version": "0.1.0",
            "manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
            "paths": {"content_root": "data", "ruleset": "rules/ruleset.json"},
            "start": {"region_id": "town", "room_id": "square"},
            "capabilities": ["inventory", "quests"],
        }), encoding="utf-8")
        (package / "rules" / "ruleset.json").write_text(json.dumps({"ruleset_id": "probe"}), encoding="utf-8")
        (package / "data" / "regions" / "town.json").write_text(json.dumps({
            "region_id": "town", "rooms": {"square": {"name": "Square", "exits": {}}},
        }), encoding="utf-8")
        (package / "data" / "quests" / "quests.json").write_text(json.dumps({
            "quest_probe": {"title": "Probe", "type": "fetch", "description": "…", "stages": [stage]},
        }), encoding="utf-8")
        return package

    def test_a_stage_with_no_objective_is_rejected(self) -> None:
        package = self._package_with_stage({"stage_index": 0, "description": "Do the thing"})
        _definition, issues = validator.load_content_set(package)
        messages = [issue.message for issue in issues if issue.severity == "error"]
        self.assertTrue(any("nothing can satisfy it" in m for m in messages), messages)

    def test_the_old_editor_shape_is_named_in_the_error(self) -> None:
        package = self._package_with_stage({
            "id": "stage_1", "description": "Kill it", "type": "KILL",
            "target": "wolf", "count": 1, "next": "",
        })
        _definition, issues = validator.load_content_set(package)
        messages = [issue.message for issue in issues if issue.severity == "error"]
        offender = next((m for m in messages if "nothing can satisfy it" in m), "")
        self.assertIn("type", offender, "the error should name the fields that misled the author")
        self.assertIn("target", offender)

    def test_a_stage_with_an_objective_is_accepted(self) -> None:
        package = self._package_with_stage({
            "stage_index": 0, "description": "Fetch it",
            "objective": {"type": "fetch", "item_id": "item_absent"},
        })
        _definition, issues = validator.load_content_set(package)
        messages = [issue.message for issue in issues if issue.severity == "error"]
        self.assertFalse(any("nothing can satisfy it" in m for m in messages), messages)

    def test_an_alternative_route_counts_as_an_objective(self) -> None:
        package = self._package_with_stage({
            "stage_index": 0, "description": "Either way",
            "objectives_any": [{"type": "fetch", "item_id": "item_absent"}],
        })
        _definition, issues = validator.load_content_set(package)
        messages = [issue.message for issue in issues if issue.severity == "error"]
        self.assertFalse(any("nothing can satisfy it" in m for m in messages), messages)


class TestRecipeIngredientReferences(unittest.TestCase):
    """An ingredient may name a rule, and the rule has to land somewhere.

    `item_id` was for years the only thing an ingredient could be. Recipes may
    now name an item family or a capability with an optional material-grade
    floor, which means the build has to check the reference against the content
    set's own contracts -- a typo in a family name would otherwise be a recipe
    that can never be crafted and never says why.
    """

    def _package_with_recipe(self, ingredients: list, *, tiers: list | None = None) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        package = root / "content_set"
        for directory in ("items", "regions", "npcs", "crafting", "contracts"):
            (package / "data" / directory).mkdir(parents=True)
        (package / "rules").mkdir(parents=True)
        (package / "presentation").mkdir(parents=True)
        (package / validator.CONTENT_SET_MANIFEST_NAME).write_text(json.dumps({
            "id": "recipe_probe", "title": "Recipe Probe", "version": "0.1.0",
            "manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
            "paths": {
                "content_root": "data",
                "ruleset": "rules/ruleset.json",
                "presentation": "presentation/default.json",
            },
            "start": {"scenario_id": "start", "region_id": "town", "room_id": "square"},
            "capabilities": ["inventory", "crafting"],
        }), encoding="utf-8")
        (package / "rules" / "ruleset.json").write_text(json.dumps({"ruleset_id": "probe"}), encoding="utf-8")
        (package / "presentation" / "default.json").write_text("{}", encoding="utf-8")
        (package / "data" / "regions" / "town.json").write_text(json.dumps({
            "region_id": "town", "rooms": {"square": {"name": "Square", "exits": {}}},
        }), encoding="utf-8")
        (package / "data" / "items" / "items.json").write_text(json.dumps({
            "item_shell": {"type": "Item", "name": "shell", "item_family": "finished_goods"},
            "item_panel": {"type": "Item", "name": "panel", "item_family": "salvaged_part"},
        }), encoding="utf-8")
        (package / "data" / "contracts" / "world_contracts.json").write_text(json.dumps({
            "schema_version": 1,
            "item_families": [
                {"id": "salvaged_part", "label": "salvaged part", "item_class": "Item",
                 "capabilities": ["crafting_material"]},
                {"id": "finished_goods", "label": "finished goods", "item_class": "Item"},
            ],
        }), encoding="utf-8")
        recipe: dict = {"name": "Probe", "result_item_id": "item_shell", "ingredients": ingredients}
        if tiers is not None:
            recipe["quality_tiers"] = tiers
        (package / "data" / "crafting" / "recipes.json").write_text(json.dumps({
            "probe_recipe": recipe,
        }), encoding="utf-8")
        return package

    def _issues(self, package: Path):
        _definition, issues = validator.load_content_set(package)
        return issues

    def _errors(self, package: Path) -> list:
        return [issue.message for issue in self._issues(package) if issue.severity == "error"]

    def test_an_exact_template_reference_is_accepted(self) -> None:
        package = self._package_with_recipe([{"item_id": "item_panel", "quantity": 1}])
        self.assertEqual([], self._errors(package))

    def test_a_declared_family_reference_is_accepted(self) -> None:
        package = self._package_with_recipe([{"item_family": "salvaged_part", "quantity": 1}])
        self.assertEqual([], self._errors(package))

    def test_a_declared_capability_reference_is_accepted(self) -> None:
        package = self._package_with_recipe([{"capability": "crafting_material", "quantity": 1}])
        self.assertEqual([], self._errors(package))

    def test_an_undeclared_family_is_an_error(self) -> None:
        package = self._package_with_recipe([{"item_family": "salvaged_prt", "quantity": 1}])
        errors = self._errors(package)
        self.assertTrue(any("salvaged_prt" in m and "contracts" in m for m in errors), errors)

    def test_an_undeclared_capability_is_a_warning_naming_the_consequence(self) -> None:
        package = self._package_with_recipe([{"capability": "crafting_materiel", "quantity": 1}])
        warnings = [issue.message for issue in self._issues(package) if issue.severity == "warning"]
        self.assertTrue(any("crafting_materiel" in m and "satisfy it" in m for m in warnings), warnings)
        self.assertEqual([], self._errors(package))

    def test_an_ingredient_naming_nothing_is_an_error(self) -> None:
        package = self._package_with_recipe([{"quantity": 2}])
        errors = self._errors(package)
        self.assertTrue(any("names nothing" in m for m in errors), errors)

    def test_naming_both_an_id_and_a_family_warns_that_one_is_ignored(self) -> None:
        package = self._package_with_recipe([
            {"item_id": "item_panel", "item_family": "salvaged_part", "quantity": 1},
        ])
        warnings = [issue.message for issue in self._issues(package) if issue.severity == "warning"]
        self.assertTrue(any("item_id" in m and "ignored" in m for m in warnings), warnings)

    def test_a_negative_material_grade_floor_is_an_error(self) -> None:
        package = self._package_with_recipe([
            {"item_family": "salvaged_part", "quantity": 1, "min_material_quality": -1},
        ])
        errors = self._errors(package)
        self.assertTrue(any("min_material_quality" in m for m in errors), errors)

    def test_a_zero_quantity_is_an_error(self) -> None:
        package = self._package_with_recipe([{"item_id": "item_panel", "quantity": 0}])
        errors = self._errors(package)
        self.assertTrue(any("quantity" in m for m in errors), errors)

    def test_an_alternatives_family_is_checked_too(self) -> None:
        package = self._package_with_recipe([
            {"item_id": "item_shell", "quantity": 1, "alternatives": [{"item_family": "absent"}]},
        ])
        errors = self._errors(package)
        self.assertTrue(any("alternatives[0]" in m and "absent" in m for m in errors), errors)

    def test_a_missing_template_reference_is_still_an_error(self) -> None:
        package = self._package_with_recipe([{"item_id": "item_absent", "quantity": 1}])
        errors = self._errors(package)
        self.assertTrue(any("missing item template" in m for m in errors), errors)


class TestSalvageRuleValidation(unittest.TestCase):
    """Nothing checked any of this, so a typo fell silently to the scrap default.

    Salvage output is an item reference, and a reference is checked the same way
    wherever content writes one. A rule keyed by an engine class is still legal
    (older sets use it) but has to name a class the engine actually has.
    """

    def _package_with_salvage(self, salvage_rules: dict, items: dict | None = None) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        package = root / "content_set"
        for directory in ("items", "regions", "contracts", "npcs"):
            (package / "data" / directory).mkdir(parents=True)
        (package / "rules").mkdir(parents=True)
        (package / "presentation").mkdir(parents=True)
        (package / validator.CONTENT_SET_MANIFEST_NAME).write_text(json.dumps({
            "id": "salvage_probe", "title": "Salvage Probe", "version": "0.1.0",
            "manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
            "paths": {
                "content_root": "data",
                "ruleset": "rules/ruleset.json",
                "presentation": "presentation/default.json",
            },
            "start": {"scenario_id": "start", "region_id": "town", "room_id": "square"},
            "capabilities": ["inventory", "crafting"],
        }), encoding="utf-8")
        (package / "presentation" / "default.json").write_text("{}", encoding="utf-8")
        (package / "rules" / "ruleset.json").write_text(json.dumps({
            "ruleset_id": "salvage_probe", "crafting": {"salvage_rules": salvage_rules},
        }), encoding="utf-8")
        (package / "data" / "regions" / "town.json").write_text(json.dumps({
            "region_id": "town", "rooms": {"square": {"name": "Square", "exits": {}}},
        }), encoding="utf-8")
        (package / "data" / "contracts" / "world_contracts.json").write_text(json.dumps({
            "schema_version": 1,
            "item_families": [
                {"id": "salvaged_part", "label": "salvaged part", "item_class": "Junk"},
            ],
        }), encoding="utf-8")
        templates = items if items is not None else {
            "item_scrap": {"type": "Item", "name": "scrap"},
        }
        (package / "data" / "items" / "items.json").write_text(json.dumps(templates), encoding="utf-8")
        return package

    def _errors(self, package: Path) -> list:
        _definition, issues = validator.load_content_set(package)
        return [issue.message for issue in issues if issue.severity == "error"]

    def test_a_family_rule_naming_a_template_is_accepted(self) -> None:
        package = self._package_with_salvage({
            "by_family": {"salvaged_part": {"item_id": "item_scrap", "quantity_per_weight": 1.0}},
            "default_item_id": "item_scrap",
        })
        self.assertEqual([], self._errors(package))

    def test_a_family_rule_naming_a_missing_template_is_an_error(self) -> None:
        package = self._package_with_salvage({
            "by_family": {"salvaged_part": {"item_id": "item_absent"}},
        })
        errors = self._errors(package)
        self.assertTrue(
            any("by_family.salvaged_part" in message and "item_absent" in message
                for message in errors),
            errors,
        )

    def test_a_family_rule_keyed_on_an_undeclared_family_is_an_error(self) -> None:
        package = self._package_with_salvage({
            "by_family": {"salvaged_prt": {"item_id": "item_scrap"}},
        })
        errors = self._errors(package)
        self.assertTrue(any("salvaged_prt" in message for message in errors), errors)

    def test_a_rule_naming_nothing_is_an_error(self) -> None:
        package = self._package_with_salvage({
            "by_family": {"salvaged_part": {"quantity_per_weight": 2.0}},
        })
        self.assertTrue(any("names nothing" in message for message in self._errors(package)))

    def test_a_class_key_that_is_not_an_item_class_is_an_error(self) -> None:
        package = self._package_with_salvage({
            "Sword": {"item_id": "item_scrap"},
            "default_item_id": "item_scrap",
        })
        errors = self._errors(package)
        self.assertTrue(any("Sword" in message and "item class" in message for message in errors), errors)

    def test_a_class_key_the_engine_has_is_accepted(self) -> None:
        package = self._package_with_salvage({
            "Weapon": {"item_id": "item_scrap"},
            "default_item_id": "item_scrap",
        })
        self.assertEqual([], self._errors(package))

    def test_a_missing_default_template_is_an_error(self) -> None:
        package = self._package_with_salvage({"default_item_id": "item_absent"})
        self.assertTrue(any("default_item_id" in message for message in self._errors(package)))

    def test_a_negative_weight_rate_is_an_error(self) -> None:
        package = self._package_with_salvage({
            "by_family": {"salvaged_part": {"item_id": "item_scrap", "quantity_per_weight": -1}},
        })
        self.assertTrue(any("quantity_per_weight" in message for message in self._errors(package)))

    def test_an_authoring_note_is_not_read_as_a_rule(self) -> None:
        package = self._package_with_salvage({
            "_comment": "Notes are not rules.",
            "default_item_id": "item_scrap",
        })
        self.assertEqual([], self._errors(package))

    def test_a_templates_own_salvage_output_is_checked_too(self) -> None:
        package = self._package_with_salvage(
            {"default_item_id": "item_scrap"},
            items={
                "item_scrap": {"type": "Item", "name": "scrap"},
                "item_odd": {
                    "type": "Item", "name": "odd",
                    "properties": {"salvage_output": {"item_id": "item_absent"}},
                },
            },
        )
        errors = self._errors(package)
        self.assertTrue(any("salvage_output" in message for message in errors), errors)


def _background_package(case: unittest.TestCase, *, stats: dict, skills: dict | None = None,
                        stat_bonuses: dict | None = None, weather: dict | None = None,
                        weather_profile: str | None = None) -> Path:
    """A minimal package whose backgrounds, ruleset and weather a test controls."""
    root = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, root, ignore_errors=True)
    package = root / "content_set"
    for directory in ("items", "regions", "npcs", "player"):
        (package / "data" / directory).mkdir(parents=True)
    (package / "rules").mkdir(parents=True)
    (package / "presentation").mkdir(parents=True)
    (package / validator.CONTENT_SET_MANIFEST_NAME).write_text(json.dumps({
        "id": "starting_probe", "title": "Starting Probe", "version": "0.1.0",
        "manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
        "paths": {
            "content_root": "data",
            "ruleset": "rules/ruleset.json",
            "presentation": "presentation/default.json",
        },
        "start": {"scenario_id": "start", "region_id": "town", "room_id": "square"},
        "capabilities": ["inventory"],
    }), encoding="utf-8")
    ruleset: dict = {"ruleset_id": "probe"}
    if stat_bonuses is not None:
        ruleset["skills"] = {"stat_bonuses": stat_bonuses}
    if weather is not None:
        ruleset["weather"] = {"profiles": weather}
    (package / "rules" / "ruleset.json").write_text(json.dumps(ruleset), encoding="utf-8")
    (package / "presentation" / "default.json").write_text("{}", encoding="utf-8")
    properties = {"weather_profile": weather_profile} if weather_profile else {}
    (package / "data" / "regions" / "town.json").write_text(json.dumps({
        "region_id": "town",
        "properties": properties,
        "rooms": {"square": {"name": "Square", "exits": {}}},
    }), encoding="utf-8")
    background: dict = {"name": "Probe", "stats": stats}
    if skills is not None:
        background["skills"] = skills
    (package / "data" / "player" / "backgrounds.json").write_text(
        json.dumps({"_comment": "a note", "probe": background}), encoding="utf-8"
    )
    return package


class TestStartingStatsAndSkills(unittest.TestCase):
    """A background's starting stats are copies into `player.stats`.

    `BackgroundManager` writes whatever keys it is handed. Nothing downstream
    ever reads `strengh`, so a typo in a background reaches the live player as a
    stat that no formula consults and no message mentions: the character is
    quietly weaker than the authored one and nothing anywhere says so.
    """

    def _package(self, **kwargs) -> Path:
        return _background_package(self, **kwargs)

    def _messages(self, package: Path, severity: str = "error") -> list:
        _definition, issues = validator.load_content_set(package)
        return [issue.message for issue in issues if issue.severity == severity]

    def test_the_engines_own_stats_are_accepted(self):
        package = self._package(stats={"strength": 11, "constitution": 12})
        self.assertEqual([], self._messages(package))

    def test_a_misspelled_stat_names_the_typo_and_the_real_vocabulary(self):
        package = self._package(stats={"strength": 11, "strengh": 14})
        messages = self._messages(package)
        self.assertEqual(1, len(messages), messages)
        self.assertIn("'strengh'", messages[0])
        self.assertIn("strength", messages[0], "the message offers the name that was meant")

    def test_the_container_of_channel_resistances_is_not_a_stat(self):
        package = self._package(stats={"strength": 11, "resistances": {"fire": 10}})
        self.assertEqual([], self._messages(package), "a nested object is a container, not a stat")

    def test_a_stat_only_this_sets_ruleset_names_is_accepted(self):
        """A set may flavour its stats; the ruleset is where it says so."""
        package = self._package(
            stats={"grit": 12},
            skills={"endurance": 1},
            stat_bonuses={"endurance": {"stat": "grit", "per_point": 2}},
        )
        self.assertEqual([], self._messages(package))

    def test_a_skill_no_ruleset_rule_backs_is_a_warning(self):
        package = self._package(
            stats={"strength": 10},
            skills={"lockpikcing": 1},
            stat_bonuses={"lockpicking": {"stat": "dexterity"}},
        )
        warnings = self._messages(package, "warning")
        self.assertEqual(1, len(warnings), warnings)
        self.assertIn("lockpikcing", warnings[0])

    def test_a_set_declaring_no_stat_bonuses_warns_about_no_skills(self):
        """Opting out of stat-backed skills is not the same as missing them.

        The editor fixture is exactly this shape, and warning there would mean a
        minimal content set could never validate clean.
        """
        package = self._package(stats={"strength": 10}, skills={"crafting": 1})
        self.assertEqual([], self._messages(package, "warning"))


class TestRegionWeatherProfiles(unittest.TestCase):
    """A region names a climate by id; the ruleset has to declare that id.

    `WeatherManager` falls back to the unmapped global weather when it cannot
    find the profile, which is the right default and a silent one: an alpine
    region authored to turn rain into snow just reports rain.
    """

    def _package(self, *, profiles: dict, selected: str) -> Path:
        return _background_package(
            self, stats={"strength": 10}, weather=profiles, weather_profile=selected
        )

    def test_a_declared_profile_is_accepted(self):
        package = self._package(profiles={"alpine": {"map": {}}}, selected="alpine")
        _definition, issues = validator.load_content_set(package)
        self.assertEqual([], [i.message for i in issues if i.severity == "error"])

    def test_an_undeclared_profile_is_an_error(self):
        package = self._package(profiles={"alpine": {"map": {}}}, selected="jungle")
        _definition, issues = validator.load_content_set(package)
        errors = [i.message for i in issues if i.severity == "error"]
        self.assertEqual(1, len(errors), errors)
        self.assertIn("jungle", errors[0])

    def test_a_set_declaring_no_profiles_at_all_says_so(self):
        package = self._package(profiles={}, selected="alpine")
        _definition, issues = validator.load_content_set(package)
        errors = [i.message for i in issues if i.severity == "error"]
        self.assertIn("declares no profiles at all", errors[0])


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


class TestServerRootPathInsertion(unittest.TestCase):
    def test_reload_inserts_missing_server_root_onto_sys_path(self) -> None:
        import importlib

        server_root = str(validator._SERVER_ROOT)
        original_path = list(sys.path)
        try:
            sys.path[:] = [p for p in sys.path if p != server_root]
            self.assertNotIn(server_root, sys.path)
            importlib.reload(validator)
            self.assertIn(server_root, sys.path)
        finally:
            sys.path[:] = original_path
            importlib.reload(validator)


if __name__ == "__main__":
    unittest.main()
