# scripts/core/Main.gd
extends Node2D

# Managers
var region_mgr: RegionManager
var world_mgr: WorldManager
var database_mgr: DatabaseManager
var cmd_proc: CommandProcessor

# Controllers
var ui_mgr: EditorUIManager
var inspector: InspectorController
var graph_controller: GraphController
var camera_controller: CameraController
var action_handler: ActionHandler

# State
var state: EditorState
var view_states: Dictionary = {}
var editor_clipboard: Array = []
var cached_hierarchy: Dictionary = {}

# Input state
var mouse_down_pos: Vector2
var deselection_primed: bool = false
var is_dragging_object: bool = false
const DRAG_PIXEL_THRESHOLD = 10

# Scene Refs
@onready var main_camera = $MainCamera
@onready var room_container = $RoomContainer
@onready var connection_layer = $ConnectionLayer
@onready var ui_layer = $UILayer
var grid_layer: GridLayer

func _ready():
	region_mgr = RegionManager.new()
	world_mgr = WorldManager.new()
	database_mgr = DatabaseManager.new()
	cmd_proc = CommandProcessor.new()
	state = EditorState.new()
	
	grid_layer = GridLayer.new(); add_child(grid_layer); move_child(grid_layer, 0)
	grid_layer.setup(main_camera)
	grid_layer.visible = false
	
	ui_mgr = EditorUIManager.new(); ui_mgr.setup(ui_layer)
	inspector = InspectorController.new(); inspector.setup(ui_layer, region_mgr, world_mgr, database_mgr)
	graph_controller = GraphController.new(); graph_controller.setup(room_container, connection_layer, state)
	camera_controller = CameraController.new(); camera_controller.setup(main_camera, ui_mgr)
	action_handler = ActionHandler.new(); action_handler.setup(self, state, cmd_proc, region_mgr, world_mgr, graph_controller, ui_mgr, inspector)
	
	inspector.set_action_handler(action_handler)
	
	_connect_ui_signals()
	_connect_inspector_signals()
	_connect_graph_signals()
	
	_bootstrap_ui()
	if FileAccess.file_exists("res://data/regions/town.json"): _load_region("town.json")
	else: _load_region("")

func _process(_delta):
	if ui_mgr:
		ui_mgr.update_status_coords(get_global_mouse_position())
		if ui_mgr.search_modal.visible and ui_mgr.search_data_cache.is_empty():
			ui_mgr.cache_search_data(world_mgr.get_all_world_data(), database_mgr.npcs, database_mgr.items)

func _bootstrap_ui():
	if ui_mgr.footer_container:
		var btn_reg = Button.new(); btn_reg.text = "Region Settings"
		ui_mgr.footer_container.add_child(btn_reg); ui_mgr.footer_container.move_child(btn_reg, 0)
		ui_mgr._apply_style(btn_reg, Color(0.2, 0.25, 0.3))
		btn_reg.pressed.connect(func(): inspector.load_region_root(region_mgr.data))
	if not DirAccess.dir_exists_absolute("res://data/regions/"): DirAccess.make_dir_recursive_absolute("res://data/regions/")
	_update_db_ui()

func _update_db_ui():
	ui_mgr.update_db_lists(
		database_mgr.npcs, 
		database_mgr.items, 
		database_mgr.templates,
		database_mgr.magic,
		database_mgr.quests,
		database_mgr.dirty_flags
	)

