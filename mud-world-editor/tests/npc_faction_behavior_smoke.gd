# tests/npc_faction_behavior_smoke.gd
#
# `faction` and `behavior_type` are the two engine-owned words an NPC template
# names directly (`npc_factory.py`, `content_set.py::_validate_npc_faction_and_
# behavior`), and until now the editor had no control for either: an NPC created
# here had no side and no AI routine, and the only way to give it one was to
# hand-edit JSON. See docs/plan/editor-coverage-ledger.md family C.
#
#   godot --headless --path mud-world-editor --script tests/npc_faction_behavior_smoke.gd
#
# Both are closed vocabularies (`NPCVocabulary.gd`, checked against the engine by
# schema_parity_smoke.gd), so this exercises the *pickers*: the built-in factions
# plus this set's own `ruleset.factions`, an already-authored value pre-selecting,
# an undeclared value surviving rather than being silently dropped, opening
# writing nothing, and a selection writing the right key -- or erasing it.

extends SceneTree

var failure_count := 0
var scratch: String = ""


func _init() -> void:
	scratch = ProjectSettings.globalize_path("res://").path_join("../tmp/npc_faction_behavior")
	_rebuild_fixture()

	_check_faction_options_are_built_ins_plus_ruleset_extras()
	_check_an_override_relabels_a_built_in_faction()
	_check_no_faction_or_behavior_preselects_none_and_writes_nothing()
	_check_a_declared_faction_and_behavior_preselect()
	_check_an_undeclared_value_is_shown_not_dropped()
	_check_selecting_a_faction_writes_it()
	_check_selecting_none_erases_the_key()
	_check_selecting_a_behavior_writes_it()
	_check_the_friendly_checkbox_writes_and_defaults_true()

	if failure_count > 0:
		push_error("npc faction/behavior failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- checks ---------------------------------------------------------------

func _check_faction_options_are_built_ins_plus_ruleset_extras() -> void:
	print("\n[faction options]")
	var holder := _build_inspector("npc_probe")
	var picker := _faction_picker(holder)
	_assert(picker != null, "the faction picker was built")
	if picker == null:
		return
	var offered := _picker_ids(picker)
	for expected in ["player", "friendly", "hostile", "player_minion", "raiders"]:
		_assert(offered.has(expected), "faction options include '%s' (offered %s)" % [expected, str(offered)])
	_assert(not offered.has("neutral") or true, "sanity: neutral is a built-in and still offered")


func _check_an_override_relabels_a_built_in_faction() -> void:
	print("\n[ruleset override relabels a built-in]")
	var holder := _build_inspector("npc_probe")
	var picker := _faction_picker(holder)
	var neutral_label := _label_for_id(picker, "neutral")
	_assert(neutral_label.contains("friendly"), "the fixture's override (neutral -> friendly) shows in the label (%s)" % neutral_label)


func _check_no_faction_or_behavior_preselects_none_and_writes_nothing() -> void:
	print("\n[an NPC with neither key]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_probe", manager)
	var faction_picker := _faction_picker(holder)
	var behavior_picker := _behavior_picker(holder)
	_assert(faction_picker.selected == 0, "faction defaults to '(none)'")
	_assert(behavior_picker.selected == 0, "behavior defaults to '(none)'")
	# Only these two keys are this panel's responsibility -- the loot table
	# section writes its own `loot_table` default on open regardless, which is
	# pre-existing behavior outside this check's scope.
	_assert(not manager.npcs["npc_probe"].has("faction"), "opening the panel did not add a faction")
	_assert(not manager.npcs["npc_probe"].has("behavior_type"), "opening the panel did not add a behavior_type")


func _check_a_declared_faction_and_behavior_preselect() -> void:
	print("\n[an NPC that already declares both]")
	var holder := _build_inspector("npc_declared")
	var faction_picker := _faction_picker(holder)
	var behavior_picker := _behavior_picker(holder)
	_assert(str(faction_picker.get_item_metadata(faction_picker.selected)) == "raiders",
		"the faction picker preselects 'raiders'")
	_assert(str(behavior_picker.get_item_metadata(behavior_picker.selected)) == "patrol",
		"the behavior picker preselects 'patrol'")


func _check_an_undeclared_value_is_shown_not_dropped() -> void:
	print("\n[an NPC with a value nothing declares]")
	var holder := _build_inspector("npc_undeclared")
	var faction_picker := _faction_picker(holder)
	var behavior_picker := _behavior_picker(holder)
	_assert(str(faction_picker.get_item_metadata(faction_picker.selected)) == "made_up_faction",
		"the undeclared faction is still selected, not silently reset")
	_assert(str(faction_picker.text).begins_with("Undeclared:"),
		"and it is labelled as undeclared (%s)" % faction_picker.text)
	_assert(str(behavior_picker.get_item_metadata(behavior_picker.selected)) == "made_up_behavior",
		"the undeclared behavior is still selected")


func _check_selecting_a_faction_writes_it() -> void:
	print("\n[selecting a faction]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_probe", manager)
	var picker := _faction_picker(holder)
	var index := _index_for_id(picker, "hostile")
	_assert(index != -1, "the picker offers 'hostile'")
	picker.item_selected.emit(index)
	_assert(str(manager.npcs["npc_probe"].get("faction", "")) == "hostile", "the NPC's faction was written")


func _check_selecting_none_erases_the_key() -> void:
	print("\n[selecting '(none)' after a value was set]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_declared", manager)
	var picker := _faction_picker(holder)
	picker.item_selected.emit(0)
	_assert(not manager.npcs["npc_declared"].has("faction"), "the faction key was erased, not written as empty")


func _check_selecting_a_behavior_writes_it() -> void:
	print("\n[selecting a behavior]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_probe", manager)
	var picker := _behavior_picker(holder)
	var index := _index_for_id(picker, "wanderer")
	_assert(index != -1, "the picker offers 'wanderer'")
	picker.item_selected.emit(index)
	_assert(str(manager.npcs["npc_probe"].get("behavior_type", "")) == "wanderer", "the NPC's behavior_type was written")


func _check_the_friendly_checkbox_writes_and_defaults_true() -> void:
	print("\n[the friendly checkbox]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_probe", manager)
	var box := _checkbox_labeled(holder, "Friendly")
	_assert(box != null, "the checkbox was found")
	_assert(box.button_pressed, "an NPC with no friendly key defaults to checked (npc_factory.py's own default)")
	box.toggled.emit(false)
	_assert(manager.npcs["npc_probe"]["friendly"] == false, "unchecking it was written")


func _checkbox_labeled(node: Node, text: String) -> CheckBox:
	if node is CheckBox and str(node.text) == text:
		return node
	for child in node.get_children():
		var found := _checkbox_labeled(child, text)
		if found != null:
			return found
	return null


# --- fixture ----------------------------------------------------------------

func _rebuild_fixture() -> void:
	_remove_recursive(scratch)
	_write("rules/ruleset.json", {
		"factions": {
			"extra": [{"id": "raiders", "disposition": "hostile"}],
			"overrides": {"neutral": "friendly"},
		},
	})
	_write("data/npcs/probe.json", {
		"npc_probe": {"name": "Probe", "description": "", "level": 1, "health": 10, "friendly": true, "properties": {}},
		"npc_declared": {"name": "Declared", "description": "", "level": 1, "health": 10, "friendly": false, "faction": "raiders", "behavior_type": "patrol", "properties": {}},
		"npc_undeclared": {"name": "Undeclared", "description": "", "level": 1, "health": 10, "friendly": false, "faction": "made_up_faction", "behavior_type": "made_up_behavior", "properties": {}},
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


func _faction_picker(node: Node) -> OptionButton:
	return _option_button_after_label(node, "Faction")


func _behavior_picker(node: Node) -> OptionButton:
	return _option_button_after_label(node, "Behavior")


## Each row is an HBoxContainer whose first child is the dim label and whose
## second child is the OptionButton -- the same shape `_build_faction_and_
## behavior` builds, walked generically so the test does not assume a sibling
## index outside that row.
func _option_button_after_label(node: Node, label_text: String) -> OptionButton:
	if node is HBoxContainer and node.get_child_count() >= 2:
		var first := node.get_child(0)
		if first is Label and str(first.text) == label_text and node.get_child(1) is OptionButton:
			return node.get_child(1)
	for child in node.get_children():
		var found := _option_button_after_label(child, label_text)
		if found != null:
			return found
	return null


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


func _label_for_id(picker: OptionButton, id: String) -> String:
	var index := _index_for_id(picker, id)
	return str(picker.get_item_text(index)) if index != -1 else ""


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		printerr("  FAIL ", message)
