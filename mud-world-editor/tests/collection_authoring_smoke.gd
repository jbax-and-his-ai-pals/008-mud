# tests/collection_authoring_smoke.gd
#
# Collections are authorable, and what the inspector writes is what the
# engine reads. `collections.json` (`engine/core/collection_manager.py`) was
# loaded by the editor but never written back. Run with:
#
#   godot --headless --path mud-world-editor --script tests/collection_authoring_smoke.gd

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
	content_set_root = ProjectSettings.globalize_path("res://").path_join("../tmp/collection_authoring/content_set")
	data_root = content_set_root.path_join("data")
	python_exe = _python_from_args()
	if python_exe == "":
		python_exe = _probe_python()
	_build_fixture()
	DataRoot._resolved = content_set_root
	DataRoot._source = "test fixture"

	_check_collections_load()
	_check_the_inspector_edits_the_engine_fields()
	_check_items_are_structural()
	_check_rewards()
	_check_a_new_collection_is_usable()
	_check_unmodelled_keys_survive()

	if python_exe != "":
		_check_the_engine_accepts_what_this_wrote()
	else:
		print("\n[engine validation]")
		print("  skip  no Python interpreter found; pass --python <path>")

	if failure_count > 0:
		push_error("collection authoring smoke failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- cases -------------------------------------------------------------------

func _check_collections_load() -> void:
	print("\n[collections load]")
	var database := DatabaseManager.new()
	_assert(database.collections.has("riverside_gem_ledger"), "a collection in collections.json is loaded")
	_assert(database.get_collection_ids().has("riverside_gem_ledger"), "and listed")
	_assert(database.dirty_flags.has("collection"), "collections have their own dirty state")


func _check_the_inspector_edits_the_engine_fields() -> void:
	print("\n[the inspector]")
	var database := DatabaseManager.new()
	var collection: Dictionary = database.collections["riverside_gem_ledger"]
	var holder := _inspector_for("riverside_gem_ledger", collection, database)

	var fields := _line_edits(holder)
	var name_field: LineEdit = null
	for line in fields:
		if str(line.text) == "Riverside Gem Ledger": name_field = line; break
	_assert(name_field != null, "the inspector renders the collection's name")
	if name_field != null:
		name_field.text_changed.emit("Gem Ledger")
		_assert(str(collection.get("name", "")) == "Gem Ledger", "and edits write the engine's field: %s" % str(collection.get("name", "")))


func _check_items_are_structural() -> void:
	print("\n[items]")
	var database := DatabaseManager.new()
	var collection: Dictionary = database.collections["riverside_gem_ledger"]
	var starting_size: int = (collection.get("items", []) as Array).size()
	var holder := _inspector_for("riverside_gem_ledger", collection, database)

	var add_buttons := _buttons(holder)
	var add_item: Button = null
	for button in add_buttons:
		if button.text == "+ Item": add_item = button; break
	_assert(add_item != null, "there is an add-item control")
	if add_item == null: return
	add_item.pressed.emit()
	_assert((collection["items"] as Array).size() == starting_size + 1, "adding an item appends one")


func _check_rewards() -> void:
	print("\n[rewards]")
	var database := DatabaseManager.new()
	var collection: Dictionary = database.collections["riverside_gem_ledger"]
	var holder := _inspector_for("riverside_gem_ledger", collection, database)

	# The XP and gold spin boxes are the only two in the panel.
	var spins: Array = []
	_find_spinboxes(holder, spins)
	_assert(spins.size() == 2, "the reward has an XP and a gold field: %d" % spins.size())
	if spins.size() != 2: return
	spins[0].value_changed.emit(150)
	_assert(int(collection.get("rewards", {}).get("xp", 0)) == 150, "the XP field writes rewards.xp: %s" % str(collection.get("rewards")))


func _check_a_new_collection_is_usable() -> void:
	print("\n[a new collection]")
	var database := DatabaseManager.new()
	database.add_collection("new_collection", {"name": "New Collection", "description": "", "items": [], "rewards": {}})
	_assert(database.collections.has("new_collection"), "it is added to the library")


func _check_unmodelled_keys_survive() -> void:
	print("\n[keys the inspector does not model]")
	var database := DatabaseManager.new()
	var collection: Dictionary = database.collections["riverside_gem_ledger"]
	collection["some_future_field"] = {"a": 1}
	var holder := _inspector_for("riverside_gem_ledger", collection, database)
	_assert(collection.get("some_future_field", {}) == {"a": 1}, "an unmodelled collection field is kept")
	var mentioned := false
	for note in _labels(holder):
		if note.text.contains("some_future_field"): mentioned = true
	_assert(mentioned, "and named, so an author can see it is there")


func _check_the_engine_accepts_what_this_wrote() -> void:
	print("\n[the engine's verdict]")
	var database := DatabaseManager.new()
	database.add_collection("full_set", {
		"name": "Full Set",
		"description": "One of everything.",
		"items": ["item_rough_gem", "item_polished_gem"],
		"rewards": {"xp": 200, "gold": 50},
	})
	var saved := database.save_all()
	_assert(saved.get("ok", false), "the edited collections file saves: %s" % str(saved.get("errors", [])))

	var result := EngineValidator.run(content_set_root, repo_root, python_exe)
	_assert(result.get("ran", false), "the validator runs: %s" % result.get("error", ""))
	var collection_errors: Array = []
	for issue in result.get("issues", []):
		if str(issue.get("path", "")).contains("collections"):
			collection_errors.append(issue)
	_assert(collection_errors.is_empty(), "a collection edited here validates: %s" % str(collection_errors))
	_assert(result.get("ok", false), "and the content set as a whole passes: %s" % str(result.get("issues", [])))


# --- helpers -----------------------------------------------------------------

func _inspector_for(id: String, collection: Dictionary, database: DatabaseManager) -> VBoxContainer:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	holders.append(holder)
	var inspector := CollectionInspector.new(holder, database)
	inspector.build(id, collection)
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


func _find_spinboxes(node: Node, found: Array) -> void:
	if node is SpinBox:
		found.append(node)
	for child in node.get_children():
		_find_spinboxes(child, found)


func _build_fixture() -> void:
	_remove_recursive(content_set_root)
	DirAccess.make_dir_recursive_absolute(data_root.path_join("items"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("npcs"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("regions"))
	DirAccess.make_dir_recursive_absolute(content_set_root.path_join("rules"))
	DirAccess.make_dir_recursive_absolute(content_set_root.path_join("presentation"))

	SaveIO.write_json(content_set_root.path_join("content_set.manifest.json"), {
		"id": "collection_fixture", "title": "Collection Fixture", "version": "0.1.0",
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
		"presentation_id": "collection_fixture", "display_name": "Collection Fixture",
	})
	SaveIO.write_json(content_set_root.path_join("rules/ruleset.json"), {"ruleset_id": "collection_fixture"})
	SaveIO.write_json(data_root.path_join("regions/fixture.json"), {
		"region_id": "fixture", "rooms": {"start": {"name": "Start", "exits": {}}},
	})
	SaveIO.write_json(data_root.path_join("items/gems.json"), {
		"item_rough_gem": {"name": "rough gem", "type": "Gem", "value": 10, "weight": 0.1},
		"item_polished_gem": {"name": "polished gem", "type": "Gem", "value": 30, "weight": 0.1},
	})
	SaveIO.write_json(data_root.path_join("collections.json"), {
		"_comment": "kept",
		"riverside_gem_ledger": {
			"name": "Riverside Gem Ledger",
			"description": "One of each gem found near Riverside.",
			"items": ["item_rough_gem", "item_polished_gem"],
			"rewards": {"xp": 100, "gold": 20},
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
