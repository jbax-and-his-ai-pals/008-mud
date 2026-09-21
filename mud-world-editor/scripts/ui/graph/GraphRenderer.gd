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
				var pair_label := _reciprocal_pair_label(data, rid, target_str, dir, rev_dir, nodes)

				var is_hl = (rid == selected_id or target_str == selected_id)
				
				# Color Selection
				var d_lower = dir.to_lower()
				var line_col = COL_DEF
				
				if d_lower in ["north", "south", "east", "west", "n", "s", "e", "w"]:
					line_col = COL_CARDINAL
				elif d_lower in ["up", "climb", "surface"]:
					line_col = COL_UP
				elif d_lower in ["down", "dive", "descend"]:
					line_col = COL_DOWN
				elif d_lower in ["in", "out", "enter", "exit", "inside", "outside"]:
					line_col = COL_IN_OUT
				else:
					line_col = COL_DIAG
				
				if not is_two_way: line_col = COL_ONE_WAY
				if is_hl: line_col = COL_HL
				
				# Determine if curved
				var is_curved_type = d_lower in ["up", "down", "climb", "descend", "surface", "dive", "in", "out", "enter", "exit", "inside", "outside"]

				# Which side a curved connection bows toward is otherwise decided by
				# the perpendicular of the line between the two rooms, so the same
				# "in"/"out" exit can bow either way depending on where its rooms
				# happen to sit -- and re-arranging the map silently flips it. The
				# author's choice lives in `_editor_exit_layout` (editor-only state,
				# kept out of the content files) as `curve: "left" | "right"` and
				# `curve_amount: "tight" | "normal" | "wide"`.
				var curve_side := ""
				var curve_scale := 1.0
				var exit_layout = rooms[rid].get("_editor_exit_layout", {})
				# Never index optional editor metadata. Older regions (and a room whose
				# other exit has a curve override) legitimately have no entry for this
				# direction; GDScript does not make the preceding type check safe for a
				# later `dictionary[key]` access.
				var this_exit_layout = exit_layout.get(dir, null) if exit_layout is Dictionary else null
				if this_exit_layout is Dictionary:
					curve_side = str(this_exit_layout.get("curve", ""))
					curve_scale = CURVE_AMOUNT_SCALE.get(
						str(this_exit_layout.get("curve_amount", "")), 1.0
					)

				if is_curved_type:
					_draw_curve_connection(canvas, start, end, line_col, is_hl, is_two_way, dir, rev_dir, pair_label, font, style, curve_side, curve_scale)
				else:
					_draw_straight_connection(canvas, start, end, line_col, is_hl, is_two_way, dir, rev_dir, pair_label, font, style, is_external)

			else:
				var stub_col = COL_DEF
				var d_l = dir.to_lower()
				if d_l in ["up", "climb", "surface"]: stub_col = COL_UP
				elif d_l in ["down", "dive", "descend"]: stub_col = COL_DOWN
				elif d_l in ["in", "out", "enter", "exit", "inside", "outside"]: stub_col = COL_IN_OUT
				
				canvas.draw_circle(start, 4.0, stub_col)
				var stub_vec = Constants.DIR_VECTORS.get(d_l, Vector2(1,0))
				var stub_end = start + (stub_vec * 35.0)
				canvas.draw_line(start, stub_end, stub_col, LINE_WIDTH)
				_draw_label_rotated(canvas, font, style, (start + stub_end)/2.0, dir.capitalize(), stub_vec.angle())

static func _draw_straight_connection(c: Node2D, from: Vector2, to: Vector2, col: Color, highlight: bool, two_way: bool, dir1: String, dir2: String, pair_label: String, font: Font, style: StyleBox, is_external: bool):
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
		_draw_label_rotated(c, font, style, mid, pair_label, angle)

## How far an authored bow is scaled. The keys mirror
## `RoomConnectionsPanel.CURVE_AMOUNT_SCALE`, which is what offers them; the
## renderer only needs to agree on what the names mean.
const CURVE_AMOUNT_SCALE := {"tight": 0.5, "normal": 1.0, "wide": 1.6}

static func _draw_curve_connection(c: Node2D, from: Vector2, to: Vector2, col: Color, highlight: bool, two_way: bool, dir1: String, dir2: String, pair_label: String, font: Font, style: StyleBox, curve_side: String = "", curve_scale: float = 1.0):
	var w = LINE_WIDTH + (2.0 if highlight else 0.0)
	var dist = from.distance_to(to)
	
	var dir_vec = (to - from).normalized()
	var perp = Vector2(-dir_vec.y, dir_vec.x)

	# An authored side wins over the geometric default. Only the *sign* is taken
	# from the author: the magnitude comes from `curve_scale`, so flipping a
	# connection mirrors it and the two controls stay independent.
	if curve_side == "left":
		perp = -perp
	elif curve_side == "right":
		pass
	
	var curve_amount = min(dist * 0.5, 120.0)
	if curve_amount < 40.0: curve_amount = 40.0
	curve_amount *= curve_scale
	
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
		_draw_label_rotated(c, font, style, mid_curve, pair_label, angle)
	else:
		_draw_label_rotated(c, font, style, mid_curve, dir1.capitalize(), angle)
		_draw_arrow_at_t(c, from, control, to, 0.9, col)

static func _draw_label_rotated(c: Node2D, font: Font, style: StyleBoxFlat, pos: Vector2, text: String, angle: float):
	var final_angle = angle
	
	# Keep text upright. This exact boundary is shared with
	# Constants.format_reciprocal_label(), so the two direction names exchange
	# places precisely when the readable label rotates by 180 degrees.
	if final_angle > PI * 0.5 or final_angle < -PI * 0.5:
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

static func _reciprocal_pair_label(data: Dictionary, first_id: String, second_id: String, first_direction: String, second_direction: String, nodes: Dictionary) -> String:
	var pair_ids := [first_id, second_id]
	pair_ids.sort()
	var label_sources: Dictionary = data.get("_editor_connection_label_sources", {})
	var source_record = label_sources.get(str(pair_ids[0]) + "|" + str(pair_ids[1]), {})
	var authored_source := str(source_record.get("source", "")) if source_record is Dictionary else _legacy_pair_source(data, first_id, second_id)
	if not nodes.has(first_id) or not nodes.has(second_id): return "%s ↔ %s" % [first_direction.capitalize(), second_direction.capitalize()]
	return Constants.format_reciprocal_pair_label(first_id, second_id, first_direction, second_direction, nodes[first_id].global_position, nodes[second_id].global_position, authored_source)

static func _legacy_pair_source(data: Dictionary, first_id: String, second_id: String) -> String:
	# Pre-metadata regions preserve the order in which rooms were authored in
	# their data file. It is the closest available definition of which reciprocal
	# exit was originally emitted, and unlike draw order does not change with view.
	var rooms: Dictionary = data.get("rooms", {})
	var order := rooms.keys()
	var first_index := order.find(first_id)
	var second_index := order.find(second_id)
	if first_index >= 0 and (second_index < 0 or first_index <= second_index): return first_id
	return second_id

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
