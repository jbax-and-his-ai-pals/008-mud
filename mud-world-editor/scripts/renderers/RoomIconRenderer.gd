# scripts/renderers/RoomIconRenderer.gd

class_name RoomIconRenderer
extends RefCounted

static func draw_icons(canvas: Control, properties: Dictionary, flags: Dictionary, color: Color):
	var x_offset = 5.0
	var y_offset = 5.0
	var icon_size = 8.0
	
	if flags.get("start", false):
		_draw_shape(canvas, Vector2(x_offset + 4, y_offset + 4), "star", Color.GOLD, icon_size, color)
		x_offset += 12
	if flags.get("npc", false):
		_draw_shape(canvas, Vector2(x_offset + 4, y_offset + 4), "face", Color.SALMON, icon_size, color)
		x_offset += 12
	if flags.get("item", false):
		_draw_shape(canvas, Vector2(x_offset + 4, y_offset + 4), "box", Color.AQUAMARINE, icon_size, color)
		x_offset += 12
		
	for key in properties:
		var val = properties[key]
		if Constants.ICON_DEFINITIONS.has(key) and (val == true or typeof(val) == TYPE_STRING):
			var def = Constants.ICON_DEFINITIONS[key]
			_draw_shape(canvas, Vector2(x_offset + 4, y_offset + 4), def.shape, def.color, icon_size, color)
			x_offset += 12
			if x_offset > canvas.size.x - 10: break

static func _draw_shape(canvas: Control, pos: Vector2, shape: String, col: Color, r: float, bg_col: Color):
	match shape:
		"circle": canvas.draw_circle(pos, r/2, col)
		"box": canvas.draw_rect(Rect2(pos - Vector2(r/2, r/2), Vector2(r,r)), col)
		"star": 
			var pts = PackedVector2Array()
			for i in range(5):
				var a = deg_to_rad(i * 72 - 90)
				pts.append(pos + Vector2(cos(a), sin(a)) * (r/2))
			canvas.draw_colored_polygon(pts, col)
		"moon":
			canvas.draw_circle(pos, r/2, col)
			canvas.draw_circle(pos + Vector2(2, -1), r/2.2, bg_col) # Cutout
		"drop":
			var pts = [pos + Vector2(0, -r/2), pos + Vector2(r/2, r/2), pos + Vector2(-r/2, r/2)]
			canvas.draw_colored_polygon(PackedVector2Array(pts), col)
		"skull":
			canvas.draw_circle(pos, r/2, col)
			canvas.draw_rect(Rect2(pos + Vector2(-r/4, r/4), Vector2(r/2, r/3)), col)
		"shield":
			var pts = [pos + Vector2(-r/2, -r/2), pos + Vector2(r/2, -r/2), pos + Vector2(0, r/2)]
			canvas.draw_colored_polygon(PackedVector2Array(pts), col)
		"tree":
			var pts = [pos + Vector2(0, -r/2), pos + Vector2(r/2, r/2), pos + Vector2(-r/2, r/2)]
			canvas.draw_colored_polygon(PackedVector2Array(pts), col)
			canvas.draw_rect(Rect2(pos + Vector2(-1, r/2), Vector2(2, 2)), Color.BROWN)
		"note":
			canvas.draw_rect(Rect2(pos - Vector2(r/4, r/2), Vector2(r/2, r)), col)
		"flake":
			canvas.draw_line(pos + Vector2(-r/2, 0), pos + Vector2(r/2, 0), col, 1.0)
			canvas.draw_line(pos + Vector2(0, -r/2), pos + Vector2(0, r/2), col, 1.0)
		"face":
			canvas.draw_circle(pos, r/2, col)
		_:
			canvas.draw_circle(pos, r/2, col)
