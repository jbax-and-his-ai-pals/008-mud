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

    def test_room_item_placements_require_a_real_quantity_and_override_object(self) -> None:
        package = self._write_package(self._case_root())
        (package / "data" / "items" / "items.json").write_text(
            json.dumps({"item_map": {"name": "Map", "type": "Item"}}), encoding="utf-8"
        )
        region_path = package / "data" / "regions" / "town.json"
        region_path.write_text(
            json.dumps({
                "region_id": "town",
                "rooms": {"square": {"name": "Square", "items": [
                    {"item_id": "item_map", "quantity": 0, "properties_override": []},
                ]}},
            }),
            encoding="utf-8",
        )
        _definition, issues = validator.load_content_set(package)
        messages = [issue.message for issue in issues]
        self.assertTrue(any("item 'item_map' quantity must be a positive integer" in message for message in messages))
        self.assertTrue(any("item 'item_map' properties_override must be an object" in message for message in messages))

    def test_room_npc_placement_overrides_have_a_checked_runtime_shape(self) -> None:
        package = self._write_package(self._case_root())
        (package / "data" / "npcs" / "npcs.json").write_text(
            json.dumps({"npc_guide": {"name": "Guide"}}), encoding="utf-8"
        )
        region_path = package / "data" / "regions" / "town.json"
        region_path.write_text(
            json.dumps({
                "region_id": "town",
                "rooms": {"square": {"name": "Square", "initial_npcs": [{
                    "template_id": "npc_guide",
                    "overrides": {"level": 0, "behavior_type": "hover", "properties_override": [], "extra": True},
                }]}},
            }),
            encoding="utf-8",
        )
        _definition, issues = validator.load_content_set(package)
        messages = [issue.message for issue in issues]
        self.assertTrue(any("override level must be an integer of at least 1" in message for message in messages))
        self.assertTrue(any("override behavior_type must be one of" in message for message in messages))
        self.assertTrue(any("override properties_override must be an object" in message for message in messages))
        self.assertTrue(any("override 'extra' is ignored by the runtime" in message for message in messages))

    def test_room_environment_has_a_small_checked_shape(self) -> None:
        package = self._write_package(self._case_root())
        region_path = package / "data" / "regions" / "town.json"
        region_path.write_text(
            json.dumps({
                "region_id": "town",
                "rooms": {"square": {"name": "Square", "env_properties": {
                    "dark": "yes", "temperature": "warm", "smell": 3, "mystery": True,
                }}},
            }),
            encoding="utf-8",
        )
        _definition, issues = validator.load_content_set(package)
        messages = [issue.message for issue in issues]
        self.assertTrue(any("env_properties.dark must be a boolean" in message for message in messages))
        self.assertTrue(any("env_properties.temperature must be normal, cold, or hot" in message for message in messages))
        self.assertTrue(any("env_properties.smell must be a string" in message for message in messages))
        self.assertTrue(any("env_properties.mystery is ignored by the runtime" in message for message in messages))

    def test_room_time_descriptions_have_a_checked_shape(self) -> None:
        package = self._write_package(self._case_root())
        region_path = package / "data" / "regions" / "town.json"
        region_path.write_text(
            json.dumps({
                "region_id": "town",
                "rooms": {"square": {"name": "Square", "time_descriptions": {"day": 3, "midnight": "ignored"}}},
            }),
            encoding="utf-8",
        )
        _definition, issues = validator.load_content_set(package)
        messages = [issue.message for issue in issues]
        self.assertTrue(any("time_descriptions.day must be a string" in message for message in messages))
        self.assertTrue(any("time_descriptions.midnight is ignored by the runtime" in message for message in messages))

    def test_npc_template_values_the_editor_authors_have_runtime_contracts(self) -> None:
        """An NPC form must not be able to save values the factory drops or misreads."""
        package = self._write_package(self._case_root())
        (package / "data" / "items" / "items.json").write_text(
            json.dumps({"item_torch": {"name": "Torch", "type": "Item"}}), encoding="utf-8"
        )
        (package / "data" / "abilities").mkdir(parents=True, exist_ok=True)
        (package / "data" / "abilities" / "spells.json").write_text(
            json.dumps({"spark": {"name": "Spark", "type": "Attack"}}), encoding="utf-8"
        )
        (package / "data" / "npcs" / "npcs.json").write_text(
            json.dumps({
                "bad_authoring": {
                    "name": "Bad", "friendly": "yes", "level": 0, "health": -1,
                    "properties": {
                        "aggression": 2, "move_cooldown": -1, "respawn_cooldown": -2,
                        "can_unlock_chests": "yes", "work_location": "town:missing",
                    },
                    "patrol_points": [1],
                    "usable_spells": ["missing_spell"],
                    "initial_inventory": [{"item_id": "missing_item", "quantity": 0}],
                    "schedule": {"25": {
                        "region_id": "town", "room_id": "missing", "activity": 2,
                        "behavior_override": "wanderer",
                    }},
                },
                "no_respawn": {
                    "name": "Summon", "properties": {"respawn_cooldown": -1},
                },
            }), encoding="utf-8"
        )
        _definition, issues = validator.load_content_set(package)
        messages = [issue.message for issue in issues]
        self.assertTrue(any("'bad_authoring'.friendly must be a boolean" in message for message in messages))
        self.assertTrue(any("'bad_authoring'.level must be an integer of at least 1" in message for message in messages))
        self.assertTrue(any("'bad_authoring'.properties.aggression must be a number from 0 to 1" in message for message in messages))
        self.assertTrue(any("'bad_authoring'.properties.respawn_cooldown must be an integer of -1 or greater" in message for message in messages))
        self.assertTrue(any("'bad_authoring'.properties.work_location must name an authored region:room" in message for message in messages))
        self.assertTrue(any("'bad_authoring'.usable_spells references a missing ability" in message for message in messages))
        self.assertTrue(any("'bad_authoring'.initial_inventory[0].quantity must be a positive integer" in message for message in messages))
        self.assertTrue(any("'bad_authoring'.schedule['25'] must use an hour from 0 to 23" in message for message in messages))
        self.assertTrue(any("behavior_override must be 'aggressive'" in message for message in messages))
        self.assertFalse(any("no_respawn.properties.respawn_cooldown" in message for message in messages))

    def test_npc_schedule_rules_have_a_checked_setting_owned_grammar(self) -> None:
        """Slots and hours must not quietly fall back to an NPC's home room."""
        package = self._write_package(self._case_root())
        (package / "rules" / "ruleset.json").write_text(
            json.dumps({
                "npc_schedules": {
                    "excluded_name_keywords": [""],
                    "room_categories": {"homes": "house"},
                    "roles": [{
                        "id": "merchant", "template_keywords": [],
                        "location_slots": {
                            "home": {"type": "category", "categories": ["missing"], "fallback": "work"},
                            "work": {"type": "elsewhere"},
                        },
                        "schedule": {"08": {"activity": "", "slot": "missing", "behavior_override": "wanderer"}},
                    }],
                },
            }), encoding="utf-8"
        )
        _definition, issues = validator.load_content_set(package)
        messages = [issue.message for issue in issues]
        self.assertTrue(any("excluded_name_keywords must be an array of non-empty strings" in message for message in messages))
        self.assertTrue(any("room_categories.homes must be an array" in message for message in messages))
        self.assertTrue(any("template_keywords must be a non-empty array" in message for message in messages))
        self.assertTrue(any("categories names undeclared category 'missing'" in message for message in messages))
        self.assertTrue(any("type must be self, property_or_self, or category" in message for message in messages))
        self.assertTrue(any("schedule['08'] must use a canonical hour" in message for message in messages))
        self.assertTrue(any("schedule['08'].slot must name this role's location slot" in message for message in messages))
        self.assertTrue(any("behavior_override must be 'aggressive'" in message for message in messages))

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
                        weather_profile: str | None = None, weather_section: dict | None = None,
                        topics: dict | None = None) -> Path:
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
    if weather_section is not None:
        ruleset["weather"] = weather_section
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
    if topics is not None:
        (package / "data" / "knowledge").mkdir(parents=True)
        (package / "data" / "knowledge" / "topics.json").write_text(json.dumps(topics), encoding="utf-8")
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