func _connect_ui_signals():
	ui_mgr.request_load_region.connect(_load_region)
	ui_mgr.request_validate.connect(func(): ui_mgr.show_validation_results(world_mgr.validate_world_links())) 
	ui_mgr.request_create_connection.connect(action_handler.create_connection)
	ui_mgr.request_create_region.connect(_create_region)
	ui_mgr.context_action.connect(action_handler.handle_context_action)
	ui_mgr.snap_toggled.connect(func(b): state.snap_enabled=b; graph_controller.set_snap(b); grid_layer.visible=(b and not state.is_world_view); grid_layer.queue_redraw())
	ui_mgr.creation_direction_selected.connect(action_handler.create_room_from_anchor)
	ui_mgr.tool_changed.connect(func(m, d): state.cur_tool_mode=m; state.cur_tool_data=d; ui_mgr.update_tool_display(m, d); if m!=EditorUIManager.ToolMode.SELECT: _deselect_all())
	ui_mgr.request_jump_to_room.connect(_jump_to_room)
	ui_mgr.request_jump_to_error.connect(func(f, i): 
		if f != region_mgr.current_filename: _load_region(f, false, true)
		await get_tree().create_timer(0.01).timeout; _jump_to_room(i)
	)
	ui_mgr.request_toggle_world_view.connect(func(enabled): _set_world_view(enabled))
	ui_mgr.request_auto_layout.connect(_on_request_layout)
	ui_mgr.request_center_view.connect(func(): camera_controller.center_on_nodes(graph_controller.get_active_nodes()))
	ui_mgr.request_copy.connect(_on_copy_request)
	ui_mgr.request_paste.connect(_on_paste_request)
	
	# Connect View Mode
	ui_mgr.view_mode_changed.connect(func(mode): graph_controller.set_view_mode(mode))

	ui_mgr.request_select_db_entry.connect(func(t, id): 
		if t=="template": return
		var d
		match t:
			"npc": d = database_mgr.npcs[id]
			"item": d = database_mgr.items[id]
			"magic": d = database_mgr.magic[id]
			"quest": d = database_mgr.quests[id]
		inspector.load_db_object(t, id, d); _deselect_room_only()
	)
	ui_mgr.request_create_db_entry.connect(func(t):
		var id = "new_" + t; var d = {"name": "New " + t.capitalize()}
		match t:
			"npc": database_mgr.add_npc(id, d)
			"item": database_mgr.add_item(id, d)
			"magic": database_mgr.add_magic(id, d)
			"quest": database_mgr.add_quest(id, d)
		_update_db_ui()
	)
	ui_mgr.request_delete_db_entry.connect(func(t, id):
		database_mgr.delete_entry(t, id); _update_db_ui(); inspector.clear_selection()
	)
	ui_mgr.request_delete_room_confirm.connect(action_handler.execute_delete_room)

func _connect_inspector_signals():
	inspector.request_rename.connect(func(o, n): 
		cmd_proc.commit(
			func(): region_mgr.rename_room(o, n); _refresh_view(); _on_node_click(n, false); _update_explorer_dirty_state(),
			func(): region_mgr.rename_room(n, o); _refresh_view(); _on_node_click(o, false); _update_explorer_dirty_state(),
			"Rename Room"
		)
	)
	inspector.request_connection_modal.connect(func(): 
		if state.selected_ids.size() == 1: 
			var id = state.selected_ids[0]
			inspector.load_connection_form(id, region_mgr.data.rooms[id].name, world_mgr.get_global_hierarchy(), region_mgr.current_filename)
	)
	inspector.connection_created.connect(action_handler.create_connection)
	inspector.target_selected_in_connector.connect(_on_connection_target_selected)
	inspector.request_save_template.connect(_on_save_template_request)
	inspector.save_triggered.connect(func(): 
		if state.is_world_view: world_mgr.save_world_layout() 
		else:
			region_mgr.save_region(); region_mgr.mark_clean(); _update_explorer_dirty_state()
			database_mgr.save_all(); _update_db_ui()
	)
	inspector.reload_triggered.connect(func():
		_deselect_all(); 
		if state.is_world_view: world_mgr.load_world_layout(); _refresh_view(); camera_controller.center_on_nodes(graph_controller.get_active_nodes())
		else: _load_region(region_mgr.current_filename, true)
	)
	inspector.data_modified.connect(_on_data_modified)
	inspector.database_modified.connect(func():
		if inspector.current_inspector:
			if inspector.cur_mode == "quest":
				database_mgr.mark_dirty("quest", inspector.current_inspector.cur_id)
			elif inspector.cur_mode in ["npc", "item", "magic"]:
				database_mgr.mark_dirty(inspector.cur_mode, inspector.current_inspector.cur_id)
		_update_db_ui()
	)
	
	inspector.request_graph_edit_mode.connect(func(qid):
		var q_data = database_mgr.quests.get(qid, {})
		inspector.load_quest_mode(qid)
		graph_controller.load_quest_graph(qid, q_data)
		camera_controller.center_on_nodes(graph_controller.get_active_nodes())
	)

