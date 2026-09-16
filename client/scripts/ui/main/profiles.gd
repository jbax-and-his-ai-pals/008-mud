# scripts/ui/main/profiles.gd
# ProfileController: extracted from main_controller.gd as part of the P8
# file-splitting pass. main.tscn is untouched -- this holds a reference
# back to the Main control (`main`) and reaches its @onready nodes and
# shared state through it, since GDScript keeps one script per node.
extends RefCounted
class_name ProfileController

var main: MainController

func _init(main_ref: MainController) -> void:
	main = main_ref

func _request_profile_presets() -> void:
	if not main._is_connected_to_game_server():
		return
	var envelope: Dictionary = main.parser.build_command_envelope("profile list", main._resolve_client_capabilities("profile list"), main._session_id)
	main._network_telemetry["lines_sent"] = int(main._network_telemetry.get("lines_sent", 0)) + 1
	main.network_lifecycle._active_client_send_line(JSON.stringify(envelope))
	main.network_lifecycle._refresh_network_labels()

func _extract_profile_preset_from_path(path_value: String) -> String:
	var normalized: String = path_value.strip_edges().replace("\\", "/")
	if normalized == "":
		return ""
	var file_name: String = normalized.get_file()
	if file_name.ends_with(".profile.json"):
		return file_name.trim_suffix(".profile.json")
	return ""

func _sync_profile_select_from_known_presets() -> void:
	main.profile_preset_select.clear()
	for preset_name: String in main._known_profile_presets:
		main.profile_preset_select.add_item(preset_name)
	if main._known_profile_presets.is_empty():
		main.profile_preset_select.disabled = true
		return
	main.profile_preset_select.disabled = false
	var selected_index: int = 0
	for idx in range(main._known_profile_presets.size()):
		if main._known_profile_presets[idx] == main._active_profile_preset:
			selected_index = idx
			break
	main.profile_preset_select.select(selected_index)

func _refresh_profile_status() -> void:
	var active_text: String = main._active_profile_preset if main._active_profile_preset != "" else "(unknown)"
	var pending_text: String = main._pending_profile_apply_preset if main._pending_profile_apply_preset != "" else "none"
	main.profile_status_label.text = "Profile: active %s | pending %s" % [active_text, pending_text]
	var can_apply: bool = main._is_connected_to_game_server() and not main._known_profile_presets.is_empty()
	main.profile_apply_button.disabled = not can_apply
	main.profile_refresh_button.disabled = not main._is_connected_to_game_server()
	main.profile_cancel_button.disabled = main._pending_profile_apply_preset == ""
	if main._pending_profile_apply_preset == "":
		main.profile_apply_button.text = "Apply Selected"
	else:
		main.profile_apply_button.text = "Confirm Apply"
	main.operator_console._refresh_operator_values()
	main.operator_console._update_operator_palette_state()

func _on_profile_selected(index: int) -> void:
	if index < 0 or index >= main._known_profile_presets.size():
		return
	var preset: String = main._known_profile_presets[index]
	main._pending_profile_apply_preset = preset
	_refresh_profile_status()

func _on_profile_refresh_pressed() -> void:
	_request_profile_presets()

func _on_profile_cancel_pressed() -> void:
	if main._pending_profile_apply_preset != "":
		main._append_log("[color=yellow]Cancelled profile apply: %s[/color]" % main._pending_profile_apply_preset)
	main._pending_profile_apply_preset = ""
	_refresh_profile_status()

func _on_profile_apply_pressed() -> void:
	var target_preset: String = ""
	if not main._known_profile_presets.is_empty():
		var idx: int = main.profile_preset_select.get_selected()
		if idx >= 0 and idx < main._known_profile_presets.size():
			target_preset = main._known_profile_presets[idx]
	if target_preset == "":
		main._append_log("[color=orange]No profile selected to apply.[/color]")
		_refresh_profile_status()
		return
	if main._pending_profile_apply_preset != target_preset:
		main._pending_profile_apply_preset = target_preset
		main._append_log("[color=yellow]Pending profile apply: %s[/color]" % target_preset)
		main._append_log("[color=yellow]Click Apply Selected again (or run 'profile apply confirm') to confirm.[/color]")
		_refresh_profile_status()
		return
	main._append_log("[color=yellow]Confirming profile apply: %s[/color]" % target_preset)
	main.network_lifecycle._send_command_to_server("profile apply %s" % target_preset)
	main._pending_profile_apply_preset = ""
	_refresh_profile_status()

