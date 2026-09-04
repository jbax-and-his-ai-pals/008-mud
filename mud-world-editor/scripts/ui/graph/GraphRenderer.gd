# scripts/ui/graph/GraphRenderer.gd
class_name GraphRenderer
extends RefCounted

# Constants for visual tweaking
const LINE_WIDTH = 3.0
const LINE_BORDER_WIDTH = 4.0
const ARROW_SIZE = 14.0
const LABEL_FONT_SIZE = 12
const LABEL_BG_COLOR = Color(0.1, 0.1, 0.1, 0.9)
const LABEL_BORDER_COLOR = Color(0.4, 0.4, 0.4, 1.0)

# Colors
const COL_DEF = Color(0.7, 0.7, 0.7, 1.0)
const COL_TWO_WAY = Color(1.0, 1.0, 1.0, 1.0)
const COL_UP = Color(0.2, 0.8, 1.0, 1.0)
const COL_DOWN = Color(0.8, 0.4, 0.2, 1.0)
const COL_HL = Color(1, 0.8, 0.2, 1.0)
const COL_ONE_WAY = Color(1.0, 0.3, 0.3, 1.0)
const COL_OUTLINE = Color(0.0, 0.0, 0.0, 0.8)

# Specific Direction Colors
const COL_IN_OUT = Color(0.7, 0.4, 0.9, 1.0)
const COL_DIAG = Color(0.4, 0.8, 0.4, 1.0)
const COL_CARDINAL = Color(0.3, 0.6, 0.9, 1.0)

static var label_style: StyleBoxFlat

static func _get_label_style() -> StyleBoxFlat:
	if not label_style:
		label_style = StyleBoxFlat.new()
		label_style.bg_color = LABEL_BG_COLOR
		label_style.set_corner_radius_all(4)
		label_style.set_border_width_all(1)
		label_style.border_color = LABEL_BORDER_COLOR
		label_style.content_margin_left = 6
		label_style.content_margin_right = 6
		label_style.content_margin_top = 2
		label_style.content_margin_bottom = 2
	return label_style

static func draw_graph(canvas: Node2D, nodes: Dictionary, data: Dictionary, selected_id: String, drag_line: Dictionary):
	var font = ThemeDB.get_fallback_font()
	var rooms = data.get("rooms", {})
	var drawn_pairs = {} 
	var style = _get_label_style()

	if drag_line.get("active", false):
		var start = canvas.to_local(drag_line.get("start", Vector2.ZERO))
		var end = canvas.to_local(drag_line.get("end", Vector2.ZERO))
		canvas.draw_line(start, end, Color.BLACK, LINE_WIDTH + 4.0)
		canvas.draw_dashed_line(start, end, Color.LIME_GREEN, LINE_WIDTH, 10.0)

	for rid in nodes:
		if not rooms.has(rid): continue 

		var node = nodes[rid]
		var exits = rooms[rid].get("exits", {})
		
		for dir in exits:
			var target_str = exits[dir]
			var is_external = ":" in target_str
			
			var target_node = null
			if nodes.has(target_str):
				target_node = nodes[target_str]

			var start_global = Vector2.ZERO
			if node.has_method("get_connection_anchor_point"):
				start_global = node.get_connection_anchor_point(dir)
			else:
				start_global = node.global_position
			
			var start = canvas.to_local(start_global)
			var end_global = Vector2.ZERO
			var end = Vector2.ZERO
			
			if target_node:
				var reverse_dir = Constants.INV_DIR_MAP.get(dir.to_lower(), "")
				if target_node.has_method("get_connection_anchor_point") and reverse_dir != "":
					end_global = target_node.get_connection_anchor_point(reverse_dir)
				else:
					end_global = target_node.global_position
				end = canvas.to_local(end_global)

			if target_node:
				var is_two_way = false
				var rev_dir = ""
				
				if not is_external and rooms.has(target_str):
					var target_exits = rooms[target_str].get("exits", {})
					for t_dir in target_exits:
						if target_exits[t_dir] == rid:
							is_two_way = true
							rev_dir = t_dir
							break

				var pair_key = [rid, target_str]
				pair_key.sort()
				if is_two_way and drawn_pairs.has(pair_key):
					continue
				if is_two_way: drawn_pairs[pair_key] = true

				var is_hl = (rid == selected_id or target_str == selected_id)
				
				# Color Selection
				var d_lower = dir.to_lower()
				var line_col = COL_DEF
				
				if d_lower in ["north", "south", "east", "west", "n", "s", "e", "w"]:
					line_col = COL_CARDINAL
				elif d_lower in ["up", "climb"]:
					line_col = COL_UP
				elif d_lower in ["down", "dive"]:
					line_col = COL_DOWN
				elif d_lower in ["in", "out"]:
					line_col = COL_IN_OUT
				else:
					line_col = COL_DIAG
				
				if not is_two_way: line_col = COL_ONE_WAY
				if is_hl: line_col = COL_HL
				
				# Determine if curved
				var is_curved_type = d_lower in ["up", "down", "climb", "dive", "in", "out"]

				if is_curved_type:
					_draw_curve_connection(canvas, start, end, line_col, is_hl, is_two_way, dir, rev_dir, font, style)
				else:
					_draw_straight_connection(canvas, start, end, line_col, is_hl, is_two_way, dir, rev_dir, font, style, is_external)

			else:
				var stub_col = COL_DEF
				var d_l = dir.to_lower()
				if d_l in ["up", "climb"]: stub_col = COL_UP
				elif d_l in ["down", "dive"]: stub_col = COL_DOWN
				elif d_l in ["in", "out"]: stub_col = COL_IN_OUT
				
				canvas.draw_circle(start, 4.0, stub_col)
				var stub_vec = Constants.DIR_VECTORS.get(d_l, Vector2(1,0))
				var stub_end = start + (stub_vec * 35.0)
				canvas.draw_line(start, stub_end, stub_col, LINE_WIDTH)
				_draw_label_rotated(canvas, font, style, (start + stub_end)/2.0, dir.capitalize(), stub_vec.angle())