func _connect_graph_signals():
	graph_controller.world_region_selected.connect(_on_world_region_selected)
	graph_controller.node_drag_started.connect(func(_id): is_dragging_object = true)
	graph_controller.world_view_builder.region_dragged.connect(func(): is_dragging_object = true)
	graph_controller.node_selected.connect(func(id): _on_node_click(id, Input.is_key_pressed(KEY_SHIFT)))
	graph_controller.node_drag_started.connect(func(id):
		if not state.is_selected(id): return 
		state.drag_start_positions.clear()
		for sel_id in state.selected_ids: state.drag_start_positions[sel_id] = graph_controller.get_node_position(sel_id)
	)
	graph_controller.node_dragging.connect(func(id, current_pos):
		var id_str = str(id)
		if not state.is_selected(id_str) or not state.drag_start_positions.has(id_str): return
		var delta = current_pos - state.drag_start_positions[id_str]
		for sel_id in state.selected_ids:
			if sel_id != id_str and state.drag_start_positions.has(sel_id):
				graph_controller.set_node_position(sel_id, state.drag_start_positions[sel_id] + delta)
	)
	graph_controller.node_dragged.connect(func(id, new_pos):
		is_dragging_object = false
		var id_str = str(id)
		if state.drag_start_positions.has(id_str) and state.is_selected(id_str):
			var delta = new_pos - state.drag_start_positions[id_str]
			if delta.length_squared() > 1.0: action_handler.commit_batch_move(delta)
	)
	graph_controller.node_right_clicked.connect(func(id):
		if state.is_world_view: return
		if ":" in str(id):
			var parts = id.split(":"); var target_region_file = parts[0] + ".json"; var target_room_id = parts[1]
			_load_region(target_region_file, false, true); await get_tree().create_timer(0.05).timeout; _jump_to_room(target_room_id)
		else: ui_mgr.show_context_menu({"Rename":0, "Delete":99, "Set Start":3}); ui_mgr.context_menu.set_meta("target_type", "room"); ui_mgr.context_menu.set_meta("target_id", str(id))
	)
	graph_controller.connection_drag_started.connect(func(id): state.dragging_conn={"active":true, "start":graph_controller.get_node_position(id), "end":Vector2.ZERO, "src":id})
	graph_controller.creation_drag_started.connect(func(id, pos): state.creating_conn={"active":true, "start_pos":pos, "end_pos":pos, "src_id":id})
	graph_controller.region_moved.connect(func(id, old, new):
		cmd_proc.commit(
			func(): world_mgr.update_world_node_pos(id, new); _refresh_view(),
			func(): world_mgr.update_world_node_pos(id, old); _refresh_view(),
			"Move Region"
		)
	)
	graph_controller.request_region_edit.connect(func(id): ui_mgr.btn_world_view.button_pressed = false; _load_region(id + ".json", false, true))

