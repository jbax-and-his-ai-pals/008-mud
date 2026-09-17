# scripts/controllers/GraphController.gd
class_name GraphController
extends RefCounted

const DistrictLayout = preload("res://scripts/generators/DistrictLayout.gd")

# Signals
signal node_selected(id)
signal node_double_clicked(id)
signal node_drag_started(id)
signal node_dragging(id, current_pos)
signal node_dragged(id, final_pos)
signal node_right_clicked(id)
signal connection_drag_started(id)
signal creation_drag_started(id, pos)
signal request_region_edit(region_id)
signal region_moved(region_id, old_pos, new_pos)
signal world_region_selected(region_id)
signal room_label_clicked(id)
signal room_label_drag_started(id)
signal room_label_dragged(id)
signal room_label_drag_ended(id)

enum ViewMode { LOCAL, WORLD, QUEST }
var current_mode = ViewMode.LOCAL
var current_view_mode_filter: String = "Default"

# Child nodes
var container: Node2D
var connection_layer: Node2D
var district_layer: Node2D

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
var label_arrange_mode := false
var show_technical_ids := false

const LOCAL_VIEW_BUILDER = preload("res://scripts/controllers/view_builders/LocalViewBuilder.gd")
const WORLD_VIEW_BUILDER = preload("res://scripts/controllers/view_builders/WorldViewBuilder.gd")
const QUEST_VIEW_BUILDER = preload("res://scripts/controllers/view_builders/QuestViewBuilder.gd")

# How much local wiggle a district border's simplification pass is allowed
# to iron out before drawing it, in pixels. Deliberately independent of the
# territory grid's own cell_size: that constant controls how tightly two
# districts' boundaries track each other, and shrinking it to tighten that
# should not, as a side effect, also shrink how much smoothing the border
# gets -- those are two different knobs answering two different complaints.
const BOUNDARY_SIMPLIFY_TOLERANCE := 56.0

# Shared between the district background renderer and the click hit-test
# below (get_district_id_at) so both agree on exactly where one district's
# territory ends and another's begins.
const DISTRICT_ROOM_RESERVE := 160.0
const DISTRICT_CORRIDOR_RESERVE := 160.0
const DISTRICT_TERRITORY_RADIUS := 176.0

func setup(_container: Node2D, _conn_layer: Node2D, p_state: EditorState, p_district_layer: Node2D = null):
	container = _container
	connection_layer = _conn_layer
	district_layer = p_district_layer
	editor_state = p_state
	
	connection_layer.z_index = 10
	connection_layer.draw.connect(_on_draw_connections)
	if district_layer:
		district_layer.z_index = -1
		district_layer.draw.connect(_on_draw_district_backgrounds)
	
	local_view_builder = LOCAL_VIEW_BUILDER.new(container)
	world_view_builder = WORLD_VIEW_BUILDER.new(container)
	quest_view_builder = QUEST_VIEW_BUILDER.new(container)
	
	_forward_builder_signals()

func _forward_builder_signals():
	local_view_builder.node_selected.connect(func(id): node_selected.emit(id))
	local_view_builder.node_double_clicked.connect(func(id): node_double_clicked.emit(id))
	local_view_builder.node_drag_started.connect(func(id): node_drag_started.emit(id))
	local_view_builder.node_dragging.connect(func(id, pos): node_dragging.emit(id, pos); queue_redraw())
	local_view_builder.node_dragged.connect(func(id, pos): node_dragged.emit(id, pos))
	local_view_builder.node_right_clicked.connect(func(id): node_right_clicked.emit(id))
	local_view_builder.connection_drag_started.connect(func(id): connection_drag_started.emit(id))
	local_view_builder.creation_drag_started.connect(func(id, pos): creation_drag_started.emit(id, pos))
	local_view_builder.label_clicked.connect(func(id): room_label_clicked.emit(id))
	local_view_builder.label_drag_started.connect(func(id): room_label_drag_started.emit(id))
	local_view_builder.label_dragged.connect(func(id): room_label_dragged.emit(id))
	local_view_builder.label_drag_ended.connect(func(id): room_label_drag_ended.emit(id))
	
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
		local_view_builder.build(region_data, editor_state.snap_enabled, world_data)
		set_label_arrange_mode(label_arrange_mode)
		set_show_technical_ids(show_technical_ids)
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
	if district_layer: district_layer.queue_redraw()
	if current_mode == ViewMode.WORLD:
		for node in world_view_builder.world_region_nodes.values():
			if is_instance_valid(node): node.queue_redraw()