static func _draw_straight_connection(c: Node2D, from: Vector2, to: Vector2, col: Color, highlight: bool, two_way: bool, dir1: String, dir2: String, font: Font, style: StyleBox, is_external: bool):
	var w = LINE_WIDTH + (2.0 if highlight else 0.0)
	var dir_vec = (to - from).normalized()
	var line_end = to
	
	# Calculate shortened line end for one-way arrows to prevent overlap
	if not two_way:
		# Arrow occupies roughly 1.1 * ARROW_SIZE from the tip backwards
		# (0.6 for center offset + 0.5 for base width + margin)
		var arrow_space = ARROW_SIZE * 1.1
		var dist = from.distance_to(to)
		
		if dist > arrow_space:
			line_end = to - (dir_vec * arrow_space)
		else:
			line_end = from # Too close to draw line
	
	c.draw_line(from, line_end, COL_OUTLINE, w + LINE_BORDER_WIDTH)
	
	if is_external:
		c.draw_dashed_line(from, line_end, col, w, 8.0)
	else:
		c.draw_line(from, line_end, col, w)
	
	var mid = (from + to) / 2.0
	var angle = (to - from).angle()
	
	if not two_way:
		# Draw arrow at the destination (to)
		var arrow_pos = to - (dir_vec * ARROW_SIZE * 0.6)
		_draw_arrow_head(c, arrow_pos, dir_vec, col)
		
		_draw_label_rotated(c, font, style, mid, dir1.capitalize(), angle)
	else:
		# Check flip condition using fuzzy epsilon
		var needs_flip = angle > (PI / 2.0 - 0.001) or angle < (-PI / 2.0 - 0.001)
		var text = ""
		if needs_flip:
			text = "%s ↔ %s" % [dir2.capitalize(), dir1.capitalize()]
		else:
			text = "%s ↔ %s" % [dir1.capitalize(), dir2.capitalize()]
			
		_draw_label_rotated(c, font, style, mid, text, angle)

