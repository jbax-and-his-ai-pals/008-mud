"""Loading and validating a content set: the entry points (`load_content_set`, `validate_content_set`).

Part of the content-set validator package (`engine/server/content_set/`); see `__init__.py`.
"""

from __future__ import annotations

import copy
import os
import json
import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from engine import conditions as _conditions
from engine.utils.messages import MESSAGES, template_problems
from .abilities import (_validate_abilities)
from .advancement import (_validate_advancement_content, _validate_starting_content)
from .contracts_items import (_validate_combat_flavor, _validate_container_templates, _validate_contract_content, _validate_crafting_station_references, _validate_item_envelopes, _validate_item_salvage_outputs, _validate_resource_node_yields, _validate_salvage_rules, _validate_vendor_orders)
from .core import (CONTENT_SET_MANIFEST_NAME, CONTENT_SET_SCHEMA_VERSION, ContentSetDefinition, ContentSetIssue, OPTIONAL_MANIFEST_PATHS, REQUIRED_MANIFEST_PATHS, REQUIRED_MANIFEST_STRINGS, REQUIRED_START_FIELDS, RUNTIME_API_VERSION, _CAPABILITY_SYSTEMS, _CONTENT_SET_ID_PATTERN, _REQUIRED_DATA_DIRECTORIES, _build_game_contract, _load_json, _parse_version, _runtime_in_range, _validate_presentation)
from .effects_conditions import (_validate_room_passage_properties)
from .feature_loot import (_validate_ambient_loot_references, _validate_collection_references, _validate_discovery_references, _validate_feature_profile)
from .item_references import (_load_contract_registry, _validate_crafting_quality_contracts, _validate_item_extension_data)
from .knowledge import (_knowledge_campaign_ids, _validate_knowledge_topics)
from .npcs import (_validate_faction_rules, _validate_npc_template_runtime_shapes, _validate_npc_trade_and_loot, _validate_npc_vocabulary)
from .quests_campaigns import (_validate_campaigns, _validate_field_interactions, _validate_instance_quests, _validate_new_quest_objective_types, _validate_quest_choice_outcomes, _validate_quest_rewards, _validate_quest_stages)
from .references import (_validate_ruleset_references)
from .regions import (_region_classification_policy, _region_hazard_coverage_required, _region_level_bands_required, _validate_district_contiguity, _validate_district_coverage_policy, _validate_region_classification, _validate_region_hazard_coverage, _validate_region_level_bands, _validate_region_spawners)
from .ruleset import (_refuse_retired_ruleset_keys, _validate_crime_and_debug_rules, _validate_region_property_keys, _validate_room_property_keys, _validate_simple_ruleset_sections)
from .schedules_social import (_validate_npc_schedule_rules, _validate_social_rules)
from .themes_affixes import (_validate_affixes, _validate_dynamic_themes, _validate_item_resistances_and_sets)
from .triggers_dialogue import (_validate_dialogue_content, _validate_scenes, _validate_triggers)
from .vehicles import _validate_vehicles
from .weather_skills import (_validate_skills_rules, _validate_weather_profiles)
from .world import (_validate_authored_world)

