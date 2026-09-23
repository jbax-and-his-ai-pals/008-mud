extends RefCounted

const SaveIO = preload("res://scripts/data/SaveIO.gd")
const Validator = preload("res://scripts/data/EngineValidator.gd")

# Structural guards only: a form must not skip entries it cannot render and
# subsequently save a shortened collection. Semantic rules remain engine-owned.
static func shape_error(data: Dictionary, object_lists: Array, objects: Array) -> String:
	for path in object_lists + objects:
		var value = data
		var present := true
		for part in str(path).split("."):
			if not value is Dictionary or not value.has(part): present = false; break
			value = value[part]
		if not present: continue
		if objects.has(path) and not value is Dictionary: return "%s must be an object; no changes were loaded." % path
		if object_lists.has(path):
			if not value is Array: return "%s must be a list; no changes were loaded." % path
			for entry in value:
				if not entry is Dictionary: return "%s contains a non-object entry; no changes were loaded." % path
	return ""

static func write(path: String, data: Dictionary, expected_hash: String) -> Dictionary:
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var python := _python_path(repo)
	var temporary_dir := repo.path_join("tmp/configuration-drafts")
	DirAccess.make_dir_recursive_absolute(temporary_dir)
	var temporary := temporary_dir.path_join("configuration-%s-%s.json" % [OS.get_process_id(), Time.get_ticks_usec()])
	var staged := SaveIO.write_json(temporary, data)
	if not staged.get("ok", false): return staged
	var output: Array = []
	var exit_code := OS.execute(python, [repo.path_join("toolkit/configuration_save.py"), path,
		ProjectSettings.globalize_path(temporary), expected_hash], output, true)
	DirAccess.remove_absolute(ProjectSettings.globalize_path(temporary))
	var raw := str(output[0]) if not output.is_empty() else ""
	var result = Validator.last_json_object(raw)
	if not result is Dictionary:
		return {"ok": false, "error": "Configuration validation could not run (exit %d). Nothing was saved.\n%s" % [exit_code, raw.right(1600)]}
	if exit_code != 0: result["ok"] = false
	return result


## A manifest capability and its explicit ruleset system declaration are one
## authoring decision.  Stage and validate both together so an interrupted or
## refused apply cannot leave the two files contradicting each other.
static func write_pair(path: String, data: Dictionary, expected_hash: String,
		paired_path: String, paired_data: Dictionary, paired_expected_hash: String) -> Dictionary:
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var temporary_dir := repo.path_join("tmp/configuration-drafts")
	DirAccess.make_dir_recursive_absolute(temporary_dir)
	var stamp := "%s-%s" % [OS.get_process_id(), Time.get_ticks_usec()]
	var first_temporary := temporary_dir.path_join("configuration-%s-a.json" % stamp)
	var second_temporary := temporary_dir.path_join("configuration-%s-b.json" % stamp)
	var first_staged := SaveIO.write_json(first_temporary, data)
	var second_staged := SaveIO.write_json(second_temporary, paired_data)
	if not first_staged.get("ok", false) or not second_staged.get("ok", false):
		DirAccess.remove_absolute(first_temporary); DirAccess.remove_absolute(second_temporary)
		return first_staged if not first_staged.get("ok", false) else second_staged
	var output: Array = []
	var exit_code := OS.execute(_python_path(repo), [repo.path_join("toolkit/configuration_transaction.py"), path,
		ProjectSettings.globalize_path(first_temporary), expected_hash, paired_path,
		ProjectSettings.globalize_path(second_temporary), paired_expected_hash], output, true)
	DirAccess.remove_absolute(first_temporary); DirAccess.remove_absolute(second_temporary)
	var raw := str(output[0]) if not output.is_empty() else ""
	var result = Validator.last_json_object(raw)
	if not result is Dictionary:
		return {"ok": false, "error": "Coordinated configuration validation could not run (exit %d). Nothing was saved.\n%s" % [exit_code, raw.right(1600)]}
	if exit_code != 0: result["ok"] = false
	return result


static func _python_path(repo: String) -> String:
	var python := "python"
	for candidate in [repo.path_join(".venv/Scripts/python.exe"), repo.path_join(".venv/bin/python")]:
		if FileAccess.file_exists(candidate): python = candidate; break
	var args := OS.get_cmdline_user_args()
	for i in range(args.size() - 1):
		if args[i] == "--python": python = args[i + 1]
	return python
