# scripts/ui/main/authoring_locks.gd
# AuthoringLockController: extracted from main_controller.gd as part of the P8
# file-splitting pass. main.tscn is untouched -- this holds a reference
# back to the Main control (`main`) and reaches its @onready nodes and
# shared state through it, since GDScript keeps one script per node.
extends RefCounted
class_name AuthoringLockController

var main: MainController

func _init(main_ref: MainController) -> void:
	main = main_ref

func _authoring_asset_id() -> String:
	return main.authoring_asset_input.text.strip_edges()

func _on_authoring_acquire_pressed() -> void:
	var asset_id: String = _authoring_asset_id()
	main.network_lifecycle._send_command_immediate("@dig %s" % asset_id)

func _on_authoring_renew_pressed() -> void:
	var asset_id: String = _authoring_asset_id()
	main.network_lifecycle._send_command_immediate("@dig %s renew" % asset_id)

func _on_authoring_release_pressed() -> void:
	var asset_id: String = _authoring_asset_id()
	main._authoring_auto_renew_accum_s = 0.0
	main._authoring_last_auto_renew_asset_id = ""
	main.network_lifecycle._send_command_immediate("@dig %s release" % asset_id)

func _on_authoring_edit_pressed() -> void:
	var asset_id: String = _authoring_asset_id()
	if not _ensure_lock_before_edit(asset_id):
		return
	main.network_lifecycle._send_command_immediate("@edit %s next" % asset_id)

func _on_authoring_edit_stale_pressed() -> void:
	var asset_id: String = _authoring_asset_id()
	if not _ensure_lock_before_edit(asset_id):
		return
	main.network_lifecycle._send_command_immediate("@edit %s stale" % asset_id)

func _request_lock_status() -> void:
	if not (main.tcp_client.is_connected_to_server() or main.ws_client.is_connected_to_server()):
		return
	main._network_telemetry["lines_sent"] = int(main._network_telemetry.get("lines_sent", 0)) + 1
	main.network_lifecycle._active_client_send_line(JSON.stringify(main.parser.build_lock_status_envelope(main._session_id)))
	main.network_lifecycle._refresh_network_labels()

func _current_authoring_asset_id() -> String:
	var aid: String = str(main._authoring_panel_state.get("asset_id", "")).strip_edges()
	if aid == "":
		aid = main.authoring_asset_input.text.strip_edges()
	return aid

func _authoring_lock_is_mine(asset_id: String) -> bool:
	var aid: String = asset_id.strip_edges()
	if aid == "":
		return false
	if not main._authoring_lock_by_asset.has(aid):
		return false
	var lock_info: Dictionary = main._authoring_lock_by_asset.get(aid, {}) as Dictionary
	var owner: String = str(lock_info.get("owner_session_id", "")).strip_edges()
	return owner != "" and owner == main._session_id

func _ensure_lock_before_edit(asset_id: String) -> bool:
	if _authoring_lock_is_mine(asset_id):
		return true
	main._append_log("[color=orange]You do not currently hold the edit lock for '%s'. Acquire lock first.[/color]" % asset_id)
	_request_lock_status()
	return false

func _tick_authoring_auto_renew(delta_s: float) -> void:
	if not main._authoring_auto_renew_enabled:
		return
	if not main._is_connected_to_game_server():
		main._authoring_auto_renew_accum_s = 0.0
		return
	var active_asset_id: String = _current_authoring_asset_id()
	if not _authoring_lock_is_mine(active_asset_id):
		main._authoring_auto_renew_accum_s = 0.0
		main._authoring_last_auto_renew_asset_id = ""
		return
	main._authoring_auto_renew_accum_s += max(0.0, delta_s)
	if main._authoring_auto_renew_accum_s < main._authoring_auto_renew_interval_s:
		return
	main._authoring_auto_renew_accum_s = 0.0
	main._authoring_last_auto_renew_asset_id = active_asset_id
	main._network_telemetry["lines_sent"] = int(main._network_telemetry.get("lines_sent", 0)) + 1
	main.network_lifecycle._active_client_send_line(JSON.stringify(main.parser.build_lock_renew_envelope(active_asset_id, main._session_id)))
	main.network_lifecycle._refresh_network_labels()

