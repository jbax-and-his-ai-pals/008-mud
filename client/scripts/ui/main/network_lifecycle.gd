# scripts/ui/main/network_lifecycle.gd
# NetworkLifecycleController: extracted from main_controller.gd as part of the P8
# file-splitting pass. main.tscn is untouched -- this holds a reference
# back to the Main control (`main`) and reaches its @onready nodes and
# shared state through it, since GDScript keeps one script per node.
extends RefCounted
class_name NetworkLifecycleController

var main: MainController

func _init(main_ref: MainController) -> void:
	main = main_ref

func _on_connect_pressed() -> void:
	main._manual_disconnect_requested = false
	main._finite_adventure_catalog.clear()
	main._finite_adventure_catalog_requested = false
	main._latest_quests_payload.clear()
	main._game_contract.clear()
	main._refresh_game_contract_affordances()
	main.finite_adventure_ui._refresh_finite_adventure_catalog_picker()
	var host := main.host_input.text.strip_edges()
	var port := int(main.port_input.text)
	main._network_telemetry["connect_attempts"] = int(main._network_telemetry.get("connect_attempts", 0)) + 1
	if _using_websocket():
		main._network_telemetry["last_transport"] = "WebSocket"
		main.ws_client.connect_to_server(host, port)
	else:
		main._network_telemetry["last_transport"] = "TCP"
		main.tcp_client.connect_to_server(host, port)
	_refresh_network_labels()

func _on_disconnect_pressed() -> void:
	main._manual_disconnect_requested = true
	_cancel_reconnect()
	main.crash_recovery.clear_marker()
	main._network_telemetry["lines_sent"] = int(main._network_telemetry.get("lines_sent", 0)) + 1
	_active_client_send_line(JSON.stringify({"type": "disconnect"}))
	main.tcp_client.disconnect_from_server()
	main.ws_client.disconnect_from_server()
	_refresh_network_labels()

func _on_send_pressed() -> void:
	_submit_command()

func _on_auto_reconnect_toggled(pressed: bool) -> void:
	_set_auto_reconnect_enabled(pressed, true)

func _on_field_pulse_pressed() -> void:
	var field_id: String = main.field_id_input.text.strip_edges().to_lower()
	if field_id == "":
		field_id = "blight"
	var x: int = main._safe_int(main.field_x_input.text, 4)
	var y: int = main._safe_int(main.field_y_input.text, 4)
	var value: float = clamp(main._safe_float(main.field_value_input.text, 1.0), 0.0, 1.0)
	var cmd := "field pulse %s %d %d %.2f" % [field_id, x, y, value]
	var envelope: Dictionary = main.parser.build_command_envelope(cmd, main._client_capabilities.duplicate(true), main._session_id)
	main._network_telemetry["lines_sent"] = int(main._network_telemetry.get("lines_sent", 0)) + 1
	_active_client_send_line(JSON.stringify(envelope))
	main._append_log("[b]> %s[/b]" % cmd)
	_refresh_network_labels()

func _on_command_submitted(_text: String) -> void:
	_submit_command()

func _history_navigate(direction: int) -> void:
	if main._command_history.is_empty():
		return
	if direction < 0:  # Up — step toward older commands.
		if main._history_cursor == -1:
			main._history_draft = main.command_input.text
			main._history_cursor = main._command_history.size() - 1
		else:
			main._history_cursor = max(0, main._history_cursor - 1)
	else:  # Down — step toward newer / exit history.
		if main._history_cursor == -1:
			return
		main._history_cursor += 1
		if main._history_cursor >= main._command_history.size():
			main._history_cursor = -1
			main.command_input.text = main._history_draft
			main.command_input.caret_column = main.command_input.text.length()
			return
	main.command_input.text = main._command_history[main._history_cursor]
	main.command_input.caret_column = main.command_input.text.length()

func _push_history(cmd: String) -> void:
	if main._command_history.is_empty() or main._command_history[-1] != cmd:
		main._command_history.append(cmd)
		if main._command_history.size() > main.HISTORY_MAX_SIZE:
			main._command_history.remove_at(0)
	main._history_cursor = -1
	main._history_draft = ""