class TestWeatherShapes(unittest.TestCase):
    """`weather.descriptions` and a profile's `map`/`travel_notes` are string
    maps `information.py`'s `weather` command and `WeatherManager` index
    directly -- a non-string value there is not missing flavor text, it is a
    crash the next time that weather rolls, so the shape is checked even
    though the weather-type keys themselves are this ruleset's own open
    vocabulary."""

    def _package(self, weather_section: dict) -> Path:
        return _background_package(self, stats={"strength": 10}, weather_section=weather_section)

    def _errors(self, package: Path) -> list:
        _definition, issues = validator.load_content_set(package)
        return [i.message for i in issues if i.severity == "error"]

    def test_string_descriptions_are_accepted(self):
        package = self._package({"descriptions": {"rain": "A steady drizzle."}})
        self.assertEqual([], self._errors(package))

    def test_a_non_string_description_is_an_error(self):
        package = self._package({"descriptions": {"rain": {"text": "A steady drizzle."}}})
        errors = self._errors(package)
        self.assertTrue(any("weather.descriptions.rain" in message for message in errors), errors)

    def test_descriptions_must_be_an_object(self):
        package = self._package({"descriptions": ["A steady drizzle."]})
        errors = self._errors(package)
        self.assertTrue(any("weather.descriptions must be an object" in message for message in errors), errors)

    def test_a_profiles_map_and_travel_notes_accept_strings(self):
        package = self._package({"profiles": {"alpine": {
            "map": {"rain": "snow"},
            "travel_notes": {"snow": "The pass may be closed."},
        }}})
        self.assertEqual([], self._errors(package))

    def test_a_non_string_map_value_is_an_error(self):
        package = self._package({"profiles": {"alpine": {"map": {"rain": 3}}}})
        errors = self._errors(package)
        self.assertTrue(any("weather.profiles.alpine.map.rain" in message for message in errors), errors)

    def test_a_non_string_travel_note_is_an_error(self):
        package = self._package({"profiles": {"alpine": {"travel_notes": {"snow": ["closed"]}}}})
        errors = self._errors(package)
        self.assertTrue(any("weather.profiles.alpine.travel_notes.snow" in message for message in errors), errors)

    def test_a_profile_that_is_not_an_object_is_an_error(self):
        package = self._package({"profiles": {"alpine": "cold"}})
        errors = self._errors(package)
        self.assertTrue(any("weather.profiles.alpine must be an object" in message for message in errors), errors)


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


