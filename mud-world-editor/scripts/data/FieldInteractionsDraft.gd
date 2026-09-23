# scripts/data/FieldInteractionsDraft.gd
#
# `data/world/field_interactions.json` (`headless/field_fx.py`): which ambient
# fields exist, whether each is positive, neutral or negative, and how strongly
# one suppresses another. The file is optional -- its absence turns the field
# system off -- so a missing file loads as an empty draft and saving creates it
# (`ConfigurationSave` with an empty expected hash). The engine's check is
# `content_set.py::_validate_field_interactions`; this mirrors the parts a form
# can get wrong so a refusal reads in the dialog's own terms.

class_name FieldInteractionsDraft
extends RefCounted

const ConfigurationSave = preload("res://scripts/data/ConfigurationSave.gd")
const POLARITIES := ["positive", "neutral", "negative"]

var path := ""
# `configuration_save.py`'s token for "no file yet"; saving then creates it.
var disk_hash := "absent"
var exists := false
var original: Dictionary = {}
var data: Dictionary = {}


static func config_path() -> String:
	return DataRoot.content_file("world/field_interactions.json")


static func load(file_path: String) -> Dictionary:
	var draft := FieldInteractionsDraft.new()
	draft.path = file_path
	if FileAccess.file_exists(file_path):
		var parsed = JSON.parse_string(FileAccess.get_file_as_string(file_path))
		if not (parsed is Dictionary): return {"ok": false, "error": "field_interactions.json must contain a JSON object."}
		var shape := ConfigurationSave.shape_error(parsed, [], ["polarities", "pairwise_rules"])
		if shape != "": return {"ok": false, "error": shape}
		for targets in parsed.get("pairwise_rules", {}).values():
			if not (targets is Dictionary): return {"ok": false, "error": "Each pairwise rule must be an object of target -> coefficient; no changes were loaded."}
		draft.exists = true
		draft.disk_hash = FileAccess.get_sha256(file_path)
		draft.original = parsed.duplicate(true)
		draft.data = parsed.duplicate(true)
	return {"ok": true, "draft": draft}


func validate() -> Array:
	var errors: Array = []
	var polarities = data.get("polarities", {})
	# The file's presence alone seeds the engine's own default field ("blight"),
	# so a new file has to say which fields this world actually has.
	if not exists and (not (polarities is Dictionary) or polarities.is_empty() or str(data.get("default_field_id", "")) == ""):
		errors.append("A new ambient field setup needs at least one field and a default field.")
	if polarities is Dictionary:
		for field_id in polarities:
			_check_id(str(field_id), "Field", errors)
			if not (str(polarities[field_id]) in POLARITIES): errors.append("Field '%s' needs a polarity of positive, neutral or negative." % field_id)
	var default_id := str(data.get("default_field_id", ""))
	if data.has("default_field_id"): _check_id(default_id, "Default field", errors)
	var fallback = data.get("fallback_positive_suppresses_negative", 0.0)
	if typeof(fallback) not in [TYPE_INT, TYPE_FLOAT] or float(fallback) < 0.0 or float(fallback) > 1.0:
		errors.append("The fallback suppression must be a number from 0 to 1.")
	var rules = data.get("pairwise_rules", {})
	if rules is Dictionary:
		for source_id in rules:
			_check_id(str(source_id), "Rule source", errors)
			for target_id in rules[source_id]:
				_check_id(str(target_id), "Rule target", errors)
				if str(target_id) == str(source_id): errors.append("'%s' cannot suppress itself." % source_id)
	return errors


func save() -> Dictionary:
	var errors := validate()
	if not errors.is_empty(): return {"ok": false, "error": "\n".join(errors)}
	var result := ConfigurationSave.write(path, data, disk_hash)
	if result.get("ok", false):
		original = data.duplicate(true)
		exists = true
		disk_hash = FileAccess.get_sha256(path)
	return result


static func _check_id(value: String, label: String, errors: Array):
	if value.strip_edges() == "": errors.append("%s needs an id." % label)
	elif value != value.strip_edges().to_lower(): errors.append("%s '%s' must be lower-case (the engine reads it as '%s')." % [label, value, value.strip_edges().to_lower()])