func _maybe_handle_local_profile_command(cmd: String) -> bool:
	var normalized: String = cmd.strip_edges().to_lower()
	if normalized == "profile help":
		main._append_log("[color=aqua]Profile commands:[/color]")
		main._append_log("[color=aqua]  profile list[/color]")
		main._append_log("[color=aqua]  profile apply <preset>[/color]")
		main._append_log("[color=aqua]  profile apply <index> (from latest list)[/color]")
		main._append_log("[color=aqua]  profile apply confirm[/color]")
		main._append_log("[color=aqua]  profile apply cancel[/color]")
		return true
	if normalized == "profile list" or normalized == "profiles":
		main._append_log("[color=aqua]Tip: use profile apply <preset>, then profile apply confirm.[/color]")
		_request_profile_presets()
		return true
	if normalized == "profile apply confirm":
		if main._pending_profile_apply_preset == "":
			main._append_log("[color=orange]No pending profile apply request.[/color]")
			return true
		var final_cmd: String = "profile apply %s" % main._pending_profile_apply_preset
		main._pending_profile_apply_preset = ""
		main.network_lifecycle._send_command_to_server(final_cmd)
		_refresh_profile_status()
		return true
	if normalized == "profile apply cancel":
		if main._pending_profile_apply_preset == "":
			main._append_log("[color=yellow]No pending profile apply request.[/color]")
		else:
			main._append_log("[color=yellow]Cancelled profile apply: %s[/color]" % main._pending_profile_apply_preset)
		main._pending_profile_apply_preset = ""
		_refresh_profile_status()
		return true
	if normalized.begins_with("profile apply "):
		var parts: PackedStringArray = normalized.split(" ", false)
		if parts.size() < 3:
			main._append_log("[color=orange]Usage: profile apply <preset_name>[/color]")
			return true
		var preset: String = parts[2].strip_edges()
		if preset == "":
			main._append_log("[color=orange]Usage: profile apply <preset_name>[/color]")
			return true
		if preset.is_valid_int():
			var idx: int = int(preset) - 1
			if idx >= 0 and idx < main._known_profile_presets.size():
				preset = main._known_profile_presets[idx]
			else:
				main._append_log("[color=orange]Unknown preset index %s. Run 'profile list' first.[/color]" % preset)
				return true
		main._pending_profile_apply_preset = preset
		main._append_log("[color=yellow]Pending profile apply: %s[/color]" % preset)
		main._append_log("[color=yellow]Run 'profile apply confirm' to proceed or 'profile apply cancel'.[/color]")
		_refresh_profile_status()
		return true
	return false

func _handle_profile_presets_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	main._known_profile_presets = PackedStringArray()
	main._active_profile_path = str(body.get("active_profile_path", main._active_profile_path)).strip_edges()
	var active_from_payload: String = _extract_profile_preset_from_path(main._active_profile_path)
	if active_from_payload != "":
		main._active_profile_preset = active_from_payload
	var presets_value: Variant = body.get("presets", [])
	if typeof(presets_value) == TYPE_ARRAY:
		main._append_log("[color=aqua]Available profile presets:[/color]")
		var index: int = 1
		for preset_value: Variant in presets_value as Array:
			var preset_name: String = str(preset_value).strip_edges()
			if preset_name == "":
				continue
			main._known_profile_presets.append(preset_name)
			main._append_log("[color=aqua]  %d) %s[/color]" % [index, preset_name])
			index += 1
	if main._known_profile_presets.is_empty():
		main._append_log("[color=yellow]No profile presets are available on this server.[/color]")
	main._operator_catalog_value_options["Profiles:Apply Selected"] = main._known_profile_presets.duplicate()
	_sync_profile_select_from_known_presets()
	_refresh_profile_status()