func set_label_arrange_mode(enabled: bool):
	label_arrange_mode = enabled
	for id in local_view_builder.room_nodes:
		var node = local_view_builder.room_nodes[id]
		if is_instance_valid(node): node.set_label_arrange_mode(enabled and region_data.get("rooms", {}).has(id))

func set_show_technical_ids(enabled: bool):
	show_technical_ids = enabled
	for node in local_view_builder.room_nodes.values():
		if is_instance_valid(node): node.set_show_technical_id(enabled)

func set_label_swap_target(room_id: String):
	for id in local_view_builder.room_nodes:
		var node = local_view_builder.room_nodes[id]
		if is_instance_valid(node): node.set_label_swap_target(label_arrange_mode and id == room_id)

func set_label_drag_source(room_id: String):
	for id in local_view_builder.room_nodes:
		var node = local_view_builder.room_nodes[id]
		if is_instance_valid(node): node.set_label_drag_source(label_arrange_mode and id == room_id)

func set_label_swap_preview(source_id: String, target_id: String):
	for id in local_view_builder.room_nodes:
		var node = local_view_builder.room_nodes[id]
		if not is_instance_valid(node): continue
		var preview_name := ""
		if label_arrange_mode and source_id != "" and target_id != "" and region_data.get("rooms", {}).has(source_id) and region_data.get("rooms", {}).has(target_id):
			if id == source_id: preview_name = str(region_data.rooms[target_id].get("name", ""))
			elif id == target_id: preview_name = str(region_data.rooms[source_id].get("name", ""))
		node.set_label_preview(preview_name)

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

