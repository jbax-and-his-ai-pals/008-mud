# scripts/controllers/GraphController.gd
class_name GraphController
extends RefCounted

# Signals
signal node_selected(id)
signal node_drag_started(id)
signal node_dragging(id, current_pos)
signal node_dragged(id, final_pos)
signal node_right_clicked(id)
signal connection_drag_started(id)
signal creation_drag_started(id, pos)
signal request_region_edit(region_id)
signal region_moved(region_id, old_pos, new_pos)
signal world_region_selected(region_id)

enum ViewMode { LOCAL, WORLD, QUEST }
var current_mode = ViewMode.LOCAL
var current_view_mode_filter: String = "Default"

# Child nodes
var container: Node2D
var connection_layer: Node2D

# View Builders
var local_view_builder: LocalViewBuilder
var world_view_builder: WorldViewBuilder
var quest_view_builder: QuestViewBuilder

# State
var editor_state: EditorState
var region_data: Dictionary
var world_data: Dictionary
var world_positions: Dictionary
var current_region_filename: String
var current_quest_data: Dictionary = {}

var selection_box: Rect2 = Rect2()
var is_box_selecting: bool = false

const LOCAL_VIEW_BUILDER = preload("res://scripts/controllers/view_builders/LocalViewBuilder.gd")
const WORLD_VIEW_BUILDER = preload("res://scripts/controllers/view_builders/WorldViewBuilder.gd")
const QUEST_VIEW_BUILDER = preload("res://scripts/controllers/view_builders/QuestViewBuilder.gd")

func setup(_container: Node2D, _conn_layer: Node2D, p_state: EditorState):
	container = _container
	connection_layer = _conn_layer
	editor_state = p_state
	
	connection_layer.z_index = 10
	connection_layer.draw.connect(_on_draw_connections)
	
	local_view_builder = LOCAL_VIEW_BUILDER.new(container)
	world_view_builder = WORLD_VIEW_BUILDER.new(container)
	quest_view_builder = QUEST_VIEW_BUILDER.new(container)
	
	_forward_builder_signals()

func _forward_builder_signals():
	local_view_builder.node_selected.connect(func(id): node_selected.emit(id))
	local_view_builder.node_drag_started.connect(func(id): node_drag_started.emit(id))
	local_view_builder.node_dragging.connect(func(id, pos): node_dragging.emit(id, pos); queue_redraw())
	local_view_builder.node_dragged.connect(func(id, pos): node_dragged.emit(id, pos))
	local_view_builder.node_right_clicked.connect(func(id): node_right_clicked.emit(id))
	local_view_builder.connection_drag_started.connect(func(id): connection_drag_started.emit(id))
	local_view_builder.creation_drag_started.connect(func(id, pos): creation_drag_started.emit(id, pos))
	
	world_view_builder.region_node_selected.connect(func(id): world_region_selected.emit(id))
	world_view_builder.region_moved.connect(func(id, old, new): region_moved.emit(id, old, new))
	world_view_builder.request_region_edit.connect(func(id): request_region_edit.emit(id))
	world_view_builder.region_dragged.connect(func(): queue_redraw())
	
	quest_view_builder.node_selected.connect(func(idx): node_selected.emit(idx))
	quest_view_builder.node_moved.connect(func(idx, pos): 
		if current_quest_data.has("stages") and idx < current_quest_data.stages.size():
			current_quest_data.stages[idx]["_editor_pos"] = [pos.x, pos.y]
		queue_redraw()
	)

func set_view_mode(mode: String):
	current_view_mode_filter = mode
	if current_mode == ViewMode.LOCAL:
		for id in local_view_builder.room_nodes:
			var node = local_view_builder.room_nodes[id]
			if region_data.get("rooms", {}).has(id):
				local_view_builder.update_node_visuals(node, region_data.rooms[id], mode)

func rebuild(p_region_data: Dictionary, p_world_data: Dictionary, p_world_pos: Dictionary, p_current_file: String):
	region_data = p_region_data
	world_data = p_world_data
	world_positions = p_world_pos
	current_region_filename = p_current_file
	
	current_mode = ViewMode.WORLD if editor_state.is_world_view else ViewMode.LOCAL
	
	if current_mode == ViewMode.WORLD:
		world_view_builder.build(world_data, world_positions, region_data, current_region_filename)
	else:
		local_view_builder.build(region_data, editor_state.snap_enabled)
		# Re-apply view mode if needed
		if current_view_mode_filter != "Default":
			set_view_mode(current_view_mode_filter)
	
	update_selection_visuals(editor_state.selected_ids)
	queue_redraw()

