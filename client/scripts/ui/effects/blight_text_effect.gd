extends RichTextEffect
class_name BlightTextEffect

# Usage: [blight amp=0.7 rate=4.0]text[/blight]
var bbcode := "blight"

func _process_custom_fx(char_fx: CharFXTransform) -> bool:
	var amp: float = _to_float(char_fx.env.get("amp", 0.0))
	if amp <= 0.0:
		return true

	var rate: float = max(_to_float(char_fx.env.get("rate", 5.0)), 0.1)
	var phase: float = float(char_fx.range.x) * 0.37
	var wave: float = sin((char_fx.elapsed_time * rate) + phase)
	var jitter_y: float = wave * amp * 3.0
	var alpha_drop: float = min(amp * 0.25, 0.4)

	char_fx.offset.y += jitter_y
	char_fx.color.a = clamp(char_fx.color.a - alpha_drop, 0.2, 1.0)
	return true

func _to_float(value: Variant) -> float:
	match typeof(value):
		TYPE_FLOAT:
			return value
		TYPE_INT:
			return float(value)
		TYPE_STRING:
			return float(value)
		_:
			return 0.0
