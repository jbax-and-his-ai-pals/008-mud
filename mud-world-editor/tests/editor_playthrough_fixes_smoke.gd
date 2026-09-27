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

	print("\n[room anchors: all eight directions, above the lines, none for a used exit]")
	var scene = main.graph_controller.get_active_nodes().get(id)
	var handles: Array = scene.anchor_container.find_children("Handle", "", true, false) if scene else []
	_assert(handles.size() == 8, "the edges and corners each have an anchor with a handle (%d)" % handles.size())
	_assert(not scene.anchor_container.z_as_relative and scene.anchor_container.z_index > 11, "anchors draw above the connection lines")
	var exits: Dictionary = rooms[id].get("exits", {}).duplicate()
	var shown := []
	var wrong := []
	for anchor in scene.anchor_container.get_children():
		var direction: String = anchor.get_meta("direction")
		if anchor.visible: shown.append(direction)
		if anchor.visible == exits.has(direction): wrong.append(direction)
	_assert(wrong.is_empty() and not shown.is_empty(), "only directions without an exit offer an anchor: %s (exits %s)" % [shown, exits.keys()])

	print("\n[clicking an anchor adds a connected room at once, in the same district]")
	var free: String = shown[0]
	var before: int = rooms.size()
	var anchor_node: Control = null
	for anchor in scene.anchor_container.get_children():
		if anchor.get_meta("direction") == free: anchor_node = anchor
	var press := InputEventMouseButton.new()
	press.button_index = MOUSE_BUTTON_LEFT; press.pressed = true
	anchor_node.gui_input.emit(press)
	rooms = main.region_mgr.data.rooms
	var added := _new_room(rooms, exits, free)
	_assert(rooms.size() == before + 1 and added != "", "one click makes a room to the %s, no menu" % free)
	if added != "":
		_assert(rooms[added]["exits"].get(Constants.INV_DIR_MAP[free], "") == id, "connected both ways")
		var p = rooms[id]["_editor_pos"]; var q = rooms[added]["_editor_pos"]
		_assert(Vector2(q[0] - p[0], q[1] - p[1]).normalized().dot(Constants.DIR_VECTORS[free].normalized()) > 0.5, "and placed on that side of the room")
		var districts: Dictionary = main.region_mgr.data.get("properties", {}).get("districts", {})
		var home := ""
		for district_id in districts:
			if districts[district_id].get("members", []).has(id): home = district_id
		_assert(home == "" or districts[home]["members"].has(added), "the new room joins %s's district (%s)" % [id, home])
		main.cmd_proc.undo()
		_assert(not main.region_mgr.data.rooms.has(added) and (home == "" or not districts[home]["members"].has(added)), "and Ctrl+Z takes it back out")
	for _i in 3: await process_frame

	print("\n[district shapes are not rebuilt by every redraw]")
	var gc = main.graph_controller
	gc.queue_redraw(); await process_frame
	var signature: String = gc._district_shape_signature
	gc.queue_redraw(); await process_frame
	_assert(signature != "" and gc._district_shape_signature == signature, "an unchanged map reuses its district shapes")
	gc.defer_district_reshape = true
	gc.set_node_position(id, gc.get_node_position(id) + Vector2(64, 0))
	gc.queue_redraw(); await process_frame
	_assert(gc._district_shape_signature == signature, "and a room being dragged leaves them alone")
	gc.defer_district_reshape = false
	gc.invalidate_district_shape(); await process_frame
	_assert(gc._district_shape_signature != signature, "until it is dropped")

	print("\n[search finds placed items]")
	main.ui_mgr.show_search_modal()
	main.ui_mgr.search_modal._on_search_text_changed("herb bed")
	var titles := []
	for card in main.ui_mgr.search_modal.search_results_box.get_children():
		if not card.is_queued_for_deletion(): titles.append(card.get_meta("search_data"))
	_assert(titles.any(func(m): return m.get("type") == "room"), "\"herb bed\" finds the rooms it is placed in")
	_assert(titles.any(func(m): return m.get("kind") == "item"), "and its item template")
	main.ui_mgr.search_modal.hide()

	print("\n[Ctrl-drag from one room onto another connects them]")
	var graph = main.graph_controller
	var all_rooms: Dictionary = main.region_mgr.data.rooms
	var pair := []
	for a in all_rooms:
		for b in all_rooms:
			if a == b or pair.size() > 0: continue
			if not graph.get_active_nodes().has(a) or not graph.get_active_nodes().has(b): continue
			var way := Constants.classify_direction(graph.get_node_position(b) - graph.get_node_position(a))
			if graph.get_node_position(a).distance_to(graph.get_node_position(b)) > 700: continue
			if all_rooms[a].get("exits", {}).has(way) or all_rooms[b].get("exits", {}).has(Constants.INV_DIR_MAP[way]): continue
			if all_rooms[a].get("exits", {}).values().has(b): continue
			pair = [a, b, way]
	_assert(pair.size() == 3, "found two nearby rooms with a free direction between them: %s" % str(pair))
	if pair.size() == 3:
		var src_node = graph.get_active_nodes()[pair[0]]
		var ctrl_press := InputEventMouseButton.new(); ctrl_press.button_index = MOUSE_BUTTON_LEFT; ctrl_press.pressed = true; ctrl_press.ctrl_pressed = true
		src_node.visual_panel.gui_input.emit(ctrl_press)
		_assert(main.state.dragging_conn.get("active", false), "Ctrl+press on a room starts a connection drag")
		var move := InputEventMouseMotion.new()
		src_node.visual_panel.gui_input.emit(move)
		var release := InputEventMouseButton.new(); release.button_index = MOUSE_BUTTON_LEFT; release.pressed = false
		# The card holds the mouse, so it reports the release; where it lands is
		# the target room's centre.
		main.graph_controller.connection_drag_released.disconnect(main.graph_controller.connection_drag_released.get_connections()[0].callable)
		main.graph_controller.connection_drag_released.connect(func(_id): main._finish_connection_drag(graph.get_node_position(pair[1])))
		src_node.visual_panel.gui_input.emit(release)
		all_rooms = main.region_mgr.data.rooms
		_assert(all_rooms[pair[0]]["exits"].get(pair[2], "") == pair[1], "letting go over the other room makes the exit %s" % pair[2])
		_assert(all_rooms[pair[1]]["exits"].get(Constants.INV_DIR_MAP[pair[2]], "") == pair[0], "and the way back")
		_assert(not main.state.dragging_conn.get("active", false) and not main.state.connection_mode, "and the drag is over, with no form left open")
		main.cmd_proc.undo()
		_assert(not main.region_mgr.data.rooms[pair[0]]["exits"].has(pair[2]), "Ctrl+Z takes the connection back")

	print("\n[the connection form's Cancel closes it]")
	main._open_connection_form(id, "Town Square")
	_assert(main.state.connection_mode and main.inspector.cur_mode == "connection", "the form is open")
	var before_anchor: int = main.region_mgr.data.rooms.size()
	main.graph_controller.anchor_clicked.emit(id, "southwest")
	_assert(main.region_mgr.data.rooms.size() == before_anchor, "an anchor click does nothing while connecting")
	var cancel = main.inspector.content_container.find_child("CancelConnection", true, false)
	_assert(cancel != null, "it has a Cancel button")
	if cancel: cancel.pressed.emit()
	_assert(not main.state.connection_mode and main.inspector.cur_mode != "connection", "Cancel leaves connection mode and closes the form")
	for _i in 2: await process_frame

	print("\n[districts follow a room through id changes and deletion, and saves]")
	var rm = main.region_mgr
	var districts_now: Dictionary = rm.data.get("properties", {}).get("districts", {})
	var home_district := ""
	for district_id in districts_now:
		if districts_now[district_id].get("members", []).has(id): home_district = district_id
	_assert(home_district != "", "%s is in a district (%s)" % [id, home_district])
	var members: Array = districts_now[home_district]["members"]
	main.inspector.request_rename.emit(id, id + "_renamed")
	_assert(members.has(id + "_renamed") and not members.has(id), "changing a room's id changes it in its district")
	main.cmd_proc.undo()
	_assert(members.has(id) and not members.has(id + "_renamed"), "and undo changes it back")
	var room_name_before_delete := str(rm.data.rooms[id].get("name", id))
	main.action_handler.execute_delete_room(id, true)
	_assert(not members.has(id), "deleting a room takes it out of its district")
	var summary_after_delete: String = main._describe_unsaved_work()
	_assert(("removed (was \"%s\")" % room_name_before_delete) in summary_after_delete, "and the unsaved list says it was removed, by name")
	main.cmd_proc.undo()
	_assert(members.has(id) and rm.data.rooms.has(id), "undo puts room and membership back")
	members.append("room_that_was_never_there")
	var saved: Dictionary = rm.save_region()
	_assert(saved.get("ok", false) and not members.has("room_that_was_never_there"), "a save drops a member naming no room instead of failing")
	var on_disk: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rm.regions_dir().path_join(rm.current_filename)))
	_assert(not str(on_disk.get("properties", {}).get("districts", {})).contains("room_that_was_never_there"), "so the engine never sees it")

	print("\n[search says what each result is]")
	main.ui_mgr.show_search_modal()
	main.ui_mgr.search_modal._on_search_text_changed("herb bed")
	var kinds := []
	for card in main.ui_mgr.search_modal.search_results_box.get_children():
		if card.is_queued_for_deletion(): continue
		var tag = card.find_child("KindTag", true, false)
		if tag: kinds.append(tag.text)
	_assert(kinds.has("Placed item") and kinds.has("Item template"), "placements and templates are labelled: %s" % str(kinds))
	main.ui_mgr.search_modal.hide()

	print("\n[a ring of rooms does not leave a darker blob in its district]")
	var ring_rooms: Dictionary = main.region_mgr.data.rooms
	var alley := ""
	for rid in ring_rooms:
		if ring_rooms[rid].get("name") == "Narrow Alley": alley = rid
	var ring := [alley]
	for step in ["southeast", "east", "northeast", "west"]:
		var known: Array = main.region_mgr.data.rooms.keys()
		main.action_handler.create_room_from_anchor(ring[-1], step, main._free_spot_from(ring[-1], step))
		for rid in main.region_mgr.data.rooms:
			if not known.has(rid): ring.append(rid)
	_assert(ring.size() == 5, "four rooms grown round from Narrow Alley")
	main.graph_controller.invalidate_district_shape()
	main.graph_controller._district_render_cache_ready = false
	var shape = main.graph_controller._get_district_render_cache()
	var ring_holes := 0
	for field_index in shape.fields.size():
		if shape.fields[field_index].id != "market_row": continue
		var loops = main.graph_controller._trace_field_boundary_loops(shape.owners, field_index, shape.cell_size)
		ring_holes = TerritoryShape.hole_flags(loops).count(true)
	_assert(ring_holes == 0, "the ground inside the ring belongs to Market Row, so no hole is painted twice")

	print("\n[unsaved-change prompts say what]")
	var summary: String = main._describe_unsaved_work()
	var room_name := str(rooms[id].get("name", id))
	_assert(room_name in summary and main._region_title() in summary and "moved" in summary and not "town.json" in summary, "the moved room is named under its region, with what happened: %s" % summary)
	var rich: String = main._unsaved_work_bbcode()
	_assert("[b]%s[/b]" % room_name in rich and "[color=" in rich, "and the prompt version is formatted")
	main.database_mgr.mark_dirty("npc", "old_bryn")
	summary = main._describe_unsaved_work()
	_assert("Content Library: old_bryn (npc)" in summary, "and so is an edited library entry")
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


# The room the `direction` exit of the source now leads to, if it is new.
func _new_room(rooms: Dictionary, old_exits: Dictionary, direction: String) -> String:
	for rid in rooms:
		var back: String = str(rooms[rid].get("exits", {}).get(Constants.INV_DIR_MAP.get(direction, ""), ""))
		if back != "" and not old_exits.has(direction) and rid.begins_with("room_") and rooms.has(back) and rooms[back].get("exits", {}).get(direction, "") == rid:
			return rid
	return ""


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String) -> void:
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