static func _draw_curve_connection(c: Node2D, from: Vector2, to: Vector2, col: Color, highlight: bool, two_way: bool, dir1: String, dir2: String, font: Font, style: StyleBox):
	var w = LINE_WIDTH + (2.0 if highlight else 0.0)
	var dist = from.distance_to(to)
	
	var dir_vec = (to - from).normalized()
	var perp = Vector2(-dir_vec.y, dir_vec.x)
	
	var curve_amount = min(dist * 0.5, 120.0)
	if curve_amount < 40.0: curve_amount = 40.0
	
	var control = (from + to) / 2.0 + (perp * curve_amount)
	
	var points = PackedVector2Array()
	var steps = 24
	for i in range(steps + 1):
		var t = float(i) / steps
		points.append(from.bezier_interpolate(control, control, to, t))
	
	c.draw_polyline(points, COL_OUTLINE, w + LINE_BORDER_WIDTH)
	c.draw_polyline(points, col, w)
	
	var mid_curve = from.bezier_interpolate(control, control, to, 0.5)
	
	# Approximate angle at midpoint for text rotation
	var t = 0.5
	var p0 = from; var p1 = control; var p2 = to
	var tangent = (2.0 * (1.0 - t) * (p1 - p0) + 2.0 * t * (p2 - p1)).normalized()
	var angle = tangent.angle()

	if two_way:
		var needs_flip = angle > (PI / 2.0 - 0.001) or angle < (-PI / 2.0 - 0.001)
		var text = ""
		if needs_flip:
			text = "%s ↔ %s" % [dir2.capitalize(), dir1.capitalize()]
		else:
			text = "%s ↔ %s" % [dir1.capitalize(), dir2.capitalize()]
		
		_draw_label_rotated(c, font, style, mid_curve, text, angle)
	else:
		_draw_label_rotated(c, font, style, mid_curve, dir1.capitalize(), angle)
		_draw_arrow_at_t(c, from, control, to, 0.9, col)

static func _draw_label_rotated(c: Node2D, font: Font, style: StyleBoxFlat, pos: Vector2, text: String, angle: float):
	var final_angle = angle
	
	# Consistency check: Flip if pointing generally Left or Down
	if final_angle > (PI / 2.0 - 0.001) or final_angle < (-PI / 2.0 - 0.001):
		final_angle += PI
	
	c.draw_set_transform(pos, final_angle, Vector2.ONE)
	var txt_size = font.get_string_size(text, HORIZONTAL_ALIGNMENT_CENTER, -1, LABEL_FONT_SIZE)
	var padding = Vector2(12, 4)
	var size = txt_size + padding
	var rect = Rect2(-size/2.0, size)
	
	c.draw_style_box(style, rect)
	var text_pos = Vector2(-txt_size.x / 2.0, txt_size.y * 0.25)
	c.draw_string(font, text_pos, text, HORIZONTAL_ALIGNMENT_CENTER, -1, LABEL_FONT_SIZE, Color.WHITE)
	c.draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)

static func _draw_arrow_midpoint(c: Node2D, from: Vector2, to: Vector2, col: Color):
	var mid = (from + to) / 2.0
	var dir = (to - from).normalized()
	_draw_arrow_head(c, mid, dir, col)

static func _draw_arrow_at_t(c: Node2D, start: Vector2, control: Vector2, end: Vector2, t: float, col: Color):
	var p0 = start; var p1 = control; var p2 = end
	var tangent = (2.0 * (1.0 - t) * (p1 - p0) + 2.0 * t * (p2 - p1)).normalized()
	var pos = start.bezier_interpolate(control, control, end, t)
	_draw_arrow_head(c, pos, tangent, col)

static func _draw_arrow_head(c: Node2D, pos: Vector2, dir: Vector2, col: Color):
	var tip = pos + (dir * ARROW_SIZE * 0.5)
	var base = pos - (dir * ARROW_SIZE * 0.5)
	var perp = Vector2(-dir.y, dir.x) * (ARROW_SIZE * 0.5)
	var p1 = base + perp
	var p2 = base - perp
	c.draw_colored_polygon(PackedVector2Array([tip, p1, p2]), COL_OUTLINE)
	var s = 0.8
	var tip_s = pos + (dir * ARROW_SIZE * 0.5 * s)
	var base_s = pos - (dir * ARROW_SIZE * 0.5 * s)
	var perp_s = Vector2(-dir.y, dir.x) * (ARROW_SIZE * 0.5 * s)
	c.draw_colored_polygon(PackedVector2Array([tip_s, base_s + perp_s, base_s - perp_s]), col)