func _unhandled_input(event):
	if event is InputEventKey and event.pressed:
		if event.keycode == KEY_Z and event.ctrl_pressed: cmd_proc.undo(); if not state.is_world_view: _refresh_view(); _on_data_modified()
		elif event.keycode == KEY_Y and event.ctrl_pressed: cmd_proc.redo(); if not state.is_world_view: _refresh_view(); _on_data_modified()
		elif event.keycode == KEY_ESCAPE:
			if state.cur_tool_mode != EditorUIManager.ToolMode.SELECT: ui_mgr.tool_changed.emit(EditorUIManager.ToolMode.SELECT, {})
			elif state.is_box_selecting: state.is_box_selecting = false; graph_controller.update_selection_box(Rect2(), false)
		elif event.keycode == KEY_F: camera_controller.center_on_nodes(graph_controller.get_active_nodes())
		elif event.keycode == KEY_F and event.ctrl_pressed: ui_mgr.show_search_modal()

	if ui_mgr.is_mouse_over_ui(): return

	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		var mouse_pos = get_global_mouse_position()
		var is_on_node = _is_mouse_on_any_node(mouse_pos)

		if event.pressed:
			is_dragging_object = false
			if not is_on_node and not state.is_box_selecting and state.cur_tool_mode == EditorUIManager.ToolMode.STAMP and state.cur_tool_data.get("type") == "room_template":
				_stamp_template_at(mouse_pos)
				return 

			if not is_on_node and not state.is_box_selecting:
				deselection_primed = true; mouse_down_pos = mouse_pos
		else:
			if deselection_primed and not is_dragging_object and mouse_pos.distance_to(mouse_down_pos) < DRAG_PIXEL_THRESHOLD: _deselect_all()
			deselection_primed = false; is_dragging_object = false

	if not state.is_box_selecting and camera_controller.handle_input(event):
		if camera_controller.is_panning: is_dragging_object = true
		graph_controller.queue_redraw(); grid_layer.queue_redraw()
		return

	if state.dragging_conn.get("active", false):
		if event is InputEventMouseButton and not event.pressed:
			var target_id = graph_controller.get_room_under_mouse(get_global_mouse_position())
			var src_name = region_mgr.data.rooms.get(state.dragging_conn.src, {}).get("name", "...")
			if target_id != "" and target_id != state.dragging_conn.src: 
				inspector.load_connection_form(state.dragging_conn.src, src_name, world_mgr.get_global_hierarchy(), region_mgr.current_filename, target_id)
			else: inspector.load_connection_form(state.dragging_conn.src, src_name, world_mgr.get_global_hierarchy(), region_mgr.current_filename)
			state.dragging_conn.active = false; graph_controller.queue_redraw()
		elif event is InputEventMouseMotion: graph_controller.queue_redraw()
		return

	if state.creating_conn.get("active", false) and event is InputEventMouseButton and not event.pressed:
		ui_mgr.show_creation_menu(event.position); state.creating_conn.active = false; graph_controller.queue_redraw()
		return

	if state.cur_tool_mode == EditorUIManager.ToolMode.SELECT and event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed and event.shift_pressed:
		state.is_box_selecting = true; state.box_select_start = get_global_mouse_position()
		return

func _is_mouse_on_any_node(mouse_pos: Vector2) -> bool:
	if state.is_world_view:
		for region_node in graph_controller.world_view_builder.world_region_nodes.values():
			if is_instance_valid(region_node):
				var cam_zoom = main_camera.zoom.x if main_camera else 1.0
				var local_rect = region_node._get_current_visuals(cam_zoom).main_rect
				var global_transform = region_node.get_global_transform()
				var global_rect = global_transform * local_rect
				if global_rect.has_point(mouse_pos): return true
	else:
		if graph_controller.get_room_under_mouse(mouse_pos) != "": return true
	return false

