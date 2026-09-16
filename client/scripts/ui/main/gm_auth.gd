# scripts/ui/main/gm_auth.gd
# GmAuthController: extracted from main_controller.gd as part of the P8
# file-splitting pass. main.tscn is untouched -- this holds a reference
# back to the Main control (`main`) and reaches its @onready nodes and
# shared state through it, since GDScript keeps one script per node.
extends RefCounted
class_name GmAuthController

var main: MainController

func _init(main_ref: MainController) -> void:
	main = main_ref

func _on_gm_auth_pressed() -> void:
	var token: String = main.gm_auth_input.text.strip_edges()
	if token == "":
		main._append_log("[color=orange]Enter a GM token first.[/color]")
		return
	main.network_lifecycle._send_command_to_server("gm auth %s" % token, "gm auth ********")
	main.gm_auth_input.text = ""

func _maybe_handle_local_gm_command(cmd: String) -> bool:
	var normalized: String = cmd.strip_edges().to_lower()
	if normalized == "gm help":
		main._append_log("[color=aqua]GM commands:[/color]")
		main._append_log("[color=aqua]  gm auth <token>[/color]")
		main._append_log("[color=aqua]  gm status[/color]")
		main._append_log("[color=aqua]  gm deauth[/color]")
		main._append_log("[color=aqua]Tip: token input is redacted in the local log.[/color]")
		return true
	if normalized == "gm status":
		main.network_lifecycle._send_command_to_server("gm status")
		return true
	if normalized == "gm deauth":
		main.network_lifecycle._send_command_to_server("gm deauth")
		return true
	if normalized == "gm auth":
		main._append_log("[color=orange]Usage: gm auth <token>[/color]")
		return true
	if normalized.begins_with("gm auth "):
		var token: String = cmd.strip_edges().substr(8).strip_edges()
		if token == "":
			main._append_log("[color=orange]Usage: gm auth <token>[/color]")
			return true
		main.network_lifecycle._send_command_to_server("gm auth %s" % token, "gm auth ********")
		return true
	return false

func _handle_auth_state_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	main._gm_granted = bool(body.get("gm_granted", false))
	main._gm_auth_configured = bool(body.get("gm_auth_configured", false))
	main._gm_auth_cooldown_seconds = int(body.get("gm_auth_cooldown_seconds", 0))
	main._session_entitlements = PackedStringArray()
	main._session_entitlements_known = false
	var entitlements_value: Variant = body.get("session_entitlements", null)
	if typeof(entitlements_value) == TYPE_ARRAY:
		main._session_entitlements_known = true
		for entitlement_variant: Variant in entitlements_value as Array:
			var entitlement_name: String = str(entitlement_variant).strip_edges()
			if entitlement_name != "":
				main._session_entitlements.append(entitlement_name)
	var authoring_mode: String = str(body.get("authoring_mode", str(main._server_profile_modes.get("authoring", "unknown"))))
	main.server_policy_auth_label.text = "Auth: GM %s  Configured %s  Cooldown %ds" % [
		("yes" if main._gm_granted else "no"),
		("yes" if main._gm_auth_configured else "no"),
		max(0, main._gm_auth_cooldown_seconds)
	]
	var status: String = "GM session: %s | auth configured: %s | authoring mode: %s" % [
		("yes" if main._gm_granted else "no"),
		("yes" if main._gm_auth_configured else "no"),
		authoring_mode
	]
	if main._gm_auth_cooldown_seconds > 0:
		status += " | cooldown: %ds" % main._gm_auth_cooldown_seconds
	main._refresh_policy_affordances()
	main._append_log("[color=aqua]%s[/color]" % status)
