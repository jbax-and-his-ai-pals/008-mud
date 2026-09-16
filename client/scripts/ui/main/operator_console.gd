# scripts/ui/main/operator_console.gd
# OperatorConsoleController: extracted from main_controller.gd as part of the P8
# file-splitting pass. main.tscn is untouched -- this holds a reference
# back to the Main control (`main`) and reaches its @onready nodes and
# shared state through it, since GDScript keeps one script per node.
extends RefCounted
class_name OperatorConsoleController

var main: MainController

func _init(main_ref: MainController) -> void:
	main = main_ref

func _operator_selected_domain() -> String:
	var selected_idx: int = main.operator_domain_select.get_selected()
	if selected_idx < 0:
		return "Policy"
	return main.operator_domain_select.get_item_text(selected_idx)

func _refresh_operator_actions() -> void:
	var domain: String = _operator_selected_domain()
	var actions_variant: Variant = main._operator_action_maps.get(domain, [])
	var actions: Array = actions_variant as Array
	main.operator_action_select.clear()
	for action_variant in actions:
		main.operator_action_select.add_item(str(action_variant))
	main.operator_action_select.disabled = actions.is_empty()
	if not actions.is_empty():
		main.operator_action_select.select(0)
	_refresh_operator_values()
	_update_operator_palette_state()

func _operator_selected_action() -> String:
	var selected_idx: int = main.operator_action_select.get_selected()
	if selected_idx >= 0 and selected_idx < main.operator_action_select.get_item_count():
		return main.operator_action_select.get_item_text(selected_idx)
	return ""

func _operator_catalog_key(domain: String, action: String) -> String:
	return "%s:%s" % [domain, action]

func _operator_requirements_for(domain: String, action: String) -> Dictionary:
	var requirements_value: Variant = main._operator_catalog_requirements.get(_operator_catalog_key(domain, action), {})
	if typeof(requirements_value) == TYPE_DICTIONARY:
		return requirements_value as Dictionary
	return {}

func _session_has_entitlement(entitlement_name: String) -> bool:
	var wanted: String = entitlement_name.strip_edges()
	if wanted == "":
		return true
	if not main._session_entitlements_known:
		return true
	for entitlement in main._session_entitlements:
		if str(entitlement) == wanted:
			return true
	return false

func _refresh_operator_values() -> void:
	var domain: String = _operator_selected_domain()
	var action: String = _operator_selected_action()
	main.operator_value_select.clear()
	var catalog_key: String = _operator_catalog_key(domain, action)
	var server_options_value: Variant = main._operator_catalog_value_options.get(catalog_key, [])
	var used_server_options: bool = false
	if typeof(server_options_value) == TYPE_ARRAY:
		for option_variant in server_options_value as Array:
			var option_name: String = str(option_variant).strip_edges()
			if option_name != "":
				main.operator_value_select.add_item(option_name)
				used_server_options = true
	if not used_server_options and domain == "Profiles" and action == "Apply Selected":
		for preset_name: String in main._known_profile_presets:
			main.operator_value_select.add_item(preset_name)
	elif not used_server_options and domain == "World Effects" and action == "Use Provider":
		var providers_value: Variant = main._world_effects_status.get("available_providers", [])
		if typeof(providers_value) == TYPE_ARRAY:
			for provider_variant in providers_value as Array:
				var provider_name: String = str(provider_variant).strip_edges()
				if provider_name != "":
					main.operator_value_select.add_item(provider_name)
	main.operator_value_select.disabled = main.operator_value_select.get_item_count() == 0
	if main.operator_value_select.get_item_count() > 0:
		main.operator_value_select.select(0)

func _update_operator_palette_state() -> void:
	var connected: bool = main._is_connected_to_game_server()
	var domain: String = _operator_selected_domain()
	var selected_action: String = _operator_selected_action()
	var requires_connected: bool = selected_action != ""
	var requirements: Dictionary = _operator_requirements_for(domain, selected_action)
	var gm_required: bool = bool(requirements.get("requires_gm", false))
	var required_entitlement: String = str(requirements.get("requires_entitlement", "")).strip_edges()
	var can_run: bool = connected and requires_connected
	if gm_required and not main._gm_granted:
		can_run = false
	if required_entitlement != "" and not _session_has_entitlement(required_entitlement):
		can_run = false
	main.operator_run_button.disabled = not can_run
	main.operator_arg_input.editable = connected
	var hint: String = "Operator: choose domain/action, then Run."
	if not connected:
		hint = "Operator: connect first."
	elif gm_required and not main._gm_granted:
		hint = "Operator: GM session required for this action."
	elif required_entitlement != "" and not main._session_entitlements_known:
		hint = "Operator: entitlement state not published yet; action may still be denied by server."
	elif required_entitlement != "" and not _session_has_entitlement(required_entitlement):
		hint = "Operator: missing entitlement '%s' for this action." % required_entitlement
	elif domain == "World Effects" and selected_action == "Use Provider":
		hint = "Operator: choose provider from list (or type override), then Run."
	elif domain == "Profiles" and selected_action == "Apply Selected":
		hint = "Operator: choose preset from list (or type override), then Run."
	main.operator_status_label.text = hint

