# scripts/ui/panels/GeneratorPreview.gd
extends Control

var current_rooms: Dictionary = {}
const PREVIEW_COLOR = Color(0.82, 0.78, 0.65) 
const BG_COLOR = Color(0.1, 0.1, 0.15)
const REF_GRID_SIZE = Vector2(250, 250) 

# Zoom & Pan State
var zoom_level: float = 1.0
var pan_offset: Vector2 = Vector2.ZERO
var is_panning: bool = false

func _ready():
	# Stop mouse events from propagating to the map below when hovering this control
	mouse_filter = Control.MOUSE_FILTER_STOP 
	# Ensure drawing does not spill out of the preview panel
	clip_contents = true

func update_preview(rooms: Dictionary):
	current_rooms = rooms
	queue_redraw()

func _gui_input(event):
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP and event.pressed:
			_apply_zoom(event.position, 1.1)
			accept_event()
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN and event.pressed:
			_apply_zoom(event.position, 1.0 / 1.1)
			accept_event()
		elif event.button_index == MOUSE_BUTTON_MIDDLE or event.button_index == MOUSE_BUTTON_LEFT:
			if event.pressed:
				is_panning = true
			else:
				is_panning = false
			accept_event()
			
	elif event is InputEventMouseMotion and is_panning:
		pan_offset += event.relative
		queue_redraw()
		accept_event()

func _apply_zoom(mouse_pos: Vector2, factor: float):
	var old_zoom = zoom_level
	zoom_level = clamp(zoom_level * factor, 0.1, 20.0)
	
	# Zoom towards mouse pointer:
	# Relative mouse position from the current center (screen center + old pan)
	var screen_center = size / 2.0
	var mouse_offset_from_center = mouse_pos - (screen_center + pan_offset)
	
	# When scaling up, we need to shift the pan opposite to the mouse direction to keep it centered
	var scale_change = zoom_level / old_zoom
	var new_mouse_offset = mouse_offset_from_center * scale_change
	
	# Adjustment needed
	pan_offset += mouse_offset_from_center - new_mouse_offset
	queue_redraw()

func _draw():
	draw_rect(get_rect(), BG_COLOR)
	
	# 1. Calculate Bounds
	var min_p = Vector2(INF, INF)
	var max_p = Vector2(-INF, -INF)
	
	if not current_rooms.is_empty():
		for id in current_rooms:
			var r = current_rooms[id]
			var p = _get_pos(r)
			min_p.x = min(min_p.x, p.x)
			min_p.y = min(min_p.y, p.y)
			max_p.x = max(max_p.x, p.x)
			max_p.y = max(max_p.y, p.y)
	else:
		min_p = Vector2(-500, -500)
		max_p = Vector2(500, 500)

	var content_size = max_p - min_p
	content_size.x = max(content_size.x, REF_GRID_SIZE.x)
	content_size.y = max(content_size.y, REF_GRID_SIZE.y)
	
	# 2. Calculate Base Scale (Fit to Screen)
	var margin = 40.0
	var avail = size - Vector2(margin * 2, margin * 2)
	
	var scale_x = avail.x / content_size.x
	var scale_y = avail.y / content_size.y
	var base_scale = min(scale_x, scale_y)
	base_scale = clamp(base_scale, 0.001, 2.0)
	
	# Combined Scale
	var final_scale = base_scale * zoom_level
	
	# Calculate Center Offset
	var grid_geometric_center = min_p + (max_p - min_p) / 2.0
	var screen_center = size / 2.0
	var origin_offset = screen_center + pan_offset - (grid_geometric_center * final_scale)

	# 3. Draw Background Grid Lines
	var grid_step = REF_GRID_SIZE * final_scale
	var start_x = fmod(origin_offset.x, grid_step.x)
	var start_y = fmod(origin_offset.y, grid_step.y)
	
	if start_x > 0: start_x -= grid_step.x
	if start_y > 0: start_y -= grid_step.y
	
	var lines_x = int(size.x / grid_step.x) + 2
	var lines_y = int(size.y / grid_step.y) + 2
	var grid_col = Color(1, 1, 1, 0.05)
	
	for i in range(lines_x + 1):
		var x = start_x + i * grid_step.x
		draw_line(Vector2(x, 0), Vector2(x, size.y), grid_col)
	for i in range(lines_y + 1):
		var y = start_y + i * grid_step.y
		draw_line(Vector2(0, y), Vector2(size.x, y), grid_col)

	# 4. Draw Connections
	for id in current_rooms:
		var r = current_rooms[id]
		var r_center_world = _get_pos(r)
		var draw_pos = origin_offset + (r_center_world * final_scale)
		
		if r.has("exits"):
			for dir in r.exits:
				var target_id = r.exits[dir]
				if ":" in target_id or not current_rooms.has(target_id): continue
				
				if dir in ["south", "east", "southeast", "southwest"]:
					var t_r = current_rooms[target_id]
					var t_center_world = _get_pos(t_r)
					var t_draw_pos = origin_offset + (t_center_world * final_scale)
					draw_line(draw_pos, t_draw_pos, Color.WHITE, 2.0 * zoom_level) 

	# 5. Draw Nodes
	var node_draw_size = REF_GRID_SIZE * final_scale * 0.6 
	var square_dim = min(node_draw_size.x, node_draw_size.y)
	var final_node_size = Vector2(square_dim, square_dim)
	
	for id in current_rooms:
		var r = current_rooms[id]
		var r_center_world = _get_pos(r)
		var draw_pos = origin_offset + (r_center_world * final_scale)
		var rect = Rect2(draw_pos - final_node_size/2, final_node_size)
		
		# Frustum Culling
		if rect.intersects(Rect2(Vector2.ZERO, size)):
			draw_rect(rect, PREVIEW_COLOR)

func _get_pos(r: Dictionary) -> Vector2:
	if r["_editor_pos"] is Array:
		return Vector2(r["_editor_pos"][0], r["_editor_pos"][1])
	return r["_editor_pos"]