func _submit_command() -> void:
	var cmd := main.command_input.text.strip_edges()
	if cmd == "":
		return
	_push_history(cmd)
	if main.authoring_locks._maybe_send_asset_update_command(cmd):
		main.command_input.text = ""
		return
	if main.authoring_locks._maybe_send_lock_command(cmd):
		main.command_input.text = ""
		return
	if main.accessibility._maybe_handle_local_network_command(cmd):
		main.command_input.text = ""
		return
	if main.theme_controller._maybe_handle_local_theme_command(cmd):
		main.command_input.text = ""
		return
	if main.accessibility._maybe_handle_local_accessibility_command(cmd):
		main.command_input.text = ""
		return
	if main.accessibility._maybe_handle_local_keybind_command(cmd):
		main.command_input.text = ""
		return
	if main.accessibility._maybe_handle_local_onboarding_command(cmd):
		main.command_input.text = ""
		return
	if main.gm_auth._maybe_handle_local_gm_command(cmd):
		main.command_input.text = ""
		return
	if main.profiles._maybe_handle_local_profile_command(cmd):
		main.command_input.text = ""
		return
	_warn_if_command_conflicts_with_policy(cmd)
	_send_command_to_server(cmd)
	main.command_input.text = ""
	_refresh_network_labels()

func _on_char_name_submitted(name: String) -> void:
	"""Send 'char create <name>' when the player confirms the creation dialog."""
	_send_command_to_server("char create %s" % name)

func _send_command_immediate(cmd: String) -> void:
	var old_text = main.command_input.text
	main.command_input.text = cmd
	_submit_command()
	if not main.command_input.text:
		main.command_input.text = old_text

func _send_command_to_server(cmd: String, display_cmd: String = "") -> void:
	var envelope: Dictionary = main.parser.build_command_envelope(cmd, main._resolve_client_capabilities(cmd), main._session_id)
	main._network_telemetry["lines_sent"] = int(main._network_telemetry.get("lines_sent", 0)) + 1
	_active_client_send_line(JSON.stringify(envelope))
	var shown: String = display_cmd
	if shown == "":
		shown = cmd
	main._append_log("[b]> %s[/b]" % shown)

func _warn_if_command_conflicts_with_policy(cmd: String) -> void:
	var normalized: String = cmd.strip_edges().to_lower()
	if normalized == "":
		return
	var world_mutation_mode: String = str(main._server_profile_modes.get("world_mutation", "")).to_lower()
	if world_mutation_mode == "readonly":
		if normalized.begins_with("@dig") or normalized.begins_with("@edit"):
			main._append_log("[color=orange]Server policy: world mutation is readonly; this command may be rejected.[/color]")
	var combat_mode: String = str(main._server_profile_modes.get("combat", "")).to_lower()
	if combat_mode == "disabled":
		if normalized.begins_with("attack ") or normalized == "attack":
			main._append_log("[color=orange]Server policy: combat is disabled; this command may be rejected.[/color]")

func _using_websocket() -> bool:
	return main.transport_select.selected == 1

func _active_client_send_line(line: String) -> void:
	if _using_websocket():
		main.ws_client.send_line(line)
	else:
		main.tcp_client.send_line(line)

func _bind_client_signals(client, label: String) -> void:
	client.connected.connect(func() -> void:
		_cancel_reconnect()
		main._reconnect_attempts = 0
		main._network_telemetry["connect_successes"] = int(main._network_telemetry.get("connect_successes", 0)) + 1
		main._network_telemetry["last_transport"] = label
		main._network_telemetry["last_connected_at"] = Time.get_datetime_string_from_system()
		main._append_log("[color=green]Connected (%s).[/color]" % label)
		main.crash_recovery.write_marker(main.host_input.text.strip_edges(), int(main.port_input.text), label)
		_refresh_network_labels()
		main.profiles._refresh_profile_status()
		if main._resume_session_id != "":
			main._network_telemetry["lines_sent"] = int(main._network_telemetry.get("lines_sent", 0)) + 1
			_active_client_send_line(JSON.stringify(main.parser.build_resume_session_envelope(main._resume_session_id)))
			_refresh_network_labels()
	)
	client.disconnected.connect(func() -> void:
		main._network_telemetry["disconnects"] = int(main._network_telemetry.get("disconnects", 0)) + 1
		main._network_telemetry["last_disconnected_at"] = Time.get_datetime_string_from_system()
		main._append_log("[color=yellow]Disconnected (%s).[/color]" % label)
		main.profiles._refresh_profile_status()
		if not main._manual_disconnect_requested and _should_auto_reconnect(label):
			_schedule_reconnect()
		_refresh_network_labels()
	)
	client.error.connect(func(message: String) -> void:
		main._network_telemetry["errors"] = int(main._network_telemetry.get("errors", 0)) + 1
		main._network_telemetry["last_error"] = "%s: %s" % [label, message]
		main._append_log("[color=red]Error (%s): %s[/color]" % [label, message])
		if not main._manual_disconnect_requested and _should_auto_reconnect(label):
			if message.begins_with("Connect failed"):
				_schedule_reconnect()
		_refresh_network_labels()
	)
	client.line_received.connect(main._on_line_received)