func get_district_preview_room_under_mouse(global_pos: Vector2) -> String:
	if current_mode != ViewMode.LOCAL or not editor_state.district_preview.get("active", false): return ""
	for room_id in editor_state.district_preview.get("positions", {}):
		var position: Vector2 = editor_state.district_preview.positions[room_id]
		var rect := Rect2(position - DistrictLayout.ROOM_CARD_SIZE / 2.0, DistrictLayout.ROOM_CARD_SIZE)
		if rect.has_point(global_pos): return str(room_id)
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
	if editor_state.district_preview.get("active", false):
		var preview_positions: Dictionary = editor_state.district_preview.get("positions", {})
		var preview_rooms: Dictionary = editor_state.district_preview.get("rooms", {})
		var preview_color := Color(0.25, 1.0, 0.45, 0.24) if editor_state.district_preview.get("valid", false) else Color(1.0, 0.3, 0.3, 0.24)
		var border_color := Color(0.3, 1.0, 0.5, 0.9) if editor_state.district_preview.get("valid", false) else Color(1.0, 0.35, 0.35, 0.9)
		# Draw the internal topology first so the ghost reads as a district, not a
		# loose collection of cards. These intentionally use the same outlined,
		# labelled visual language as normal map connections, with ghost colors.
		var drawn_ghost_pairs := {}
		for room_id in preview_rooms:
			var source_pos: Vector2 = preview_positions.get(room_id, Vector2.ZERO)
			for exit_name in preview_rooms[room_id].get("exits", {}):
				var target_id := str(preview_rooms[room_id]["exits"][exit_name])
				if preview_positions.has(target_id):
					var pair := [str(room_id), target_id]; pair.sort()
					var pair_key: String = str(pair[0]) + "|" + str(pair[1])
					var reverse_name := ""
					for candidate_direction in preview_rooms[target_id].get("exits", {}):
						if str(preview_rooms[target_id]["exits"][candidate_direction]) == str(room_id): reverse_name = str(candidate_direction); break
					if reverse_name != "" and drawn_ghost_pairs.has(pair_key): continue
					if reverse_name != "": drawn_ghost_pairs[pair_key] = true
					# Generated ghost rooms have no persisted metadata yet. Their stable
					# creation order supplies the same source rule used for legacy maps.
					var room_order := preview_rooms.keys()
					var ghost_source := str(room_id) if room_order.find(room_id) <= room_order.find(target_id) else target_id
					var connection_text := Constants.format_reciprocal_pair_label(str(room_id), target_id, str(exit_name), reverse_name, source_pos, preview_positions[target_id], ghost_source) if reverse_name != "" else str(exit_name).capitalize()
					_draw_ghost_connection(source_pos, preview_positions[target_id], connection_text, border_color)
		for room_id in preview_positions:
			var position: Vector2 = preview_positions[room_id]
			var ghost_rect := Rect2(position - DistrictLayout.ROOM_CARD_SIZE / 2.0, DistrictLayout.ROOM_CARD_SIZE)
			connection_layer.draw_rect(ghost_rect, preview_color, true)
			connection_layer.draw_rect(ghost_rect, border_color, false, 2.0)
			var label := str(preview_rooms.get(room_id, {}).get("name", room_id))
			connection_layer.draw_string(ThemeDB.get_fallback_font(), position + Vector2(-70, 4), label, HORIZONTAL_ALIGNMENT_CENTER, 140, 11, border_color)
			if str(editor_state.district_preview.get("selected_port", "")) == str(room_id):
				connection_layer.draw_circle(position, 12.0, Color.GOLD, false, 2.5)
		var port_id := str(editor_state.district_preview.get("selected_port", ""))
		var destination_id := str(editor_state.district_preview.get("target_room", ""))
		var pending_direction := str(editor_state.district_preview.get("direction", ""))
		if port_id != "" and destination_id != "" and pending_direction != "" and preview_positions.has(port_id) and local_view_builder.room_nodes.has(destination_id):
			var destination_pos: Vector2 = local_view_builder.room_nodes[destination_id].position
			var port_pos: Vector2 = preview_positions[port_id]
			var reciprocal := str(Constants.INV_DIR_MAP.get(pending_direction, ""))
			# The picker defines the first direction from the ghost port to the town.
			var connection_invalid: bool = not editor_state.district_preview.get("connection_errors", []).is_empty()
			var connection_color := Color(1.0, 0.34, 0.34, 0.95) if connection_invalid else Color(0.35, 0.8, 1.0, 0.95)
			_draw_ghost_connection(port_pos, destination_pos, Constants.format_reciprocal_label(pending_direction, reciprocal, port_pos, destination_pos), connection_color)
			# A destination marker makes it unambiguous which real room will receive
			# the pending connection without making it look selected for editing.
			connection_layer.draw_circle(destination_pos, 18.0, Color(0.35, 0.8, 1.0, 0.16), true)
			connection_layer.draw_circle(destination_pos, 18.0, Color(0.35, 0.8, 1.0, 0.95), false, 2.0)
			connection_layer.draw_string(ThemeDB.get_fallback_font(), destination_pos + Vector2(-24, -26), "DEST", HORIZONTAL_ALIGNMENT_CENTER, 48, 10, Color(0.6, 0.9, 1.0, 1.0))

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

