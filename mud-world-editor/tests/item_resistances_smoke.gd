# tests/item_resistances_smoke.gd
#
# properties.resistances (`contracts/equipment.py::armor_resistances`; schema
# `contracts/registry.py:129`): per-damage-type resistance an item grants when
# worn. It is a map, so the generic item-property table only ever showed it
# read-only ("a dedicated item-property editor (not available here yet)"). See
# docs/plan/editor-coverage-ledger.md family D.
#
#   godot --headless --path mud-world-editor --script tests/item_resistances_smoke.gd
#
# Damage types come from this set's own data/combat/elements.json, the same
# vocabulary CombatVocabularyDialog authors -- the picker offers only types
# this set declares. The map is keyed by damage type, so switching a row's
# type is a key rebuild, refused on a collision the same way the loot table's
# item rename is.

extends SceneTree

var failure_count := 0
var scratch: String = ""


func _init() -> void:
	scratch = ProjectSettings.globalize_path("res://").path_join("../tmp/item_resistances")
	_rebuild_fixture()

	_check_opening_an_item_with_no_resistances_writes_nothing()
	_check_it_is_not_also_shown_read_only()
	_check_an_authored_item_shows_its_resistances()
	_check_adding_a_resistance_picks_an_unused_type()
	_check_editing_a_value()
	_check_switching_a_rows_type_is_a_key_rebuild()
	_check_switching_onto_an_existing_type_is_refused()
	_check_removing_the_last_resistance_erases_the_key()
	_check_a_set_with_no_combat_vocabulary_shows_no_section()

	if failure_count > 0:
		push_error("item resistances failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


func _check_opening_an_item_with_no_resistances_writes_nothing() -> void:
	print("\n[an item with no resistances]")
	var manager := _manager()
	_build_inspector_from("item_plain", manager)
	var props: Dictionary = manager.items["item_plain"].get("properties", {})
	_assert(not props.has("resistances"), "opening the panel did not add resistances")


func _check_it_is_not_also_shown_read_only() -> void:
	print("\n[no duplicate read-only row]")
	var holder := _build_inspector("item_armor")
	# PropertyTagRow.build_nested_row always labels its row "<key>: ".
	var found_readonly := false
	for label in _all_labels(holder):
		if str(label.text) == "resistances: ":
			found_readonly = true
	_assert(not found_readonly, "resistances is not also shown as a generic read-only row")


func _check_an_authored_item_shows_its_resistances() -> void:
	print("\n[an authored item]")
	var holder := _build_inspector("item_armor")
	var rows := _rows(holder)
	_assert(rows.size() == 2, "two resistance rows (%d)" % rows.size())


func _check_adding_a_resistance_picks_an_unused_type() -> void:
	print("\n[adding a resistance]")
	var manager := _manager()
	var holder := _build_inspector_from("item_plain", manager)
	var add := _button_labeled(holder, "+ Resistance")
	add.pressed.emit()
	var written: Dictionary = manager.items["item_plain"]["properties"]["resistances"]
	_assert(written.size() == 1, "one resistance was added")
	_assert(written.values()[0] == 0.0, "it defaults to 0.0")


func _check_editing_a_value() -> void:
	print("\n[editing a value]")
	var manager := _manager()
	var holder := _build_inspector_from("item_armor", manager)
	var row: Node = _rows(holder)[0]
	var field := _first_spinbox(row)
	field.value = 0.5
	field.value_changed.emit(0.5)
	var written: Dictionary = manager.items["item_armor"]["properties"]["resistances"]
	_assert(written.values().has(0.5), "the value was written (%s)" % str(written))


func _check_switching_a_rows_type_is_a_key_rebuild() -> void:
	print("\n[switching a row's damage type]")
	var manager := _manager()
	var holder := _build_inspector_from("item_single_res", manager)
	var row: Node = _rows(holder)[0]
	var picker := _first_option_button(row)
	var index := _index_for_id(picker, "poison")
	_assert(index != -1, "the picker offers 'poison'")
	picker.item_selected.emit(index)
	var written: Dictionary = manager.items["item_single_res"]["properties"]["resistances"]
	_assert(written.has("poison") and not written.has("fire"), "the key moved (%s)" % str(written.keys()))
	_assert(written.get("poison", -1.0) == 0.25, "and the value moved with it")


func _check_switching_onto_an_existing_type_is_refused() -> void:
	print("\n[switching onto a type already present]")
	var manager := _manager()
	var holder := _build_inspector_from("item_armor", manager)
	var row: Node = _rows(holder)[0]
	var picker := _first_option_button(row)
	var other_type := _second_resistance_type(manager, "item_armor")
	var index := _index_for_id(picker, other_type)
	picker.item_selected.emit(index)
	var written: Dictionary = manager.items["item_armor"]["properties"]["resistances"]
	_assert(written.size() == 2, "the collision left both resistances alone (%s)" % str(written.keys()))


func _check_removing_the_last_resistance_erases_the_key() -> void:
	print("\n[removing the only resistance]")
	var manager := _manager()
	var holder := _build_inspector_from("item_single_res", manager)
	var row: Node = _rows(holder)[0]
	var remove := _last_button(row)
	remove.pressed.emit()
	_assert(not manager.items["item_single_res"]["properties"].has("resistances"), "the now-empty key was erased")


func _check_a_set_with_no_combat_vocabulary_shows_no_section() -> void:
	print("\n[a set with no data/combat/elements.json]")
	var no_vocab_root: String = scratch.path_join("no_vocab")
	DirAccess.make_dir_recursive_absolute(no_vocab_root.path_join("data/items"))
	_write_to(no_vocab_root, "data/items/probe.json", {"item_probe": {"name": "Probe", "type": "Item", "weight": 1, "value": 1}})
	DataRoot._resolved = no_vocab_root
	DataRoot._source = "test fixture"
	var manager := DatabaseManager.new()
	var holder := _build_inspector_from("item_probe", manager)
	_assert(_button_labeled(holder, "+ Resistance") == null, "no resistances section without a declared vocabulary")


# --- fixture ----------------------------------------------------------------

func _rebuild_fixture() -> void:
	_remove_recursive(scratch)
	_write("data/combat/elements.json", {"valid_damage_types": ["fire", "poison", "cold"]})
	_write("data/items/probe.json", {
		"item_plain": {"name": "Plain", "type": "Item", "weight": 1, "value": 1},
		"item_armor": {
			"name": "Armor", "type": "Armor", "weight": 5, "value": 10,
			"properties": {"resistances": {"fire": 0.1, "cold": 0.2}},
		},
		"item_single_res": {
			"name": "Single Res", "type": "Armor", "weight": 5, "value": 10,
			"properties": {"resistances": {"fire": 0.25}},
		},
	})


func _write(relative: String, payload: Dictionary) -> void:
	_write_to(scratch, relative, payload)


func _write_to(root_dir: String, relative: String, payload: Dictionary) -> void:
	var path := root_dir.path_join(relative)
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


func _find_named(node: Node, wanted_name: String) -> Node:
	if str(node.name) == wanted_name:
		return node
	for child in node.get_children():
		var found := _find_named(child, wanted_name)
		if found != null:
			return found
	return null


func _rows(node: Node) -> Array:
	var holder := _find_named(node, "Resistances")
	if holder == null:
		return []
	var out: Array = []
	for child in holder.get_children():
		if child is HBoxContainer:
			out.append(child)
	return out


func _all_buttons(node: Node) -> Array:
	var out: Array = []
	if node is Button:
		out.append(node)
	for child in node.get_children():
		out.append_array(_all_buttons(child))
	return out


func _button_labeled(node: Node, text: String) -> Button:
	for child in _all_buttons(node):
		if str(child.text) == text:
			return child
	return null


func _last_button(node: Node) -> Button:
	var buttons := _all_buttons(node)
	return buttons[buttons.size() - 1] if not buttons.is_empty() else null


func _first_option_button(node: Node) -> OptionButton:
	if node is OptionButton:
		return node
	for child in node.get_children():
		var found := _first_option_button(child)
		if found != null:
			return found
	return null


func _first_spinbox(node: Node) -> SpinBox:
	if node is SpinBox:
		return node
	for child in node.get_children():
		var found := _first_spinbox(child)
		if found != null:
			return found
	return null


func _all_labels(node: Node) -> Array:
	var out: Array = []
	if node is Label:
		out.append(node)
	for child in node.get_children():
		out.append_array(_all_labels(child))
	return out


func _index_for_id(picker: OptionButton, id: String) -> int:
	for index in range(picker.item_count):
		if str(picker.get_item_metadata(index)) == id:
			return index
	return -1


## Rows render in sorted key order; this returns whichever key is NOT the
## first row's, i.e. the collision target for a two-entry map.
func _second_resistance_type(manager: DatabaseManager, item_id: String) -> String:
	var res: Dictionary = manager.items[item_id]["properties"]["resistances"]
	var keys: Array = res.keys(); keys.sort()
	return str(keys[1]) if keys.size() > 1 else ""


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		printerr("  FAIL ", message)
