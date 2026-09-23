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
	var shape := ConfigurationSave.shape_error(parsed, ["factions.extra", "advancement.grants", "crime.custody.concealed_tool_requirements"], ["world", "world.regions", "status", "systems", "combat", "combat.retreat", "factions", "skills", "skills.stat_bonuses", "npc_schedules", "advancement", "advancement.curve", "quest_generation", "economy", "locksmithing", "calendar", "spawning", "elites", "npc_naming", "player_defaults", "crime", "crime.witness", "crime.consequences", "crime.custody"])
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

# The scheduler is optional: a setting without this section simply leaves NPC
# schedules entirely in template content.  Removing the last authored role and
# category should therefore remove the section instead of leaving a misleading
# empty configuration behind.
func set_npc_schedules(schedule_rules: Dictionary):
	if schedule_rules.is_empty(): data.erase("npc_schedules")
	else: data["npc_schedules"] = schedule_rules.duplicate(true)

func set_advancement(advancement: Dictionary):
	if advancement.is_empty(): data.erase("advancement")
	else: data["advancement"] = advancement.duplicate(true)

func set_weather_descriptions(descriptions: Dictionary):
	if descriptions.is_empty(): _section("weather").erase("descriptions")
	else: _section("weather")["descriptions"] = descriptions.duplicate(true)

func set_weather_profiles(profiles: Dictionary):
	if profiles.is_empty(): _section("weather").erase("profiles")
	else: _section("weather")["profiles"] = profiles.duplicate(true)

func set_quest_generation(section: Dictionary):
	if section.is_empty(): data.erase("quest_generation")
	else: data["quest_generation"] = section.duplicate(true)

## Replaces each WorldRulesSection-owned section with its composed value; a
## section the form emptied and the file never had is not created.
func set_world_rules(sections: Dictionary):
	for name in ["economy", "locksmithing", "calendar", "spawning", "elites", "npc_naming", "player_defaults"]:
		if sections.has(name): data[name] = sections[name].duplicate(true)
		else: data.erase(name)

func set_crime(section: Dictionary):
	if section.is_empty(): data.erase("crime")
	else: data["crime"] = section.duplicate(true)

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
	if data.has("npc_schedules") and not (data["npc_schedules"] is Dictionary):
		errors.append("npc_schedules must be an object.")
	if data.has("advancement") and not (data["advancement"] is Dictionary):
		errors.append("advancement must be an object.")
	var retreat = data.get("combat", {}).get("retreat", {}) if data.get("combat", {}) is Dictionary else {}
	if retreat is Dictionary and not retreat.is_empty():
		for key in ["base_difficulty", "difficulty_per_hostile_level"]:
			if retreat.has(key) and (typeof(retreat[key]) not in [TYPE_INT, TYPE_FLOAT] or float(retreat[key]) < 0): errors.append("combat.retreat.%s must be a non-negative number." % key)
	var weather = data.get("weather", {})
	if weather is Dictionary:
		if weather.has("descriptions"): _validate_string_map(weather["descriptions"], "weather.descriptions", errors)
		if weather.has("profiles"):
			if not (weather["profiles"] is Dictionary): errors.append("weather.profiles must be an object.")
			else:
				for profile_id_variant in weather["profiles"]:
					var profile_id := str(profile_id_variant).strip_edges()
					var profile = weather["profiles"][profile_id_variant]
					if profile_id == "": errors.append("A weather profile needs an id.")
					if not (profile is Dictionary): errors.append("weather.profiles.%s must be an object." % profile_id); continue
					if profile.has("map"): _validate_string_map(profile["map"], "weather.profiles.%s.map" % profile_id, errors)
					if profile.has("travel_notes"): _validate_string_map(profile["travel_notes"], "weather.profiles.%s.travel_notes" % profile_id, errors)
	_validate_quest_generation(data.get("quest_generation", {}), errors)
	# Both are str.format-ted with fixed fields, so any other placeholder raises
	# the first time an elite or a randomly named NPC spawns.
	if data.get("elites") is Dictionary and data["elites"].get("name_pattern") is String:
		_validate_placeholders(data["elites"]["name_pattern"], ["prefix", "name"], "elites.name_pattern", errors)
	if data.get("npc_naming") is Dictionary and data["npc_naming"].get("random_name_pattern") is String:
		_validate_placeholders(data["npc_naming"]["random_name_pattern"], ["first_name", "title"], "npc_naming.random_name_pattern", errors)
	return errors

## The subset of `content_set.py::_validate_ruleset_references` a form edit can
## break on its own. Rooms, items, NPCs and quests are chosen from pickers, so
## only the text an author types freely is rechecked here.
static func _validate_quest_generation(section, errors: Array):
	if not (section is Dictionary):
		errors.append("quest_generation must be an object.")
		return
	var notices = section.get("authored_board_templates", [])
	if notices is Array:
		for entry in notices:
			if entry is Dictionary and entry.get("repeatable") is Dictionary and str(entry["repeatable"].get("unavailable_text", "")).strip_edges() == "":
				errors.append("Repeatable notice '%s' needs text explaining why it is down." % str(entry.get("template_id", "")))
	var naming = section.get("procedural_naming", {})
	if naming is Dictionary and naming.get("default_name_pattern") is String:
		_validate_placeholders(naming["default_name_pattern"], ["Adjective", "Noun"], "quest_generation.procedural_naming.default_name_pattern", errors)
	var instance = section.get("instance_quest", {})
	if instance is Dictionary:
		for key in ["title_pattern", "description_pattern"]:
			if instance.get(key) is String: _validate_placeholders(instance[key], ["creature_name"], "quest_generation.instance_quest.%s" % key, errors)
	var templates = section.get("text_templates", {})
	if templates is Dictionary:
		for quest_type in templates:
			if not (templates[quest_type] is Dictionary): continue
			for key in ["title", "description"]:
				if templates[quest_type].get(key) is String:
					_validate_placeholders(templates[quest_type][key], QUEST_TEXT_FIELDS, "quest_generation.text_templates.%s.%s" % [quest_type, key], errors)

const QUEST_TEXT_FIELDS := [
	"giver_name", "quantity", "target_name_plural", "location_description",
	"item_name_plural", "source_enemy_name_plural", "item_to_deliver_name",
	"recipient_name", "recipient_location_description",
]

static func _validate_placeholders(text: String, allowed: Array, label: String, errors: Array):
	var regex := RegEx.create_from_string("\\{([^{}]*)\\}")
	var unescaped := text.replace("{{", "").replace("}}", "")
	for found in regex.search_all(unescaped):
		var field_name := found.get_string(1)
		if not (field_name in allowed): errors.append("%s uses unknown placeholder {%s}." % [label, field_name])

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

## `information.py`'s `weather` command and `WeatherManager` index these by key
## and expect a string back -- mirrors `content_set.py::_validate_weather_shapes`.
static func _validate_string_map(value, label: String, errors: Array):
	if not (value is Dictionary):
		errors.append("%s must be an object." % label)
		return
	for key in value:
		if not (value[key] is String):
			errors.append("%s.%s must be a string." % [label, str(key)])
