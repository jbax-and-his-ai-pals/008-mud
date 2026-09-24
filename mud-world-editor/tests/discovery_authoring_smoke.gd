# tests/discovery_authoring_smoke.gd
#
# Discoveries are authorable, and what the inspector writes is what the engine
# reads. `discoveries.json` (`engine/core/discovery_manager.py`) was loaded by
# the editor but never written back. Run with:
#
#   godot --headless --path mud-world-editor --script tests/discovery_authoring_smoke.gd

extends SceneTree

const SaveIO = preload("res://scripts/data/SaveIO.gd")

var failure_count := 0
var repo_root: String = ""
var content_set_root: String = ""
var data_root: String = ""
var python_exe: String = ""
var holders: Array = []


func _init() -> void:
	repo_root = ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	content_set_root = ProjectSettings.globalize_path("res://").path_join("../tmp/discovery_authoring/content_set")
	data_root = content_set_root.path_join("data")
	python_exe = _python_from_args()
	if python_exe == "":
		python_exe = _probe_python()
	_build_fixture()
	DataRoot._resolved = content_set_root
	DataRoot._source = "test fixture"

	_check_discoveries_load()
	_check_the_inspector_edits_the_engine_fields()
	_check_item_triggers_are_structural()
	_check_tag_triggers()
	_check_a_new_discovery_is_usable()
	_check_unmodelled_keys_survive()

	if python_exe != "":
		_check_the_engine_accepts_what_this_wrote()
	else:
		print("\n[engine validation]")
		print("  skip  no Python interpreter found; pass --python <path>")

	if failure_count > 0:
		push_error("discovery authoring smoke failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- cases -------------------------------------------------------------------

func _check_discoveries_load() -> void:
	print("\n[discoveries load]")
	var database := DatabaseManager.new()
	_assert(database.discoveries.has("riverside_clay"), "a discovery in discoveries.json is loaded")
	_assert(database.get_discovery_ids().has("riverside_clay"), "and listed")
	_assert(database.dirty_flags.has("discovery"), "discoveries have their own dirty state")


func _check_the_inspector_edits_the_engine_fields() -> void:
	print("\n[the inspector]")
	var database := DatabaseManager.new()
	var discovery: Dictionary = database.discoveries["riverside_clay"]
	var holder := _inspector_for("riverside_clay", discovery, database)

	var fields := _line_edits(holder)
	var name_field: LineEdit = null
	for line in fields:
		if str(line.text) == "Riverbank Clay": name_field = line; break
	_assert(name_field != null, "the inspector renders the discovery's name")
	if name_field != null:
		name_field.text_changed.emit("River Clay")
		_assert(str(discovery.get("name", "")) == "River Clay", "and edits write the engine's field: %s" % str(discovery.get("name", "")))


func _check_item_triggers_are_structural() -> void:
	print("\n[item triggers]")
	var database := DatabaseManager.new()
	var discovery: Dictionary = database.discoveries["riverside_clay"]
	_assert((discovery.get("item_ids", []) as Array) == ["item_river_clay"], "the fixture starts with one item trigger")
	var holder := _inspector_for("riverside_clay", discovery, database)

	var add_buttons := _buttons(holder)
	var add_item: Button = null
	for button in add_buttons:
		if button.text == "+ Item": add_item = button; break
	_assert(add_item != null, "there is an add-item control")
	if add_item == null: return
	add_item.pressed.emit()
	_assert((discovery["item_ids"] as Array).size() == 2, "adding a trigger appends one")


func _check_tag_triggers() -> void:
	print("\n[tag triggers]")
	var database := DatabaseManager.new()
	var discovery: Dictionary = {"name": "Fresh", "description": ""}
	var holder := _inspector_for("fresh", discovery, database)
	var tag_field: LineEdit = null
	for line in _line_edits(holder):
		if line.placeholder_text.begins_with("field_material"): tag_field = line; break
	_assert(tag_field != null, "a tag field is offered")
	if tag_field == null: return
	tag_field.text_changed.emit("field_material, gem")
	_assert((discovery.get("item_tags", []) as Array) == ["field_material", "gem"],
		"comma-separated tags become a list: %s" % str(discovery.get("item_tags")))


func _check_a_new_discovery_is_usable() -> void:
	print("\n[a new discovery]")
	var database := DatabaseManager.new()
	database.add_discovery("new_discovery", {"name": "New Discovery", "description": "", "item_ids": []})
	_assert(database.discoveries.has("new_discovery"), "it is added to the library")


func _check_unmodelled_keys_survive() -> void:
	print("\n[keys the inspector does not model]")
	var database := DatabaseManager.new()
	var discovery: Dictionary = database.discoveries["riverside_clay"]
	discovery["some_future_field"] = {"a": 1}
	var holder := _inspector_for("riverside_clay", discovery, database)
	_assert(discovery.get("some_future_field", {}) == {"a": 1}, "an unmodelled discovery field is kept")
	var mentioned := false
	for note in _labels(holder):
		if note.text.contains("some_future_field"): mentioned = true
	_assert(mentioned, "and named, so an author can see it is there")


func _check_the_engine_accepts_what_this_wrote() -> void:
	print("\n[the engine's verdict]")
	var database := DatabaseManager.new()
	database.add_discovery("sunken_lake", {
		"name": "The Sunken Lake",
		"description": "Miners broke through into water no map accounted for.",
		"item_ids": ["item_river_clay"],
		"item_tags": ["field_material"],
	})
	var saved := database.save_all()
	_assert(saved.get("ok", false), "the edited discoveries file saves: %s" % str(saved.get("errors", [])))

	var result := EngineValidator.run(content_set_root, repo_root, python_exe)
	_assert(result.get("ran", false), "the validator runs: %s" % result.get("error", ""))
	var discovery_errors: Array = []
	for issue in result.get("issues", []):
		if str(issue.get("path", "")).contains("discoveries"):
			discovery_errors.append(issue)
	_assert(discovery_errors.is_empty(), "a discovery edited here validates: %s" % str(discovery_errors))
	_assert(result.get("ok", false), "and the content set as a whole passes: %s" % str(result.get("issues", [])))


# --- helpers -----------------------------------------------------------------

func _inspector_for(id: String, discovery: Dictionary, database: DatabaseManager) -> VBoxContainer:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	holders.append(holder)
	var inspector := DiscoveryInspector.new(holder, database)
	inspector.build(id, discovery)
	return holder


func _line_edits(node: Node) -> Array:
	var found: Array = []
	if node is LineEdit:
		found.append(node)
	for child in node.get_children():
		found.append_array(_line_edits(child))
	return found


func _buttons(node: Node) -> Array:
	var found: Array = []
	if node is Button:
		found.append(node)
	for child in node.get_children():
		found.append_array(_buttons(child))
	return found


func _labels(node: Node) -> Array:
	var found: Array = []
	if node is Label:
		found.append(node)
	for child in node.get_children():
		found.append_array(_labels(child))
	return found


func _build_fixture() -> void:
	_remove_recursive(content_set_root)
	DirAccess.make_dir_recursive_absolute(data_root.path_join("items"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("npcs"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("regions"))
	DirAccess.make_dir_recursive_absolute(content_set_root.path_join("rules"))
	DirAccess.make_dir_recursive_absolute(content_set_root.path_join("presentation"))

	SaveIO.write_json(content_set_root.path_join("content_set.manifest.json"), {
		"id": "discovery_fixture", "title": "Discovery Fixture", "version": "0.1.0",
		"manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
		"paths": {
			"content_root": "data",
			"ruleset": "rules/ruleset.json",
			"presentation": "presentation/default.json",
		},
		"start": {"scenario_id": "fixture", "region_id": "fixture", "room_id": "start"},
		"capabilities": ["inventory"],
	})
	SaveIO.write_json(content_set_root.path_join("presentation/default.json"), {
		"presentation_id": "discovery_fixture", "display_name": "Discovery Fixture",
	})
	SaveIO.write_json(content_set_root.path_join("rules/ruleset.json"), {"ruleset_id": "discovery_fixture"})
	SaveIO.write_json(data_root.path_join("regions/fixture.json"), {
		"region_id": "fixture", "rooms": {"start": {"name": "Start", "exits": {}}},
	})
	SaveIO.write_json(data_root.path_join("items/materials.json"), {
		"item_river_clay": {"name": "river clay", "type": "Item", "value": 5, "weight": 0.3},
	})
	SaveIO.write_json(data_root.path_join("discoveries.json"), {
		"_comment": "kept",
		"riverside_clay": {
			"name": "Riverbank Clay",
			"description": "Fine river clay can become vessels and tiles.",
			"item_ids": ["item_river_clay"],
		},
	})


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


func _python_from_args() -> String:
	var args := OS.get_cmdline_user_args()
	for index in range(args.size()):
		if args[index] == "--python" and index + 1 < args.size():
			return args[index + 1]
	return ""


func _probe_python() -> String:
	var candidates := [
		repo_root.path_join(".venv/Scripts/python.exe"),
		repo_root.path_join(".venv/bin/python"),
		repo_root.path_join(".conda/python.exe"),
		"python",
	]
	for candidate in candidates:
		if candidate == "python" or FileAccess.file_exists(candidate):
			return candidate
	return ""


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		push_error("FAIL: " + message)
