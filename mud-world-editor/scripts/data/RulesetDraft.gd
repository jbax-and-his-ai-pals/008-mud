# scripts/data/RulesetDraft.gd
#
# A ruleset is engine configuration, not disposable editor UI state. This small
# draft model makes one guarantee before a form is allowed to write it: sections
# the current editor does not understand survive verbatim. Typed forms update
# only their owned paths, validate their own shape, and SaveIO verifies the write.

class_name RulesetDraft
extends RefCounted

const ConfigurationSave = preload("res://scripts/data/ConfigurationSave.gd")

var path := ""
var disk_hash := ""
var original: Dictionary = {}
var data: Dictionary = {}

static func load(ruleset_path: String) -> Dictionary:
	if not FileAccess.file_exists(ruleset_path):
		return {"ok": false, "error": "No ruleset exists at %s." % ruleset_path}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(ruleset_path))
	if not (parsed is Dictionary):
		return {"ok": false, "error": "Ruleset at %s is not a JSON object." % ruleset_path}
	var shape := ConfigurationSave.shape_error(parsed, ["factions.extra"], ["world", "world.regions", "status", "systems", "factions", "skills", "skills.stat_bonuses"])
	if shape != "": return {"ok": false, "error": shape}
	var draft := RulesetDraft.new()
	draft.disk_hash = FileAccess.get_sha256(ruleset_path)
	draft.path = ruleset_path
	draft.original = parsed.duplicate(true)
	draft.data = parsed.duplicate(true)
	return {"ok": true, "draft": draft}

func is_dirty() -> bool:
	return JSON.stringify(data) != JSON.stringify(original)

func set_general(ruleset_id: String, world_mode: String, progression_model: String):
	data["ruleset_id"] = ruleset_id.strip_edges()
	data["world_mode"] = world_mode.strip_edges()
	data["progression_model"] = progression_model.strip_edges()

func set_status_stats(stats: Array):
	var status := _section("status")
	status["stats"] = _clean_id_list(stats)

func set_system_enabled(system_id: String, enabled: bool):
	var systems := _section("systems")
	var system = systems.get(system_id, {})
	if not (system is Dictionary): system = {}
	system["enabled"] = enabled
	systems[system_id] = system

func set_faction_extras(extras: Array):
	_section("factions")["extra"] = extras.duplicate(true)

func set_salvage_rules(rules: Dictionary):
	_section("crafting")["salvage_rules"] = rules.duplicate(true)

func set_skill_stat_bonuses(bonuses: Dictionary):
	_section("skills")["stat_bonuses"] = bonuses.duplicate(true)

func set_region_policy(require_classification: bool, require_level_bands: bool,
		require_hazard_coverage: bool, biomes: Array, region_types: Array):
	var regions: Dictionary = _section("world").get("regions", {})
	if not (regions is Dictionary): regions = {}
	_section("world")["regions"] = regions
	regions["require_classification"] = require_classification
	regions["require_level_bands"] = require_level_bands
	regions["require_hazard_coverage"] = require_hazard_coverage
	regions["biomes"] = _clean_id_list(biomes)
	regions["region_types"] = _clean_id_list(region_types)

func validate() -> Array:
	var errors: Array = []
	if str(data.get("ruleset_id", "")).strip_edges() == "":
		errors.append("Ruleset ID is required.")
	var status = data.get("status", {})
	if status is Dictionary and status.has("stats"):
		_validate_unique_strings(status["stats"], "status.stats", errors)
	var regions = data.get("world", {}).get("regions", {}) if data.get("world", {}) is Dictionary else {}
	if regions is Dictionary:
		for key in ["biomes", "region_types"]:
			if regions.has(key): _validate_unique_strings(regions[key], "world.regions.%s" % key, errors)
	var factions = data.get("factions", {})
	if factions is Dictionary and factions.has("extra"):
		if not (factions["extra"] is Array): errors.append("factions.extra must be a list.")
		else:
			var faction_ids := {}
			for entry in factions["extra"]:
				if not entry is Dictionary: errors.append("Each factions.extra entry must be an object."); continue
				var faction_id := str(entry.get("id", "")).strip_edges()
				var disposition := str(entry.get("disposition", "")).strip_edges()
				if faction_id == "": errors.append("A custom faction needs an ID.")
				elif faction_ids.has(faction_id): errors.append("factions.extra repeats '%s'." % faction_id)
				faction_ids[faction_id] = true
				if not disposition in ["hostile", "friendly", "neutral", "player"]:
					errors.append("Faction '%s' has invalid disposition '%s'." % [faction_id, disposition])
	var skills = data.get("skills", {})
	if skills is Dictionary and skills.has("stat_bonuses"):
		var bonuses = skills["stat_bonuses"]
		if not (bonuses is Dictionary): errors.append("skills.stat_bonuses must be an object.")
		else:
			var skill_ids := {}
			for skill_id_variant in bonuses:
				var skill_id := str(skill_id_variant).strip_edges()
				if skill_id == "": errors.append("A skill bonus needs a skill id.")
				elif skill_ids.has(skill_id): errors.append("skills.stat_bonuses repeats '%s'." % skill_id)
				skill_ids[skill_id] = true
	return errors

func save() -> Dictionary:
	var errors := validate()
	if not errors.is_empty(): return {"ok": false, "error": "\n".join(errors)}
	var result := ConfigurationSave.write(path, data, disk_hash)
	if result.get("ok", false):
		original = data.duplicate(true)
		disk_hash = FileAccess.get_sha256(path)
	return result

func _section(key: String) -> Dictionary:
	if not (data.get(key) is Dictionary): data[key] = {}
	return data[key]

static func _clean_id_list(values: Array) -> Array:
	var out: Array = []
	for raw in values:
		var value := str(raw).strip_edges()
		out.append(value)
	return out

static func _validate_unique_strings(value, label: String, errors: Array):
	if not (value is Array):
		errors.append("%s must be a list." % label)
		return
	var seen := {}
	for entry in value:
		var text := str(entry).strip_edges()
		if text == "": errors.append("%s cannot contain an empty value." % label)
		elif seen.has(text): errors.append("%s repeats '%s'." % [label, text])
		seen[text] = true
