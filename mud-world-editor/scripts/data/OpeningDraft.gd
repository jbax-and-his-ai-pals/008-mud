# The opening is the author-facing first-session promise: prose and suggested
# actions, coupled to the manifest start only through scenario_id.
class_name OpeningDraft
extends RefCounted

const ConfigurationSave = preload("res://scripts/data/ConfigurationSave.gd")

var path := ""
var disk_hash := ""
var original: Dictionary = {}
var data: Dictionary = {}
var expected_scenario_id := ""

func open(opening_path: String, scenario_id: String) -> Dictionary:
	if not FileAccess.file_exists(opening_path): return {"ok": false, "error": "No opening file exists at %s." % opening_path}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(opening_path))
	if not parsed is Dictionary: return {"ok": false, "error": "The opening file is not a JSON object."}
	if not parsed.get("objectives", []) is Array: return {"ok": false, "error": "opening.objectives must be a list."}
	for entry in parsed.get("objectives", []):
		if not entry is Dictionary: return {"ok": false, "error": "Each opening objective must be an object."}
	path = opening_path; disk_hash = FileAccess.get_sha256(path); original = parsed.duplicate(true); data = parsed.duplicate(true); expected_scenario_id = scenario_id
	return {"ok": true}

func is_dirty() -> bool: return JSON.stringify(data) != JSON.stringify(original)

func validate() -> Array:
	var errors: Array = []
	if str(data.get("scenario_id", "")).strip_edges() != expected_scenario_id: errors.append("The opening scenario id must remain '%s' to match the manifest start." % expected_scenario_id)
	for key in ["heading", "intro", "objectives_heading"]:
		if str(data.get(key, "")).strip_edges() == "": errors.append("opening.%s cannot be empty." % key)
	var seen := {}
	if not data.get("objectives", []) is Array: errors.append("opening.objectives must be a list.")
	else:
		for index in data["objectives"].size():
			var entry = data["objectives"][index]
			if not entry is Dictionary: errors.append("Objective %d must be an object." % (index + 1)); continue
			var objective_id := str(entry.get("id", "")).strip_edges()
			if objective_id == "": errors.append("Objective %d needs an id." % (index + 1))
			elif seen.has(objective_id): errors.append("Opening objectives repeat '%s'." % objective_id)
			seen[objective_id] = true
			for key in ["instruction", "command"]:
				if str(entry.get(key, "")).strip_edges() == "": errors.append("Objective '%s' needs %s." % [objective_id if objective_id != "" else str(index + 1), key])
	return errors

func save() -> Dictionary:
	var errors := validate()
	if not errors.is_empty(): return {"ok": false, "error": "\n".join(errors)}
	var result := ConfigurationSave.write(path, data, disk_hash)
	if result.get("ok", false): original = data.duplicate(true); disk_hash = FileAccess.get_sha256(path)
	return result