func _on_operator_domain_selected(_index: int) -> void:
	_refresh_operator_actions()

func _on_operator_action_selected(_index: int) -> void:
	_refresh_operator_values()
	_update_operator_palette_state()

func _operator_selected_value() -> String:
	var idx: int = main.operator_value_select.get_selected()
	if idx >= 0 and idx < main.operator_value_select.get_item_count():
		return main.operator_value_select.get_item_text(idx).strip_edges()
	return ""

func _on_operator_run_pressed() -> void:
	var domain: String = _operator_selected_domain()
	var action: String = _operator_selected_action()
	if action == "":
		return
	var requirements: Dictionary = _operator_requirements_for(domain, action)
	if bool(requirements.get("requires_gm", false)) and not main._gm_granted:
		main._append_log("[color=orange]GM session required for this operator action.[/color]")
		_update_operator_palette_state()
		return
	var required_entitlement: String = str(requirements.get("requires_entitlement", "")).strip_edges()
	if required_entitlement != "" and not _session_has_entitlement(required_entitlement):
		main._append_log("[color=orange]Missing entitlement for this operator action: %s[/color]" % required_entitlement)
		_update_operator_palette_state()
		return
	var arg: String = main.operator_arg_input.text.strip_edges()
	var picked_value: String = _operator_selected_value()
	if domain == "Policy":
		main.network_lifecycle._send_command_immediate("server policy")
	elif domain == "Profiles":
		if action == "List Profiles":
			main.profiles._request_profile_presets()
		elif action == "Apply Selected":
			var selected_preset: String = arg if arg != "" else picked_value
			if selected_preset != "":
				main._pending_profile_apply_preset = selected_preset
			main.profiles._on_profile_apply_pressed()
	elif domain == "World Effects":
		if action == "Providers":
			main.network_lifecycle._send_command_immediate("effects providers")
		elif action == "Status":
			main.network_lifecycle._send_command_immediate("effects status")
		elif action == "Use Provider":
			var provider_id: String = arg if arg != "" else picked_value
			if provider_id == "":
				main._append_log("[color=orange]Provide provider id in operator arg input first.[/color]")
				return
			main.network_lifecycle._send_command_immediate("effects use %s" % provider_id)
	elif domain == "Auth":
		if action == "GM Status":
			main.network_lifecycle._send_command_immediate("gm status")
		elif action == "GM Deauth":
			main.network_lifecycle._send_command_immediate("gm deauth")
		elif action == "GM Auth":
			var token: String = arg
			if token == "":
				token = main.gm_auth_input.text.strip_edges()
			if token == "":
				main._append_log("[color=orange]Provide GM token in arg input or GM token field first.[/color]")
				return
			main.network_lifecycle._send_command_to_server("gm auth %s" % token, "gm auth ********")
	elif domain == "Authoring":
		if action == "Lock Status":
			main.authoring_locks._request_lock_status()
		elif action == "Acquire Lock":
			main.authoring_locks._on_authoring_acquire_pressed()
		elif action == "Renew Lock":
			main.authoring_locks._on_authoring_renew_pressed()
		elif action == "Release Lock":
			main.authoring_locks._on_authoring_release_pressed()
		elif action == "Edit Next":
			main.authoring_locks._on_authoring_edit_pressed()
		elif action == "Edit Stale":
			main.authoring_locks._on_authoring_edit_stale_pressed()
	_update_operator_palette_state()

func _apply_operator_catalog_payload(catalog: Dictionary) -> void:
	var domains_value: Variant = catalog.get("domains", {})
	if typeof(domains_value) == TYPE_DICTIONARY:
		var domains_dict: Dictionary = domains_value as Dictionary
		var remapped: Dictionary = {}
		for key_variant in domains_dict.keys():
			var domain_key: String = str(key_variant)
			var actions_value: Variant = domains_dict.get(key_variant, [])
			var actions: Array = []
			if typeof(actions_value) == TYPE_ARRAY:
				for action_variant in actions_value as Array:
					actions.append(str(action_variant))
			remapped[domain_key] = actions
		if not remapped.is_empty():
			main._operator_action_maps = remapped
	var value_options_value: Variant = catalog.get("value_options", {})
	if typeof(value_options_value) == TYPE_DICTIONARY:
		main._operator_catalog_value_options = (value_options_value as Dictionary).duplicate(true)
	var requirements_value: Variant = catalog.get("requirements", {})
	if typeof(requirements_value) == TYPE_DICTIONARY:
		main._operator_catalog_requirements = (requirements_value as Dictionary).duplicate(true)
	else:
		main._operator_catalog_requirements = {}
	_refresh_operator_actions()