class TestKnowledgeTopics(unittest.TestCase):
    """`data/knowledge/topics.json` (`knowledge_manager.py`) had no validator at
    all -- `_load_topics` swallows a malformed file into an empty dict with only
    a print(), so a typo'd condition kind or effect key here reached a player as
    a topic that simply never answers, with no error anywhere. The condition
    language (`_check_conditions`) is deliberately separate from
    `engine/conditions.py`'s `KNOWN_KINDS` -- this is the NPC/world-state
    vocabulary a topic response gates on, not the shared dialogue/title one."""

    def _package(self, topics: dict) -> Path:
        return _background_package(self, stats={"strength": 10}, topics=topics)

    def _errors(self, package: Path) -> list:
        _definition, issues = validator.load_content_set(package)
        return [i.message for i in issues if i.severity == "error"]

    def test_a_well_formed_topic_is_accepted(self):
        package = self._package({
            "__common_topics__": ["rumor"],
            "rumor": {
                "display_name": "Rumor",
                "keywords": ["gossip"],
                "responses": [{"text": "Word is the bridge is out.", "priority": 1}],
            },
        })
        self.assertEqual([], self._errors(package))

    def test_a_response_needs_non_empty_text(self):
        package = self._package({"rumor": {"responses": [{"priority": 1}]}})
        errors = self._errors(package)
        self.assertTrue(any("responses[0].text" in message for message in errors), errors)

    def test_common_topics_must_name_a_declared_topic(self):
        package = self._package({"__common_topics__": ["ghost_topic"], "rumor": {"responses": []}})
        errors = self._errors(package)
        self.assertTrue(any("ghost_topic" in message for message in errors), errors)

    def test_keywords_must_be_an_array_of_strings(self):
        package = self._package({"rumor": {"keywords": ["ok", 5], "responses": []}})
        errors = self._errors(package)
        self.assertTrue(any("rumor'.keywords" in message for message in errors), errors)

    def test_an_unknown_condition_kind_is_an_error(self):
        package = self._package({"rumor": {"responses": [{"text": "Hi.", "conditions": {"reputation": 5}}]}})
        errors = self._errors(package)
        self.assertTrue(any("conditions.reputation" in message and "not a condition" in message for message in errors), errors)

    def test_an_unknown_effect_key_is_an_error(self):
        package = self._package({"rumor": {"responses": [{"text": "Hi.", "effects": {"telepathy": True}}]}})
        errors = self._errors(package)
        self.assertTrue(any("effects" in message and "telepathy" in message for message in errors), errors)

    def test_knowledge_state_must_reference_a_declared_topic(self):
        package = self._package({
            "rumor": {"responses": [{"text": "Hi.", "conditions": {"knowledge_state": {"topic_id": "nope", "state": "known"}}}]},
        })
        errors = self._errors(package)
        self.assertTrue(any("knowledge_state.topic_id" in message for message in errors), errors)

    def test_knowledge_state_accepts_a_self_reference(self):
        package = self._package({
            "rumor": {"responses": [{"text": "Hi."}]},
            "other": {"responses": [{"text": "Hi.", "conditions": {"knowledge_state": {"topic_id": "rumor", "state": "discussed"}}}]},
        })
        self.assertEqual([], self._errors(package))

    def test_quest_state_validates_its_own_fields(self):
        package = self._package({
            "rumor": {"responses": [{
                "text": "Hi.",
                "conditions": {"quest_state": {"state": "sideways", "from_this_npc": "yes"}},
            }]},
        })
        errors = self._errors(package)
        self.assertTrue(any("quest_state.state" in message for message in errors), errors)
        self.assertTrue(any("quest_state.from_this_npc" in message for message in errors), errors)

    def test_campaign_state_requires_a_real_campaign(self):
        package = self._package({
            "rumor": {"responses": [{"text": "Hi.", "conditions": {"campaign_state": {"campaign_id": "ghost_campaign", "state": "active"}}}]},
        })
        (package / "data" / "campaigns").mkdir(parents=True)
        (package / "data" / "campaigns" / "real.json").write_text(
            json.dumps({"campaign_id": "real_campaign", "name": "Real", "description": "", "start_node_id": "s", "nodes": {"s": {"description": "", "type": "END"}}}),
            encoding="utf-8",
        )
        errors = self._errors(package)
        self.assertTrue(any("campaign_state.campaign_id" in message for message in errors), errors)

    def test_a_malformed_topics_file_is_an_error_not_a_silent_empty_dict(self):
        package = self._package({"rumor": "not an object"})
        errors = self._errors(package)
        self.assertTrue(any("rumor" in message and "must be an object" in message for message in errors), errors)


