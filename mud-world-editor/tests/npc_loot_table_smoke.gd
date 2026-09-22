# tests/npc_loot_table_smoke.gd
#
# Two defects in NPCInspector.gd's loot table section, found while adding the
# faction/behavior pickers (docs/plan/editor-coverage-ledger.md family C):
#
#   1. A drop's item id was a Label, so an author could add a drop but never say
#      which item it was without hand-editing the JSON afterward.
#   2. `_build_loot_table` wrote `cur_data["loot_table"] = {}` unconditionally on
#      every open, so viewing an NPC that drops nothing was enough to make it
#      start dropping an empty table on the next save -- the "editor silently
#      rewrote content on open" defect class this project keeps paying for
#      (see SaveIO.gd's int/float normalization history).
#
#   godot --headless --path mud-world-editor --script tests/npc_loot_table_smoke.gd

extends SceneTree

var failure_count := 0
var scratch: String = ""


func _init() -> void:
	scratch = ProjectSettings.globalize_path("res://").path_join("../tmp/npc_loot_table")
	_rebuild_fixture()

	_check_opening_an_npc_with_no_drops_writes_nothing()
	_check_the_item_picker_offers_known_items_and_preselects()
	_check_choosing_a_different_item_renames_the_entry()
	_check_choosing_an_id_already_in_the_table_is_refused()
	_check_gold_value_has_no_picker()

	if failure_count > 0:
		push_error("npc loot table failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


func _check_opening_an_npc_with_no_drops_writes_nothing() -> void:
	print("\n[an NPC with no loot_table]")
	var manager := _manager()
	_build_inspector_from("npc_no_loot", manager)
	_assert(not manager.npcs["npc_no_loot"].has("loot_table"), "opening the panel did not add a loot_table")


func _check_the_item_picker_offers_known_items_and_preselects() -> void:
	print("\n[the item picker]")
	var holder := _build_inspector("npc_looted")
	var picker := _item_picker_for(holder, "item_alpha")
	_assert(picker != null, "the drop's row has an item picker, not a label")
	if picker == null:
		return
	_assert(str(picker.get_item_metadata(picker.selected)) == "item_alpha", "it preselects the entry's own item")
	var offered := _picker_ids(picker)
	_assert(offered.has("item_alpha") and offered.has("item_beta"), "it offers every known item (%s)" % str(offered))


func _check_choosing_a_different_item_renames_the_entry() -> void:
	print("\n[renaming a drop by picking a different item]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_looted", manager)
	var picker := _item_picker_for(holder, "item_alpha")
	var index := _index_for_id(picker, "item_beta")
	# item_beta is already in this table (see fixture); picking it must be
	# refused so it cannot silently overwrite/merge the other drop.
	picker.item_selected.emit(index)
	var table: Dictionary = manager.npcs["npc_looted"]["loot_table"]
	_assert(table.has("item_alpha") and table.has("item_beta"), "a collision leaves both entries alone")

	# A fresh, uncontested id renames cleanly.
	var holder2 := _build_inspector_from("npc_single_drop", manager)
	var picker2 := _item_picker_for(holder2, "item_alpha")
	var index2 := _index_for_id(picker2, "item_beta")
	picker2.item_selected.emit(index2)
	var table2: Dictionary = manager.npcs["npc_single_drop"]["loot_table"]
	_assert(not table2.has("item_alpha") and table2.has("item_beta"), "an uncontested rename moves the entry (%s)" % str(table2.keys()))
	_assert(float(table2.get("item_beta", {}).get("chance", -1)) == 0.25, "the entry's own data moved with it, not a fresh default")


func _check_choosing_an_id_already_in_the_table_is_refused() -> void:
	print("\n[refusing a collision]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_looted", manager)
	var picker := _item_picker_for(holder, "item_alpha")
	var same_index := picker.selected
	picker.item_selected.emit(same_index)
	var table: Dictionary = manager.npcs["npc_looted"]["loot_table"]
	_assert(table.size() == 2, "picking the same item again changes nothing")


func _check_gold_value_has_no_picker() -> void:
	print("\n[gold_value]")
	var holder := _build_inspector("npc_looted")
	var gold_picker := _item_picker_for(holder, "gold_value")
	_assert(gold_picker == null, "the gold row has no item picker to pick an item for")


# --- fixture ----------------------------------------------------------------

func _rebuild_fixture() -> void:
	_remove_recursive(scratch)
	_write("data/items/loot.json", {
		"item_alpha": {"name": "Alpha", "type": "Item", "weight": 1, "value": 1},
		"item_beta": {"name": "Beta", "type": "Item", "weight": 1, "value": 1},
	})
	_write("data/npcs/probe.json", {
		"npc_no_loot": {"name": "No Loot", "description": "", "level": 1, "health": 10, "friendly": false, "properties": {}},
		"npc_looted": {
			"name": "Looted", "description": "", "level": 1, "health": 10, "friendly": false, "properties": {},
			"loot_table": {
				"item_alpha": {"chance": 0.5, "quantity": [1, 1]},
				"item_beta": {"chance": 0.25, "quantity": [1, 2]},
			},
		},
		"npc_single_drop": {
			"name": "Single Drop", "description": "", "level": 1, "health": 10, "friendly": false, "properties": {},
			"loot_table": {"item_alpha": {"chance": 0.25, "quantity": [1, 1]}},
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


## The loot section has no node names to key off, so this walks every row
## (an HBoxContainer whose children include an OptionButton) and returns the
## picker whose currently selected metadata equals `item_id`, or whose row
## contains a Label with that exact text (the gold_value / "not found" case).
func _item_picker_for(node: Node, item_id: String) -> OptionButton:
	for picker in _all_option_buttons(node):
		if str(picker.get_item_metadata(picker.selected)) == item_id:
			return picker
	return null


func _all_option_buttons(node: Node) -> Array:
	var out: Array = []
	if node is OptionButton:
		out.append(node)
	for child in node.get_children():
		out.append_array(_all_option_buttons(child))
	return out


func _picker_ids(picker: OptionButton) -> Array:
	var out: Array = []
	for index in range(picker.item_count):
		var id := str(picker.get_item_metadata(index))
		if id != "":
			out.append(id)
	return out


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
