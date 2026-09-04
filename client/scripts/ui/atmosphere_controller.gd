extends CanvasLayer
class_name AtmosphereController

@export var overlay_path: NodePath
@export var audio_player_path: NodePath

var _overlay: ColorRect
var _audio_player: AudioStreamPlayer
var _generator_playback: AudioStreamGeneratorPlayback
var _phase: float = 0.0
var _sample_rate: float = 44100.0
var _current_intensity: float = 0.0
var _target_intensity: float = 0.0
var _target_polarity: String = "neutral"

func _ready() -> void:
	_overlay = get_node_or_null(overlay_path) as ColorRect
	_audio_player = get_node_or_null(audio_player_path) as AudioStreamPlayer
	if _audio_player == null:
		return
	var stream := AudioStreamGenerator.new()
	stream.mix_rate = _sample_rate
	stream.buffer_length = 0.25
	_audio_player.stream = stream
	_audio_player.play()
	_generator_playback = _audio_player.get_stream_playback() as AudioStreamGeneratorPlayback

func _process(delta: float) -> void:
	_current_intensity = lerpf(_current_intensity, _target_intensity, clamp(delta * 6.0, 0.0, 1.0))
	_update_overlay()
	_fill_audio_buffer()

func apply_world_state(field_id: String, polarity: String, cells: Array) -> void:
	if field_id == "":
		return
	_target_polarity = polarity
	_target_intensity = _compute_intensity(cells)

func _compute_intensity(cells: Array) -> float:
	if cells.is_empty():
		return 0.0
	var total: float = 0.0
	var count: int = 0
	for raw_cell in cells:
		if typeof(raw_cell) != TYPE_DICTIONARY:
			continue
		var cell: Dictionary = raw_cell as Dictionary
		total += clamp(float(cell.get("value", 0.0)), 0.0, 1.0)
		count += 1
	if count <= 0:
		return 0.0
	return clamp(total / float(count), 0.0, 1.0)

func _update_overlay() -> void:
	if _overlay == null:
		return
	var mat := _overlay.material as ShaderMaterial
	if mat == null:
		return
	var tint := Color(0.0, 0.0, 0.0, 0.0)
	if _target_polarity == "negative":
		tint = Color(0.0, 0.0, 0.0, clamp(_current_intensity * 0.32, 0.0, 0.32))
	elif _target_polarity == "positive":
		tint = Color(1.0, 1.0, 1.0, clamp(_current_intensity * 0.12, 0.0, 0.12))
	mat.set_shader_parameter("overlay_tint", tint)
	mat.set_shader_parameter("effect_strength", _current_intensity)

func _fill_audio_buffer() -> void:
	if _generator_playback == null:
		return
	var frames_available: int = _generator_playback.get_frames_available()
	if frames_available <= 0:
		return
	var base_hz: float = 85.0
	if _target_polarity == "positive":
		base_hz = 170.0
	elif _target_polarity == "neutral":
		base_hz = 120.0
	var volume: float = 0.005 + (_current_intensity * 0.02)
	for _i in range(frames_available):
		_phase += TAU * base_hz / _sample_rate
		if _phase > TAU:
			_phase -= TAU
		var sample: float = sin(_phase) * volume
		_generator_playback.push_frame(Vector2(sample, sample))
