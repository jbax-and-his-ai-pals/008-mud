# scripts/scenes/RegionScene.gd
class_name RegionScene
extends Node2D

signal region_selected(region_id)
signal region_moved_committed(old_pos, new_pos)
signal region_dragged(new_pos)
signal request_edit(region_id)

var region_id: String = ""
var dragging: bool = false
var drag_start_pos: Vector2
var _is_selected: bool = false

# Layout Data
var content_rect: Rect2 # The static area containing the nodes
var bg_color: Color
var cached_rooms: Dictionary = {}

const ROOM_SIZE = Vector2(80, 80)
const PADDING = 200.0
const MIN_VISUAL_SIZE = Vector2(2000, 1500)
const BASE_HEADER_HEIGHT = 60.0 # Base height before scaling

func setup(id: String, data: Dictionary, color: Color):
	region_id = id
	bg_color = color
	cached_rooms = data.get("rooms", {})
	
	# 1. Calculate the actual bounds of the room nodes themselves.
	var min_p = Vector2(INF, INF)
	var max_p = Vector2(-INF, -INF)
	var has_rooms = false
	
	for r_id in cached_rooms:
		has_rooms = true
		var ep = cached_rooms[r_id].get("_editor_pos", [0, 0])
		var local_pos = Vector2(ep[0], ep[1])
		
		min_p.x = min(min_p.x, local_pos.x)
		min_p.y = min(min_p.y, local_pos.y)
		max_p.x = max(max_p.x, local_pos.x)
		max_p.y = max(max_p.y, local_pos.y)
	
	if not has_rooms:
		min_p = Vector2(-100, -100)
		max_p = Vector2(100, 100)
	
	# 2. Determine the final size of the content area, enforcing the minimum size.
	var content_size_raw = (max_p - min_p) + ROOM_SIZE
	var final_content_area_size = Vector2(
		max(content_size_raw.x, MIN_VISUAL_SIZE.x),
		max(content_size_raw.y, MIN_VISUAL_SIZE.y)
	)
	
	# 3. Center the final, padded box on the geometric center of the actual content.
	var content_geometric_center = min_p + (content_size_raw / 2.0)
	var final_padded_size = final_content_area_size + Vector2(PADDING * 2, PADDING * 2)
	
	content_rect = Rect2(
		content_geometric_center - (final_padded_size / 2.0),
		final_padded_size
	)
	
	queue_redraw()

func set_selected(is_selected: bool):
	_is_selected = is_selected
	queue_redraw()

func get_global_center() -> Vector2:
	return global_position + content_rect.get_center()

func get_room_local_center(room_id: String) -> Vector2:
	if cached_rooms.has(room_id):
		return _get_vec(cached_rooms[room_id]) + (ROOM_SIZE / 2.0)
	return Vector2.ZERO

func _get_current_visuals(zoom: float) -> Dictionary:
	# Calculate dynamic scaling based on zoom
	var scale_factor = clamp(1.0 / sqrt(zoom), 1.0, 4.0)
	
	# Counteract the node's own scale to keep visuals consistent
	var inv_scale = 1.0 / self.scale.x
	
	# Scale the header's base height to compensate for the node's scale
	var effective_header_height = BASE_HEADER_HEIGHT * scale_factor * inv_scale
	
	# Grow header UPWARDS from content rect using the correctly scaled height
	var header_r = Rect2(
		content_rect.position.x, 
		content_rect.position.y - effective_header_height,
		content_rect.size.x, 
		effective_header_height
	)
	
	var total_r = header_r.merge(content_rect)
	
	# If the node is scaled (i.e., in World View), use a smaller base font size.
	var base_font_size = 16.0 if self.scale.x < 1.0 else 32.0
	
	return {
		"scale": scale_factor,
		"header_rect": header_r,
		"main_rect": total_r,
		# Font size also needs to be scaled up to look correct after node scaling
		"font_size": int((base_font_size * scale_factor) * inv_scale)
	}