# One field per district: its member rooms' positions (for the
# nearest-owner/reserved-room rules) and its internal room-to-room
# segments (for the corridor rule). Shared by the background renderer and
# the click hit-test below, so both agree on exactly what territory a
# district owns.
func _build_district_fields() -> Array:
	var districts: Dictionary = region_data.get("properties", {}).get("districts", {})
	var fields: Array = []
	for district_id in districts:
		var district: Dictionary = districts[district_id]
		var members: Array = district.get("members", district.get("rooms", []))
		var positions: Array[Vector2] = []
		for room_id in members:
			if local_view_builder.room_nodes.has(room_id): positions.append(local_view_builder.room_nodes[room_id].position)
		if positions.is_empty(): continue
		var color := Color.from_string(str(district.get("color", "#5d83a6")), Color("5d83a6"))
		var segments: Array = []
		var drawn_internal_links := {}
		for room_id in members:
			if not region_data.get("rooms", {}).has(room_id) or not local_view_builder.room_nodes.has(room_id): continue
			var room: Dictionary = region_data.rooms[room_id]
			for direction in room.get("exits", {}):
				var target_id := str(room["exits"][direction])
				if members.has(target_id) and local_view_builder.room_nodes.has(target_id):
					var pair := [str(room_id), target_id]; pair.sort()
					var pair_key := str(pair[0]) + "|" + str(pair[1])
					if not drawn_internal_links.has(pair_key):
						drawn_internal_links[pair_key] = true
						segments.append({"from": local_view_builder.room_nodes[room_id].position, "to": local_view_builder.room_nodes[target_id].position})
		fields.append({"id": str(district_id), "name": str(district.get("name", district_id)), "color": color, "positions": positions, "segments": segments})
	return fields

# Resolves exactly the same reserved-room / corridor / nearest-territory
# rules _on_draw_district_backgrounds uses to decide a cell's owner, but for
# one point instead of a whole grid -- cheap enough to call from a mouse
# click rather than recomputing the full territory map just to hit-test it.
func _resolve_district_field_index(point: Vector2, fields: Array) -> int:
	var reserved_field := -1
	var reserved_distance := INF
	var corridor_field := -1
	var corridor_distance := INF
	var best_field := -1
	var best_distance := INF
	for field_index in range(fields.size()):
		var member_distance := _district_member_distance(point, fields[field_index])
		if member_distance < DISTRICT_ROOM_RESERVE and member_distance < reserved_distance:
			reserved_distance = member_distance
			reserved_field = field_index
		var segment_distance := _district_segment_distance(point, fields[field_index])
		if segment_distance < DISTRICT_CORRIDOR_RESERVE and segment_distance < corridor_distance:
			corridor_distance = segment_distance
			corridor_field = field_index
		var distance := _district_field_distance(point, fields[field_index])
		if distance < best_distance:
			best_distance = distance
			best_field = field_index
	if reserved_field >= 0: return reserved_field
	if corridor_field >= 0: return corridor_field
	if best_distance <= DISTRICT_TERRITORY_RADIUS: return best_field
	return -1

# The id of the district that owns `world_pos` in the local room-graph
# view, or "" if the point is outside every district's territory (or we're
# not showing districts at all right now).
func get_district_id_at(world_pos: Vector2) -> String:
	if current_mode != ViewMode.LOCAL or region_data.is_empty(): return ""
	var fields := _build_district_fields()
	if fields.is_empty(): return ""
	var field_index := _resolve_district_field_index(world_pos, fields)
	if field_index < 0: return ""
	return str(fields[field_index]["id"])

