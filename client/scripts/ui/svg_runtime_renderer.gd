extends Node
class_name SvgRuntimeRenderer

func _validate_svg_1bit(svg_text: String) -> PackedStringArray:
	var violations := PackedStringArray()
	var regex := RegEx.new()
	regex.compile("(fill|stroke)=\\\"([^\\\"]+)\\\"")
	var allowed := ["black", "white", "#000000", "#ffffff", "#000", "#fff", "none", "transparent"]
	
	for result in regex.search_all(svg_text):
		var attr: String = result.get_string(1)
		var val: String = result.get_string(2).strip_edges().to_lower()
		if not allowed.has(val):
			violations.append("invalid %s color '%s'" % [attr, val])
			
	return violations

func render_svg_texture(svg_text: String, target_size: Vector2i = Vector2i(128, 128)) -> Texture2D:
	var image := Image.new()
	var err: int = image.load_svg_from_string(svg_text)
	if err != OK:
		return null

	if image.get_width() <= 0 or image.get_height() <= 0:
		return null

	if target_size.x > 0 and target_size.y > 0:
		image.resize(target_size.x, target_size.y, Image.INTERPOLATE_NEAREST)

	_apply_1bit_post(image)
	return ImageTexture.create_from_image(image)

func _apply_1bit_post(image: Image) -> void:
	image.lock()
	for y in range(image.get_height()):
		for x in range(image.get_width()):
			var c: Color = image.get_pixel(x, y)
			var lum: float = (c.r + c.g + c.b) / 3.0
			if lum >= 0.5:
				image.set_pixel(x, y, Color(1, 1, 1, c.a))
			else:
				image.set_pixel(x, y, Color(0, 0, 0, c.a))
	image.unlock()
