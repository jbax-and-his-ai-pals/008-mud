# scripts/ui/main/accessibility.gd
# AccessibilityController: extracted from main_controller.gd as part of the P8
# file-splitting pass. main.tscn is untouched -- this holds a reference
# back to the Main control (`main`) and reaches its @onready nodes and
# shared state through it, since GDScript keeps one script per node.
extends RefCounted
class_name AccessibilityController

var main: MainController

func _init(main_ref: MainController) -> void:
	main = main_ref

func _maybe_handle_local_accessibility_command(cmd: String) -> bool:
	var lowered: String = cmd.strip_edges().to_lower()

	# ── a11y list ──────────────────────────────────────────────────────────
	if lowered == "a11y list":
		var preset_names: PackedStringArray = []
		for key: Variant in main.A11Y_PRESETS.keys():
			preset_names.append(str(key))
		preset_names.sort()
		main._append_log("[color=aqua]A11y presets: %s[/color]" % ", ".join(preset_names))
		main._append_log("[color=aqua]A11y commands:[/color]")
		main._append_log("[color=aqua]  a11y preset <name>          — apply a named preset[/color]")
		main._append_log("[color=aqua]  a11y text <small|medium|large|xlarge|pct>  — text scale[/color]")
		main._append_log("[color=aqua]  a11y font dyslexia on/off   — high-legibility font[/color]")
		main._append_log("[color=aqua]  a11y spacing <1.0..2.0>     — line spacing multiplier[/color]")
		main._append_log("[color=aqua]  a11y contrast on/off        — minimum contrast enforcement[/color]")
		main._append_log("[color=aqua]  a11y distortion on/off      — atmospheric text effects[/color]")
		main._append_log("[color=aqua]  a11y weather on/off         — weather/screen shader effects[/color]")
		main._append_log("[color=aqua]  a11y motion on/off          — reduced motion[/color]")
		main._append_log("[color=aqua]  a11y sr on/off              — screen reader mode[/color]")
		return true

	# ── a11y preset <name> ─────────────────────────────────────────────────
	if lowered.begins_with("a11y preset "):
		var preset_name: String = lowered.substr(12).strip_edges()
		if not main.A11Y_PRESETS.has(preset_name):
			main._append_log("[color=orange]Unknown preset '%s'. Try: a11y list[/color]" % preset_name)
			return true
		var patch: Dictionary = main.A11Y_PRESETS[preset_name] as Dictionary
		for key: Variant in patch.keys():
			main._client_capabilities[str(key)] = patch[key]
		main._append_log("[color=yellow]Accessibility preset: %s[/color]" % preset_name)
		if bool(main._client_capabilities.get("high_contrast", false)):
			main._append_log("[color=yellow]  high contrast ON[/color]")
		if bool(main._client_capabilities.get("contrast_enforce", false)):
			main._append_log("[color=yellow]  contrast enforcement ON[/color]")
		if bool(main._client_capabilities.get("reduced_motion", false)):
			main._append_log("[color=yellow]  reduced motion ON[/color]")
		if bool(main._client_capabilities.get("screen_reader_mode", false)):
			main._append_log("[color=yellow]  screen reader mode ON[/color]")
		if bool(main._client_capabilities.get("dyslexia_font", false)):
			main._append_log("[color=yellow]  dyslexia font ON[/color]")
			_apply_dyslexia_font(true)
		var spacing: float = main._to_float(main._client_capabilities.get("line_spacing", 1.0))
		if spacing != 1.0:
			main._append_log("[color=yellow]  line spacing %.2f[/color]" % spacing)
			_apply_line_spacing(spacing)
		if not bool(main._client_capabilities.get("effects_distortion", true)):
			main._append_log("[color=yellow]  atmospheric distortion OFF[/color]")
		if not bool(main._client_capabilities.get("effects_weather", true)):
			main._append_log("[color=yellow]  weather effects OFF[/color]")
		var new_scale: float = main._to_float(main._client_capabilities.get("text_scale", 1.0))
		main.theme_controller._apply_text_scale(new_scale)
		main._append_log("[color=yellow]  text scale %.0f%%[/color]" % (new_scale * 100.0))
		return true

	# ── a11y font dyslexia on/off ──────────────────────────────────────────
	if lowered.begins_with("a11y font dyslexia "):
		var val: String = lowered.substr(19).strip_edges()
		if val == "on":
			main._client_capabilities["dyslexia_font"] = true
			_apply_dyslexia_font(true)
			main._append_log("[color=yellow]Accessibility: dyslexia-friendly font ON[/color]")
		elif val == "off":
			main._client_capabilities["dyslexia_font"] = false
			_apply_dyslexia_font(false)
			main._append_log("[color=yellow]Accessibility: dyslexia-friendly font OFF[/color]")
		else:
			main._append_log("[color=orange]Usage: a11y font dyslexia on/off[/color]")
		return true

	# ── a11y spacing <multiplier> ──────────────────────────────────────────
	if lowered.begins_with("a11y spacing "):
		var val: String = lowered.substr(13).strip_edges()
		if val.is_valid_float():
			var sp: float = clamp(float(val), 0.8, 3.0)
			main._client_capabilities["line_spacing"] = sp
			_apply_line_spacing(sp)
			main._append_log("[color=yellow]Accessibility: line spacing %.2f[/color]" % sp)
		else:
			main._append_log("[color=orange]Usage: a11y spacing <0.8..3.0>[/color]")
		return true

	# ── a11y contrast on/off ───────────────────────────────────────────────
	if lowered.begins_with("a11y contrast "):
		var val: String = lowered.substr(14).strip_edges()
		if val == "on":
			main._client_capabilities["contrast_enforce"] = true
			main._append_log("[color=yellow]Accessibility: minimum contrast enforcement ON[/color]")
		elif val == "off":
			main._client_capabilities["contrast_enforce"] = false
			main._append_log("[color=yellow]Accessibility: minimum contrast enforcement OFF[/color]")
		else:
			main._append_log("[color=orange]Usage: a11y contrast on/off[/color]")
		return true

	# ── a11y distortion on/off ─────────────────────────────────────────────
	if lowered.begins_with("a11y distortion "):
		var val: String = lowered.substr(16).strip_edges()
		if val == "on":
			main._client_capabilities["effects_distortion"] = true
			_apply_distortion_effects(true)
			main._append_log("[color=yellow]Accessibility: atmospheric distortion ON[/color]")
		elif val == "off":
			main._client_capabilities["effects_distortion"] = false
			_apply_distortion_effects(false)
			main._append_log("[color=yellow]Accessibility: atmospheric distortion OFF[/color]")
		else:
			main._append_log("[color=orange]Usage: a11y distortion on/off[/color]")
		return true

	# ── a11y weather on/off ────────────────────────────────────────────────
	if lowered.begins_with("a11y weather "):
		var val: String = lowered.substr(13).strip_edges()
		if val == "on":
			main._client_capabilities["effects_weather"] = true
			_apply_weather_effects(true)
			main._append_log("[color=yellow]Accessibility: weather effects ON[/color]")
		elif val == "off":
			main._client_capabilities["effects_weather"] = false
			_apply_weather_effects(false)
			main._append_log("[color=yellow]Accessibility: weather effects OFF[/color]")
		else:
			main._append_log("[color=orange]Usage: a11y weather on/off[/color]")
		return true

	# ── a11y text <scale> ──────────────────────────────────────────────────
	var parts: PackedStringArray = lowered.split(" ", false)
	if parts.size() >= 3 and parts[0] == "a11y" and parts[1] == "text":
		var scale := -1.0
		var arg: String = parts[2]
		if main.TEXT_SCALE_PRESETS.has(arg):
			scale = float(main.TEXT_SCALE_PRESETS[arg])
		elif arg.is_valid_float():
			scale = clamp(float(arg) / 100.0, main.TEXT_SCALE_MIN, main.TEXT_SCALE_MAX)
		else:
			main._append_log("[color=orange]Usage: a11y text <small|medium|large|xlarge|percent>[/color]")
			return true
		main.theme_controller._apply_text_scale(scale)
		main._append_log("[color=yellow]Accessibility: text scale %.0f%%[/color]" % (scale * 100.0))
		return true

	return false