func _on_draw_district_backgrounds():
	if current_mode != ViewMode.LOCAL or region_data.is_empty() or district_layer == null: return
	var fields := _build_district_fields()
	if fields.is_empty(): return
	var font := ThemeDB.get_fallback_font()
	var bounds := Rect2()
	var has_bounds := false
	for field in fields:
		for position in field["positions"]:
			var pad_bounds := Rect2(position - Vector2(176, 176), Vector2(352, 352))
			bounds = pad_bounds if not has_bounds else bounds.merge(pad_bounds)
			has_bounds = true
	if not has_bounds: return
	# Shared influence cells produce a continuous territory map. Each cell
	# has exactly one owner, so fills stay uniform; the smoothing pass below
	# turns the exposed cell edges into curves. A finer grid keeps two
	# districts meeting at an angle closer together -- a diagonal boundary
	# between square cells is inherently a staircase with up to one cell's
	# width of "play" between how each side's own mask rounds it, so a
	# smaller cell shrinks that residual gap rather than removing it.
	var cell_size := 32.0
	var room_reserve := DISTRICT_ROOM_RESERVE
	# Wider than a room card: a district connection should read as a deliberate
	# land bridge, not a hairline that can disappear at normal editor zoom.
	var corridor_reserve := DISTRICT_CORRIDOR_RESERVE
	var territory_radius := DISTRICT_TERRITORY_RADIUS
	var owners := {}
	for cell_x in range(int(floor(bounds.position.x / cell_size)), int(ceil(bounds.end.x / cell_size))):
		for cell_y in range(int(floor(bounds.position.y / cell_size)), int(ceil(bounds.end.y / cell_size))):
			var sample := (Vector2(cell_x, cell_y) + Vector2(0.5, 0.5)) * cell_size
			var best_field := -1
			var best_distance := INF
			var reserved_field := -1
			var reserved_distance := INF
			var corridor_field := -1
			var corridor_distance := INF
			for field_index in range(fields.size()):
				var member_distance := _district_member_distance(sample, fields[field_index])
				if member_distance < room_reserve and member_distance < reserved_distance:
					reserved_distance = member_distance
					reserved_field = field_index
				var segment_distance := _district_segment_distance(sample, fields[field_index])
				if segment_distance < corridor_reserve and segment_distance < corridor_distance:
					corridor_distance = segment_distance
					corridor_field = field_index
				var distance := _district_field_distance(sample, fields[field_index])
				if distance < best_distance:
					best_distance = distance
					best_field = field_index
			if reserved_field >= 0:
				owners[Vector2i(cell_x, cell_y)] = reserved_field
			elif corridor_field >= 0:
				owners[Vector2i(cell_x, cell_y)] = corridor_field
			elif best_distance <= territory_radius:
				owners[Vector2i(cell_x, cell_y)] = best_field
	# Lock internal corridors in after the shared influence pass. This is the
	# continuity guarantee: a neighboring district may meet a corridor at a
	# ridge, but cannot reclaim it and split one district into visual islands.
	for field_index in range(fields.size()):
		for segment in fields[field_index]["segments"]:
			var from: Vector2 = segment["from"]
			var to: Vector2 = segment["to"]
			var min_x := int(floor((minf(from.x, to.x) - corridor_reserve) / cell_size))
			var max_x := int(ceil((maxf(from.x, to.x) + corridor_reserve) / cell_size))
			var min_y := int(floor((minf(from.y, to.y) - corridor_reserve) / cell_size))
			var max_y := int(ceil((maxf(from.y, to.y) + corridor_reserve) / cell_size))
			for cell_x in range(min_x, max_x):
				for cell_y in range(min_y, max_y):
					var cell := Vector2i(cell_x, cell_y)
					var sample := (Vector2(cell_x, cell_y) + Vector2(0.5, 0.5)) * cell_size
					var nearest := Geometry2D.get_closest_point_to_segment(sample, from, to)
					if sample.distance_to(nearest) > corridor_reserve: continue
					var room_owner := _district_reserved_room_owner(sample, fields, room_reserve)
					if room_owner < 0 or room_owner == field_index: owners[cell] = field_index
	owners = _despeckle_owners(owners)
	# The cell grid decides ownership; from here on it only decides *shape*.
	# Tracing each district's own cell mask into closed loops, collapsing the
	# staircase noise a diagonal boundary produces at this cell size, then
	# corner-cutting what's left turns the ridged cell edges into a calm,
	# irregular coastline that still hugs the real, uneven territory beneath
	# it -- no two districts round the same way, because no two districts
	# have the same rooms. Both passes are local (each new point depends only
	# on its immediate neighbors along the boundary), which is also why two
	# districts sharing an edge end up with matching curves there rather than
	# two independently-wobbling lines that drift apart.
	var field_loops: Array = []
	for field_index in range(fields.size()):
		var loops: Array = []
		for loop in _trace_field_boundary_loops(owners, field_index, cell_size):
			var simplified := _simplify_loop_douglas_peucker(loop, BOUNDARY_SIMPLIFY_TOLERANCE)
			loops.append(_chaikin_smooth_closed_loop(simplified, 4))
		field_loops.append(loops)
	var selected_district_id := str(editor_state.selected_district_id) if editor_state else ""
	for field_index in range(fields.size()):
		var color: Color = fields[field_index]["color"]
		var is_selected: bool = selected_district_id != "" and str(fields[field_index]["id"]) == selected_district_id
		var fill := Color(color.r, color.g, color.b, 0.24 if is_selected else 0.13)
		for loop in field_loops[field_index]:
			if loop.size() >= 3: district_layer.draw_colored_polygon(PackedVector2Array(loop), fill)
	for field_index in range(fields.size()):
		var color: Color = fields[field_index]["color"]
		var is_selected: bool = selected_district_id != "" and str(fields[field_index]["id"]) == selected_district_id
		var ridge := color.lightened(0.35) if is_selected else Color(color.r, color.g, color.b, 0.78)
		if is_selected: ridge.a = 1.0
		var ridge_width := 3.5 if is_selected else 2.0
		for loop in field_loops[field_index]:
			if loop.size() < 2: continue
			var closed := PackedVector2Array(loop)
			closed.append(loop[0])
			district_layer.draw_polyline(closed, ridge, ridge_width, true)
	for field in fields:
		var positions: Array[Vector2] = field["positions"]
		var label_pos := positions[0]
		for position in positions:
			if position.y < label_pos.y or (is_equal_approx(position.y, label_pos.y) and position.x < label_pos.x): label_pos = position
		var title := str(field["name"])
		var title_size := font.get_string_size(title, HORIZONTAL_ALIGNMENT_LEFT, -1, 12)
		var color: Color = field["color"]
		district_layer.draw_string(font, label_pos + Vector2(-104, -92 + title_size.y), title, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(color.r, color.g, color.b, 0.94))

