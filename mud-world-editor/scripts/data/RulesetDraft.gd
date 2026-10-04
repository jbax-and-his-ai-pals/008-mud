# scripts/data/RulesetDraft.gd
#
# A ruleset is engine configuration, not disposable editor UI state. This small
# draft model makes one guarantee before a form is allowed to write it: sections
# the current editor does not understand survive verbatim. Typed forms update
# only their owned paths, validate their own shape, and SaveIO verifies the write.

class_name RulesetDraft
extends RefCounted

const ConfigurationSave = preload("res://scripts/data/ConfigurationSave.gd")
# How a kill's experience can be shared (engine/core/kill_credit.py; schema_parity_smoke ties this to the engine).
const SHARING_MODES := ["proportional", "equal", "killer"]
const SHARING_DEFAULT_MIN_SHARE := 0.05
const SHARING_DEFAULT_MEMORY_SECONDS := 300
const LEVEL_UP_DEFAULT_STAT_GROWTH := 1
const LEVEL_UP_DEFAULT_HEALTH_BASE := 5
# The engine's own words (engine/utils/messages.py; schema_parity_smoke ties these to the engine):
# key -> [the engine's words, the fields a replacement may use].
const MESSAGES := {
	"kill_experience": ["You gain {amount} experience!", ["amount"]],
	"kill_gold": ["You find {amount} {currency}.", ["amount", "currency"]],
	"shared_experience": ["You gain {amount} experience for your part in defeating {name}.", ["amount", "name"]],
	"level_reached": ["You have reached level {level}!", ["level"]],
	"levels_gained": ["You have gained {count} levels and are now level {level}!", ["count", "level"]],
	"defeated": ["You have been defeated!", []],
	"respawn_hint": ["Type 'respawn' to rise again at {place}.", ["place"]],
	"summon_departs": ["Your {name} crumbles to dust.", ["name"]],
	"quest_complete": ["[Quest Complete] {title}", ["title"]],
}

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
	var shape := ConfigurationSave.shape_error(parsed, ["factions.extra", "advancement.grants", "crime.custody.concealed_tool_requirements"], ["world", "world.regions", "status", "systems", "combat", "combat.retreat", "combat.experience_sharing", "factions", "skills", "skills.stat_bonuses", "npc_schedules", "advancement", "advancement.curve", "advancement.level_up", "advancement.level_up.stat_growth", "messages", "quest_generation", "economy", "locksmithing", "calendar", "spawning", "elites", "npc_naming", "player_defaults", "crime", "crime.witness", "crime.consequences", "crime.custody"])
	if shape != "": return {"ok": false, "error": shape}
	var draft := RulesetDraft.new()
	draft.disk_hash = FileAccess.get_sha256(ruleset_path)
	draft.path = ruleset_path
	draft.original = parsed.duplicate(true)
	draft.data = parsed.duplicate(true)
	return {"ok": true, "draft": draft}

func is_dirty() -> bool:
	return JSON.stringify(data) != JSON.stringify(original)

# `ruleset_id` and `world_mode` were written here and read by nothing (the
# world mode is the server's feature profile); the engine now refuses both.
func set_progression_model(progression_model: String):
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

## Why `text` cannot stand in for the engine's words for `key` ("" when it can). The same rule the engine applies.
static func message_problem(key: String, text) -> String:
	if not (text is String) or str(text).strip_edges() == "": return "it must be text"
	var allowed: Array = MESSAGES[key][1]
	var regex := RegEx.new()
	regex.compile("\\{([^{}]*)\\}")
	var stripped := str(text)
	for found in regex.search_all(str(text)):
		var field := found.get_string(1)
		if not (field in allowed): return "{%s} is not a field this message has (it may use: %s)" % [field, ", ".join(allowed.map(func(name): return "{%s}" % name)) if not allowed.is_empty() else "none"]
		stripped = stripped.replace(found.get_string(), "")
	if stripped.contains("{") or stripped.contains("}"): return "it has a stray brace"
	return ""


func set_advancement(advancement: Dictionary):
	if advancement.is_empty(): data.erase("advancement")
	else: data["advancement"] = advancement.duplicate(true)

func set_weather_descriptions(descriptions: Dictionary):
	if descriptions.is_empty(): _section("weather").erase("descriptions")
	else: _section("weather")["descriptions"] = descriptions.duplicate(true)

func set_weather_profiles(profiles: Dictionary):
	if profiles.is_empty(): _section("weather").erase("profiles")
	else: _section("weather")["profiles"] = profiles.duplicate(true)