def _quest_generation_package(case: unittest.TestCase, quest_generation: dict) -> Path:
    package = _background_package(case, stats={"strength": 10})
    (package / "data" / "npcs" / "people.json").write_text(
        json.dumps({"elder": {"name": "Elder", "level": 1}}), encoding="utf-8"
    )
    (package / "data" / "items" / "goods.json").write_text(
        json.dumps({"parcel": {"type": "Item", "name": "parcel"}}), encoding="utf-8"
    )
    ruleset_path = package / "rules" / "ruleset.json"
    ruleset = json.loads(ruleset_path.read_text(encoding="utf-8"))
    ruleset["quest_generation"] = quest_generation
    ruleset_path.write_text(json.dumps(ruleset), encoding="utf-8")
    return package


class TestQuestGenerationPolicy(unittest.TestCase):
    """Only `authored_board_templates` used to be checked. Everything else in
    `quest_generation` failed quietly: an NPC-interest key naming no template
    was never read (fantasy_frontier's `guard`/`villager` keys, so town guards
    never offered procedural work), a bad text placeholder became "Task", and a
    bad `instance_quest` placeholder raised mid-generation."""

    def _errors(self, quest_generation: dict) -> list:
        package = _quest_generation_package(self, quest_generation)
        _definition, issues = validator.load_content_set(package)
        return [i.message for i in issues if i.severity == "error"]

    def test_a_well_formed_section_is_accepted(self):
        self.assertEqual([], self._errors({
            "quest_board_locations": ["town:square"],
            "delivery_package_item_id": "parcel",
            "board_display_name": "Notices",
            "turn_in_phrases": ["complete"],
            "npc_quest_interests": {"elder": ["kill", "fetch"]},
            "procedural_naming": {"adjectives": ["Old"], "nouns": ["Key"], "default_name_pattern": "{Adjective} {Noun}", "default_base_template_id": "parcel"},
            "instance_quest": {"title_pattern": "Rats: {creature_name}", "description_pattern": "Clear {creature_name}."},
            "text_templates": {"kill": {"title": "Hunt {target_name_plural}", "description": "{giver_name} wants {quantity} gone."}},
        }))

    def test_a_board_location_must_name_a_real_room(self):
        errors = self._errors({"quest_board_locations": ["town:nowhere", "no_colon"]})
        self.assertTrue(any("town:nowhere" in m for m in errors), errors)
        self.assertTrue(any("quest_board_locations[1]" in m and "region_id:room_id" in m for m in errors), errors)

    def test_the_delivery_package_must_be_a_real_item(self):
        errors = self._errors({"delivery_package_item_id": "ghost_parcel"})
        self.assertTrue(any("ghost_parcel" in m for m in errors), errors)

    def test_an_interest_key_must_name_a_real_npc_template(self):
        errors = self._errors({"npc_quest_interests": {"guard": ["kill"]}})
        self.assertTrue(any("npc_quest_interests.guard" in m and "missing NPC template" in m for m in errors), errors)

    def test_interest_tags_must_be_strings(self):
        errors = self._errors({"npc_quest_interests": {"elder": ["kill", 3]}})
        self.assertTrue(any("npc_quest_interests.elder" in m for m in errors), errors)

    def test_turn_in_phrases_must_be_non_empty_strings(self):
        errors = self._errors({"turn_in_phrases": ["complete", ""]})
        self.assertTrue(any("turn_in_phrases" in m for m in errors), errors)

    def test_a_naming_pattern_only_fills_adjective_and_noun(self):
        errors = self._errors({"procedural_naming": {"default_name_pattern": "{Adjective} {Colour} {Noun}"}})
        self.assertTrue(any("default_name_pattern" in m and "Colour" in m for m in errors), errors)

    def test_an_instance_pattern_only_fills_creature_name(self):
        errors = self._errors({"instance_quest": {"title_pattern": "Clear the {region_name}"}})
        self.assertTrue(any("instance_quest.title_pattern" in m and "region_name" in m for m in errors), errors)

    def test_a_text_template_placeholder_must_be_one_the_generator_fills(self):
        errors = self._errors({"text_templates": {"fetch": {"title": "Get {item_name_plural}", "description": "From {villain}."}}})
        self.assertTrue(any("text_templates.fetch.description" in m and "villain" in m for m in errors), errors)

    def test_a_text_template_must_be_for_a_generated_quest_type(self):
        errors = self._errors({"text_templates": {"escort": {"title": "Escort", "description": "Walk."}}})
        self.assertTrue(any("text_templates.escort" in m for m in errors), errors)

    def test_escaped_braces_are_not_placeholders(self):
        self.assertEqual([], self._errors({"text_templates": {"kill": {"title": "{{Bounty}} {target_name_plural}", "description": "Go."}}}))

    def test_other_checks_run_without_authored_board_templates(self):
        errors = self._errors({"authored_board_templates": None, "delivery_package_item_id": "ghost_parcel"})
        self.assertTrue(any("ghost_parcel" in m for m in errors), errors)


