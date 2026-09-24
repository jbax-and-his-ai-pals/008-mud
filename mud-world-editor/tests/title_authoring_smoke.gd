# tests/title_authoring_smoke.gd
#
# Titles are authorable, and what the inspector writes is what the engine
# reads. `titles.json` had no surface at all -- the earned-identity system
# that replaced classes was hand-written JSON only. Run with:
#
#   godot --headless --path mud-world-editor --script tests/title_authoring_smoke.gd
#
# The last check hands the saved file to the engine's validator, which checks
# every condition kind against `engine/conditions.py` and every guild's
# `place` against a real region room -- so a title authored here is one the
# game can load and actually grant.

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
	content_set_root = ProjectSettings.globalize_path("res://").path_join("../tmp/title_authoring/content_set")
	data_root = content_set_root.path_join("data")
	python_exe = _python_from_args()
	if python_exe == "":
		python_exe = _probe_python()
	_build_fixture()
	DataRoot._resolved = content_set_root
	DataRoot._source = "test fixture"

	_check_titles_load()
	_check_the_inspector_edits_the_engine_fields()
	_check_empty_condition_is_not_written()
	_check_condition_editor_writes_engine_shape()
	_check_requirements_list()
	_check_conferred_by_guild_picker()
	_check_new_guild_creation()
	_check_a_new_title_is_usable()
	_check_unmodelled_keys_survive()

	if python_exe != "":
		_check_the_engine_accepts_what_this_wrote()
	else:
		print("\n[engine validation]")
		print("  skip  no Python interpreter found; pass --python <path>")

	if failure_count > 0:
		push_error("title authoring smoke failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- cases -------------------------------------------------------------------

func _check_titles_load() -> void:
	print("\n[titles load]")
	var database := DatabaseManager.new()
	_assert(database.titles.has("hand"), "a title in titles.json is loaded")
	_assert(database.get_title_ids().has("hand"), "and listed")
	_assert(database.guilds.has("riverside_workward"), "its guild registry is loaded")
	_assert(database.guild_name("riverside_workward") == "The Riverside Workward", "with the guild's real name")
	_assert(database.dirty_flags.has("title"), "titles have their own dirty state")


func _check_the_inspector_edits_the_engine_fields() -> void:
	print("\n[the inspector]")
	var database := DatabaseManager.new()
	var title: Dictionary = database.titles["hand"]
	var holder := _inspector_for("hand", title, database)

	var fields := _line_edits(holder)
	var name_field: LineEdit = null
	for line in fields:
		if str(line.text) == "Hand": name_field = line; break
	_assert(name_field != null, "the inspector renders the title's name")
	if name_field != null:
		name_field.text_changed.emit("Journeyman")
		_assert(str(title.get("name", "")) == "Journeyman", "and edits write the engine's field: %s" % str(title.get("name", "")))


# A blank condition must never be written merely by opening the inspector --
# `_condition_issues` reports any condition object with no `kind` as an error,
# so a brand-new title with nothing chosen yet must stay conditionless.
func _check_empty_condition_is_not_written() -> void:
	print("\n[a fresh title has no condition]")
	var database := DatabaseManager.new()
	var title: Dictionary = {"name": "Fresh"}
	_inspector_for("fresh", title, database)
	_assert(not title.has("condition"), "building the inspector does not invent a condition: %s" % str(title))


func _check_condition_editor_writes_engine_shape() -> void:
	print("\n[condition editor]")
	var database := DatabaseManager.new()
	var title: Dictionary = {"name": "Fresh"}
	var holder := _inspector_for("fresh", title, database)

	# Both `Conferred by` and `Condition` render an OptionButton; find the one
	# that actually offers condition kinds rather than assuming an index.
	var kind_picker: OptionButton = null
	var chosen_index := -1
	for picker in _option_buttons(holder):
		for index in range(picker.item_count):
			if picker.get_item_text(index) == "level_at_least":
				kind_picker = picker; chosen_index = index; break
		if kind_picker != null: break
	_assert(kind_picker != null, "level_at_least is one of the offered condition kinds")
	if kind_picker == null: return
	kind_picker.item_selected.emit(chosen_index)
	_assert(str(title.get("condition", {}).get("kind", "")) == "level_at_least",
		"picking a kind writes {kind: ...}: %s" % str(title.get("condition")))

	# After a kind is chosen the inspector rebuilds; find the "value" field on
	# the fresh widget tree and set it.
	holder = _inspector_for("fresh", title, database)
	var value_field: LineEdit = null
	for line in _line_edits(holder):
		if line.placeholder_text == "int" and str(line.text) == "0":
			value_field = line; break
	_assert(value_field != null, "the kind's own field (value: int) is rendered")
	if value_field != null:
		value_field.text_changed.emit("5")
		_assert(int(title.get("condition", {}).get("value", 0)) == 5,
			"and writes an int, not a string: %s" % str(title.get("condition")))


func _check_requirements_list() -> void:
	print("\n[requirements list]")
	var database := DatabaseManager.new()
	var title: Dictionary = {"name": "Fresh", "condition": {"kind": "level_at_least", "value": 3}}
	var holder := _inspector_for("fresh", title, database)

	var add_buttons := _buttons(holder)
	var add_requirement: Button = null
	for button in add_buttons:
		if button.text == "+ Requirement": add_requirement = button; break
	_assert(add_requirement != null, "there is an add-requirement control")
	if add_requirement == null: return
	add_requirement.pressed.emit()
	_assert((title.get("requirements", []) as Array).size() == 1, "adding a requirement appends one")
	_assert((title["requirements"][0] as Dictionary).is_empty(), "starting blank, same as a fresh condition")


func _check_conferred_by_guild_picker() -> void:
	print("\n[conferred by]")
	var database := DatabaseManager.new()
	var title: Dictionary = database.titles["hand"]
	var holder := _inspector_for("hand", title, database)
	var pickers := _option_buttons(holder)
	var guild_picker: OptionButton = null
	for picker in pickers:
		for index in range(picker.item_count):
			if picker.get_item_text(index).contains("riverside_workward"): guild_picker = picker; break
	_assert(guild_picker != null, "the existing guild appears in a picker")


func _check_new_guild_creation() -> void:
	print("\n[a new guild]")
	var database := DatabaseManager.new()
	var title: Dictionary = {"name": "Fresh"}
	var holder := _inspector_for("fresh", title, database)

	var pickers := _option_buttons(holder)
	_assert(not pickers.is_empty(), "the conferred-by picker exists")
	if pickers.is_empty(): return
	var guild_picker: OptionButton = pickers[0]
	var new_guild_index := -1
	for index in range(guild_picker.item_count):
		if guild_picker.get_item_text(index).begins_with("+ New guild"): new_guild_index = index; break
	_assert(new_guild_index >= 0, "there is a create-new-guild option")
	if new_guild_index < 0: return
	guild_picker.item_selected.emit(new_guild_index)

	var fields := _line_edits(holder)
	var id_field: LineEdit = null
	var name_field: LineEdit = null
	for line in fields:
		if line.placeholder_text == "guild id": id_field = line
		elif line.placeholder_text.begins_with("guild name"): name_field = line
	_assert(id_field != null and name_field != null, "the new-guild fields appear")
	if id_field == null or name_field == null: return
	id_field.text = "new_lodge"
	name_field.text = "The New Lodge"
	var add_button: Button = null
	for button in _buttons(holder):
		if button.text == "Add": add_button = button; break
	_assert(add_button != null, "a button commits the new guild")
	if add_button == null: return
	add_button.pressed.emit()
	_assert(database.guilds.has("new_lodge"), "the guild is added to the registry: %s" % str(database.guilds.keys()))
	_assert(str(title.get("conferred_by", {}).get("guild_id", "")) == "new_lodge",
		"and the title is conferred by it immediately: %s" % str(title.get("conferred_by")))


func _check_a_new_title_is_usable() -> void:
	print("\n[a new title]")
	var database := DatabaseManager.new()
	database.add_title("new_title", {"name": "New Title", "description": ""})
	_assert(database.titles.has("new_title"), "it is added to the library")
	_assert(not database.titles["new_title"].has("condition"),
		"and starts without a condition rather than an invalid placeholder")


func _check_unmodelled_keys_survive() -> void:
	print("\n[keys the inspector does not model]")
	var database := DatabaseManager.new()
	var title: Dictionary = database.titles["hand"]
	title["some_future_field"] = {"a": 1}
	var holder := _inspector_for("hand", title, database)
	_assert(title.get("some_future_field", {}) == {"a": 1}, "an unmodelled title field is kept")
	var mentioned := false
	for note in _labels(holder):
		if note.text.contains("some_future_field"): mentioned = true
	_assert(mentioned, "and named, so an author can see it is there")


# The proof: the engine resolves what the inspector wrote.
func _check_the_engine_accepts_what_this_wrote() -> void:
	print("\n[the engine's verdict]")
	var database := DatabaseManager.new()
	database.add_guild("new_lodge", "The New Lodge", "fixture:start")
	database.add_title("apprentice", {
		"name": "Apprentice",
		"description": "Newly welcomed.",
		"conferred_by": {"name": "The New Lodge", "guild_id": "new_lodge"},
		"condition": {"kind": "level_at_least", "value": 3},
		"requirements": [{"kind": "skill_at_least", "skill": "crafting", "value": 2}],
	})
	var saved := database.save_all()
	_assert(saved.get("ok", false), "the edited titles file saves: %s" % str(saved.get("errors", [])))

	var result := EngineValidator.run(content_set_root, repo_root, python_exe)
	_assert(result.get("ran", false), "the validator runs: %s" % result.get("error", ""))
	# Errors only. The skill audit reports accurately that `crafting` is named by
	# these titles without a declared level; that is advisory, the gate tolerates
	# it, and a warning is not something this check should fail on.
	var title_errors: Array = []
	for issue in result.get("issues", []):
		if str(issue.get("severity", "")) != "error":
			continue
		if str(issue.get("path", "")).contains("titles"):
			title_errors.append(issue)
	_assert(title_errors.is_empty(), "a title edited here validates: %s" % str(title_errors))
	_assert(result.get("ok", false), "and the content set as a whole passes: %s" % str(result.get("issues", [])))


# --- helpers -----------------------------------------------------------------

func _inspector_for(id: String, title: Dictionary, database: DatabaseManager) -> VBoxContainer:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	holders.append(holder)
	var inspector := TitleInspector.new(holder, database)
	inspector.build(id, title)
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


func _option_buttons(node: Node) -> Array:
	var found: Array = []
	if node is OptionButton:
		found.append(node)
	for child in node.get_children():
		found.append_array(_option_buttons(child))
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
		"id": "title_fixture", "title": "Title Fixture", "version": "0.1.0",
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
		"presentation_id": "title_fixture", "display_name": "Title Fixture",
	})
	SaveIO.write_json(content_set_root.path_join("rules/ruleset.json"), {})
	SaveIO.write_json(data_root.path_join("regions/fixture.json"), {
		"region_id": "fixture", "rooms": {"start": {"name": "Start", "exits": {}}},
	})
	SaveIO.write_json(data_root.path_join("titles.json"), {
		"_comment": "kept",
		"_guilds": {
			"riverside_workward": {"name": "The Riverside Workward", "place": "fixture:start"},
		},
		"hand": {
			"name": "Hand",
			"description": "You have done enough honest work that people ask for you by name.",
			"conferred_by": {"name": "The Riverside Workward", "guild_id": "riverside_workward"},
			"condition": {"kind": "skill_at_least", "skill": "crafting", "value": 3},
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