from .abilities import (  # noqa: F401
    _ability_ids,
    _condition_issues,
    _validate_abilities,
)
from .advancement import (  # noqa: F401
    _CONTRACT_REGISTRY_CACHE,
    _player_stat_names,
    _ruleset_stat_names,
    _validate_advancement_content,
    _validate_advancement_section,
    _validate_background_stats,
    _validate_item_grant_matchers,
    _validate_starting_content,
)
from .contracts_items import (  # noqa: F401
    FLAVOR_LINES,
    _salvage_rule_issues,
    _validate_combat_flavor,
    _validate_container_templates,
    _validate_contract_content,
    _validate_crafting_station_references,
    _validate_item_envelopes,
    _validate_item_salvage_outputs,
    _validate_resource_node_yields,
    _validate_salvage_rules,
    _validate_vendor_orders,
)
from .core import (  # noqa: F401
    CONTENT_SET_MANIFEST_NAME,
    CONTENT_SET_SCHEMA_VERSION,
    ContentSetDefinition,
    ContentSetIssue,
    GameContract,
    OPTIONAL_MANIFEST_PATHS,
    PRESENTATION_ACCESSIBILITY_KEYS,
    PRESENTATION_KEYS,
    REQUIRED_MANIFEST_PATHS,
    REQUIRED_MANIFEST_STRINGS,
    REQUIRED_START_FIELDS,
    RUNTIME_API_VERSION,
    _CAPABILITY_SYSTEMS,
    _CONTENT_SET_ID_PATTERN,
    _DISABLED_PROGRESSION_MODELS,
    _ITEM_CLASS_READ_PROPERTIES,
    _ITEM_FIELD_KINDS_WHEN_NONE,
    _ITEM_FIXED_KEYS,
    _REQUIRED_DATA_DIRECTORIES,
    _RULESET_SYSTEMS,
    _THEME_PACK_ID_PATTERN,
    _build_game_contract,
    _item_field_kinds,
    _json_kind,
    _load_definitions,
    _load_json,
    _parse_version,
    _runtime_in_range,
    _validate_presentation,
)
from .definitions import (  # noqa: F401
    _item_placement_override_issues,
    _load_definition_ids,
    _teleport_destinations,
)
from .effects_conditions import (  # noqa: F401
    ENV_INTERACTION_KEYS,
    EXIT_REQUIREMENT_KEYS,
    _CAMPAIGN_KEYS,
    _CAMPAIGN_NODE_KEYS,
    _CAMPAIGN_TRANSITION_KEYS,
    _check_condition,
    _check_effect_block,
    _check_effect_guards,
    _check_exit_consume_list,
    _check_node_effects_do_not_raise,
    _check_reveal_exit,
    _check_room_reference,
    _condition_leaves,
    _effect_identifiers,
    _flags_set_by,
    _guaranteed_leaves,
    _validate_room_passage_properties,
)
from .feature_loot import (  # noqa: F401
    LOOT_KEYS,
    _validate_ambient_loot_references,
    _validate_collection_references,
    _validate_discovery_references,
    _validate_feature_profile,
    _validate_loot_settings,
)
from .identifiers import (  # noqa: F401
    _BENEFIT_EFFECTS,
    _CONDITION_REFERENCES,
    _content_identifier_sets,
    _with_ruleset_stats,
)
from .item_references import (  # noqa: F401
    _item_reference_issues,
    _load_contract_registry,
    _recipe_ingredient_issues,
    _validate_crafting_quality_contracts,
    _validate_item_extension_data,
)
from .knowledge import (  # noqa: F401
    _knowledge_campaign_ids,
    _knowledge_region_ids,
    _validate_knowledge_topics,
)
from .npcs import (  # noqa: F401
    _GIFT_PREFERENCE_KEYS,
    _LOOT_ENTRY_KEYS,
    _NPC_PROPERTY_KEYS,
    _SIMPLE_RULESET_SECTION_KEYS,
    _STOCK_ENTRY_KEYS,
    _npc_property_errors,
    _npc_property_near_misses,
    _validate_faction_rules,
    _validate_npc_template_runtime_shapes,
    _validate_npc_trade_and_loot,
    _validate_npc_vocabulary,
)
from .quests_campaigns import (  # noqa: F401
    FIELD_POLARITIES,
    QUEST_REWARD_KEYS,
    _FIELD_INTERACTION_KEYS,
    _INTRO_BEAT_KEYS,
    _STAGE_KEYS,
    _STAGE_TEXT_KEYS,
    _load_recipes,
    _stage_objectives,
    _text_of_set_files,
    _validate_campaigns,
    _validate_field_interactions,
    _validate_instance_quests,
    _validate_new_quest_objective_types,
    _validate_quest_choice_outcomes,
    _validate_quest_rewards,
    _validate_quest_stages,
    _validate_stage_fields,
)
from .references import (  # noqa: F401
    _format_placeholders,
    _quest_board_room_refs,
    _validate_ruleset_references,
)
from .regions import (  # noqa: F401
    _REGION_SPAWNER_KEYS,
    _hazard_bite_problem,
    _region_classification_policy,
    _region_hazard_coverage_required,
    _region_level_bands_required,
    _validate_district_contiguity,
    _validate_district_coverage_policy,
    _validate_region_classification,
    _validate_region_hazard_coverage,
    _validate_region_level_bands,
    _validate_region_spawners,
    validate_region_policy,
)
from .ruleset import (  # noqa: F401
    _CRIME_KEYS,
    _CRIME_NON_NEGATIVE,
    _RETIRED_RULESET_KEYS,
    _THEME_FORMATTED_LISTS,
    _THEME_KEYS,
    _THEME_LITERAL_LISTS,
    _refuse_retired_ruleset_keys,
    _validate_crime_and_debug_rules,
    _validate_region_property_keys,
    _validate_room_property_keys,
    _validate_simple_ruleset_sections,
)
from .schedules_social import (  # noqa: F401
    _validate_npc_schedule_rules,
    _validate_social_rules,
)
from .themes_affixes import (  # noqa: F401
    AFFIX_PREFIX_MODIFIERS,
    _AFFIX_FILE_KEYS,
    _AFFIX_KEYS,
    _validate_affixes,
    _validate_dynamic_themes,
    _validate_item_resistances_and_sets,
)
from .triggers_dialogue import (  # noqa: F401
    _validate_dialogue_content,
    _validate_scenes,
    _validate_triggers,
)
from .weather_skills import (  # noqa: F401
    _QUEST_TEXT_TEMPLATE_FIELDS,
    _QUEST_TEXT_TEMPLATE_TYPES,
    _validate_skills_rules,
    _validate_weather_chances,
    _validate_weather_profiles,
    _validate_weather_shapes,
)
from .world import (  # noqa: F401
    _validate_authored_world,
    _validate_patrol_routes,
)


