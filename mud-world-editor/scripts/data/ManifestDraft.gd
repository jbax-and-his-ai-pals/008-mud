# scripts/data/ManifestDraft.gd
#
# The content set's manifest is configuration: it names the set, its paths, where
# a character starts, and which systems exist. Batch 6B's gate is that an author
# can change the start and a capability *after* creation, and that the engine --
# not this form -- says whether the result is coherent.
#
# So a draft owns only the fields the dialog shows, keeps everything else verbatim,
# and saves through the same staged engine verdict the ruleset and contract dialogs
# use. Two things it deliberately does not offer: the `id` (it is the directory
# name and the identity saves are partitioned by) and `paths` (moving them is a
# different operation with its own refusals -- see `configuration_save.py`).

class_name ManifestDraft
extends RefCounted

const ConfigurationSave = preload("res://scripts/data/ConfigurationSave.gd")
const Scaffold = preload("res://scripts/data/ContentSetScaffold.gd")

var path := ""
var disk_hash := ""
var original: Dictionary = {}
var data: Dictionary = {}

## Read the manifest into this draft. An instance method rather than a static
## factory: a `class_name` that names itself does not compile until the project
## has scanned the script, and a headless check must not depend on that.
func open(manifest_path: String) -> Dictionary:
	if not FileAccess.file_exists(manifest_path):
		return {"ok": false, "error": "No manifest exists at %s." % manifest_path}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(manifest_path))
	if not (parsed is Dictionary):
		return {"ok": false, "error": "The manifest at %s is not a JSON object." % manifest_path}
	# `capabilities` is a list of names, not a list of objects, so only the two
	# object-valued fields go through the shared structural guard.
	var shape := ConfigurationSave.shape_error(parsed, [], ["paths", "start"])
	if shape != "":
		return {"ok": false, "error": shape}
	if not parsed.get("capabilities", []) is Array:
		return {"ok": false, "error": "capabilities must be a list of capability names."}
	path = manifest_path
	disk_hash = FileAccess.get_sha256(manifest_path)
	original = parsed.duplicate(true)
	data = parsed.duplicate(true)
	return {"ok": true, "error": ""}

func is_dirty() -> bool:
	return JSON.stringify(data) != JSON.stringify(original)

func start_field(name: String) -> String:
	var start: Dictionary = data.get("start", {}) if data.get("start") is Dictionary else {}
	return str(start.get(name, ""))

func title_value() -> String:
	return str(data.get("title", ""))

func capabilities() -> Array:
	var declared = data.get("capabilities", [])
	return declared.duplicate() if declared is Array else []

func set_title(value: String) -> void:
	data["title"] = value.strip_edges()

func set_start(scenario_id: String, region_id: String, room_id: String) -> void:
	var start: Dictionary = data.get("start", {}) if data.get("start") is Dictionary else {}
	start["scenario_id"] = scenario_id.strip_edges()
	start["region_id"] = region_id.strip_edges()
	start["room_id"] = room_id.strip_edges()
	data["start"] = start

## Capabilities in the engine's own order, so an unrelated edit does not reorder
## the list and a diff stays readable.
func set_capabilities(enabled: Array) -> void:
	var chosen := {}
	for entry in enabled:
		chosen[str(entry)] = true
	var ordered: Array = []
	for known in Scaffold.CAPABILITIES:
		if chosen.has(known):
			ordered.append(known)
			chosen.erase(known)
	for leftover in chosen:
		ordered.append(leftover)
	data["capabilities"] = ordered

func validate() -> Array:
	var errors: Array = []
	var declared_id := str(data.get("id", "")).strip_edges()
	if declared_id == "":
		errors.append("The manifest needs an id.")
	elif declared_id != str(original.get("id", "")).strip_edges():
		errors.append("The set id is the directory name and cannot be changed here.")
	for key in Scaffold.REQUIRED_STRINGS:
		if str(data.get(key, "")).strip_edges() == "":
			errors.append("Manifest field '%s' cannot be empty." % key)
	var start: Dictionary = data.get("start", {}) if data.get("start") is Dictionary else {}
	for field in Scaffold.REQUIRED_START_FIELDS:
		if str(start.get(field, "")).strip_edges() == "":
			errors.append("start.%s is required: the game has to know where a character begins." % field)
	var seen := {}
	for entry in capabilities():
		var capability := str(entry).strip_edges()
		if not Scaffold.CAPABILITIES.has(capability):
			errors.append("'%s' is not a capability the engine knows. Known: %s." % [capability, ", ".join(Scaffold.CAPABILITIES)])
		elif seen.has(capability):
			errors.append("capabilities repeats '%s'." % capability)
		seen[capability] = true
	return errors

func save() -> Dictionary:
	var errors := validate()
	if not errors.is_empty():
		return {"ok": false, "error": "\n".join(errors)}
	var result := ConfigurationSave.write(path, data, disk_hash)
	if result.get("ok", false):
		original = data.duplicate(true)
		disk_hash = FileAccess.get_sha256(path)
	return result


func save_with_ruleset(ruleset_path: String, ruleset_data: Dictionary, ruleset_hash: String) -> Dictionary:
	var errors := validate()
	if not errors.is_empty():
		return {"ok": false, "error": "\n".join(errors)}
	var result := ConfigurationSave.write_pair(path, data, disk_hash, ruleset_path, ruleset_data, ruleset_hash)
	if result.get("ok", false):
		original = data.duplicate(true)
		disk_hash = FileAccess.get_sha256(path)
	return result