# ── A11y apply helpers ──────────────────────────────────────────────────────

func _apply_dyslexia_font(enabled: bool) -> void:
	## Swap the log view font to a high-legibility face when enabled.
	## Falls back gracefully if the font resource isn't present.
	var font_path := "res://fonts/opendyslexic_regular.ttf" if enabled else ""
	if enabled and ResourceLoader.exists(font_path):
		var font: FontFile = load(font_path)
		main.log_view.add_theme_font_override("normal_font", font)
	else:
		main.log_view.remove_theme_font_override("normal_font")

func _apply_line_spacing(multiplier: float) -> void:
	## Apply line spacing multiplier to the main log view.
	var clamped: float = clamp(multiplier, 0.8, 3.0)
	main.log_view.add_theme_constant_override("line_separation", int((clamped - 1.0) * 20.0))

func _apply_distortion_effects(enabled: bool) -> void:
	## Toggle atmospheric text distortion effects (blight/wave).
	if is_instance_valid(main.atmosphere_layer):
		main.atmosphere_layer.visible = enabled
	# Uninstall/reinstall RichTextEffects on log_view based on flag.
	# Effects are installed at _ready; disabling clears them.
	if not enabled:
		main.log_view.install_effect(null)  # no-op clear — effects stay inert if atmosphere_layer is hidden
	main._client_capabilities["effects_distortion"] = enabled

