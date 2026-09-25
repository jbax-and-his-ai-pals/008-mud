# tests/editor_playthrough_fixes_smoke.gd
#
# What a hands-on playthrough of the editor turned up:
#
# - Ctrl+Y (redo), Ctrl+F (search) and F (recentre) did nothing: the key chain
#   ran in `_unhandled_input`, so a focused control ate the keys first, and F
#   with the Explorer focused fell to the tree's type-ahead and jumped the
#   selection between regions instead.
# - The room anchors you drag a new connected room out of were bare hit areas:
#   hovering a room showed nothing to drag from.
# - "Unsaved changes" prompts said only *that* something was unsaved, not what.
# - The world view drew every region but the open one as a single square: room
#   positions live in the editor/ sidecar, and the world data never merged it.
#
#   godot --headless --path mud-world-editor --script tests/editor_playthrough_fixes_smoke.gd

extends SceneTree

var main: Node2D
var started := false
var failures := 0


func _initialize() -> void:
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var fixture := repo.path_join("tmp/playthrough-fixes-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "test fixture"
	main = load("res://scenes/Main.tscn").instantiate()
	root.add_child(main)


func _process(_delta: float) -> bool:
	if started: return false
	started = true
	_run.call_deferred()
	return false


func _run() -> void:
	await process_frame
	var rooms: Dictionary = main.region_mgr.data.get("rooms", {})
	_assert(not rooms.is_empty(), "a region is open (%s)" % main.region_mgr.current_filename)
	var id: String = rooms.keys()[0]

	print("\n[undo, redo, search and recentre from the keyboard]")
	var explorer: Tree = null
	for tree in main.find_children("*", "Tree", true, false):
		if tree.is_visible_in_tree(): explorer = tree; break
	if explorer: explorer.grab_focus()
	main._on_node_click(id, false)
	var p0 = rooms[id].get("_editor_pos", [0, 0])
	main.state.drag_start_positions = {id: Vector2(p0[0], p0[1])}
	main.action_handler.commit_batch_move(Vector2(64, 0))
	var moved = rooms[id]["_editor_pos"]
	await _press(KEY_Z, true)
	_assert(rooms[id]["_editor_pos"] == p0, "Ctrl+Z puts the room back")
	await _press(KEY_Y, true)
	_assert(rooms[id]["_editor_pos"] == moved and main.cmd_proc.redo_stack.is_empty(), "Ctrl+Y moves it again")
	await _press(KEY_F, true)
	_assert(main.ui_mgr.search_modal.visible, "Ctrl+F opens search")
	main.ui_mgr.search_modal.hide()
	await process_frame
	if explorer: explorer.grab_focus()
	var selected_before = explorer.get_selected() if explorer else null
	main.main_camera.position = Vector2(-99999, -99999)
	await _press(KEY_F, false)
	_assert(main.main_camera.position != Vector2(-99999, -99999), "F recentres the view, with the Explorer focused")
	_assert(explorer == null or explorer.get_selected() == selected_before, "and does not type-ahead in the Explorer")

	print("\n[room anchors are visible]")
	var scene = main.graph_controller.get_active_nodes().get(id)
	var handles: Array = scene.anchor_container.find_children("Handle", "", true, false) if scene else []
	_assert(handles.size() == 4, "each of the four anchors has a drawn handle (%d)" % handles.size())

	print("\n[unsaved-change prompts say what]")
	var summary: String = main._describe_unsaved_work()
	var room_name := str(rooms[id].get("name", id))
	_assert(room_name in summary and main.region_mgr.current_filename in summary, "the moved room is named: %s" % summary)
	main.database_mgr.mark_dirty("npc", "old_bryn")
	summary = main._describe_unsaved_work()
	_assert("library npc: old_bryn" in summary, "and so is an edited library entry")
	_assert(not "old_bryn" in main._describe_unsaved_work(false), "which a region switch (it keeps the library) leaves out")

	print("\n[the world view draws every region's rooms]")
	var world: Dictionary = main.world_mgr.get_all_world_data()
	var spread := 0
	for rid in world:
		var seen := {}
		for room in world[rid].get("rooms", {}).values():
			seen[str(room.get("_editor_pos", [0, 0]))] = true
		if seen.size() > 1: spread += 1
	_assert(spread >= world.size() - 1, "regions have their rooms laid out, not stacked at one point (%d of %d)" % [spread, world.size()])

	if failures > 0: push_error("editor playthrough fixes smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _press(code: Key, ctrl: bool) -> void:
	var event := InputEventKey.new()
	event.keycode = code; event.ctrl_pressed = ctrl; event.pressed = true
	Input.parse_input_event(event)
	await process_frame
	await process_frame
	var up := event.duplicate(); up.pressed = false
	Input.parse_input_event(up)
	await process_frame


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String) -> void:
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
