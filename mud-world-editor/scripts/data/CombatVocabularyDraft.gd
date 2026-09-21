# Safe authoring model for data/combat/elements.json.  This file is shared
# vocabulary: contracts, spells and room hazards may name it, so validation is
# deliberately conservative and no write occurs until the local shape is sound.
class_name CombatVocabularyDraft
extends RefCounted

const ConfigurationSave = preload("res://scripts/data/ConfigurationSave.gd")

var path := ""
var disk_hash := ""
var original: Dictionary = {}
var data: Dictionary = {}

static func load(elements_path: String) -> Dictionary:
	if not FileAccess.file_exists(elements_path): return {"ok": false, "error": "No combat vocabulary exists at %s." % elements_path}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(elements_path))
	if not (parsed is Dictionary): return {"ok": false, "error": "Combat vocabulary must contain a JSON object."}
	var shape := ConfigurationSave.shape_error(parsed, [], ["hazards"])
	if shape != "": return {"ok": false, "error": shape}
	if not parsed.get("valid_damage_types", []) is Array: return {"ok": false, "error": "Damage channels must be a list."}
	for hazard in parsed.get("hazards", {}).values():
		if not hazard is Dictionary: return {"ok": false, "error": "Hazards must contain object records; no changes were loaded."}
	var draft := CombatVocabularyDraft.new(); draft.disk_hash = FileAccess.get_sha256(elements_path)
	draft.path = elements_path; draft.original = parsed.duplicate(true); draft.data = parsed.duplicate(true)
	return {"ok": true, "draft": draft}

func set_damage_types(types: Array, default_type: String):
	data["valid_damage_types"] = types.map(func(value): return str(value).strip_edges()); data["default_damage_type"] = default_type.strip_edges()

func set_hazards(hazards: Dictionary): data["hazards"] = hazards.duplicate(true)

func validate() -> Array:
	var errors: Array = []
	var types = data.get("valid_damage_types", [])
	if not (types is Array): return ["valid_damage_types must be a list."]
	var clean := _strings(types)
	if clean.is_empty(): errors.append("At least one damage type is required.")
	if clean.size() != types.size(): errors.append("Damage types must be unique, non-empty names.")
	var default_type := str(data.get("default_damage_type", "")).strip_edges()
	if default_type == "" or not clean.has(default_type): errors.append("default_damage_type must name one declared damage type.")
	var hazards = data.get("hazards", {})
	if not (hazards is Dictionary): return errors + ["hazards must be an object."]
	for hazard_id in hazards:
		var record = hazards[hazard_id]
		if str(hazard_id).strip_edges() == "" or not (record is Dictionary): errors.append("Each hazard needs a non-empty id and an object record."); continue
		var channel := str(record.get("channel", "")).strip_edges()
		if channel == "" or not clean.has(channel): errors.append("Hazard '%s' must use a declared damage channel." % hazard_id)
		if str(record.get("flavor", "")).strip_edges() == "": errors.append("Hazard '%s' needs player-facing flavor text." % hazard_id)
		for key in ["damage", "tick_interval"]:
			if not (record.get(key, null) is float or record.get(key, null) is int) or float(record.get(key, 0.0)) <= 0.0: errors.append("Hazard '%s' %s must be positive." % [hazard_id, key])
	return errors

func save() -> Dictionary:
	var errors := validate()
	if not errors.is_empty(): return {"ok": false, "error": "\n".join(errors)}
	var result := ConfigurationSave.write(path, data, disk_hash)
	if result.get("ok", false):
		original = data.duplicate(true)
		disk_hash = FileAccess.get_sha256(path)
	return result

static func _strings(values: Array) -> Array:
	var out: Array = []
	for value in values:
		var text := str(value).strip_edges()
		if text != "" and not out.has(text): out.append(text)
	return out