func load_quest_graph(quest_id: String, q_data: Dictionary):
	current_mode = ViewMode.QUEST
	current_quest_data = q_data
	quest_view_builder.build(q_data)
	queue_redraw()

func queue_redraw():
	if editor_state == null: return
	connection_layer.queue_redraw()
	if current_mode == ViewMode.WORLD:
		for node in world_view_builder.world_region_nodes.values():
			if is_instance_valid(node): node.queue_redraw()

func update_highlight_visuals():
	if current_mode == ViewMode.LOCAL:
		for id in local_view_builder.room_nodes:
			var node = local_view_builder.room_nodes[id]
			if is_instance_valid(node):
				node.set_highlighted(id == editor_state.highlighted_target_id)

func update_specific_node(id: String, p_region_data: Dictionary):
	if current_mode == ViewMode.LOCAL and local_view_builder.room_nodes.has(id):
		var node = local_view_builder.room_nodes[id]
		if p_region_data.get("rooms", {}).has(id):
			var data = p_region_data.rooms[id]
			node.position = Vector2(data._editor_pos[0], data._editor_pos[1])
			node.set_info(data.get("name", "Unnamed"), id)
			local_view_builder.update_node_visuals(node, data, current_view_mode_filter)
		elif p_region_data.get("_proxy_positions", {}).has(id):
			var pos_data = p_region_data._proxy_positions[id]
			node.position = Vector2(pos_data[0], pos_data[1])
		queue_redraw()

func set_node_position(id: String, pos: Vector2):
	if current_mode == ViewMode.LOCAL and local_view_builder.room_nodes.has(id):
		local_view_builder.room_nodes[id].position = pos

func update_selection_visuals(selected_ids: Array):
	if current_mode == ViewMode.WORLD:
		for rid in world_view_builder.world_region_nodes:
			var node = world_view_builder.world_region_nodes[rid]
			if is_instance_valid(node): node.set_selected(rid in selected_ids)
	elif current_mode == ViewMode.LOCAL:
		for rid in local_view_builder.room_nodes:
			var node = local_view_builder.room_nodes[rid]
			if is_instance_valid(node): node.set_selected(rid in selected_ids)
	elif current_mode == ViewMode.QUEST:
		for idx in quest_view_builder.quest_nodes:
			var node = quest_view_builder.quest_nodes[idx]
			pass

func set_snap(enabled: bool):
	if current_mode == ViewMode.LOCAL:
		for node in local_view_builder.room_nodes.values():
			node.snap_step = 32 if enabled else 0

func get_node_position(id: String) -> Vector2:
	if current_mode == ViewMode.LOCAL and local_view_builder.room_nodes.has(id):
		return local_view_builder.room_nodes[id].position
	return Vector2.ZERO

func get_room_under_mouse(global_pos: Vector2) -> String:
	if current_mode != ViewMode.LOCAL: return ""
	for id in local_view_builder.room_nodes:
		var node = local_view_builder.room_nodes[id]
		var rect = node.get_node("VisualPanel").get_global_rect()
		if rect.has_point(global_pos): return id
	return ""

func get_nodes_in_rect(global_rect: Rect2) -> Array:
	var result = []
	if current_mode == ViewMode.LOCAL:
		for id in local_view_builder.room_nodes:
			if global_rect.has_point(local_view_builder.room_nodes[id].global_position):
				result.append(id)
	return result

func update_selection_box(rect: Rect2, active: bool):
	selection_box = rect; is_box_selecting = active; queue_redraw()

func get_active_nodes() -> Dictionary:
	if current_mode == ViewMode.WORLD: return world_view_builder.world_region_nodes
	if current_mode == ViewMode.QUEST: return quest_view_builder.quest_nodes
	return local_view_builder.room_nodes

# --- DRAWING ---

func _on_draw_connections():
	if editor_state == null: return

	if current_mode == ViewMode.QUEST:
		quest_view_builder.draw_connections(connection_layer, current_quest_data)
		return

	if current_mode == ViewMode.WORLD:
		_draw_world_connections()
	else:
		_draw_local_connections()