def _instance_template(**overrides) -> dict:
    template = {
        "type": "instance",
        "level": 1,
        "giver_npc_template_id": "homeowner",
        "possible_entry_regions": ["town"],
        "objective": {"type": "clear_region", "possible_target_template_ids": ["rat"]},
        "layout_generation_config": {
            "min_rooms": 2, "max_rooms": 3, "region_name": "House",
            "possible_room_names": ["Hall"], "target_count": [1, 2],
        },
    }
    template.update(overrides)
    return template


class TestInstanceQuests(unittest.TestCase):
    """`quests/instances.json` had no validator: `content_set.py` read only
    `quests.json`. A template without targets or an existing entry region is
    never offered, an objective other than `clear_region` never completes, and
    a reversed range or empty room-name pool raises inside `random` while the
    quest board fills."""

    def _errors(self, instances: dict, quests: dict | None = None) -> list:
        package = _background_package(self, stats={"strength": 10})
        (package / "data" / "npcs" / "people.json").write_text(json.dumps({
            "homeowner": {"name": "Homeowner", "level": 1},
            "rat": {"name": "Rat", "level": 1},
        }), encoding="utf-8")
        (package / "data" / "quests").mkdir()
        (package / "data" / "quests" / "instances.json").write_text(json.dumps(instances), encoding="utf-8")
        if quests is not None:
            (package / "data" / "quests" / "quests.json").write_text(json.dumps(quests), encoding="utf-8")
        _definition, issues = validator.load_content_set(package)
        return [i.message for i in issues if i.severity == "error"]

    def test_a_well_formed_template_is_accepted(self):
        self.assertEqual([], self._errors({"_comment": "note", "infestation": _instance_template()}))

    def test_only_instance_type_belongs_here(self):
        errors = self._errors({"infestation": _instance_template(type="kill")})
        self.assertTrue(any("infestation'.type" in m for m in errors), errors)

    def test_the_objective_must_be_clear_region(self):
        errors = self._errors({"infestation": _instance_template(objective={"type": "kill", "possible_target_template_ids": ["rat"]})})
        self.assertTrue(any("clear_region" in m for m in errors), errors)

    def test_targets_are_required_and_must_be_real(self):
        errors = self._errors({
            "empty": _instance_template(objective={"type": "clear_region", "possible_target_template_ids": []}),
            "ghost": _instance_template(objective={"type": "clear_region", "possible_target_template_ids": ["ghoul"]}),
        })
        self.assertTrue(any("'empty'" in m and "never offered" in m for m in errors), errors)
        self.assertTrue(any("'ghoul'" in m for m in errors), errors)

    def test_giver_and_completion_npcs_must_be_real(self):
        errors = self._errors({"infestation": _instance_template(
            giver_npc_template_id="stranger",
            objective={"type": "clear_region", "possible_target_template_ids": ["rat"], "completion_npc_template_id": "ghost"},
        )})
        self.assertTrue(any("'stranger'" in m for m in errors), errors)
        self.assertTrue(any("completion_npc_template_id" in m and "'ghost'" in m for m in errors), errors)

    def test_entry_regions_must_exist(self):
        errors = self._errors({"infestation": _instance_template(possible_entry_regions=["atlantis"])})
        self.assertTrue(any("'atlantis'" in m for m in errors), errors)

    def test_reversed_ranges_are_errors(self):
        layout = {"min_rooms": 5, "max_rooms": 2, "target_count": [4, 1]}
        errors = self._errors({"infestation": _instance_template(layout_generation_config=layout)})
        self.assertTrue(any("min_rooms (5)" in m for m in errors), errors)
        self.assertTrue(any("target_count minimum (4)" in m for m in errors), errors)

    def test_target_count_must_be_a_pair(self):
        errors = self._errors({"infestation": _instance_template(layout_generation_config={"target_count": 3})})
        self.assertTrue(any("target_count must be [min, max]" in m for m in errors), errors)

    def test_an_empty_room_name_pool_is_an_error(self):
        errors = self._errors({"infestation": _instance_template(layout_generation_config={"possible_room_names": []})})
        self.assertTrue(any("possible_room_names" in m for m in errors), errors)

    def test_an_id_shared_with_quests_json_is_an_error(self):
        errors = self._errors(
            {"infestation": _instance_template()},
            quests={"infestation": {"title": "T", "stages": [{"objective": {"type": "kill", "target_template_id": "rat", "required_quantity": 1}}]}},
        )
        self.assertTrue(any("also declared in quests.json" in m for m in errors), errors)

    def test_rewards_must_be_non_negative_integers(self):
        errors = self._errors({"infestation": _instance_template(rewards={"xp": -5})})
        self.assertTrue(any("rewards.xp" in m for m in errors), errors)


