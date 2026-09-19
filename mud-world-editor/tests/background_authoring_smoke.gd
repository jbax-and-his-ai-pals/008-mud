# tests/background_authoring_smoke.gd
#
# Backgrounds are authorable, and what the inspector writes is what the
# engine reads. `player/backgrounds.json` (`engine/core/backgrounds.py`) --
# the system that replaced classes -- had no editor surface at all. Run with:
#
#   godot --headless --path mud-world-editor --script tests/background_authoring_smoke.gd

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
	content_set_root = ProjectSettings.globalize_path("res://").path_join("../tmp/background_authoring/content_set")
	data_root = content_set_root.path_join("data")
	python_exe = _python_from_args()
	if python_exe == "":
		python_exe = _probe_python()
	_build_fixture()
	DataRoot._resolved = content_set_root
	DataRoot._source = "test fixture"

	_check_backgrounds_load()
	_check_the_inspector_edits_the_engine_fields()
	_check_stats_are_structural()
	_check_default_marker()
	_check_inventory_is_structural()
	_check_a_new_background_is_usable()
	_check_unmodelled_keys_survive()

	if python_exe != "":
		_check_the_engine_accepts_what_this_wrote()
	else:
		print("\n[engine validation]")
		print("  skip  no Python interpreter found; pass --python <path>")

	if failure_count > 0:
		push_error("background authoring smoke failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- cases -------------------------------------------------------------------

func _check_backgrounds_load() -> void:
	print("\n[backgrounds load]")
	var database := DatabaseManager.new()
	_assert(database.backgrounds.has("wanderer"), "a background in backgrounds.json is loaded")
	_assert(database.get_background_ids().has("wanderer"), "and listed")
	_assert(database.backgrounds_default == "wanderer", "the declared default is read: %s" % database.backgrounds_default)
	_assert(database.dirty_flags.has("background"), "backgrounds have their own dirty state")


func _check_the_inspector_edits_the_engine_fields() -> void:
	print("\n[the inspector]")
	var database := DatabaseManager.new()
	var background: Dictionary = database.backgrounds["wanderer"]
	var holder := _inspector_for("wanderer", background, database)

	var fields := _line_edits(holder)
	var name_field: LineEdit = null
	for line in fields:
		if str(line.text) == "Wanderer": name_field = line; break
	_assert(name_field != null, "the inspector renders the background's name")
	if name_field != null:
		name_field.text_changed.emit("Drifter")
		_assert(str(background.get("name", "")) == "Drifter", "and edits write the engine's field: %s" % str(background.get("name", "")))


func _check_stats_are_structural() -> void:
	print("\n[stats]")
	var database := DatabaseManager.new()
	var background: Dictionary = database.backgrounds["wanderer"]
	var holder := _inspector_for("wanderer", background, database)

	var spins: Array = []
	_find_spinboxes(holder, spins)
	# 8 stats + a starting-gold field.
	_assert(spins.size() >= 8, "at least the 8 stat fields are rendered: %d" % spins.size())
	# strength is authored as 11 in the fixture; find and bump it.
	var strength_spin: SpinBox = null
	for spin in spins:
		if int(spin.value) == 11: strength_spin = spin; break
	_assert(strength_spin != null, "the authored strength value (11) is shown")
	if strength_spin != null:
		strength_spin.value_changed.emit(15)
		_assert(int(background.get("stats", {}).get("strength", 0)) == 15,
			"and editing it writes stats.strength: %s" % str(background.get("stats")))


func _check_default_marker() -> void:
	print("\n[default marker]")
	var database := DatabaseManager.new()
	var labourer: Dictionary = database.backgrounds["labourer"]
	var holder := _inspector_for("labourer", labourer, database)
	var make_default: Button = null
	for button in _buttons(holder):
		if button.text == "Make default": make_default = button; break
	_assert(make_default != null, "a non-default background offers to become the default")
	if make_default == null: return
	make_default.pressed.emit()
	_assert(database.backgrounds_default == "labourer", "pressing it changes the default: %s" % database.backgrounds_default)


func _check_inventory_is_structural() -> void:
	print("\n[inventory]")
	var database := DatabaseManager.new()
	var background: Dictionary = database.backgrounds["wanderer"]
	var starting_size: int = (background.get("inventory", []) as Array).size()
	var holder := _inspector_for("wanderer", background, database)

	var add_item: Button = null
	for button in _buttons(holder):
		if button.text == "+ Item": add_item = button; break
	_assert(add_item != null, "there is an add-inventory-item control")
	if add_item == null: return
	add_item.pressed.emit()
	_assert((background["inventory"] as Array).size() == starting_size + 1, "adding an item appends one")


func _check_a_new_background_is_usable() -> void:
	print("\n[a new background]")
	var database := DatabaseManager.new()
	database.add_background("new_background", {"name": "New Background", "description": "", "stats": {}, "inventory": [], "starting_gold": 0})
	_assert(database.backgrounds.has("new_background"), "it is added to the library")


func _check_unmodelled_keys_survive() -> void:
	print("\n[keys the inspector does not model]")
	var database := DatabaseManager.new()
	var background: Dictionary = database.backgrounds["wanderer"]
	background["some_future_field"] = {"a": 1}
	var holder := _inspector_for("wanderer", background, database)
	_assert(background.get("some_future_field", {}) == {"a": 1}, "an unmodelled background field is kept")
	var mentioned := false
	for note in _labels(holder):
		if note.text.contains("some_future_field"): mentioned = true
	_assert(mentioned, "and named, so an author can see it is there")


func _check_the_engine_accepts_what_this_wrote() -> void:
	print("\n[the engine's verdict]")
	var database := DatabaseManager.new()
	database.add_background("apprentice", {
		"name": "Apprentice",
		"description": "Learning a trade.",
		"stats": {"strength": 10, "dexterity": 10, "constitution": 10, "agility": 10, "intelligence": 12, "wisdom": 10, "spell_power": 2, "magic_resist": 2},
		"equipment": {"body": "item_starter_tunic"},
		"inventory": [{"item_id": "item_starter_dagger", "quantity": 1}],
		"skills": {"crafting": 1},
		"recipes": ["tie_wildflower_posy"],
		"starting_gold": 5,
	})
	var saved := database.save_all()
	_assert(saved.get("ok", false), "the edited backgrounds file saves: %s" % str(saved.get("errors", [])))

	var result := EngineValidator.run(content_set_root, repo_root, python_exe)
	_assert(result.get("ran", false), "the validator runs: %s" % result.get("error", ""))
	var background_errors: Array = []
	for issue in result.get("issues", []):
		if str(issue.get("path", "")).contains("backgrounds"):
			background_errors.append(issue)
	_assert(background_errors.is_empty(), "a background edited here validates: %s" % str(background_errors))
	_assert(result.get("ok", false), "and the content set as a whole passes: %s" % str(result.get("issues", [])))


# --- helpers -----------------------------------------------------------------

func _inspector_for(id: String, background: Dictionary, database: DatabaseManager) -> VBoxContainer:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	holders.append(holder)
	var inspector := BackgroundInspector.new(holder, database)
	inspector.build(id, background)
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
	DirAccess.make_dir_recursive_absolute(data_root.path_join("crafting"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("player"))
	DirAccess.make_dir_recursive_absolute(content_set_root.path_join("rules"))
	DirAccess.make_dir_recursive_absolute(content_set_root.path_join("presentation"))

	SaveIO.write_json(content_set_root.path_join("content_set.manifest.json"), {
		"id": "background_fixture", "title": "Background Fixture", "version": "0.1.0",
		"manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
		"paths": {
			"content_root": "data",
			"ruleset": "rules/ruleset.json",
			"presentation": "presentation/default.json",
		},
		"start": {"scenario_id": "fixture", "region_id": "fixture", "room_id": "start"},
		"capabilities": ["inventory", "crafting"],
	})
	SaveIO.write_json(content_set_root.path_join("presentation/default.json"), {
		"presentation_id": "background_fixture", "display_name": "Background Fixture",
	})
	SaveIO.write_json(content_set_root.path_join("rules/ruleset.json"), {"ruleset_id": "background_fixture"})
	SaveIO.write_json(data_root.path_join("regions/fixture.json"), {
		"region_id": "fixture", "rooms": {"start": {"name": "Start", "exits": {}}},
	})
	SaveIO.write_json(data_root.path_join("items/starter.json"), {
		"item_starter_dagger": {"name": "starter dagger", "type": "Weapon", "value": 5, "weight": 0.5},
		"item_starter_tunic": {"name": "starter tunic", "type": "Armor", "value": 5, "weight": 1.0},
	})
	SaveIO.write_json(data_root.path_join("crafting/basics.json"), {
		"tie_wildflower_posy": {
			"name": "Tie Wildflower Posy", "description": "A small bouquet.",
			"result_item_id": "item_starter_dagger", "result_quantity": 1,
			"ingredients": [{"item_id": "item_starter_dagger", "quantity": 1}],
		},
	})
	SaveIO.write_json(data_root.path_join("player/backgrounds.json"), {
		"_comment": "kept",
		"_default": "wanderer",
		"wanderer": {
			"name": "Wanderer",
			"description": "Nothing marks you out yet.",
			"stats": {
				"strength": 11, "dexterity": 11, "constitution": 11, "agility": 11,
				"intelligence": 10, "wisdom": 11, "spell_power": 2, "magic_resist": 3,
			},
			"inventory": [{"item_id": "item_starter_dagger", "quantity": 1}],
			"skills": {"crafting": 0},
			"recipes": [],
			"starting_gold": 0,
		},
		"labourer": {
			"name": "Labourer",
			"description": "Strong back, honest work.",
			"stats": {
				"strength": 13, "dexterity": 10, "constitution": 12, "agility": 9,
				"intelligence": 9, "wisdom": 10, "spell_power": 0, "magic_resist": 2,
			},
			"inventory": [{"item_id": "item_starter_dagger", "quantity": 1}],
			"starting_gold": 0,
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
