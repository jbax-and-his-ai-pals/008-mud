# tests/item_station_type_suggestion_smoke.gd
#
# `properties.crafting_station_type` (an item's own scalar property) is what a
# recipe's `station_required` picker matches against
# (`RecipeInspector._station_picker`, which scans every item for this same
# property). It stayed free text -- an author can name a station type nothing
# has used yet -- but had no suggestions, so a typo here silently makes a
# station unreachable from any recipe that meant to name it. See
# docs/plan/editor-coverage-ledger.md family E.
#
#   godot --headless --path mud-world-editor --script tests/item_station_type_suggestion_smoke.gd

extends SceneTree

var failure_count := 0
var scratch: String = ""


func _init() -> void:
	scratch = ProjectSettings.globalize_path("res://").path_join("../tmp/item_station_type_suggestion")
	_rebuild_fixture()

	_check_the_suggestion_list_is_every_other_items_station_type()
	_check_choosing_a_suggestion_writes_it()

	if failure_count > 0:
		push_error("item station type suggestion failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


func _check_the_suggestion_list_is_every_other_items_station_type() -> void:
	print("\n[the suggestion list]")
	var holder := _build_inspector("item_probe")
	var menu := _station_menu_button(holder)
	_assert(menu != null, "the suggestion button was found next to the crafting_station_type row")
	if menu == null:
		return
	menu.about_to_popup.emit()
	var popup := menu.get_popup()
	var offered: Array = []
	for index in range(popup.item_count):
		offered.append(str(popup.get_item_text(index)))
	_assert(offered == ["anvil", "forge"], "it offers every station type in use, sorted (%s)" % str(offered))


func _check_choosing_a_suggestion_writes_it() -> void:
	print("\n[choosing a suggestion]")
	var manager := _manager()
	var holder := _build_inspector_from("item_probe", manager)
	var menu := _station_menu_button(holder)
	menu.about_to_popup.emit()
	var popup := menu.get_popup()
	popup.id_pressed.emit(popup.get_item_id(0))
	_assert(str(manager.items["item_probe"]["properties"].get("crafting_station_type", "")) == "anvil", "picking the first suggestion wrote it")


# --- fixture ----------------------------------------------------------------

func _rebuild_fixture() -> void:
	_remove_recursive(scratch)
	_write("data/items/probe.json", {
		"item_forge": {"name": "Forge", "type": "Item", "weight": 100, "value": 500, "properties": {"crafting_station_type": "forge"}},
		"item_anvil": {"name": "Anvil", "type": "Item", "weight": 80, "value": 300, "properties": {"crafting_station_type": "anvil"}},
		"item_probe": {"name": "Probe", "type": "Item", "weight": 1, "value": 1, "properties": {"crafting_station_type": ""}},
	})


func _write(relative: String, payload: Dictionary) -> void:
	var path := scratch.path_join(relative)
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(payload, "  "))
	file.close()


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			var child := path.path_join(name)
			if dir.current_is_dir():
				_remove_recursive(child)
			else:
				DirAccess.remove_absolute(child)
		name = dir.get_next()
	dir.list_dir_end()
	DirAccess.remove_absolute(path)


# --- harness ------------------------------------------------------------------

func _manager() -> DatabaseManager:
	DataRoot._resolved = scratch
	DataRoot._source = "test fixture"
	return DatabaseManager.new()


func _build_inspector(item_id: String) -> Node:
	return _build_inspector_from(item_id, _manager())


func _build_inspector_from(item_id: String, manager: DatabaseManager) -> Node:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	var inspector := DatabaseInspector.new(holder)
	inspector.set_db_manager(manager)
	inspector.build("item", item_id, manager.items[item_id])
	return holder


## The row is an HBoxContainer with a key LineEdit reading "crafting_station_type";
## the suggestion MenuButton is a sibling further along the same row.
func _station_menu_button(node: Node) -> MenuButton:
	if node is HBoxContainer:
		var key_field: LineEdit = null
		for child in node.get_children():
			if child is LineEdit and str(child.text) == "crafting_station_type": key_field = child
		if key_field != null:
			for child in node.get_children():
				if child is MenuButton: return child
	for child in node.get_children():
		var found := _station_menu_button(child)
		if found != null:
			return found
	return null


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		printerr("  FAIL ", message)