def _resolve_manifest_path(content_set_path: Path | str) -> Path:
    """Return the manifest path for a package directory or manifest filename."""

    path = Path(content_set_path)
    return path / CONTENT_SET_MANIFEST_NAME if path.is_dir() else path


# Loading a set reads and validates every file in it, and a test suite does that once per test. A test run
# turns this on (`tests/__init__.py`) and a set that has not changed on disk is then answered from memory; a
# running server never does, so there is nothing to go stale.
_LOAD_CACHE: dict[tuple, tuple] | None = None


def enable_load_cache() -> None:
    global _LOAD_CACHE
    if _LOAD_CACHE is None:
        _LOAD_CACHE = {}


def _package_fingerprint(root: Path) -> tuple:
    """Every file under a set with its size and modification time: any edit changes it."""
    entries = []
    for directory, _names, files in os.walk(root):
        for name in files:
            try:
                info = os.stat(os.path.join(directory, name))
            except OSError:
                continue
            entries.append((os.path.join(directory, name), info.st_mtime_ns, info.st_size))
    entries.sort()
    return tuple(entries)


def load_content_set(
    content_set_path: Path | str,
    runtime_api: str = RUNTIME_API_VERSION,
) -> tuple[ContentSetDefinition | None, list[ContentSetIssue]]:
    """Load and validate one content set without starting a game runtime."""

    if _LOAD_CACHE is None:
        return _load_content_set_uncached(content_set_path, runtime_api)
    manifest = _resolve_manifest_path(content_set_path).resolve()
    key = (str(manifest), runtime_api, _package_fingerprint(manifest.parent))
    if key not in _LOAD_CACHE:
        _LOAD_CACHE[key] = copy.deepcopy(_load_content_set_uncached(content_set_path, runtime_api))
    return copy.deepcopy(_LOAD_CACHE[key])