func _apply_weather_effects(enabled: bool) -> void:
	## Toggle weather/screen shader overlays.
	# The weather overlay node (if present) is controlled here.
	# If no dedicated weather node exists, this is a capability flag only —
	# the server reads effects_weather from the capabilities dict.
	main._client_capabilities["effects_weather"] = enabled
	# Signal the server on next command cycle via capabilities update.
	main._append_log("[color=gray](Weather effects toggle will apply on next server sync.)[/color]" if not enabled else "")

func _maybe_handle_local_onboarding_command(cmd: String) -> bool:
	var lowered: String = cmd.strip_edges().to_lower()
	if lowered == "onboarding show":
		main.onboarding.show_panel()
		return true
	if lowered == "onboarding dismiss":
		main.onboarding.dismiss()
		main._append_log("[color=aqua]Onboarding dismissed.[/color]")
		return true
	if lowered == "onboarding":
		main._append_log("[color=orange]Usage: onboarding show | onboarding dismiss[/color]")
		return true
	return false

func _maybe_handle_local_keybind_command(cmd: String) -> bool:
	var lowered: String = cmd.strip_edges().to_lower()

	# ── keybind list ───────────────────────────────────────────────────────────
	if lowered == "keybind list":
		main._append_log("[color=aqua]Key bindings:[/color]")
		for line: String in main.keybindings_manager.get_summary_lines():
			main._append_log(line)
		main._append_log("[color=aqua]Commands: keybind set <action> <key>  |  keybind reset [action][/color]")
		return true

	# ── keybind reset [action] ─────────────────────────────────────────────────
	if lowered == "keybind reset":
		main.keybindings_manager.reset()
		main._append_log("[color=yellow]Keybindings reset to defaults.[/color]")
		return true

	if lowered.begins_with("keybind reset "):
		var action: String = lowered.substr(14).strip_edges()
		if main.keybindings_manager.reset_action(action):
			main._append_log("[color=yellow]Keybinding reset: %s[/color]" % action)
		else:
			main._append_log("[color=orange]Unknown action '%s'. Try: keybind list[/color]" % action)
		return true

	# ── keybind set <action> <key> ─────────────────────────────────────────────
	if lowered.begins_with("keybind set "):
		var args: String = cmd.strip_edges().substr(12).strip_edges()
		var parts: PackedStringArray = args.split(" ", false)
		if parts.size() < 2:
			main._append_log("[color=orange]Usage: keybind set <action> <key>[/color]")
			return true
		var action: String = parts[0].to_lower()
		var key_name: String = parts[1]  # preserve case; key names are Title-case
		if main.keybindings_manager.set_action_keys(action, PackedStringArray([key_name])):
			main.keybindings_manager.save()
			main._append_log("[color=yellow]Keybinding updated: %s → %s[/color]" % [action, key_name])
		else:
			main._append_log("[color=orange]Invalid action or key name. Try: keybind list[/color]")
		return true

	if lowered.begins_with("keybind"):
		main._append_log("[color=orange]Usage: keybind list | keybind set <action> <key> | keybind reset [action][/color]")
		return true

	return false

