extends RichTextEffect
class_name AtmosphericTextEffect

# Usage: [atmo type=shiver severity=0.6 duration_ms=1500]text[/atmo]
var bbcode := "atmo"

func _process_custom_fx(char_fx: CharFXTransform) -> bool:
	var fx_type: String = str(char_fx.env.get("type", ""))
	var severity: float = clamp(_to_float(char_fx.env.get("severity", 0.0)), 0.0, 1.0)
	if severity <= 0.0:
		return true

	match fx_type:
		"shiver":
			_apply_shiver(char_fx, severity)
		"bleed":
			_apply_bleed(char_fx, severity)
		"rot":
			_apply_rot(char_fx, severity)
		_:
			_apply_shiver(char_fx, severity * 0.25)
	return true

func _apply_shiver(char_fx: CharFXTransform, severity: float) -> void:
	var phase: float = float(char_fx.range.x) * 0.47
	var jitter_x: float = sin((char_fx.elapsed_time * (8.0 + (6.0 * severity))) + phase) * severity * 1.6
	var jitter_y: float = cos((char_fx.elapsed_time * (7.0 + (5.0 * severity))) + phase) * severity * 1.2
	char_fx.offset.x += jitter_x
	char_fx.offset.y += jitter_y

func _apply_bleed(char_fx: CharFXTransform, severity: float) -> void:
	var phase: float = float(char_fx.range.x) * 0.31
	char_fx.offset.y += abs(sin((char_fx.elapsed_time * 3.0) + phase)) * severity * 2.2
	char_fx.color.r = clamp(char_fx.color.r + (0.25 * severity), 0.0, 1.0)
	char_fx.color.g = clamp(char_fx.color.g - (0.25 * severity), 0.0, 1.0)
	char_fx.color.b = clamp(char_fx.color.b - (0.25 * severity), 0.0, 1.0)

func _apply_rot(char_fx: CharFXTransform, severity: float) -> void:
	var phase: float = float(char_fx.range.x) * 0.23
	var wobble: float = sin((char_fx.elapsed_time * 2.0) + phase) * severity * 1.4
	char_fx.offset.x += wobble
	char_fx.color.a = clamp(char_fx.color.a - (0.35 * severity), 0.15, 1.0)
	char_fx.color.g = clamp(char_fx.color.g - (0.20 * severity), 0.0, 1.0)

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