def _load_content_set_uncached(
    content_set_path: Path | str,
    runtime_api: str = RUNTIME_API_VERSION,
) -> tuple[ContentSetDefinition | None, list[ContentSetIssue]]:
    manifest_path = _resolve_manifest_path(content_set_path).resolve()
    issues: list[ContentSetIssue] = []
    payload = _load_json(manifest_path, issues, "content-set manifest")
    if not isinstance(payload, dict):
        if payload is not None:
            issues.append(ContentSetIssue("error", str(manifest_path), "content-set manifest must be a JSON object"))
        return None, issues

    package_root = manifest_path.parent
    for key in REQUIRED_MANIFEST_STRINGS:
        value = payload.get(key)
        if not isinstance(value, str) or value.strip() == "":
            issues.append(ContentSetIssue("error", str(manifest_path), f"missing/invalid string field '{key}'"))

    content_set_id = str(payload.get("id", "")).strip()
    if content_set_id and _CONTENT_SET_ID_PATTERN.fullmatch(content_set_id) is None:
        issues.append(ContentSetIssue("error", str(manifest_path), "id must match [a-z][a-z0-9_]*"))

    schema_version = str(payload.get("manifest_schema_version", "")).strip()
    if schema_version and schema_version != CONTENT_SET_SCHEMA_VERSION:
        issues.append(
            ContentSetIssue(
                "error",
                str(manifest_path),
                f"unsupported manifest_schema_version '{schema_version}', expected '{CONTENT_SET_SCHEMA_VERSION}'",
            )
        )

    minimum = str(payload.get("engine_api_min", "")).strip()
    maximum = str(payload.get("engine_api_max", "")).strip()
    lower = _parse_version(minimum)
    upper = _parse_version(maximum)
    if minimum and maximum:
        if lower is None or upper is None:
            issues.append(ContentSetIssue("error", str(manifest_path), "engine_api_min/max must be dotted numeric versions"))
        elif lower > upper:
            issues.append(ContentSetIssue("error", str(manifest_path), "engine_api_min must be <= engine_api_max"))
        elif not _runtime_in_range(runtime_api, minimum, maximum):
            issues.append(
                ContentSetIssue(
                    "error",
                    str(manifest_path),
                    f"runtime API {runtime_api} outside supported range {minimum}..{maximum}",
                )
            )

    paths = payload.get("paths")
    if not isinstance(paths, dict):
        issues.append(ContentSetIssue("error", str(manifest_path), "paths must be an object"))
        return None, issues

    resolved_paths: dict[str, Path] = {}
    for key in REQUIRED_MANIFEST_PATHS:
        value = paths.get(key)
        if not isinstance(value, str) or value.strip() == "":
            issues.append(ContentSetIssue("error", str(manifest_path), f"paths.{key} must be a non-empty string"))
            continue
        resolved_paths[key] = (package_root / value).resolve()

    # Every optional path must be a non-empty string when it is named at all; what
    # each one *contains* is checked by its own branch below.
    for key in OPTIONAL_MANIFEST_PATHS:
        if key not in paths:
            continue
        value = paths.get(key)
        if not isinstance(value, str) or value.strip() == "":
            issues.append(ContentSetIssue("error", str(manifest_path), f"paths.{key} must be a non-empty string when provided"))

    feature_profile_path: Path | None = None
    profile_value = paths.get("feature_profile")
    if isinstance(profile_value, str) and profile_value.strip():
        feature_profile_path = (package_root / profile_value).resolve()
        profile_payload = _load_json(feature_profile_path, issues, "feature profile")
        if profile_payload is not None and not isinstance(profile_payload, dict):
            issues.append(ContentSetIssue("error", str(feature_profile_path), "feature profile must be a JSON object"))
        content_dir = resolved_paths.get("content_root")
        campaign_ids = _knowledge_campaign_ids(content_dir, []) if content_dir is not None else set()
        # The selected profile, and the set's other profiles beside it: they are
        # authored to be selected, and would boot with the same silent defaults.
        profile_paths = [feature_profile_path] + [
            path.resolve() for path in sorted(feature_profile_path.parent.glob("*.profile.json"))
            if path.resolve() != feature_profile_path
        ]
        for path in profile_paths:
            payload_here = profile_payload if path == feature_profile_path else _load_json(path, issues, "feature profile")
            if isinstance(payload_here, dict):
                _validate_feature_profile(payload_here, path, issues, campaign_ids)
    opening_path: Path | None = None
    opening_payload: dict[str, Any] = {}
    opening_value = paths.get("opening")
    if isinstance(opening_value, str) and opening_value.strip():
        opening_path = (package_root / opening_value).resolve()
        raw_opening = _load_json(opening_path, issues, "opening scenario")
        if raw_opening is not None and not isinstance(raw_opening, dict):
            issues.append(ContentSetIssue("error", str(opening_path), "opening scenario must be a JSON object"))
        elif isinstance(raw_opening, dict):
            opening_payload = raw_opening

    content_root = resolved_paths.get("content_root")
    if content_root is not None:
        if not content_root.is_dir():
            issues.append(ContentSetIssue("error", str(manifest_path), f"paths.content_root does not resolve to a directory: {content_root}"))
        else:
            required_directories = list(_REQUIRED_DATA_DIRECTORIES)
            declared_capabilities = payload.get("capabilities")
            if isinstance(declared_capabilities, list) and "quests" in declared_capabilities:
                # Campaigns are currently a quest-progression implementation,
                # so their authored data belongs to the same optional system.
                required_directories.extend(("quests", "campaigns"))
            for directory in required_directories:
                if not (content_root / directory).is_dir():
                    issues.append(ContentSetIssue("error", str(content_root), f"missing required data directory '{directory}'"))

    ruleset_payload: dict[str, Any] = {}
    presentation_payload: dict[str, Any] = {}
    for key, label in (("ruleset", "ruleset"), ("presentation", "presentation")):
        target = resolved_paths.get(key)
        if target is None:
            continue
        nested_payload = _load_json(target, issues, label)
        if nested_payload is not None and not isinstance(nested_payload, dict):
            issues.append(ContentSetIssue("error", str(target), f"{label} must be a JSON object"))
        elif key == "ruleset" and isinstance(nested_payload, dict):
            ruleset_payload = nested_payload
        elif key == "presentation" and isinstance(nested_payload, dict):
            if _validate_presentation(nested_payload, target, issues):
                presentation_payload = nested_payload

    capabilities = payload.get("capabilities")
    capability_values: tuple[str, ...] = ()
    if not isinstance(capabilities, list):
        issues.append(ContentSetIssue("error", str(manifest_path), "capabilities must be an array"))
    else:
        normalized = [str(capability).strip() for capability in capabilities]
        if any(value == "" for value in normalized):
            issues.append(ContentSetIssue("error", str(manifest_path), "capabilities entries must be non-empty strings"))
        if len(set(normalized)) != len(normalized):
            issues.append(ContentSetIssue("error", str(manifest_path), "capabilities entries must be unique"))
        # The vocabulary is the engine's, and until now it had no allowlist here:
        # `"craftting"` validated clean and enabled nothing at all, so a set could
        # be born with a system it never got. The world editor has always filtered
        # against this same list (and parity-checks its copy), which made the
        # editor stricter than the engine it is editing for.
        unknown = sorted(set(normalized) - set(_CAPABILITY_SYSTEMS))
        for capability in unknown:
            issues.append(ContentSetIssue(
                "error", str(manifest_path),
                f"capabilities names '{capability}', which is not an engine capability "
                f"(known: {', '.join(_CAPABILITY_SYSTEMS)}) -- it would enable nothing",
            ))
        capability_values = tuple(normalized)

    start = payload.get("start")
    start_region_id = ""
    start_room_id = ""
    if not isinstance(start, dict):
        issues.append(ContentSetIssue("error", str(manifest_path), "start must be an object"))
    else:
        for key in REQUIRED_START_FIELDS:
            value = start.get(key)
            if not isinstance(value, str) or value.strip() == "":
                issues.append(ContentSetIssue("error", str(manifest_path), f"start.{key} must be a non-empty string"))
        start_region_id = str(start.get("region_id", "")).strip()
        start_room_id = str(start.get("room_id", "")).strip()

    if opening_path is not None and opening_payload:
        opening_scenario_id = str(opening_payload.get("scenario_id", "")).strip()
        if "pace" in opening_payload:
            from engine.utils import pacing

            opening_pace = opening_payload["pace"]
            if opening_pace != "instant" and pacing.resolve_pace(opening_pace) is None:
                issues.append(ContentSetIssue(
                    "error", str(opening_path),
                    f"opening pace {opening_pace!r} is not a pace (\"instant\", a name -- {', '.join(pacing.TEXT_PACES)} -- "
                    f"or characters per second from {pacing.PACE_RANGE[0]} to {pacing.PACE_RANGE[1]})",
                ))
        if opening_scenario_id == "":
            issues.append(ContentSetIssue("error", str(opening_path), "opening scenario requires a non-empty 'scenario_id'"))
        elif start and opening_scenario_id != str(start.get("scenario_id", "")).strip():
            issues.append(ContentSetIssue("error", str(opening_path), "opening scenario_id must match start.scenario_id"))

    game_contract = _build_game_contract(capability_values, ruleset_payload, issues, resolved_paths.get("ruleset", manifest_path))

    if content_root is not None and content_root.is_dir() and start_region_id and start_room_id:
        region_path = content_root / "regions" / f"{start_region_id}.json"
        region_payload = _load_json(region_path, issues, "start region")
        if isinstance(region_payload, dict):
            rooms = region_payload.get("rooms")
            if not isinstance(rooms, dict) or start_room_id not in rooms:
                issues.append(
                    ContentSetIssue(
                        "error",
                        str(region_path),
                        f"start.room_id '{start_room_id}' does not exist in region '{start_region_id}'",
                    )
                )

        _validate_authored_world(content_root, start_region_id, start_room_id, issues)
        _validate_district_contiguity(content_root, issues)
        ruleset_source_path = resolved_paths.get("ruleset")
        if ruleset_source_path is not None:
            require_region_level_bands = _region_level_bands_required(
                ruleset_payload, issues, ruleset_source_path
            )
            require_region_hazard_coverage = _region_hazard_coverage_required(
                ruleset_payload, issues, ruleset_source_path
            )
            require_region_classification, region_biomes, region_types = _region_classification_policy(
                ruleset_payload, issues, ruleset_source_path
            )
            _validate_district_coverage_policy(ruleset_payload, issues, ruleset_source_path)
            _validate_region_level_bands(
                content_root, issues, required=require_region_level_bands
            )
            _validate_region_classification(content_root, issues, required=require_region_classification, biomes=region_biomes, region_types=region_types)
            _validate_region_hazard_coverage(
                content_root, issues, required=require_region_hazard_coverage
            )
            _validate_ruleset_references(content_root, ruleset_payload, issues, ruleset_source_path)
            _validate_ambient_loot_references(content_root, ruleset_payload, issues, ruleset_source_path)
            _validate_advancement_content(content_root, ruleset_payload, issues, ruleset_source_path)
        _validate_starting_content(content_root, issues, ruleset_payload)
        _validate_skills_rules(ruleset_payload, issues, ruleset_source_path)
        _validate_social_rules(ruleset_payload, issues, ruleset_source_path, content_root, capability_values)
        _validate_faction_rules(ruleset_payload, issues, ruleset_source_path)
        _validate_npc_vocabulary(content_root, issues, ruleset_payload)
        _validate_npc_template_runtime_shapes(content_root, issues)
        _validate_npc_trade_and_loot(content_root, issues)
        _validate_npc_schedule_rules(ruleset_payload, issues, ruleset_source_path)
        _validate_weather_profiles(content_root, ruleset_payload, issues, ruleset_source_path)
        _validate_simple_ruleset_sections(content_root, ruleset_payload, issues, ruleset_source_path)
        _validate_crime_and_debug_rules(content_root, ruleset_payload, issues, ruleset_source_path)
        _refuse_retired_ruleset_keys(ruleset_payload, issues, ruleset_source_path)
        _validate_room_property_keys(content_root, ruleset_payload, issues)
        _validate_region_property_keys(content_root, issues)
        _validate_dynamic_themes(content_root, ruleset_payload, issues, ruleset_source_path)
        _validate_affixes(content_root, issues)
        _validate_item_resistances_and_sets(content_root, issues)
        _validate_contract_content(content_root, issues)
        _validate_dialogue_content(content_root, issues, ruleset_payload)
        _validate_triggers(content_root, issues, ruleset_payload)
        _validate_scenes(content_root, issues, ruleset_payload)
        _validate_vehicles(content_root, issues)
        _validate_knowledge_topics(content_root, issues)
        _validate_room_passage_properties(content_root, issues)
        _validate_campaigns(content_root, issues, ruleset_payload)
        _validate_abilities(content_root, issues)
        _validate_item_envelopes(content_root, issues)
        _validate_combat_flavor(content_root, issues)
        _validate_region_spawners(content_root, issues)
        _validate_quest_stages(content_root, issues)
        _validate_quest_rewards(content_root, issues)
        _validate_instance_quests(content_root, issues)
        _validate_field_interactions(content_root, issues)
        _validate_quest_choice_outcomes(content_root, issues)
        _validate_new_quest_objective_types(content_root, issues)
        _validate_collection_references(content_root, issues)
        _validate_discovery_references(content_root, issues)
        # One registry for every check that has to resolve a family or a
        # capability against the content set's own declarations, rather than one
        # parse per check.
        contract_registry = _load_contract_registry(content_root)
        _validate_vendor_orders(content_root, issues)
        _validate_resource_node_yields(content_root, issues)
        _validate_container_templates(content_root, issues)
        _validate_crafting_station_references(content_root, issues)
        _validate_crafting_quality_contracts(content_root, issues, contract_registry)
        _validate_salvage_rules(
            content_root, issues, contract_registry,
            ruleset_path=resolved_paths.get("ruleset"),
            ruleset_payload=ruleset_payload,
        )
        _validate_item_salvage_outputs(content_root, issues, contract_registry)
        _validate_item_extension_data(content_root, issues, ruleset_payload)

    if any(issue.severity == "error" for issue in issues):
        return None, issues

    return (
        ContentSetDefinition(
            manifest_path=manifest_path,
            package_root=package_root,
            content_set_id=content_set_id,
            title=str(payload["title"]).strip(),
            version=str(payload["version"]).strip(),
            content_root=content_root,
            feature_profile_path=feature_profile_path,
            ruleset_path=resolved_paths["ruleset"],
            ruleset=ruleset_payload,
            presentation_path=resolved_paths["presentation"],
            presentation=presentation_payload,
            opening_path=opening_path,
            opening=opening_payload,
            start_region_id=start_region_id,
            start_room_id=start_room_id,
            capabilities=capability_values,
            game_contract=game_contract,
        ),
        issues,
    )


def validate_content_set(content_set_path: Path, runtime_api: str = RUNTIME_API_VERSION) -> list[ContentSetIssue]:
    _definition, issues = load_content_set(content_set_path, runtime_api=runtime_api)
    return issues