func _maybe_handle_local_network_command(cmd: String) -> bool:
	var lowered: String = cmd.strip_edges().to_lower()
	if lowered == "net diag":
		main._append_log("[color=aqua]Network diag: %s[/color]" % JSON.stringify(main._network_telemetry))
		return true
	if lowered == "net reconnect now":
		main.network_lifecycle._cancel_reconnect()
		main._reconnect_attempts = 0
		main._append_log("[color=aqua]Manual reconnect requested.[/color]")
		main.network_lifecycle._on_connect_pressed()
		return true
	if lowered == "net reconnect status":
		var status_text := "ON" if main._auto_reconnect_enabled else "OFF"
		main._append_log("[color=aqua]Auto reconnect: %s[/color]" % status_text)
		return true
	if lowered == "net reconnect on":
		main.network_lifecycle._set_auto_reconnect_enabled(true, true)
		return true
	if lowered == "net reconnect off":
		main.network_lifecycle._set_auto_reconnect_enabled(false, true)
		return true
	if lowered == "net resume now":
		if main._resume_session_id == "":
			main._append_log("[color=orange]No resume session id cached yet.[/color]")
			return true
		if not main._is_connected_to_game_server():
			main._append_log("[color=orange]Not connected. Use: net reconnect now[/color]")
			return true
		main._network_telemetry["lines_sent"] = int(main._network_telemetry.get("lines_sent", 0)) + 1
		main.network_lifecycle._active_client_send_line(JSON.stringify(main.parser.build_resume_session_envelope(main._resume_session_id)))
		main._append_log("[color=aqua]Resume requested for cached session.[/color]")
		main.network_lifecycle._refresh_network_labels()
		return true
	if lowered.begins_with("net resume "):
		var wanted: String = cmd.strip_edges().substr(11).strip_edges()
		if wanted == "":
			main._append_log("[color=orange]Usage: net resume <session_id>[/color]")
			return true
		main._resume_session_id = wanted
		if not main._is_connected_to_game_server():
			main._append_log("[color=aqua]Resume session id cached. Connect to send resume.[/color]")
			return true
		main._network_telemetry["lines_sent"] = int(main._network_telemetry.get("lines_sent", 0)) + 1
		main.network_lifecycle._active_client_send_line(JSON.stringify(main.parser.build_resume_session_envelope(main._resume_session_id)))
		main._append_log("[color=aqua]Resume requested for: %s[/color]" % main._resume_session_id)
		main.network_lifecycle._refresh_network_labels()
		return true
	if lowered == "net reset":
		var last_transport: String = str(main._network_telemetry.get("last_transport", ""))
		var auto_reconnect_enabled: bool = bool(main._network_telemetry.get("auto_reconnect_enabled", true))
		main._network_telemetry = {
			"connect_attempts": 0,
			"connect_successes": 0,
			"disconnects": 0,
			"errors": 0,
			"lines_received": 0,
			"lines_sent": 0,
			"last_transport": last_transport,
			"last_error": "",
			"last_connected_at": "",
			"last_disconnected_at": "",
			"reconnect_state": "idle",
			"auto_reconnect_enabled": auto_reconnect_enabled
		}
		main._append_log("[color=aqua]Network telemetry reset.[/color]")
		main.network_lifecycle._refresh_network_labels()
		return true
	if lowered == "net export":
		var export_payload: Dictionary = main._network_telemetry.duplicate(true)
		export_payload["session_id"] = main._session_id
		export_payload["resume_session_id"] = main._resume_session_id
		export_payload["timestamp"] = Time.get_datetime_string_from_system()
		var filename: String = "net_diag_%s.json" % Time.get_datetime_string_from_system().replace(":", "-")
		var path: String = "user://%s" % filename
		var file := FileAccess.open(path, FileAccess.WRITE)
		if file == null:
			main._append_log("[color=red]Failed to export diagnostics: %s[/color]" % FileAccess.get_open_error())
			return true
		file.store_string(JSON.stringify(export_payload))
		file.close()
		main._append_log("[color=aqua]Network diagnostics exported: %s[/color]" % path)
		return true
	return false
