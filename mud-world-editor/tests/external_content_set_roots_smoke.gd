# tests/external_content_set_roots_smoke.gd
#
# An author can keep a content set outside the checkout and still discover it
# from the editor.  Registering is intentionally only a settings edit: it must
# not copy, move, or otherwise mutate the set being registered.

extends SceneTree

const SaveIO = preload("res://scripts/data/SaveIO.gd")

var failure_count := 0
var scratch_root := ""
var settings_path := ""
var previous_settings := ""
var previous_settings_existed := false


func _initialize() -> void:
	# Match DataRoot's canonical spelling.  Comparing an unresolved `../tmp`
	# spelling to a stored normalized root would test a path-string accident,
	# rather than registration and discovery.
	scratch_root = DataRoot._normalize(ProjectSettings.globalize_path("res://").path_join("../tmp/external_content_set_roots_smoke/elsewhere_set"))
	settings_path = ProjectSettings.globalize_path("user://editor_settings.json")
	previous_settings_existed = FileAccess.file_exists(settings_path)
	if previous_settings_existed:
		previous_settings = FileAccess.get_file_as_string(settings_path)
	_remove_recursive(scratch_root.get_base_dir())
	DirAccess.make_dir_recursive_absolute(scratch_root)
	var written := SaveIO.write_json(scratch_root.path_join("content_set.manifest.json"), {
		"id": "elsewhere_set", "title": "Elsewhere Set", "version": "0.1.0",
		"manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
		"paths": {"content_root": "data", "ruleset": "rules/ruleset.json", "presentation": "presentation/default.json"},
		"start": {"scenario_id": "elsewhere_set", "region_id": "start", "room_id": "start"},
		"capabilities": [],
	})
	_assert(written.get("ok", false), "the scratch external set has a manifest")
	SaveIO.write_json(settings_path, {})
	DataRoot._resolved = ""
	DataRoot._source = ""
	call_deferred("_run")


func _run() -> void:
	var invalid := DataRoot.register_content_set_root(scratch_root.get_base_dir())
	_assert(not invalid.get("ok", false), "a parent folder without a manifest cannot be registered")

	var registered := DataRoot.register_content_set_root(scratch_root)
	_assert(registered.get("ok", false), "a manifest-bearing external folder can be registered")
	_assert(DataRoot.is_registered_content_set_root(scratch_root), "the external folder is marked as registered")
	var choices := DataRoot.available_content_sets()
	_assert(choices.has(scratch_root), "the registered external set appears in the chooser list")
	_assert(choices.count(scratch_root) == 1, "the chooser does not duplicate a registered set")

	var second_register := DataRoot.register_content_set_root(scratch_root)
	_assert(second_register.get("ok", false) and second_register.get("already_registered", false),
		"registering the same path again is a harmless no-op")
	_assert(DataRoot.set_root(scratch_root), "the editor accepts the registered set as its active root")
	var remembered := DataRoot.write_settings(scratch_root)
	_assert(remembered.get("ok", false), "the active-root setting writes")
	var payload = JSON.parse_string(FileAccess.get_file_as_string(settings_path))
	_assert(typeof(payload) == TYPE_DICTIONARY and str(payload.get("content_set_root", "")) == scratch_root,
		"the active root is remembered")
	_assert(typeof(payload.get("content_set_roots", [])) == TYPE_ARRAY and payload["content_set_roots"].has(scratch_root),
		"remembering the active root preserves registered roots")

	var active_removal := DataRoot.unregister_content_set_root(scratch_root)
	_assert(not active_removal.get("ok", false), "the active external root cannot be forgotten accidentally")
	_restore_settings()
	DataRoot._resolved = ""
	DataRoot._source = ""
	_remove_recursive(scratch_root.get_base_dir())
	if failure_count > 0:
		push_error("external content-set roots smoke failed (%d)" % failure_count)
		quit(1)
	else:
		print("external content-set roots smoke passed")
		quit(0)


func _restore_settings() -> void:
	if previous_settings_existed:
		var file := FileAccess.open(settings_path, FileAccess.WRITE)
		if file != null:
			file.store_string(previous_settings)
			file.close()
	else:
		DirAccess.remove_absolute(settings_path)


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		var child := path.path_join(name)
		if dir.current_is_dir():
			_remove_recursive(child)
		else:
			DirAccess.remove_absolute(child)
		name = dir.get_next()
	dir.list_dir_end()
	DirAccess.remove_absolute(path)


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		push_error("FAIL: " + message)