func _district_field_distance(point: Vector2, field: Dictionary) -> float:
	var closest := _district_member_distance(point, field)
	for segment in field.get("segments", []):
		var nearest := Geometry2D.get_closest_point_to_segment(point, segment["from"], segment["to"])
		closest = minf(closest, point.distance_to(nearest))
	return closest

func _district_member_distance(point: Vector2, field: Dictionary) -> float:
	var closest := INF
	for position in field.get("positions", []): closest = minf(closest, point.distance_to(position))
	return closest

func _district_reserved_room_owner(point: Vector2, fields: Array, reserve: float) -> int:
	var owner := -1
	var closest := INF
	for field_index in range(fields.size()):
		var distance := _district_member_distance(point, fields[field_index])
		if distance < reserve and distance < closest:
			closest = distance
			owner = field_index
	return owner

func _district_segment_distance(point: Vector2, field: Dictionary) -> float:
	var closest := INF
	for segment in field.get("segments", []):
		var nearest := Geometry2D.get_closest_point_to_segment(point, segment["from"], segment["to"])
		closest = minf(closest, point.distance_to(nearest))
	return closest

# A cell whose 4-neighbors are mostly one other district is noise, not a
# real feature -- the nearest-owner/reserved/corridor rules above are each
# individually reasonable but can flip a single stray cell's owner right at
# the seam between two districts, which then shows up downstream as a small
# jagged notch or spike DP has no reason to remove (a lone flipped cell is a
# real, if tiny, deviation from any chord near it). Requiring 3 of 4
# neighbors to agree before reassigning a cell is deliberately strict: it
# only cleans up single-cell pockets and leaves genuine thin necks or
# corridors (which are many cells wide, so never look this isolated) alone.
func _despeckle_owners(owners: Dictionary) -> Dictionary:
	var neighbor_offsets := [Vector2i(0, -1), Vector2i(0, 1), Vector2i(1, 0), Vector2i(-1, 0)]
	var cleaned := owners.duplicate()
	for cell in owners:
		var current: int = owners[cell]
		var counts: Dictionary = {}
		for offset in neighbor_offsets:
			if not owners.has(cell + offset): continue
			var neighbor_owner: int = owners[cell + offset]
			counts[neighbor_owner] = counts.get(neighbor_owner, 0) + 1
		var best_owner := current
		var best_count: int = counts.get(current, 0)
		for owner in counts:
			if counts[owner] > best_count:
				best_count = counts[owner]
				best_owner = owner
		if best_owner != current and best_count >= 3: cleaned[cell] = best_owner
	return cleaned