class TestFieldInteractions(unittest.TestCase):
    """`world/field_interactions.json` had no validator, and its loader drops
    or clamps anything it does not understand without a word."""

    def _issues(self, config) -> list:
        package = _background_package(self, stats={"strength": 10})
        (package / "data" / "world").mkdir()
        (package / "data" / "world" / "field_interactions.json").write_text(json.dumps(config), encoding="utf-8")
        _definition, issues = validator.load_content_set(package)
        return [(i.severity, i.message) for i in issues if i.path.endswith("field_interactions.json")]

    def _errors(self, config) -> list:
        return [message for severity, message in self._issues(config) if severity == "error"]

    def test_a_well_formed_file_is_accepted(self):
        self.assertEqual([], self._issues({
            "fallback_positive_suppresses_negative": 0.6,
            "default_field_id": "blight",
            "polarities": {"sanctity": "positive", "blight": "negative"},
            "pairwise_rules": {"sanctity": {"blight": 0.5}},
        }))

    def test_an_unknown_polarity_is_an_error(self):
        errors = self._errors({"polarities": {"hope": "good"}})
        self.assertTrue(any("polarities.hope" in m for m in errors), errors)

    def test_coefficients_must_be_between_zero_and_one(self):
        errors = self._errors({"fallback_positive_suppresses_negative": 1.5, "pairwise_rules": {"a": {"b": "strong"}}})
        self.assertTrue(any(m.startswith("fallback_positive_suppresses_negative") for m in errors), errors)
        self.assertTrue(any("pairwise_rules.a.b" in m for m in errors), errors)

    def test_an_unknown_top_level_key_is_an_error(self):
        errors = self._errors({"pairwise_rule": {}})
        self.assertTrue(any("'pairwise_rule' is not" in m for m in errors), errors)

    def test_field_ids_must_be_lower_case(self):
        errors = self._errors({"polarities": {"Blight": "negative"}})
        self.assertTrue(any("'Blight'" in m and "'blight'" in m for m in errors), errors)

    def test_a_self_suppression_rule_is_an_error(self):
        errors = self._errors({"pairwise_rules": {"blight": {"blight": 0.5}}})
        self.assertTrue(any("never suppresses itself" in m for m in errors), errors)

    def test_undeclared_fields_are_warnings(self):
        issues = self._issues({
            "default_field_id": "mist",
            "polarities": {"blight": "negative"},
            "pairwise_rules": {"sanctty": {"blight": 0.5}},
        })
        warnings = [m for severity, m in issues if severity == "warning"]
        self.assertEqual([], [m for severity, m in issues if severity == "error"])
        self.assertTrue(any("'mist'" in m for m in warnings), warnings)
        self.assertTrue(any("'sanctty'" in m for m in warnings), warnings)


