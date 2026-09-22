# tests/npc_dialogue_binding_smoke.gd
#
# `properties.dialogue` (`dialogue/manager.py::NPC_GRAPH_KEY`) binds an NPC to
# one authored conversation graph, and had no editor control at all -- an NPC
# could not be given a conversation without hand-editing JSON. See
# docs/plan/editor-coverage-ledger.md family C.
#
#   godot --headless --path mud-world-editor --script tests/npc_dialogue_binding_smoke.gd

extends SceneTree

var failure_count := 0
var scratch: String = ""


func _init() -> void:
	scratch = ProjectSettings.globalize_path("res://").path_join("../tmp/npc_dialogue_binding")
	_rebuild_fixture()

	_check_opening_an_unbound_npc_writes_nothing()
	_check_a_bound_npc_preselects_its_graph()
	_check_a_missing_graph_is_shown_not_dropped()
	_check_binding_a_graph_writes_it()
	_check_unbinding_erases_the_key()

	if failure_count > 0:
		push_error("npc dialogue binding failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


func _check_opening_an_unbound_npc_writes_nothing() -> void:
	print("\n[an unbound NPC]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_unbound", manager)
	var picker := _graph_picker(holder)
	_assert(picker.selected == 0, "the picker defaults to '(none)'")
	var props: Dictionary = manager.npcs["npc_unbound"].get("properties", {})
	_assert(not props.has("dialogue"), "opening the panel did not bind a graph")


func _check_a_bound_npc_preselects_its_graph() -> void:
	print("\n[an NPC already bound to a graph]")
	var holder := _build_inspector("npc_bound")
	var picker := _graph_picker(holder)
	_assert(str(picker.get_item_metadata(picker.selected)) == "greeting_graph", "it preselects 'greeting_graph'")


func _check_a_missing_graph_is_shown_not_dropped() -> void:
	print("\n[an NPC bound to a graph that no longer exists]")
	var holder := _build_inspector("npc_missing_graph")
	var picker := _graph_picker(holder)
	_assert(str(picker.get_item_metadata(picker.selected)) == "ghost_graph", "the stale id is still selected")
	_assert(str(picker.text).begins_with("Missing:"), "and shown as missing (%s)" % picker.text)


func _check_binding_a_graph_writes_it() -> void:
	print("\n[binding a graph]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_unbound", manager)
	var picker := _graph_picker(holder)
	var index := _index_for_id(picker, "greeting_graph")
	_assert(index != -1, "the picker offers 'greeting_graph'")
	picker.item_selected.emit(index)
	_assert(str(manager.npcs["npc_unbound"]["properties"].get("dialogue", "")) == "greeting_graph", "the binding was written")


func _check_unbinding_erases_the_key() -> void:
	print("\n[unbinding]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_bound", manager)
	var picker := _graph_picker(holder)
	picker.item_selected.emit(0)
	_assert(not manager.npcs["npc_bound"]["properties"].has("dialogue"), "the dialogue key was erased")


# --- fixture ----------------------------------------------------------------

func _rebuild_fixture() -> void:
	_remove_recursive(scratch)
	_write("data/dialogue/greeting.json", {"id": "greeting_graph", "root": "start", "nodes": {"start": {"text": "Hello."}}})
	_write("data/npcs/probe.json", {
		"npc_unbound": {"name": "Unbound", "description": "", "level": 1, "health": 10, "friendly": true, "properties": {}},
		"npc_bound": {"name": "Bound", "description": "", "level": 1, "health": 10, "friendly": true, "properties": {"dialogue": "greeting_graph"}},
		"npc_missing_graph": {"name": "Missing Graph", "description": "", "level": 1, "health": 10, "friendly": true, "properties": {"dialogue": "ghost_graph"}},
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


## The graph picker is the only OptionButton preceded by a "Graph" label.
func _graph_picker(node: Node) -> OptionButton:
	if node is HBoxContainer and node.get_child_count() >= 2:
		var first := node.get_child(0)
		if first is Label and str(first.text) == "Graph" and node.get_child(1) is OptionButton:
			return node.get_child(1)
	for child in node.get_children():
		var found := _graph_picker(child)
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