# Walks the owned-cell mask for one field into one or more closed,
# world-space vertex loops (its outer boundary, plus any hole it has been
# squeezed into by a neighbor -- rare, but not assumed away). Every owned
# cell contributes its clockwise-facing edges wherever the neighbor across
# that edge belongs to someone else (or nobody); those directed edges chain
# start-to-end into full loops because a raster region's boundary always
# does, regardless of its shape.
func _trace_field_boundary_loops(owners: Dictionary, field_index: int, cell_size: float) -> Array:
	var next_vertex: Dictionary = {}
	var vertex_by_key: Dictionary = {}
	for cell in owners:
		if int(owners[cell]) != field_index: continue
		var cx: int = cell.x
		var cy: int = cell.y
		var tl := Vector2(cx, cy) * cell_size
		var tr := Vector2(cx + 1, cy) * cell_size
		var br := Vector2(cx + 1, cy + 1) * cell_size
		var bl := Vector2(cx, cy + 1) * cell_size
		if int(owners.get(Vector2i(cx, cy - 1), -1)) != field_index: _add_boundary_edge(next_vertex, vertex_by_key, tl, tr)
		if int(owners.get(Vector2i(cx + 1, cy), -1)) != field_index: _add_boundary_edge(next_vertex, vertex_by_key, tr, br)
		if int(owners.get(Vector2i(cx, cy + 1), -1)) != field_index: _add_boundary_edge(next_vertex, vertex_by_key, br, bl)
		if int(owners.get(Vector2i(cx - 1, cy), -1)) != field_index: _add_boundary_edge(next_vertex, vertex_by_key, bl, tl)
	var visited: Dictionary = {}
	var loops: Array = []
	for start_key in next_vertex.keys():
		if visited.has(start_key): continue
		var loop: Array = []
		var current_key: String = start_key
		var guard := 0
		while not visited.has(current_key) and next_vertex.has(current_key) and guard < 100000:
			visited[current_key] = true
			loop.append(vertex_by_key[current_key])
			current_key = _boundary_vertex_key(next_vertex[current_key])
			guard += 1
		if loop.size() >= 3: loops.append(loop)
	return loops

func _boundary_vertex_key(v: Vector2) -> String:
	return "%d:%d" % [roundi(v.x), roundi(v.y)]

func _add_boundary_edge(next_vertex: Dictionary, vertex_by_key: Dictionary, from: Vector2, to: Vector2) -> void:
	var from_key := _boundary_vertex_key(from)
	vertex_by_key[from_key] = from
	vertex_by_key[_boundary_vertex_key(to)] = to
	next_vertex[from_key] = to

# Collapses a run of small cell-grid steps down to its real corners. A
# diagonal-ish boundary at this cell size is a long staircase of tiny
# alternating steps; every one of those steps is a genuine direction change,
# so simple collinearity checks cannot remove them, but they are also not a
# real feature of the district's shape -- just this grid's resolution.
# Douglas-Peucker keeps only the points a straight chord could not
# approximate within `tolerance`, so a whole staircase run collapses to the
# two points at its ends wherever it is, in fact, straight-ish.
#
# A closed loop needs an anchor point to open it into the chain the
# algorithm actually operates on; an earlier version picked the two most
# distant points to split it in half, but that choice depends on the
# loop's overall shape, not just the run being simplified, and two
# different shapes sharing one straight edge could pick different anchors
# and simplify that shared edge differently. Anchoring on the loop's own
# first point instead is arbitrary in the same way, but harmlessly so: the
# recursive algorithm below always keeps both ends of whatever chain it is
# given and only discards a point when a straight chord already
# approximates it, so no real corner can be lost regardless of where the
# seam falls.
func _simplify_loop_douglas_peucker(loop: Array, tolerance: float) -> Array:
	var n := loop.size()
	if n < 5: return loop
	var unrolled: Array = loop.duplicate()
	unrolled.append(loop[0])
	var simplified := _douglas_peucker_open(unrolled, tolerance)
	if simplified.size() >= 2 and simplified[0].is_equal_approx(simplified[simplified.size() - 1]):
		simplified = simplified.slice(0, simplified.size() - 1)
	return simplified if simplified.size() >= 3 else loop

