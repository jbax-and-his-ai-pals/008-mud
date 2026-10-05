# tests/item_grants_spells_smoke.gd
#
# properties.grants_spells (`npcs/companion_gear.py::granted_spells`): abilities a companion who holds an item can cast (a harp
# that carries a song). The item inspector offers them for a weapon or armour as a picker per ability: opening writes nothing,
# choosing writes the id, and removing the last one erases the key.
#
#   godot --headless --path mud-world-editor --script tests/item_grants_spells_smoke.gd

extends SceneTree

var failure_count := 0
var scratch: String = ""


func _init() -> void:
	scratch = ProjectSettings.globalize_path("res://").path_join("../tmp/item_grants_spells")
	_rebuild_fixture()
	_check_opening_writes_nothing_and_a_weapon_can_add_one()
	_check_choosing_and_removing()
	_check_a_plain_item_is_not_offered_the_section()
	if failure_count > 0:
		push_error("item grants_spells failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


func _check_opening_writes_nothing_and_a_weapon_can_add_one() -> void:
	print("\n[adding]")
	var manager := _manager()
	var holder := _build_inspector_from("item_harp", manager)
	_assert(not manager.items["item_harp"].get("properties", {}).has("grants_spells"), "opening the panel wrote nothing")
	var add := _find_named(holder, "AddGrantedSpell") as Button
	_assert(add != null, "a weapon has the + Ability button")
	add.pressed.emit()
	_assert(manager.items["item_harp"]["properties"].get("grants_spells") == [""], "adding starts an empty slot")


func _check_choosing_and_removing() -> void:
	print("\n[choosing and removing]")
	var manager := _manager()
	var holder := _build_inspector_from("item_harp", manager)
	(_find_named(holder, "AddGrantedSpell") as Button).pressed.emit()
	var picker := _find_named(holder, "GrantedSpellPicker_0") as OptionButton
	var ids: Array = []
	for index in picker.item_count: ids.append(str(picker.get_item_metadata(index)))
	_assert(ids.has("lullaby"), "the set's abilities are offered (%s)" % str(ids))
	picker.select(ids.find("lullaby")); picker.item_selected.emit(ids.find("lullaby"))
	_assert(manager.items["item_harp"]["properties"]["grants_spells"] == ["lullaby"], "choosing writes the id")
	(_find_named(holder, "RemoveGrantedSpell_0") as Button).pressed.emit()
	_assert(not manager.items["item_harp"]["properties"].has("grants_spells"), "removing the last one erases the key")


func _check_a_plain_item_is_not_offered_the_section() -> void:
	print("\n[a plain item]")
	var holder := _build_inspector("item_pebble")
	_assert(_find_named(holder, "AddGrantedSpell") == null, "an ordinary item has no grants-abilities section")


# --- fixture and harness --------------------------------------------------------------

func _rebuild_fixture() -> void:
	_remove_recursive(scratch)
	_write("data/combat/elements.json", {"valid_damage_types": ["fire"]})
	_write("data/magic/probe.json", {"lullaby": {"name": "Lullaby", "description": "", "mana_cost": 0, "cooldown": 1, "target_type": "all_enemies",
		"cast_message": "x", "hit_message": "x", "level_required": 1, "effects": [{"type": "apply_effect", "effect_data": {"name": "Sleep", "tags": ["sleep"]}}]}})
	_write("data/items/probe.json", {
		"item_harp": {"name": "Harp", "type": "Weapon", "weight": 2, "value": 1, "properties": {"damage": 2}},
		"item_pebble": {"name": "Pebble", "type": "Item", "weight": 1, "value": 1, "properties": {}},
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
	if node == null:
		return null
	if str(node.name) == wanted_name:
		return node
	for child in node.get_children():
		var found := _find_named(child, wanted_name)
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


func _assert(condition: bool, message: String) -> void:
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition:
		failure_count += 1