func _stamp_template_at(pos: Vector2):
	var template_id = state.cur_tool_data.get("id")
	if not database_mgr.templates.has(template_id): return
	
	var tmpl_data = database_mgr.templates[template_id]
	var new_id = "room_" + str(Time.get_ticks_msec()) + "_" + str(randi() % 1000)
	while region_mgr.data.rooms.has(new_id):
		new_id = "room_" + str(Time.get_ticks_msec()) + "_" + str(randi() % 1000)
	
	var new_room_data = tmpl_data.duplicate(true)
	new_room_data.erase("_filename")
	new_room_data.erase("id")
	new_room_data.exits = {} 
	new_room_data._editor_pos = [pos.x, pos.y]
	
	cmd_proc.commit(
		func():
			region_mgr.add_room_data(new_id, new_room_data)
			_refresh_view(); _on_node_click(new_id, false)
			region_mgr.mark_room_dirty(new_id); _update_explorer_dirty_state(),
		func():
			region_mgr.remove_room_data(new_id)
			_refresh_view(); _update_explorer_dirty_state(),
		"Stamp Room Template"
	)

func _on_save_template_request(room_id):
	if not region_mgr.data.rooms.has(room_id): return
	var room_data = region_mgr.data.rooms[room_id].duplicate(true)
	var template_id = room_data.get("name", "template").to_snake_case() + "_tpl"
	database_mgr.save_template(template_id, room_data)
	_update_db_ui()
	print("Saved template: " + template_id)

func _on_copy_request():
	editor_clipboard.clear()
	if state.selected_ids.is_empty(): return
	for id in state.selected_ids:
		if region_mgr.data.rooms.has(id):
			editor_clipboard.append(region_mgr.data.rooms[id].duplicate(true))
	print("Copied %d rooms." % editor_clipboard.size())

func _on_paste_request():
	if editor_clipboard.is_empty() or state.is_world_view: return
	var new_ids = []; var paste_offset = Vector2(50, 50)
	for room_data in editor_clipboard:
		var new_id = "room_" + str(Time.get_ticks_msec()) + "_" + str(randi() % 1000)
		while region_mgr.data.rooms.has(new_id):
			new_id = "room_" + str(Time.get_ticks_msec()) + "_" + str(randi() % 1000)
			
		var new_data = room_data.duplicate(true)
		var old_pos = Vector2(new_data._editor_pos[0], new_data._editor_pos[1])
		var new_pos = old_pos + paste_offset
		new_data._editor_pos = [new_pos.x, new_pos.y]
		new_data.exits = {}
		region_mgr.add_room_data(new_id, new_data)
		region_mgr.mark_room_dirty(new_id)
		new_ids.append(new_id)
	
	_refresh_view()
	state.set_selection(new_ids)
	_update_selection_state()
	_update_explorer_dirty_state()
	print("Pasted %d rooms." % editor_clipboard.size())

func _load_region(file, force_reload: bool = false, keep_ui_visible: bool = false):
	if state.is_world_view:
		# Use helper to sync button state
		ui_mgr.set_world_view_button_state(false)
		_set_world_view(false)
	
	if not force_reload and file == region_mgr.current_filename and file != "": return
	
	if region_mgr.current_filename != "": view_states[region_mgr.current_filename] = {"pos": main_camera.position, "zoom": main_camera.zoom}
	
	if file == "" or region_mgr.load_region(file):
		if not keep_ui_visible: _deselect_all()
		_refresh_view()
		
		if view_states.has(file):
			var vs = view_states[file]; main_camera.position = vs.pos; main_camera.zoom = vs.zoom
		else:
			camera_controller.center_on_nodes(graph_controller.get_active_nodes())

		var rooms = region_mgr.data.get("rooms", {})
		var exit_count = 0
		for r in rooms.values():
			exit_count += r.get("exits", {}).size()
		ui_mgr.update_status_info(region_mgr.data.get("name", file), rooms.size(), "", exit_count)
		ui_mgr.call_deferred("refresh_explorer", world_mgr.get_global_hierarchy(), file, "")

func _create_region(name, rooms_data):
	if not name.ends_with(".json"): name += ".json"
	var new_data = { "region_id": name.replace(".json", ""), "description": "New region", "rooms": rooms_data }
	var file = FileAccess.open("res://data/regions/" + name, FileAccess.WRITE)
	if file: file.store_string(JSON.stringify(new_data, "\t")); file.close()
	_load_region(name)