func _douglas_peucker_open(points: Array, tolerance: float) -> Array:
	var n := points.size()
	if n < 3: return points
	var start: Vector2 = points[0]
	var end: Vector2 = points[n - 1]
	var max_dist := 0.0
	var split_index := 0
	for i in range(1, n - 1):
		var nearest := Geometry2D.get_closest_point_to_segment(points[i], start, end)
		var dist: float = points[i].distance_to(nearest)
		if dist > max_dist:
			max_dist = dist
			split_index = i
	if max_dist <= tolerance:
		return [start, end]
	var left := _douglas_peucker_open(points.slice(0, split_index + 1), tolerance)
	var right := _douglas_peucker_open(points.slice(split_index, n), tolerance)
	var combined: Array = left.duplicate()
	combined.append_array(right.slice(1, right.size()))
	return combined

# Chaikin corner-cutting: each edge contributes two new points a quarter of
# the way in from each end, replacing the original corner. Unlike a spline
# through every point, this can only ever move a boundary *inward* toward
# its own edges, never bulge past them -- which is what keeps two adjacent
# districts' independently-smoothed shared border tight against each other
# rather than drifting apart, and keeps the curve calm instead of
# overshooting at sharp corners. A few iterations converge quickly; more
# than that just re-rounds an already-round shape.
func _chaikin_smooth_closed_loop(loop: Array, iterations: int = 3) -> Array:
	var points := loop
	for _iteration in range(iterations):
		var n := points.size()
		if n < 3: break
		var next: Array = []
		for i in range(n):
			var p0: Vector2 = points[i]
			var p1: Vector2 = points[(i + 1) % n]
			next.append(p0.lerp(p1, 0.25))
			next.append(p0.lerp(p1, 0.75))
		points = next
	return points

func _draw_ghost_connection(from: Vector2, to: Vector2, label: String, color: Color):
	if from.is_equal_approx(to): return
	connection_layer.draw_line(from, to, Color(0.03, 0.06, 0.10, 0.72), 6.0)
	connection_layer.draw_line(from, to, _with_alpha(color, 0.78), 2.5)
	var direction := (to - from).normalized()
	var midpoint := (from + to) * 0.5
	var perpendicular := Vector2(-direction.y, direction.x)
	var tip := to - direction * 18.0
	var base := tip - direction * 10.0
	connection_layer.draw_colored_polygon(PackedVector2Array([tip, base + perpendicular * 6.0, base - perpendicular * 6.0]), _with_alpha(color, 0.9))
	var font := ThemeDB.get_fallback_font()
	var text_size := font.get_string_size(label, HORIZONTAL_ALIGNMENT_CENTER, -1, 11)
	var angle := direction.angle()
	if angle > PI * 0.5 or angle < -PI * 0.5:
		angle += PI
	connection_layer.draw_set_transform(midpoint, angle, Vector2.ONE)
	var label_rect := Rect2(-text_size * 0.5 - Vector2(7, 4), text_size + Vector2(14, 8))
	connection_layer.draw_rect(label_rect, Color(0.04, 0.07, 0.12, 0.88), true)
	connection_layer.draw_rect(label_rect, _with_alpha(color, 0.72), false, 1.0)
	connection_layer.draw_string(font, Vector2(-text_size.x * 0.5, text_size.y * 0.35), label, HORIZONTAL_ALIGNMENT_LEFT, -1, 11, Color.WHITE)
	connection_layer.draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)

func _with_alpha(color: Color, alpha: float) -> Color:
	return Color(color.r, color.g, color.b, alpha)
	
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