func _apply_lock_state_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	main._authoring_lock_by_asset.clear()
	var active_variant: Variant = body.get("active_locks", [])
	if typeof(active_variant) == TYPE_ARRAY:
		for entry_variant in active_variant as Array:
			if typeof(entry_variant) != TYPE_DICTIONARY:
				continue
			var entry: Dictionary = entry_variant as Dictionary
			var aid: String = str(entry.get("asset_id", "")).strip_edges()
			if aid == "":
				continue
			main._authoring_lock_by_asset[aid] = {
				"owner_session_id": str(entry.get("owner_session_id", "")),
				"expires_at": float(entry.get("expires_at", 0.0))
			}
	var active_asset_id: String = _current_authoring_asset_id()
	if not _authoring_lock_is_mine(active_asset_id):
		main._authoring_auto_renew_accum_s = 0.0
		main._authoring_last_auto_renew_asset_id = ""
	_refresh_authoring_status()

func _apply_lock_delta_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	var aid: String = str(body.get("asset_id", "")).strip_edges()
	if aid == "":
		return
	var state: String = str(body.get("state", "")).to_lower()
	if state == "released" or state == "released_disconnect":
		main._authoring_lock_by_asset.erase(aid)
	else:
		main._authoring_lock_by_asset[aid] = {
			"owner_session_id": str(body.get("owner_session_id", "")),
			"expires_at": float(body.get("expires_at", 0.0))
		}
	if not _authoring_lock_is_mine(aid):
		main._authoring_auto_renew_accum_s = 0.0
		if main._authoring_last_auto_renew_asset_id == aid:
			main._authoring_last_auto_renew_asset_id = ""
	_refresh_authoring_status(aid)

func _refresh_authoring_status(preferred_asset_id: String = "") -> void:
	var aid: String = preferred_asset_id.strip_edges()
	if aid == "":
		aid = main.authoring_asset_input.text.strip_edges()

	var revision_text: String = "--"
	if main._asset_revisions.has(aid):
		revision_text = str(int(main._asset_revisions.get(aid, 0)))

	var lock_text: String = "none"
	var lock_state: String = "none"
	var lock_owner: String = ""
	var is_mine: bool = false
	var remain_s: float = 0.0
	var expires_at_s: float = 0.0
	if main._authoring_lock_by_asset.has(aid):
		var lock_info: Dictionary = main._authoring_lock_by_asset.get(aid, {}) as Dictionary
		var owner: String = str(lock_info.get("owner_session_id", "")).strip_edges()
		if owner == "":
			owner = "unknown"
		lock_owner = owner
		var owner_short: String = owner.left(8)
		var expires_at: float = float(lock_info.get("expires_at", 0.0))
		var remain: float = max(0.0, expires_at - Time.get_unix_time_from_system())
		remain_s = remain
		expires_at_s = expires_at
		is_mine = owner == main._session_id
		lock_state = "mine" if is_mine else "theirs"
		lock_text = "owner %s (%.1fs)" % [owner_short, remain]

	main._authoring_panel_state = {
		"asset_id": aid,
		"lock_state": lock_state,
		"lock_owner": lock_owner,
		"lock_expires_at": expires_at_s,
		"lock_remaining_s": remain_s,
		"is_mine": is_mine
	}

	var access_summary: String = _authoring_access_summary()
	main.authoring_status_label.text = "Authoring: asset %s  lock %s (%s)  rev %s  |  %s" % [aid, lock_text, lock_state, revision_text, access_summary]

func _authoring_access_summary() -> String:
	var world_mutation_mode: String = str(main._server_profile_modes.get("world_mutation", "")).to_lower()
	if world_mutation_mode == "readonly":
		return "world readonly"
	var authoring_mode: String = str(main._server_profile_modes.get("authoring", "")).to_lower()
	if authoring_mode == "disabled":
		return "authoring disabled"
	var requires_gm: bool = authoring_mode == "gm_only" or bool(main._server_auth_policy.get("authoring_requires_gm", false))
	if requires_gm:
		if main._gm_granted:
			return "authoring enabled (gm)"
		if not main._gm_auth_configured:
			return "gm auth unavailable"
		if main._gm_auth_cooldown_seconds > 0:
			return "gm cooldown %ds" % main._gm_auth_cooldown_seconds
		return "gm auth required"
	return "authoring enabled"