func _on_node_click(id: String, shift_mod: bool):
	if state.is_world_view: return
	
	match state.cur_tool_mode:
		EditorUIManager.ToolMode.PAINT:
			var k = state.cur_tool_data.get("key", ""); var v = state.cur_tool_data.get("val", "")
			if k and region_mgr.data.rooms.has(id): 
				if not region_mgr.data.rooms[id].has("properties"): region_mgr.data.rooms[id]["properties"] = {}
				var val = v if not v in ["true", "false"] else v == "true"
				region_mgr.data.rooms[id]["properties"][k] = val; _on_data_modified()
			return
		EditorUIManager.ToolMode.STAMP:
			if state.cur_tool_data.get("type") == "room_template": return 
			if not region_mgr.data.rooms.has(id): return
			var t = state.cur_tool_data.get("type"); var cid = state.cur_tool_data.get("id")
			var key = "initial_npcs" if t == "npc" else "items"
			var data_key = "template_id" if t == "npc" else "item_id"
			if not region_mgr.data.rooms[id].has(key): region_mgr.data.rooms[id][key] = []
			region_mgr.data.rooms[id][key].append({data_key: cid}); _on_data_modified()
			return
	
	if state.dragging_conn.active and id != state.dragging_conn.src: return
	
	if inspector.cur_mode == "connection":
		var parts = id.split(":"); inspector.set_connection_target(parts[0], parts[1])
		return

	if shift_mod:
		if state.is_selected(id): state.remove_from_selection(id)
		else: state.add_to_selection(id)
	elif not state.is_selected(id):
		state.set_selection([id])
	
	_update_selection_state()

func _on_connection_target_selected(target_id: String):
	state.highlighted_target_id = target_id
	if target_id != "" and inspector.connection_editor:
		state.connection_preview.active = true
		state.connection_preview.source_id = inspector.connection_editor.conn_src_id
		state.connection_preview.target_id = target_id
	else:
		state.connection_preview.active = false
	graph_controller.update_highlight_visuals(); graph_controller.queue_redraw()

func _on_world_region_selected(region_id: String):
	if not state.is_world_view: return
	state.set_selection([region_id])
	graph_controller.update_selection_visuals(state.selected_ids)
	var all_data = world_mgr.get_all_world_data()
	if all_data.has(region_id): inspector.load_region_root(all_data[region_id])
	graph_controller.queue_redraw()

func _update_selection_state():
	graph_controller.update_selection_visuals(state.selected_ids)
	if state.selected_ids.size() == 1:
		var id = state.selected_ids[0]
		
		if graph_controller.current_mode == GraphController.ViewMode.QUEST:
			pass
		else:
			camera_controller.focus_on(graph_controller.get_node_position(id), false)
			
		if region_mgr.data.rooms.has(id):
			inspector.load_room(id, region_mgr.data.rooms[id]); ui_mgr.select_room_item(id)
		else: inspector.load_external_ref(id)
	elif state.selected_ids.size() > 1:
		inspector.load_multi_selection(state.selected_ids); ui_mgr.select_room_item("")
	else:
		_deselect_all(false)

func _jump_to_room(id):
	_on_node_click(id, false); camera_controller.focus_on(graph_controller.get_node_position(id), true)

func _refresh_view():
	graph_controller.rebuild(region_mgr.data, world_mgr.get_all_world_data(), world_mgr.world_node_positions, region_mgr.current_filename)