class TestAlternateAdvancementFile(unittest.TestCase):
    """`AdvancementManager` also reads `<content_root>/advancement.json`, with
    the ruleset section laid over it key by key. Only the ruleset section was
    checked, so a dead grant kind in the file paid nothing and said nothing."""

    def _issues(self, table, ruleset_section=None) -> list:
        package = _background_package(self, stats={"strength": 10})
        (package / "data" / "advancement.json").write_text(json.dumps(table), encoding="utf-8")
        if ruleset_section is not None:
            ruleset_path = package / "rules" / "ruleset.json"
            ruleset = json.loads(ruleset_path.read_text(encoding="utf-8"))
            ruleset["advancement"] = ruleset_section
            ruleset_path.write_text(json.dumps(ruleset), encoding="utf-8")
        _definition, issues = validator.load_content_set(package)
        return [(i.severity, i.message) for i in issues if i.path.endswith("advancement.json")]

    def test_a_well_formed_file_is_accepted(self):
        self.assertEqual([], self._issues({
            "curve": {"base": 120, "multiplier": 1.3},
            "grants": [{"id": "first_region", "xp": 20, "match": {"kind": "region"}}],
        }))

    def test_the_file_gets_the_same_checks_as_the_ruleset(self):
        issues = self._issues({"grants": [{"id": "odd", "xp": 5, "match": {"kind": "sneezing"}}]})
        self.assertTrue(any(s == "error" and "'sneezing'" in m for s, m in issues), issues)

    def test_a_key_the_ruleset_also_sets_is_reported_as_ignored(self):
        issues = self._issues(
            {"grants": [{"id": "first_region", "xp": 20, "match": {"kind": "region"}}]},
            ruleset_section={"grants": [{"id": "first_npc", "xp": 10, "match": {"kind": "npc"}}]},
        )
        self.assertTrue(any(s == "warning" and "'grants' here is ignored" in m for s, m in issues), issues)


