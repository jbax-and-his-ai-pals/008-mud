# tests/npc_dialog_topics_smoke.gd
#
# `dialog` (`npc_factory.py:156`; `npc.py:85,124-125`): a flat topic -> reply
# map for `ask <npc> about <topic>`, independent of the `properties.dialogue`
# graph binding -- a hostile NPC with no graph can still answer a handful of
# topics. Had no editor control at all. See
# docs/plan/editor-coverage-ledger.md family C.
#
#   godot --headless --path mud-world-editor --script tests/npc_dialog_topics_smoke.gd
#
# The map is keyed by topic, so renaming a topic is a key rebuild -- checked the
# same way the loot table's item rename is: a collision is refused rather than
# merging two topics' replies into one.

extends SceneTree

var failure_count := 0
var scratch: String = ""


func _init() -> void:
	scratch = ProjectSettings.globalize_path("res://").path_join("../tmp/npc_dialog_topics")
	_rebuild_fixture()

	_check_opening_an_npc_with_no_dialog_writes_nothing()
	_check_an_authored_npc_shows_its_topics()
	_check_adding_a_topic()
	_check_editing_a_reply()
	_check_renaming_a_topic()
	_check_renaming_onto_an_existing_topic_is_refused()
	_check_removing_the_last_topic_erases_the_key()

	if failure_count > 0:
		push_error("npc dialog topics failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


func _check_opening_an_npc_with_no_dialog_writes_nothing() -> void:
	print("\n[an NPC with no dialog]")
	var manager := _manager()
	_build_inspector_from("npc_no_dialog", manager)
	_assert(not manager.npcs["npc_no_dialog"].has("dialog"), "opening the panel did not add a dialog map")


func _check_an_authored_npc_shows_its_topics() -> void:
	print("\n[an NPC that already declares topics]")
	var holder := _build_inspector("npc_talkative")
	var rows := _rows(holder)
	_assert(rows.size() == 2, "two topic rows (%d)" % rows.size())


func _check_adding_a_topic() -> void:
	print("\n[adding a topic]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_no_dialog", manager)
	var add := _add_button(holder)
	add.pressed.emit()
	var written: Dictionary = manager.npcs["npc_no_dialog"]["dialog"]
	_assert(written.has("topic"), "a fresh topic key was created (%s)" % str(written.keys()))


func _check_editing_a_reply() -> void:
	print("\n[editing a reply]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_talkative", manager)
	var row: Node = _rows(holder)[0]
	var fields := _line_edits(row)
	fields[1].text = "A brand new reply."
	fields[1].text_changed.emit("A brand new reply.")
	var written: Dictionary = manager.npcs["npc_talkative"]["dialog"]
	_assert(written.values().has("A brand new reply."), "the reply text was written")


func _check_renaming_a_topic() -> void:
	print("\n[renaming a topic]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_single_topic", manager)
	var row: Node = _rows(holder)[0]
	var fields := _line_edits(row)
	fields[0].text_submitted.emit("renamed")
	var written: Dictionary = manager.npcs["npc_single_topic"]["dialog"]
	_assert(written.has("renamed") and not written.has("greeting"), "the key moved (%s)" % str(written.keys()))
	_assert(written.get("renamed", "") == "Hello there.", "and the reply moved with it")


func _check_renaming_onto_an_existing_topic_is_refused() -> void:
	print("\n[renaming onto a topic that already exists]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_talkative", manager)
	var row: Node = _rows(holder)[0]
	var fields := _line_edits(row)
	var other_topic: Node = _rows(holder)[1]
	var other_fields := _line_edits(other_topic)
	var other_topic_name: String = other_fields[0].text
	fields[0].text_submitted.emit(other_topic_name)
	var written: Dictionary = manager.npcs["npc_talkative"]["dialog"]
	_assert(written.size() == 2, "the collision left both topics alone (%s)" % str(written.keys()))


func _check_removing_the_last_topic_erases_the_key() -> void:
	print("\n[removing the only topic]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_single_topic", manager)
	var row: Node = _rows(holder)[0]
	var remove := _remove_button(row)
	remove.pressed.emit()
	_assert(not manager.npcs["npc_single_topic"].has("dialog"), "the now-empty dialog key was erased")


# --- fixture ----------------------------------------------------------------

func _rebuild_fixture() -> void:
	_remove_recursive(scratch)
	_write("data/npcs/probe.json", {
		"npc_no_dialog": {"name": "No Dialog", "description": "", "level": 1, "health": 10, "friendly": true, "properties": {}},
		"npc_talkative": {
			"name": "Talkative", "description": "", "level": 1, "health": 10, "friendly": true, "properties": {},
			"dialog": {"greeting": "Hello there.", "forge": "The forge is hot."},
		},
		"npc_single_topic": {
			"name": "Single Topic", "description": "", "level": 1, "health": 10, "friendly": true, "properties": {},
			"dialog": {"greeting": "Hello there."},
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


func _find_named(node: Node, wanted_name: String) -> Node:
	if str(node.name) == wanted_name:
		return node
	for child in node.get_children():
		var found := _find_named(child, wanted_name)
		if found != null:
			return found
	return null


func _rows(node: Node) -> Array:
	var holder := _find_named(node, "DialogTopics")
	if holder == null:
		return []
	var out: Array = []
	for child in holder.get_children():
		if child is HBoxContainer:
			out.append(child)
	return out


func _line_edits(row: Node) -> Array:
	var out: Array = []
	for child in row.get_children():
		if child is LineEdit:
			out.append(child)
	return out


func _remove_button(row: Node) -> Button:
	for child in row.get_children():
		if child is Button:
			return child
	return null


## The "+ Topic" button sits in the header row, the previous sibling of
## "DialogTopics" in the same parent.
func _add_button(node: Node) -> Button:
	var rows := _find_named(node, "DialogTopics")
	if rows == null:
		return null
	var header := rows.get_parent().get_child(rows.get_index() - 1)
	for child in _all_buttons(header):
		if str(child.text) == "+ Topic":
			return child
	return null


func _all_buttons(node: Node) -> Array:
	var out: Array = []
	if node is Button:
		out.append(node)
	for child in node.get_children():
		out.append_array(_all_buttons(child))
	return out


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		printerr("  FAIL ", message)
