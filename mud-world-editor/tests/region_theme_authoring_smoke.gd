# tests/region_theme_authoring_smoke.gd
#
# `regions/dynamic_themes.json` (world/region_generator.py) had no editor
# control and no validator; it now has both (ThemeInspector,
# content_set.py::_validate_dynamic_themes). fantasy_frontier's three real
# themes and shared word lists are the fixture, and the edited set is run
# through the engine's validator at the end.
#
#   godot --headless --path mud-world-editor --script tests/region_theme_authoring_smoke.gd

extends SceneTree

var failures := 0
var fixture := ""
var inspectors: Array = []


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/region-themes-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "test fixture"
	var path := DatabaseManager.themes_file()
	var original := FileAccess.get_file_as_string(path)

	print("\n[loading and resaving]")
	var manager := DatabaseManager.new()
	_assert(manager.themes.keys() == ["forest", "caves", "mountains"], "the three shipped themes load in order")
	_assert(manager.theme_placeholders.has("adjective") and manager.theme_placeholders.has("noun"), "the shared word lists load")
	var before := JSON.stringify(manager.themes["caves"])
	_inspect(manager, "caves")
	_assert(JSON.stringify(manager.themes["caves"]) == before, "opening a theme writes nothing into it")
	manager.mark_dirty("theme", "caves")
	_assert(manager.save_all().get("ok", false), "saving reported ok")
	_assert(FileAccess.get_file_as_string(path) == original, "an unedited save is byte-identical")

	print("\n[editing]")
	manager = DatabaseManager.new()
	var holder := _inspect(manager, "caves")
	var caves: Dictionary = manager.themes["caves"]
	_edit(holder.find_child("Description", true, false), "A labyrinth of wet stone.")
	var descriptions: TextEdit = holder.find_child("RoomDescriptions", true, false)
	descriptions.text = "A {adjective} passage.\nA {adjective} chamber."
	descriptions.text_changed.emit()
	_assert(caves["room_descriptions"] == ["A {adjective} passage.", "A {adjective} chamber."], "room descriptions are one per line")
	var names: TextEdit = holder.find_child("RoomNames", true, false)
	names.text = "\n  \n"
	names.text_changed.emit()
	_assert(not caves.has("room_names"), "an emptied list is removed, not written as []")
	names.text = "Tunnel"; names.text_changed.emit()

	var troll_row: Node = holder.find_child("Monster_troll", true, false)
	(troll_row.get_node("Weight") as SpinBox).value = 3
	_assert(int(caves["spawner"]["monster_types"]["troll"]) == 3, "a creature weight was written")
	(holder.find_child("LevelMax", true, false) as SpinBox).value = 9
	_assert(caves["spawner"]["level_range"] == [2, 9], "the level range was written as integers")

	_button(holder, "+ Word List").pressed.emit()
	_assert(manager.theme_placeholders.has("word"), "a shared word list was added")
	var word_row: Node = holder.find_child("Words_word", true, false)
	_edit(word_row.get_node("Words"), "hollow, sunken")
	_assert(manager.theme_placeholders["word"] == ["hollow", "sunken"], "its words were written")

	print("\n[creating and deleting]")
	manager.add_theme("swamp", {"name_templates": ["New Region"], "description": "", "room_names": ["Room"], "room_descriptions": ["An empty space."]})
	_assert(manager.save_all().get("ok", false), "saving the edits and a new theme reported ok")
	var reloaded := DatabaseManager.new()
	_assert(reloaded.themes.has("swamp") and reloaded.themes["caves"]["description"] == "A labyrinth of wet stone.", "both reload from disk")
	_assert(reloaded.theme_placeholders["word"] == ["hollow", "sunken"], "and the word list")
	var saved: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	_assert(saved.keys() == ["themes", "placeholders"], "the file keeps its top-level order")

	print("\n[the engine accepts the result]")
	var output: Array = []
	var python := repo.path_join(".venv/Scripts/python.exe")
	if not FileAccess.file_exists(python): python = repo.path_join(".venv/bin/python")
	var code := OS.execute(python, [repo.path_join("toolkit/content_set_validator.py"), fixture], output, true)
	_assert(code == 0, "the engine's validator accepts the edited set")
	if code != 0: print("\n".join(output).right(1500))

	reloaded.delete_entry("theme", "swamp")
	_assert(reloaded.save_all().get("ok", false) and not DatabaseManager.new().themes.has("swamp"), "a deleted theme is gone after reload")

	if failures > 0: push_error("region theme authoring failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _inspect(manager: DatabaseManager, id: String) -> Node:
	var holder := VBoxContainer.new(); root.add_child(holder)
	var inspector := ThemeInspector.new(holder, manager); inspectors.append(inspector)
	inspector.build(id, manager.themes[id])
	return holder


func _button(node: Node, text: String) -> Button:
	if node is Button and str(node.text) == text: return node
	for child in node.get_children():
		var found := _button(child, text)
		if found != null: return found
	return null


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _edit(field: LineEdit, value: String):
	field.text = value; field.text_changed.emit(value)


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