func _maybe_send_asset_update_command(cmd: String) -> bool:
	var tokens: PackedStringArray = cmd.strip_edges().split(" ", false)
	if tokens.is_empty():
		return false
	var lowered_head: String = tokens[0].to_lower()
	var is_legacy: bool = lowered_head == "assetupdate"
	var is_authoring: bool = lowered_head == "@edit"
	if not is_legacy and not is_authoring:
		return false

	var asset_id: String = _current_authoring_asset_id()
	var mode: String = "next"

	if is_legacy:
		if tokens.size() < 2:
			main._append_log("[color=orange]Usage: assetupdate <next|stale>[/color]")
			return true
		mode = tokens[1].to_lower()
	else:
		if tokens.size() < 3:
			main._append_log("[color=orange]Usage: @edit <asset_id> <next|stale>[/color]")
			return true
		asset_id = tokens[1].strip_edges()
		mode = tokens[2].to_lower()
		if asset_id == "":
			main._append_log("[color=orange]Usage: @edit <asset_id> <next|stale>[/color]")
			return true

	if mode != "next" and mode != "stale":
		main._append_log("[color=orange]Unknown edit mode '%s'. Use next or stale.[/color]" % mode)
		return true
	if is_authoring and not _ensure_lock_before_edit(asset_id):
		return true

	var known_revision: int = int(main._asset_revisions.get(asset_id, 1))
	var base_revision: int = known_revision if mode == "next" else max(0, known_revision - 1)
	var svg_text := "<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32' viewBox='0 0 32 32'><rect width='32' height='32' fill='white'/><rect x='1' y='1' width='30' height='30' fill='black'/><rect x='6' y='6' width='20' height='20' fill='white'/><rect x='12' y='12' width='8' height='8' fill='black'/></svg>"
	var envelope: Dictionary = main.parser.build_asset_update_envelope(asset_id, base_revision, svg_text, "Updated concentric-square emblem.", main._session_id)
	main._network_telemetry["lines_sent"] = int(main._network_telemetry.get("lines_sent", 0)) + 1
	main.network_lifecycle._active_client_send_line(JSON.stringify(envelope))
	main._append_log("[b]> %s[/b]" % cmd)
	main.network_lifecycle._refresh_network_labels()
	return true

func _maybe_send_lock_command(cmd: String) -> bool:
	var tokens: PackedStringArray = cmd.strip_edges().split(" ", false)
	if tokens.is_empty():
		return false
	var lowered_head: String = tokens[0].to_lower()
	var is_legacy: bool = lowered_head == "lock"
	var is_authoring: bool = lowered_head == "@dig"
	if not is_legacy and not is_authoring:
		return false

	var action: String = "acquire"
	var asset_id: String = _current_authoring_asset_id()

	if is_legacy:
		if tokens.size() < 2:
			main._append_log("[color=orange]Usage: lock <acquire|release|renew|status>[/color]")
			return true
		action = tokens[1].to_lower()
	else:
		if tokens.size() < 2:
			main._append_log("[color=orange]Usage: @dig <asset_id> [acquire|release|renew][/color]")
			return true
		asset_id = tokens[1].strip_edges()
		if tokens.size() >= 3:
			action = tokens[2].to_lower()
		if asset_id == "":
			main._append_log("[color=orange]Usage: @dig <asset_id> [acquire|release|renew][/color]")
			return true

	if action == "acquire":
		main._network_telemetry["lines_sent"] = int(main._network_telemetry.get("lines_sent", 0)) + 1
		main.network_lifecycle._active_client_send_line(JSON.stringify(main.parser.build_lock_acquire_envelope(asset_id, main._session_id)))
		main._append_log("[b]> %s[/b]" % cmd)
		main.network_lifecycle._refresh_network_labels()
		return true
	if action == "release":
		main._network_telemetry["lines_sent"] = int(main._network_telemetry.get("lines_sent", 0)) + 1
		main.network_lifecycle._active_client_send_line(JSON.stringify(main.parser.build_lock_release_envelope(asset_id, main._session_id)))
		main._append_log("[b]> %s[/b]" % cmd)
		main.network_lifecycle._refresh_network_labels()
		return true
	if action == "renew":
		main._network_telemetry["lines_sent"] = int(main._network_telemetry.get("lines_sent", 0)) + 1
		main.network_lifecycle._active_client_send_line(JSON.stringify(main.parser.build_lock_renew_envelope(asset_id, main._session_id)))
		main._append_log("[b]> %s[/b]" % cmd)
		main.network_lifecycle._refresh_network_labels()
		return true
	if action == "status":
		_request_lock_status()
		main._append_log("[b]> %s[/b]" % cmd)
		return true
	main._append_log("[color=orange]Unknown lock action '%s'. Use acquire, release, renew, or status.[/color]" % action)
	return true