func _apply_degraded_mode(reason: String) -> void:
	if main._degraded_mode_active:
		return
	main._degraded_mode_active = true
	main._client_capabilities["rich_text"] = false
	main._client_capabilities["reduced_motion"] = true
	main._append_log("[color=orange]Degraded mode active: %s[/color]" % reason)

func _refresh_network_labels() -> void:
	var transport: String = str(main._network_telemetry.get("last_transport", "--"))
	var attempts: int = int(main._network_telemetry.get("connect_attempts", 0))
	var connects: int = int(main._network_telemetry.get("connect_successes", 0))
	var disconnects: int = int(main._network_telemetry.get("disconnects", 0))
	var errors: int = int(main._network_telemetry.get("errors", 0))
	main.network_summary_label.text = "Transport %s  Attempts %d  Up %d  Down %d  Err %d" % [
		transport, attempts, connects, disconnects, errors
	]

	var sent: int = int(main._network_telemetry.get("lines_sent", 0))
	var recv: int = int(main._network_telemetry.get("lines_received", 0))
	var last_error: String = str(main._network_telemetry.get("last_error", "")).strip_edges()
	var reconnect_state: String = str(main._network_telemetry.get("reconnect_state", "idle"))
	var auto_reconnect_enabled: bool = bool(main._network_telemetry.get("auto_reconnect_enabled", true))
	var countdown := ""
	if main._reconnect_pending:
		var remaining: float = max(0.0, float(main._reconnect_deadline_msec - Time.get_ticks_msec()) / 1000.0)
		countdown = "  Reconnect in %.1fs" % remaining
	if last_error == "":
		last_error = "none"
	var reconnect_mode: String = "ON" if auto_reconnect_enabled else "OFF"
	main.network_detail_label.text = "Sent %d  Recv %d  Last error: %s  Reconnect(%s): %s%s" % [
		sent, recv, last_error, reconnect_mode, reconnect_state, countdown
	]

func _should_auto_reconnect(label: String) -> bool:
	if not main._auto_reconnect_enabled:
		return false
	return (_using_websocket() and label == "WebSocket") or ((not _using_websocket()) and label == "TCP")

func _schedule_reconnect() -> void:
	if main._reconnect_attempts >= main._max_reconnect_attempts:
		main._network_telemetry["reconnect_state"] = "exhausted"
		main._append_log("[color=orange]Reconnect exhausted after %d attempts.[/color]" % main._reconnect_attempts)
		return
	main._reconnect_attempts += 1
	var wait_seconds: int = min(30, int(pow(2.0, float(main._reconnect_attempts - 1))))
	main._reconnect_deadline_msec = Time.get_ticks_msec() + (wait_seconds * 1000)
	main._reconnect_pending = true
	main._network_telemetry["reconnect_state"] = "pending_%ds" % wait_seconds
	main._append_log("[color=yellow]Auto reconnect attempt %d/%d in %ds.[/color]" % [
		main._reconnect_attempts, main._max_reconnect_attempts, wait_seconds
	])

func _cancel_reconnect() -> void:
	main._reconnect_pending = false
	main._network_telemetry["reconnect_state"] = "idle"

func _set_auto_reconnect_enabled(enabled: bool, log_change: bool) -> void:
	main._auto_reconnect_enabled = enabled
	main._network_telemetry["auto_reconnect_enabled"] = enabled
	if not enabled:
		_cancel_reconnect()
	if log_change:
		if enabled:
			main._append_log("[color=aqua]Auto reconnect enabled.[/color]")
		else:
			main._append_log("[color=aqua]Auto reconnect disabled.[/color]")
	_sync_auto_reconnect_button()
	_refresh_network_labels()

func _sync_auto_reconnect_button() -> void:
	main.auto_reconnect_button.button_pressed = main._auto_reconnect_enabled
	main.auto_reconnect_button.text = "Auto Reconnect: %s" % ("ON" if main._auto_reconnect_enabled else "OFF")

func _on_crash_recovery_restore(host: String, port: int, session_id: String, transport: String) -> void:
	main.host_input.text = host
	main.port_input.text = str(port)
	main.transport_select.selected = 1 if transport == "WebSocket" else 0
	main._resume_session_id = session_id
	main._append_log("[color=aqua]Crash recovery: reconnecting to %s:%d…[/color]" % [host, port])
	_on_connect_pressed()