class TestSimpleRulesetSections(unittest.TestCase):
    """locksmithing, economy, calendar, spawning, elites, player_defaults and
    npc_naming were validated by nothing. Their readers fall back silently on a
    value they cannot use, and two `str.format` patterns raise at spawn time."""

    def _issues(self, **sections) -> list:
        package = _background_package(self, stats={"strength": 10})
        (package / "data" / "items" / "goods.json").write_text(
            json.dumps({"knife": {"type": "Item", "name": "knife"}}), encoding="utf-8"
        )
        ruleset_path = package / "rules" / "ruleset.json"
        ruleset = json.loads(ruleset_path.read_text(encoding="utf-8"))
        ruleset.update(sections)
        ruleset_path.write_text(json.dumps(ruleset), encoding="utf-8")
        _definition, issues = validator.load_content_set(package)
        return [(i.severity, i.message) for i in issues if i.path.endswith("ruleset.json")]

    def _errors(self, **sections) -> list:
        return [m for s, m in self._issues(**sections) if s == "error"]

    def test_well_formed_sections_are_accepted(self):
        self.assertEqual([], self._issues(
            locksmithing={"skill": "lockpicking"},
            economy={"currency_name": "credits"},
            calendar={"day_names": ["One", "Two"], "month_names": ["First"], "start_time": {"hour": 9, "minute": 30}},
            spawning={"no_spawn_keywords": ["square"]},
            elites={"chance": 0.1, "stat_multiplier": 1.5, "name_pattern": "{prefix} {name}", "prefixes": ["Alpha"]},
            player_defaults={"player_class": "Scout", "starting_inventory": ["knife", {"item_id": "knife", "quantity": 2}]},
            npc_naming={"first_names": ["Ada", "Bo"], "random_name_pattern": "{first_name} the {title}"},
        ))

    def test_a_misspelt_key_is_an_error(self):
        errors = self._errors(spawning={"no_spawn_keyword": ["square"]})
        self.assertTrue(any("spawning.no_spawn_keyword is not" in m for m in errors), errors)

    def test_pattern_placeholders_that_would_raise_are_errors(self):
        errors = self._errors(elites={"name_pattern": "{rank} {name}"}, npc_naming={"random_name_pattern": "{surname}"})
        self.assertTrue(any("elites.name_pattern" in m and "rank" in m for m in errors), errors)
        self.assertTrue(any("npc_naming.random_name_pattern" in m and "surname" in m for m in errors), errors)

    def test_a_calendar_the_engine_would_replace_is_an_error(self):
        errors = self._errors(calendar={"day_names": ["One", ""], "start_time": {"hour": 24}})
        self.assertTrue(any("calendar.day_names" in m for m in errors), errors)
        self.assertTrue(any("calendar.start_time.hour" in m for m in errors), errors)

    def test_elite_numbers_are_range_checked(self):
        errors = self._errors(elites={"chance": 2, "stat_multiplier": 0})
        self.assertTrue(any("elites.chance" in m for m in errors), errors)
        self.assertTrue(any("elites.stat_multiplier" in m for m in errors), errors)

    def test_starting_inventory_must_name_real_items_with_integer_quantities(self):
        errors = self._errors(player_defaults={"starting_inventory": ["ghost_item", {"item_id": "knife", "quantity": "two"}]})
        self.assertTrue(any("'ghost_item'" in m for m in errors), errors)
        self.assertTrue(any("starting_inventory[1].quantity" in m for m in errors), errors)

    def test_default_spells_must_exist(self):
        errors = self._errors(player_defaults={"magic": {"known_spells": ["fireball"]}})
        self.assertTrue(any("'fireball'" in m for m in errors), errors)

    def test_repeated_first_names_and_unused_keywords_are_warnings(self):
        issues = self._issues(npc_naming={"first_names": ["Ada", "Ada"]}, spawning={"no_spawn_keywords": ["cathedral"]})
        warnings = [m for s, m in issues if s == "warning"]
        self.assertEqual([], [m for s, m in issues if s == "error"])
        self.assertTrue(any("'Ada'" in m for m in warnings), warnings)
        self.assertTrue(any("'cathedral'" in m for m in warnings), warnings)


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
