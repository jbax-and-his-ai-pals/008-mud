# tests/npc_behavior_tuning_smoke.gd
#
# properties.{aggression,flee_threshold,respawn_cooldown,wander_chance,
# move_cooldown,spell_cast_chance,work_location,can_unlock_chests,
# sells_houses}, top-level patrol_points, usable_spells and
# initial_inventory (npc_factory.py:159-240,202-207; ai/movement.py:101-105;
# combat.py:174-180; housing.py; locksmithing.py) had no editor control at
# all -- none of an NPC's own movement/combat tuning, its patrol route, its
# spell pool or its starting inventory could be authored without hand-editing
# JSON. See docs/plan/editor-coverage-ledger.md family C.
#
#   godot --headless --path mud-world-editor --script tests/npc_behavior_tuning_smoke.gd

extends SceneTree

var failure_count := 0
var scratch: String = ""


func _init() -> void:
	scratch = ProjectSettings.globalize_path("res://").path_join("../tmp/npc_behavior_tuning")
	_rebuild_fixture()

	_check_opening_a_plain_npc_writes_nothing()
	_check_editing_a_behavior_fraction()
	_check_editing_work_location_and_clearing_it()
	_check_toggling_a_flag_on_and_off()
	_check_patrol_points_round_trip()
	_check_usable_spells_round_trip()
	_check_initial_inventory_round_trip()
	_check_the_shipped_authored_npc_is_unchanged()

	if failure_count > 0:
		push_error("npc behavior tuning failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


func _check_opening_a_plain_npc_writes_nothing() -> void:
	print("\n[a plain NPC]")
	var manager := _manager()
	_build_inspector_from("npc_plain", manager)
	var npc: Dictionary = manager.npcs["npc_plain"]
	var props: Dictionary = npc.get("properties", {})
	for key in ["aggression", "flee_threshold", "respawn_cooldown", "wander_chance", "move_cooldown", "spell_cast_chance", "work_location", "can_unlock_chests", "sells_houses"]:
		_assert(not props.has(key), "opening the panel did not add properties.%s" % key)
	for key in ["patrol_points", "usable_spells", "initial_inventory"]:
		_assert(not npc.has(key), "opening the panel did not add %s" % key)


func _check_editing_a_behavior_fraction() -> void:
	print("\n[editing a behavior fraction]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_plain", manager)
	var field := _spinbox_after_label(holder, "Aggression")
	_assert(field != null, "the aggression control was found")
	field.value = 0.75
	field.value_changed.emit(0.75)
	_assert(float(manager.npcs["npc_plain"]["properties"]["aggression"]) == 0.75, "aggression was written")


func _check_editing_work_location_and_clearing_it() -> void:
	print("\n[work location]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_plain", manager)
	var field := _line_edit_after_label(holder, "Work location")
	field.text = "town:blacksmith"
	field.text_changed.emit("town:blacksmith")
	_assert(str(manager.npcs["npc_plain"]["properties"]["work_location"]) == "town:blacksmith", "work_location was written")
	field.text = ""
	field.text_changed.emit("")
	_assert(not manager.npcs["npc_plain"]["properties"].has("work_location"), "clearing the field erased the key")


func _check_toggling_a_flag_on_and_off() -> void:
	print("\n[a boolean flag]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_plain", manager)
	var box := _checkbox_labeled(holder, "Can unlock chests")
	box.toggled.emit(true)
	_assert(bool(manager.npcs["npc_plain"]["properties"].get("can_unlock_chests", false)), "the flag was set")
	box.toggled.emit(false)
	_assert(not manager.npcs["npc_plain"]["properties"].has("can_unlock_chests"), "un-toggling erased the key rather than writing false")


func _check_patrol_points_round_trip() -> void:
	print("\n[patrol points]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_plain", manager)
	var add := _button_after_rows(holder, "PatrolPoints", "+ Room")
	add.pressed.emit()
	var rows := _rows(holder, "PatrolPoints")
	_assert(rows.size() == 1, "one row after adding")
	var field := _first_line_edit(rows[0])
	field.text = "market_square"
	field.text_changed.emit("market_square")
	_assert(manager.npcs["npc_plain"]["patrol_points"] == ["market_square"], "the room id was written")
	var remove := _last_button(rows[0])
	remove.pressed.emit()
	_assert(not manager.npcs["npc_plain"].has("patrol_points"), "removing the only stop erased the key")


func _check_usable_spells_round_trip() -> void:
	print("\n[usable spells]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_plain", manager)
	var add := _button_after_rows(holder, "UsableSpells", "+ Spell")
	add.pressed.emit()
	var rows := _rows(holder, "UsableSpells")
	var picker := _first_option_button(rows[0])
	var index := _index_for_id(picker, "spell_firebolt")
	_assert(index != -1, "the picker offers spell_firebolt")
	picker.item_selected.emit(index)
	_assert(manager.npcs["npc_plain"]["usable_spells"] == ["spell_firebolt"], "the spell was written")


func _check_initial_inventory_round_trip() -> void:
	print("\n[initial inventory]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_plain", manager)
	var add := _button_after_rows(holder, "InitialInventory", "+ Item")
	add.pressed.emit()
	var rows := _rows(holder, "InitialInventory")
	var picker := _first_option_button(rows[0])
	var index := _index_for_id(picker, "item_torch")
	picker.item_selected.emit(index)
	var written: Array = manager.npcs["npc_plain"]["initial_inventory"]
	_assert(str(written[0].get("item_id", "")) == "item_torch", "the item choice was written")
	_assert(int(written[0].get("quantity", -1)) == 1, "quantity defaults to 1")


func _check_the_shipped_authored_npc_is_unchanged() -> void:
	print("\n[an already-authored NPC]")
	var manager := _manager()
	var before := JSON.stringify(manager.npcs["npc_tuned"])
	_build_inspector_from("npc_tuned", manager)
	_assert(JSON.stringify(manager.npcs["npc_tuned"]) == before, "opening a fully-authored NPC changed nothing")


# --- fixture ----------------------------------------------------------------

func _rebuild_fixture() -> void:
	_remove_recursive(scratch)
	_write("data/items/loot.json", {"item_torch": {"name": "Torch", "type": "Item", "weight": 1, "value": 1}})
	_write("data/magic/spells.json", {"spell_firebolt": {"name": "Firebolt", "type": "Attack", "mana_cost": 5}})
	_write("data/npcs/probe.json", {
		"npc_plain": {"name": "Plain", "description": "", "level": 1, "health": 10, "friendly": true, "properties": {}},
		"npc_tuned": {
			"name": "Tuned", "description": "", "level": 1, "health": 10, "friendly": true,
			"properties": {"aggression": 0.5, "work_location": "town:forge"},
			"patrol_points": ["a", "b"],
			"usable_spells": ["spell_firebolt"],
			"initial_inventory": [{"item_id": "item_torch", "quantity": 2}],
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


func _build_inspector_from(npc_id: String, manager: DatabaseManager) -> Node:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	var inspector := DatabaseInspector.new(holder)
	inspector.set_db_manager(manager)
	inspector.build("npc", npc_id, manager.npcs[npc_id])
	return holder


func _find_named(node: Node, wanted_name: String) -> Node:
	if str(node.name) == wanted_name:
		return node
	for child in node.get_children():
		var found := _find_named(child, wanted_name)
		if found != null:
			return found
	return null


func _rows(node: Node, container_name: String) -> Array:
	var holder := _find_named(node, container_name)
	if holder == null:
		return []
	var out: Array = []
	for child in holder.get_children():
		if child is HBoxContainer:
			out.append(child)
	return out


func _button_after_rows(node: Node, rows_container_name: String, text: String) -> Button:
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


func _first_line_edit(node: Node) -> LineEdit:
	if node is LineEdit:
		return node
	for child in node.get_children():
		var found := _first_line_edit(child)
		if found != null:
			return found
	return null


func _spinbox_after_label(node: Node, label_text: String) -> SpinBox:
	if node is HBoxContainer and node.get_child_count() >= 2:
		var first := node.get_child(0)
		if first is Label and str(first.text) == label_text and node.get_child(1) is SpinBox:
			return node.get_child(1)
	for child in node.get_children():
		var found := _spinbox_after_label(child, label_text)
		if found != null:
			return found
	return null


func _line_edit_after_label(node: Node, label_text: String) -> LineEdit:
	if node is HBoxContainer and node.get_child_count() >= 2:
		var first := node.get_child(0)
		if first is Label and str(first.text) == label_text and node.get_child(1) is LineEdit:
			return node.get_child(1)
	for child in node.get_children():
		var found := _line_edit_after_label(child, label_text)
		if found != null:
			return found
	return null


func _checkbox_labeled(node: Node, text: String) -> CheckBox:
	if node is CheckBox and str(node.text) == text:
		return node
	for child in node.get_children():
		var found := _checkbox_labeled(child, text)
		if found != null:
			return found
	return null


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