func _draw_local_connections():
	if editor_state.connection_preview.get("active", false):
		var src_id = editor_state.connection_preview.source_id
		var tgt_id = editor_state.connection_preview.target_id
		if local_view_builder.room_nodes.has(src_id) and local_view_builder.room_nodes.has(tgt_id):
			var p1 = local_view_builder.room_nodes[src_id].position
			var p2 = local_view_builder.room_nodes[tgt_id].position
			connection_layer.draw_dashed_line(p1, p2, Color.MAGENTA, 3.0, 10.0)
	
	if editor_state.creating_conn.get("active", false):
		connection_layer.draw_line(editor_state.creating_conn.start_pos, editor_state.creating_conn.end_pos, Color.LIME_GREEN, 3.0)
	
	# Connection Drag Visuals
	if editor_state.dragging_conn.get("active", false):
		var mouse_pos = connection_layer.get_global_mouse_position()
		editor_state.dragging_conn.end = mouse_pos
		
		# Draw drag line
		var start_pos = connection_layer.to_local(editor_state.dragging_conn.start)
		var end_pos = connection_layer.to_local(editor_state.dragging_conn.end)
		
		# Check for potential target snapping
		var target_id = get_room_under_mouse(mouse_pos)
		var src_id = editor_state.dragging_conn.src
		
		if target_id != "" and target_id != src_id and local_view_builder.room_nodes.has(target_id):
			var target_node = local_view_builder.room_nodes[target_id]
			end_pos = target_node.position # Snap line end to center
			
			# Draw Glow around target
			var rect = Rect2(target_node.position - Vector2(45, 45), Vector2(90, 90))
			connection_layer.draw_rect(rect, Color(0.2, 1.0, 0.4, 0.3), false, 4.0)
			
		connection_layer.draw_line(start_pos, end_pos, Color(1.0, 0.8, 0.2), 3.0)
	
	GraphRenderer.draw_graph(connection_layer, local_view_builder.room_nodes, region_data, editor_state.selected_ids[0] if editor_state.selected_ids.size() == 1 else "", editor_state.dragging_conn)
	
	if is_box_selecting:
		var col = Color(0.2, 0.6, 1.0, 0.3); var border = Color(0.4, 0.8, 1.0, 0.8)
		var local_rect = Rect2(connection_layer.to_local(selection_box.position), selection_box.size)
		connection_layer.draw_rect(local_rect, col, true); connection_layer.draw_rect(local_rect, border, false, 1.0)

func _draw_world_connections():
	var drawn_pairs = {}
	var cam = connection_layer.get_viewport().get_camera_2d()
	var zoom = cam.zoom.x if cam else 1.0
	var scale_factor = clamp(1.0 / sqrt(zoom), 1.0, 3.0)
	var base_line_width = 0.5
	var selected_region_id = editor_state.selected_ids[0] if not editor_state.selected_ids.is_empty() else ""
	
	for src_rid in world_data:
		for src_room_id in world_data[src_rid].get("rooms", {}):
			for dir in world_data[src_rid].rooms[src_room_id].get("exits", {}):
				var target_raw = world_data[src_rid].rooms[src_room_id].exits[dir]
				if ":" in target_raw:
					var parts = target_raw.split(":"); var tgt_rid = parts[0]; var tgt_room_id = parts[1]
					if tgt_rid != src_rid and world_view_builder.world_region_nodes.has(src_rid) and world_view_builder.world_region_nodes.has(tgt_rid):
						var is_highlighted = (src_rid == selected_region_id or tgt_rid == selected_region_id)
						var is_bi = world_data.get(tgt_rid, {}).get("rooms", {}).get(tgt_room_id, {}).get("exits", {}).values().has(src_rid + ":" + src_room_id)
						if is_bi:
							var k = [src_rid, tgt_rid]; k.sort()
							var key = k[0] + k[1]
							if drawn_pairs.has(key): continue
							drawn_pairs[key] = true
						
						var n_src = world_view_builder.world_region_nodes[src_rid]
						var n_tgt = world_view_builder.world_region_nodes[tgt_rid]
						var p1 = n_src.global_position + (n_src.get_room_local_center(src_room_id) * n_src.scale)
						var p2 = n_tgt.global_position + (n_tgt.get_room_local_center(tgt_room_id) * n_tgt.scale)
						var line_width = (base_line_width * 2 if is_bi else base_line_width) * scale_factor
						var line_color = Color.GOLD if is_highlighted else (Color.WHITE if is_bi else Color(0.8, 0.8, 0.8, 0.5))
						
						if is_bi or is_highlighted: connection_layer.draw_line(p1, p2, line_color, line_width * (2.0 if is_highlighted else 1.0))
						else: connection_layer.draw_dashed_line(p1, p2, line_color, line_width, 4.0 * scale_factor)