func _draw():
	var cam = get_viewport().get_camera_2d()
	var zoom = cam.zoom.x if cam else 1.0
	var viz = _get_current_visuals(zoom)
	
	var scale_factor = viz.scale
	var header_rect = viz.header_rect
	var main_rect = viz.main_rect
	
	# Palette
	var col_header = bg_color.darkened(0.2)
	var col_content = bg_color.darkened(0.6)
	col_content.a = 0.95
	var col_border = Color(0.85, 0.85, 0.85, 1.0)
	var col_text = Color(1, 1, 1, 1.0)
	
	# Counteract node scale for consistent visual weight
	var inv_scale = 1.0 / self.scale.x
	
	# 1. Drop Shadow
	var shadow_off = Vector2(16, 16) * scale_factor * inv_scale
	draw_rect(Rect2(main_rect.position + shadow_off, main_rect.size), Color(0,0,0,0.5), true)
	
	# 2. Backgrounds
	draw_rect(content_rect, col_content, true)
	draw_rect(header_rect, col_header, true)
	
	# 3. Frame / Border
	var border_w = 4.0 * scale_factor * inv_scale
	# Draw outer frame
	draw_rect(main_rect, col_border, false, border_w)
	
	# Draw header divider bar using a filled rectangle for proper height
	var bar_y = content_rect.position.y
	draw_rect(
		Rect2(main_rect.position.x, bar_y - (border_w / 2.0), main_rect.size.x, border_w),
		col_border
	)
	
	# 4. Title
	var font = ThemeDB.get_fallback_font()
	var title = region_id.capitalize().replace("_", " ")
	var font_size = viz.font_size
	
	# Center text in header rect
	var str_size = font.get_string_size(title, HORIZONTAL_ALIGNMENT_CENTER, -1, font_size)
	var center_x = header_rect.position.x + (header_rect.size.x / 2.0) - (str_size.x / 2.0)
	var center_y = header_rect.position.y + (header_rect.size.y / 2.0) + (str_size.y / 3.0)
	
	draw_string(font, Vector2(center_x, center_y), title, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, col_text)
	
	# 5. Internal Connections
	for r_id in cached_rooms:
		var start = _get_vec(cached_rooms[r_id]) + (ROOM_SIZE/2)
		var exits = cached_rooms[r_id].get("exits", {})
		for dir in exits:
			var target = exits[dir]
			if not ":" in target and cached_rooms.has(target):
				var end = _get_vec(cached_rooms[target]) + (ROOM_SIZE/2)
				draw_line(start, end, Color(1, 1, 1, 0.15), 2.0 * scale_factor * inv_scale)

	# 6. Nodes (Rooms)
	var node_col = Color(0.9, 0.9, 0.9, 0.5)
	for r_id in cached_rooms:
		var pos = _get_vec(cached_rooms[r_id])
		var rect = Rect2(pos, ROOM_SIZE)
		draw_rect(rect, node_col, true)
		draw_rect(rect, Color(0,0,0,0.5), false, 1.0 * scale_factor * inv_scale)
		
	# 7. Draw Selection Highlight (if selected)
	if _is_selected:
		var select_border_width = 8.0 * scale_factor * inv_scale
		draw_rect(main_rect, Color.GOLD, false, select_border_width)

func _get_vec(r_data) -> Vector2:
	var ep = r_data.get("_editor_pos", [0,0])
	return Vector2(ep[0], ep[1])

func _unhandled_input(event):
	if event is InputEventMouseButton:
		var cam = get_viewport().get_camera_2d()
		var zoom = cam.zoom.x if cam else 1.0
		var viz = _get_current_visuals(zoom)
		var hit_rect = viz.main_rect
		
		if event.button_index == MOUSE_BUTTON_LEFT:
			if event.pressed:
				var local_mouse = get_local_mouse_position()
				if hit_rect.has_point(local_mouse):
					dragging = true
					drag_start_pos = position
					region_selected.emit(region_id)
					get_viewport().set_input_as_handled()
			else:
				if dragging:
					dragging = false
					if position.distance_to(drag_start_pos) > 1.0:
						region_moved_committed.emit(drag_start_pos, position)
		
		elif event.button_index == MOUSE_BUTTON_RIGHT and event.pressed:
			var local_mouse = get_local_mouse_position()
			if hit_rect.has_point(local_mouse):
				request_edit.emit(region_id)
				get_viewport().set_input_as_handled()

	if event is InputEventMouseMotion and dragging:
		var cam = get_viewport().get_camera_2d()
		var zoom = cam.zoom if cam else Vector2.ONE
		position += event.relative / zoom
		region_dragged.emit(position)