func _set_world_view(enabled: bool):
	var cache_key = "world_view" if state.is_world_view else region_mgr.current_filename
	if cache_key != "": view_states[cache_key] = {"pos": main_camera.position, "zoom": main_camera.zoom}
	
	state.is_world_view = enabled
	state.creating_conn = { "active": false }; state.dragging_conn = { "active": false }
	_deselect_all()
	grid_layer.visible = state.snap_enabled and not state.is_world_view
	_refresh_view()
	
	if enabled:
		inspector.load_world_mode()
		var all_data = world_mgr.get_all_world_data()
		var total_rooms = 0
		for r_data in all_data.values():
			total_rooms += r_data.get("rooms", {}).size()
		ui_mgr.update_status_info("World Map", total_rooms, "%d Regions" % all_data.size())
		
		if view_states.has("world_view"):
			var vs = view_states["world_view"]; main_camera.position = vs.pos; main_camera.zoom = vs.zoom
		else: main_camera.zoom = Vector2.ONE; camera_controller.center_on_nodes(graph_controller.get_active_nodes())
	elif view_states.has(region_mgr.current_filename):
		# Re-calculate and display region info when switching back
		var rooms = region_mgr.data.get("rooms", {})
		var exit_count = 0
		for r in rooms.values():
			exit_count += r.get("exits", {}).size()
		ui_mgr.update_status_info(region_mgr.data.get("name", region_mgr.current_filename), rooms.size(), "", exit_count)
		
		var vs = view_states[region_mgr.current_filename]; main_camera.position = vs.pos; main_camera.zoom = vs.zoom

func _on_request_layout():
	if state.is_world_view:
		var all_data = world_mgr.get_all_world_data()
		var old_positions = world_mgr.world_node_positions.duplicate()
		var new_positions = LayoutOptimizer.optimize_world_layout(all_data)
		cmd_proc.commit(
			func():
				for rid in new_positions: world_mgr.update_world_node_pos(rid, new_positions[rid])
				_refresh_view(),
			func():
				world_mgr.world_node_positions = old_positions; _refresh_view(),
			"Auto-Arrange World Map"
		)
	else:
		var old_pos = {}; for id in region_mgr.data.rooms: old_pos[id] = Vector2(region_mgr.data.rooms[id]._editor_pos[0], region_mgr.data.rooms[id]._editor_pos[1])
		var new_pos = LayoutOptimizer.optimize_layout(region_mgr.data.rooms)
		cmd_proc.commit(
			func():
				for id in new_pos: region_mgr.set_room_pos(id, new_pos[id])
				_refresh_view(); camera_controller.center_on_nodes(graph_controller.get_active_nodes()),
			func():
				for id in old_pos: region_mgr.set_room_pos(id, old_pos[id])
				_refresh_view(); camera_controller.center_on_nodes(graph_controller.get_active_nodes()),
			"Auto-Arrange Layout"
		)

func _deselect_all(hide_ui: bool = true): 
	state.clear_selection()
	if state.is_world_view:
		graph_controller.update_selection_visuals([])
		inspector.load_world_mode()
	else:
		graph_controller.update_selection_visuals([])
		inspector.clear_selection(hide_ui)

func _deselect_room_only(): 
	state.clear_selection(); graph_controller.update_selection_visuals([])

func _on_data_modified():
	if not state.is_world_view:
		for id in state.selected_ids:
			region_mgr.mark_room_dirty(id)
			graph_controller.update_specific_node(id, region_mgr.data)
		_update_explorer_dirty_state()
	graph_controller.queue_redraw()

func _update_explorer_dirty_state():
	if cached_hierarchy.is_empty():
		cached_hierarchy = world_mgr.get_global_hierarchy()
	
	if region_mgr.data.has("region_id"):
		var rid = region_mgr.data.region_id
		var live_rooms = {}
		for r_id in region_mgr.data.rooms:
			live_rooms[r_id] = region_mgr.data.rooms[r_id].get("name", "Unnamed")
		
		cached_hierarchy[rid] = {
			"filename": region_mgr.current_filename, 
			"rooms": live_rooms
		}

	var selected = state.selected_ids[0] if not state.selected_ids.is_empty() else ""
	ui_mgr.refresh_explorer(cached_hierarchy, region_mgr.current_filename, selected)
	ui_mgr.update_dirty_visuals(region_mgr.current_filename, region_mgr.is_region_dirty, region_mgr.dirty_room_ids)
