# scripts/ui/graph/GridLayer.gd
class_name GridLayer
extends Node2D

var camera: Camera2D
var grid_step: int = 32
var grid_color: Color = Color(1, 1, 1, 0.05)
var axis_color: Color = Color(1, 1, 1, 0.1)

func setup(_camera: Camera2D):
	camera = _camera

func _draw():
	# Don't draw if hidden or camera isn't ready
	if not visible or not camera:
		return
		
	var vp_rect = get_viewport_rect()
	var cam_pos = camera.position
	var zm = camera.zoom
	
	# Calculate visible world bounds, expanded slightly to prevent edge popping
	var visible_size = vp_rect.size / zm
	var tl = cam_pos - (visible_size / 2.0) - Vector2(grid_step, grid_step)
	var br = cam_pos + (visible_size / 2.0) + Vector2(grid_step, grid_step)
	
	# Snap start/end to grid
	var start_x = floor(tl.x / grid_step) * grid_step
	var end_x = ceil(br.x / grid_step) * grid_step
	var start_y = floor(tl.y / grid_step) * grid_step
	var end_y = ceil(br.y / grid_step) * grid_step
	
	var points = PackedVector2Array()
	
	# Vertical Lines
	for x in range(start_x, end_x, grid_step):
		if x == 0: continue # Skip axis for special color later
		points.append(Vector2(x, tl.y))
		points.append(Vector2(x, br.y))
		
	# Horizontal Lines
	for y in range(start_y, end_y, grid_step):
		if y == 0: continue # Skip axis
		points.append(Vector2(tl.x, y))
		points.append(Vector2(br.x, y))
		
	# Draw the massive batch of lines
	draw_multiline(points, grid_color)
	
	# Draw Origin Axes if visible
	if start_x <= 0 and end_x >= 0:
		draw_line(Vector2(0, tl.y), Vector2(0, br.y), axis_color, 2.0)
	if start_y <= 0 and end_y >= 0:
		draw_line(Vector2(tl.x, 0), Vector2(br.x, 0), axis_color, 2.0)
