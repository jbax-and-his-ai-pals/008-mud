# tests/npc_gift_preferences_smoke.gd
#
# `properties.gift_preferences` (`use_give.py::_gift_affinity`): five lists an
# NPC's gift reactions read from, and none of them had an editor control -- an
# NPC could be given anything and never show a preference, because the shape
# only existed in the reader. See docs/plan/editor-coverage-ledger.md family C.
#
#   godot --headless --path mud-world-editor --script tests/npc_gift_preferences_smoke.gd
#
# Two of the five (`preferred_item_ids`, `disliked_item_ids`) are item-id lists
# and reuse the loot table's picker; the other three (`preferred_categories`,
# `preferred_gift_tags`, `disliked_gift_tags`) are open text vocabularies (an
# item's own `category`/`gift_tags`, not an engine-closed set) and are text
# rows. This checks both shapes: nothing is written by opening, an entry
# round-trips through the real control, and removing the last entry in a list
# erases the list rather than leaving an empty array behind.

extends SceneTree

var failure_count := 0
var scratch: String = ""


func _init() -> void:
	scratch = ProjectSettings.globalize_path("res://").path_join("../tmp/npc_gift_preferences")
	_rebuild_fixture()

	_check_opening_an_npc_with_no_preferences_writes_nothing()
	_check_an_authored_npc_shows_its_lists()
	_check_adding_an_item_entry_and_picking_an_item()
	_check_adding_a_tag_entry_and_typing_a_tag()
	_check_removing_the_last_entry_erases_the_list()

	if failure_count > 0:
		push_error("npc gift preferences failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


func _check_opening_an_npc_with_no_preferences_writes_nothing() -> void:
	print("\n[an NPC with no gift_preferences]")
	var manager := _manager()
	_build_inspector_from("npc_no_prefs", manager)
	var props: Dictionary = manager.npcs["npc_no_prefs"].get("properties", {})
	_assert(not props.has("gift_preferences"), "opening the panel did not add gift_preferences")


func _check_an_authored_npc_shows_its_lists() -> void:
	print("\n[an NPC that already declares preferences]")
	var holder := _build_inspector("npc_liked")
	var item_rows := _rows_under(holder, "GiftItems_preferred_item_ids")
	_assert(item_rows.size() == 1, "one preferred item row (%d)" % item_rows.size())
	var tag_rows := _rows_under(holder, "GiftTags_preferred_gift_tags")
	_assert(tag_rows.size() == 1, "one preferred tag row (%d)" % tag_rows.size())


func _check_adding_an_item_entry_and_picking_an_item() -> void:
	print("\n[adding an item preference]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_no_prefs", manager)
	var add := _button_labeled(holder, "GiftItems_preferred_item_ids", "+ Item")
	_assert(add != null, "the add-item button was found")
	if add == null:
		return
	add.pressed.emit()
	var rows := _rows_under(holder, "GiftItems_preferred_item_ids")
	_assert(rows.size() == 1, "one row after adding")
	var picker := _first_option_button(rows[0])
	var index := _index_for_id(picker, "item_alpha")
	_assert(index != -1, "the picker offers item_alpha")
	picker.item_selected.emit(index)
	var written: Array = manager.npcs["npc_no_prefs"]["properties"]["gift_preferences"]["preferred_item_ids"]
	_assert(written == ["item_alpha"], "the choice was written (%s)" % str(written))


func _check_adding_a_tag_entry_and_typing_a_tag() -> void:
	print("\n[adding a preferred tag]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_no_prefs", manager)
	var add := _button_labeled(holder, "GiftTags_preferred_gift_tags", "+ Tag")
	add.pressed.emit()
	var rows := _rows_under(holder, "GiftTags_preferred_gift_tags")
	var field := _first_line_edit(rows[0])
	field.text = "floral"
	field.text_changed.emit("floral")
	var written: Array = manager.npcs["npc_no_prefs"]["properties"]["gift_preferences"]["preferred_gift_tags"]
	_assert(written == ["floral"], "the typed tag was written (%s)" % str(written))


func _check_removing_the_last_entry_erases_the_list() -> void:
	print("\n[removing the only entry]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_liked", manager)
	var rows := _rows_under(holder, "GiftItems_preferred_item_ids")
	var remove := _last_button(rows[0])
	remove.pressed.emit()
	var prefs: Dictionary = manager.npcs["npc_liked"]["properties"]["gift_preferences"]
	_assert(not prefs.has("preferred_item_ids"), "the now-empty list key was erased, not left as []")


# --- fixture ----------------------------------------------------------------

func _rebuild_fixture() -> void:
	_remove_recursive(scratch)
	_write("data/items/loot.json", {
		"item_alpha": {"name": "Alpha", "type": "Item", "weight": 1, "value": 1},
	})
	_write("data/npcs/probe.json", {
		"npc_no_prefs": {"name": "No Prefs", "description": "", "level": 1, "health": 10, "friendly": true, "properties": {}},
		"npc_liked": {
			"name": "Liked", "description": "", "level": 1, "health": 10, "friendly": true,
			"properties": {"gift_preferences": {"preferred_item_ids": ["item_alpha"], "preferred_gift_tags": ["floral"]}},
		},
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


func _build_inspector(npc_id: String) -> Node:
	return _build_inspector_from(npc_id, _manager())


func _build_inspector_from(npc_id: String, manager: DatabaseManager) -> Node:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	var inspector := DatabaseInspector.new(holder)
	inspector.set_db_manager(manager)
	inspector.build("npc", npc_id, manager.npcs[npc_id])
	return holder


func _rows_under(node: Node, container_name: String) -> Array:
	var holder := _find_named(node, container_name)
	if holder == null:
		return []
	var out: Array = []
	for child in holder.get_children():
		if child is HBoxContainer:
			out.append(child)
	return out


func _find_named(node: Node, wanted_name: String) -> Node:
	if str(node.name) == wanted_name:
		return node
	for child in node.get_children():
		var found := _find_named(child, wanted_name)
		if found != null:
			return found
	return null


## The "+ Item"/"+ Tag" button sits in the header row directly above the named
## rows container, i.e. its previous sibling.
func _button_labeled(node: Node, rows_container_name: String, text: String) -> Button:
	var rows := _find_named(node, rows_container_name)
	if rows == null:
		return null
	var header := rows.get_parent().get_child(rows.get_index() - 1)
	for child in _all_buttons(header):
		if str(child.text) == text:
			return child
	return null


func _all_buttons(node: Node) -> Array:
	var out: Array = []
	if node is Button:
		out.append(node)
	for child in node.get_children():
		out.append_array(_all_buttons(child))
	return out


func _first_option_button(node: Node) -> OptionButton:
	if node is OptionButton:
		return node
	for child in node.get_children():
		var found := _first_option_button(child)
		if found != null:
			return found
	return null


func _first_line_edit(node: Node) -> LineEdit:
	if node is LineEdit:
		return node
	for child in node.get_children():
		var found := _first_line_edit(child)
		if found != null:
			return found
	return null


func _last_button(node: Node) -> Button:
	var buttons := _all_buttons(node)
	return buttons[buttons.size() - 1] if not buttons.is_empty() else null


func _index_for_id(picker: OptionButton, id: String) -> int:
	for index in range(picker.item_count):
		if str(picker.get_item_metadata(index)) == id:
			return index
	return -1


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		printerr("  FAIL ", message)
