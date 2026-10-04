# tests/item_attack_modes_smoke.gd
#
# properties.attack_modes (`contracts/equipment.py::attack_modes`): the ways a weapon may be struck, one chosen at random for
# each blow. The item inspector shows them for a weapon: a verb, an optional sentence, an optional damage type and a bonus
# for each; opening writes nothing, a blank erases a key, and the last mode removed erases the list.
#
#   godot --headless --path mud-world-editor --script tests/item_attack_modes_smoke.gd

extends SceneTree

var failure_count := 0
var scratch: String = ""


func _init() -> void:
	scratch = ProjectSettings.globalize_path("res://").path_join("../tmp/item_attack_modes")
	_rebuild_fixture()

	_check_a_weapon_with_one_way_writes_nothing_until_a_mode_is_added()
	_check_only_weapons_are_offered_modes()
	_check_an_authored_spear_shows_both_modes()
	_check_editing_a_mode()
	_check_removing_the_last_mode_erases_the_list()

	if failure_count > 0:
		push_error("item attack modes failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


func _check_a_weapon_with_one_way_writes_nothing_until_a_mode_is_added() -> void:
	print("\n[a weapon with one way]")
	var manager := _manager()
	var holder := _build_inspector_from("item_sword", manager)
	_assert(not manager.items["item_sword"].get("properties", {}).has("attack_modes"), "opening the panel wrote nothing")
	var add := _find_named(holder, "AddAttackMode") as Button
	_assert(add != null, "a weapon has the + Mode button")
	add.pressed.emit()
	var modes: Array = manager.items["item_sword"]["properties"].get("attack_modes", [])
	_assert(modes.size() == 1 and modes[0] == {"verb": "strike"}, "adding one starts a plain {verb: strike}: %s" % str(modes))


func _check_only_weapons_are_offered_modes() -> void:
	print("\n[only a weapon]")
	var holder := _build_inspector("item_cloak")
	_assert(_find_named(holder, "AddAttackMode") == null, "armour has no attack modes section")


func _check_an_authored_spear_shows_both_modes() -> void:
	print("\n[an authored spear]")
	var holder := _build_inspector("item_spear")
	_assert(_find_named(holder, "AttackMode0") != null and _find_named(holder, "AttackMode1") != null, "a card for each mode")
	_assert((_find_named(holder, "Mode_verb_0") as LineEdit).text == "thrust" and (_find_named(holder, "Mode_verb_1") as LineEdit).text == "slash", "each shows its verb")
	_assert((_find_named(holder, "Mode_type_1") as OptionButton).get_item_text((_find_named(holder, "Mode_type_1") as OptionButton).selected) == "slashing", "and its damage type")
	for label in _all_labels(holder):
		_assert(str(label.text) != "attack_modes: ", "and it is not also shown as a read-only generic row")


func _check_editing_a_mode() -> void:
	print("\n[editing]")
	var manager := _manager()
	var holder := _build_inspector_from("item_spear", manager)
	var modes: Array = manager.items["item_spear"]["properties"]["attack_modes"]
	var verb := _find_named(holder, "Mode_verb_0") as LineEdit
	verb.text = "jab at"; verb.text_changed.emit("jab at")
	_assert(modes[0]["verb"] == "jab at", "the verb is written")
	var sentence := _find_named(holder, "Mode_text_0") as LineEdit
	sentence.text = "{attacker} {verb} {defender}"; sentence.text_changed.emit(sentence.text)
	_assert(modes[0]["text"] == "{attacker} {verb} {defender}", "the sentence is written")
	sentence.text = ""; sentence.text_changed.emit("")
	_assert(not modes[0].has("text"), "and a blank one is erased, not written empty")
	var picker := _find_named(holder, "Mode_type_0") as OptionButton
	picker.select(3); picker.item_selected.emit(3)
	_assert(modes[0]["weapon_damage_type"] == "crushing", "a damage type is written by name")
	picker.select(0); picker.item_selected.emit(0)
	_assert(not modes[0].has("weapon_damage_type"), "and the weapon's own erases it")
	var bonus := _find_named(holder, "Mode_bonus_0") as SpinBox
	bonus.value = 3; bonus.value_changed.emit(3.0)
	_assert(modes[0]["damage_bonus"] == 3 and typeof(modes[0]["damage_bonus"]) == TYPE_INT, "a bonus is written as a whole number")
	bonus.value = 0; bonus.value_changed.emit(0.0)
	_assert(not modes[0].has("damage_bonus"), "and zero is not written")


func _check_removing_the_last_mode_erases_the_list() -> void:
	print("\n[removing]")
	var manager := _manager()
	var holder := _build_inspector_from("item_spear", manager)
	var remove := _find_named(_find_named(holder, "AttackMode1"), "RemoveAttackMode") as Button
	remove.pressed.emit()
	_assert((manager.items["item_spear"]["properties"]["attack_modes"] as Array).size() == 1, "one mode is gone")
	var again := _build_inspector_from("item_spear", manager)
	(_find_named(_find_named(again, "AttackMode0"), "RemoveAttackMode") as Button).pressed.emit()
	_assert(not manager.items["item_spear"]["properties"].has("attack_modes"), "the last one takes the key with it")


# --- fixture and harness --------------------------------------------------------------

func _rebuild_fixture() -> void:
	_remove_recursive(scratch)
	_write("data/combat/elements.json", {"valid_damage_types": ["fire"]})
	_write("data/items/probe.json", {
		"item_sword": {"name": "Sword", "type": "Weapon", "weight": 3, "value": 1, "properties": {"damage": 8}},
		"item_cloak": {"name": "Cloak", "type": "Armor", "weight": 1, "value": 1, "properties": {"defense": 1}},
		"item_spear": {
			"name": "Spear", "type": "Weapon", "weight": 4, "value": 1,
			"properties": {"damage": 9, "attack_modes": [
				{"name": "thrust", "verb": "thrust", "weapon_damage_type": "piercing"},
				{"name": "slash", "verb": "slash", "weapon_damage_type": "slashing", "damage_bonus": 1},
			]},
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