# null: no table of the set's own, so the engine's plays.
func set_weather_chances(chances):
	if chances == null or (chances is Dictionary and chances.is_empty()): _section("weather").erase("chances")
	else: _section("weather")["chances"] = chances.duplicate(true)

func set_quest_generation(section: Dictionary):
	if section.is_empty(): data.erase("quest_generation")
	else: data["quest_generation"] = section.duplicate(true)

## Replaces each WorldRulesSection-owned section with its composed value; a
## section the form emptied and the file never had is not created.
func set_world_rules(sections: Dictionary):
	for name in ["economy", "locksmithing", "calendar", "spawning", "elites", "npc_naming", "player_defaults", "companions"]:
		if sections.has(name): data[name] = sections[name].duplicate(true)
		else: data.erase(name)

func set_crime(section: Dictionary):
	if section.is_empty(): data.erase("crime")
	else: data["crime"] = section.duplicate(true)

func set_social(section: Dictionary):
	if section.is_empty(): data.erase("social")
	else: data["social"] = section.duplicate(true)

func set_loot(section: Dictionary):
	if section.is_empty(): data.erase("loot")
	else: data["loot"] = section.duplicate(true)

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
	for retired in ["ruleset_id", "world_mode"]:
		if data.has(retired):
			errors.append("%s is not read by anything and has been removed; delete it from the ruleset." % retired)
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
	var said = data.get("messages", {})
	if said is Dictionary:
		for key in said:
			if not MESSAGES.has(str(key)): errors.append("messages.%s is not a message the engine says (known: %s)." % [str(key), ", ".join(MESSAGES.keys())]); continue
			var problem := message_problem(str(key), said[key])
			if problem != "": errors.append("messages.%s: %s." % [str(key), problem])
	var level_up = data.get("advancement", {}).get("level_up", {}) if data.get("advancement", {}) is Dictionary else {}
	if level_up is Dictionary and not level_up.is_empty():
		var growth = level_up.get("stat_growth", {})
		if growth is Dictionary:
			for stat in growth:
				if typeof(growth[stat]) not in [TYPE_INT, TYPE_FLOAT] or float(growth[stat]) < 0: errors.append("advancement.level_up.stat_growth.%s must be a number of 0 or more." % str(stat))
		if level_up.has("health_base") and (typeof(level_up["health_base"]) not in [TYPE_INT, TYPE_FLOAT] or float(level_up["health_base"]) < 0): errors.append("advancement.level_up.health_base must be a number of 0 or more.")
	var retreat = data.get("combat", {}).get("retreat", {}) if data.get("combat", {}) is Dictionary else {}
	if retreat is Dictionary and not retreat.is_empty():
		for key in ["base_difficulty", "difficulty_per_hostile_level"]:
			if retreat.has(key) and (typeof(retreat[key]) not in [TYPE_INT, TYPE_FLOAT] or float(retreat[key]) < 0): errors.append("combat.retreat.%s must be a non-negative number." % key)
	var sharing = data.get("combat", {}).get("experience_sharing", {}) if data.get("combat", {}) is Dictionary else {}
	if sharing is Dictionary and not sharing.is_empty():
		if sharing.has("mode") and not (str(sharing["mode"]) in SHARING_MODES): errors.append("combat.experience_sharing.mode must be one of %s." % ", ".join(SHARING_MODES))
		if sharing.has("min_share") and (typeof(sharing["min_share"]) not in [TYPE_INT, TYPE_FLOAT] or float(sharing["min_share"]) < 0 or float(sharing["min_share"]) >= 1): errors.append("combat.experience_sharing.min_share must be a number from 0 up to (not including) 1.")
		if sharing.has("memory_seconds") and (typeof(sharing["memory_seconds"]) not in [TYPE_INT, TYPE_FLOAT] or float(sharing["memory_seconds"]) < 0): errors.append("combat.experience_sharing.memory_seconds must be a number of seconds, 0 or more.")
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

## The subset of `content_set/references.py::_validate_ruleset_references` a form edit can
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
## and expect a string back -- mirrors `content_set/weather_skills.py::_validate_weather_shapes`.
static func _validate_string_map(value, label: String, errors: Array):
	if not (value is Dictionary):
		errors.append("%s must be an object." % label)
		return
	for key in value:
		if not (value[key] is String):
			errors.append("%s.%s must be a string." % [label, str(key)])
