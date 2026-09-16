# scripts/ui/main/finite_adventure_ui.gd
# FiniteAdventureUiController: extracted from main_controller.gd as part of the P8
# file-splitting pass. main.tscn is untouched -- this holds a reference
# back to the Main control (`main`) and reaches its @onready nodes and
# shared state through it, since GDScript keeps one script per node.
extends RefCounted
class_name FiniteAdventureUiController

var main: MainController

func _init(main_ref: MainController) -> void:
	main = main_ref

func _handle_finite_adventure_state_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var previous_state: Dictionary = main._finite_adventure_state.duplicate(true)
	main._finite_adventure_state = (payload as Dictionary).duplicate(true)
	_maybe_log_finite_adventure_state_change(previous_state, main._finite_adventure_state)
	_refresh_finite_adventure_panel()

func _handle_finite_adventure_summary_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var previous_summary: Dictionary = main._finite_adventure_summary.duplicate(true)
	main._finite_adventure_summary = (payload as Dictionary).duplicate(true)
	_maybe_log_finite_adventure_summary_change(previous_summary, main._finite_adventure_summary)
	_refresh_finite_adventure_panel()

func _handle_finite_adventure_report_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	main._finite_adventure_report = (payload as Dictionary).duplicate(true)
	if bool(main._finite_adventure_report.get("available", false)):
		var format_name: String = str(main._finite_adventure_report.get("format", "text"))
		var file_hint: String = str(main._finite_adventure_report.get("file_name_hint", "")).strip_edges()
		main._append_log("[color=aqua]Adventure report ready: %s%s[/color]" % [
			format_name,
			(" (%s)" % file_hint) if file_hint != "" else ""
		])
	_refresh_finite_adventure_panel()

func _handle_finite_adventure_catalog_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = (payload as Dictionary).duplicate(true)
	var entries_value: Variant = body.get("campaigns", [])
	main._finite_adventure_catalog.clear()
	if typeof(entries_value) == TYPE_ARRAY:
		for entry_value in entries_value as Array:
			if typeof(entry_value) == TYPE_DICTIONARY:
				main._finite_adventure_catalog.append((entry_value as Dictionary).duplicate(true))
	main._finite_adventure_catalog_requested = true
	_refresh_finite_adventure_catalog_picker()
	var count: int = main._finite_adventure_catalog.size()
	var default_campaign_id: String = str(body.get("default_campaign_id", "")).strip_edges()
	var suffix: String = ""
	if default_campaign_id != "":
		suffix = " Default: %s." % default_campaign_id
	main._append_log("[color=aqua]Adventure catalog loaded: %d campaign(s).%s[/color]" % [count, suffix])
	_refresh_finite_adventure_panel()

func _refresh_finite_adventure_panel() -> void:
	main.adventure_title_label.text = "Adventure"
	if main._finite_adventure_state.is_empty():
		main.adventure_state_label.text = "Run: unavailable"
	else:
		var enabled: bool = bool(main._finite_adventure_state.get("enabled", false))
		var status: String = str(main._finite_adventure_state.get("status", "not_started"))
		var campaign_id: String = str(main._finite_adventure_state.get("campaign_id", "")).strip_edges()
		var default_campaign_id: String = str(main._finite_adventure_state.get("default_campaign_id", "")).strip_edges()
		var current_node: String = str(main._finite_adventure_state.get("current_node", "")).strip_edges()
		var checkpoint_available: bool = bool(main._finite_adventure_state.get("checkpoint_available", false))
		var checkpoint_node: String = str(main._finite_adventure_state.get("checkpoint_node", "")).strip_edges()
		var replay_supported: bool = bool(main._finite_adventure_state.get("replay_supported", false))
		var run_label: String = "enabled" if enabled else "disabled"
		var parts: PackedStringArray = PackedStringArray()
		parts.append("Run: %s" % run_label)
		parts.append("status=%s" % status)
		if campaign_id != "":
			parts.append("campaign=%s" % campaign_id)
		elif default_campaign_id != "":
			parts.append("default=%s" % default_campaign_id)
		if current_node != "":
			parts.append("node=%s" % current_node)
		parts.append("checkpoint=%s" % ("yes" if checkpoint_available else "no"))
		if checkpoint_available and checkpoint_node != "":
			parts.append("restore=%s" % checkpoint_node)
		parts.append("replay=%s" % ("yes" if replay_supported else "no"))
		if not main._finite_adventure_catalog.is_empty():
			parts.append("catalog=%d" % main._finite_adventure_catalog.size())
		main.adventure_state_label.text = "  ".join(parts)
		if default_campaign_id != "" and main.adventure_campaign_input.text.strip_edges() == "":
			main.adventure_campaign_input.placeholder_text = "Campaign id (%s)" % default_campaign_id
		else:
			main.adventure_campaign_input.placeholder_text = "Campaign id (optional)"

	if main._finite_adventure_summary.is_empty() or not bool(main._finite_adventure_summary.get("available", false)):
		main.adventure_summary_label.text = "Summary: unavailable"
	else:
		var campaign_name: String = str(main._finite_adventure_summary.get("campaign_name", "")).strip_edges()
		if campaign_name == "":
			campaign_name = str(main._finite_adventure_summary.get("campaign_id", "(unknown)"))
		var status_text: String = str(main._finite_adventure_summary.get("status", ""))
		var outcome: String = str(main._finite_adventure_summary.get("outcome", ""))
		var player_name: String = str(main._finite_adventure_summary.get("player_name", "")).strip_edges()
		var duration_value: Variant = main._finite_adventure_summary.get("duration_seconds", null)
		var duration_text: String = "--"
		if typeof(duration_value) == TYPE_FLOAT or typeof(duration_value) == TYPE_INT:
			duration_text = "%.1fs" % float(duration_value)
		main.adventure_summary_label.text = "Summary: %s  %s/%s  player=%s  duration=%s" % [
			campaign_name,
			status_text,
			outcome,
			player_name if player_name != "" else "--",
			duration_text
		]

	if main._finite_adventure_catalog.is_empty():
		main.adventure_catalog_label.text = "Campaigns: unavailable"
	else:
		var selected_campaign_id: String = _selected_finite_adventure_catalog_campaign_id()
		var catalog_parts: PackedStringArray = []
		catalog_parts.append("Campaigns: %d" % main._finite_adventure_catalog.size())
		if selected_campaign_id != "":
			var selected_entry: Dictionary = _finite_adventure_catalog_entry(selected_campaign_id)
			var selected_name: String = str(selected_entry.get("name", selected_campaign_id)).strip_edges()
			var selected_desc: String = str(selected_entry.get("description", "")).strip_edges()
			catalog_parts.append("selected=%s" % selected_name)
			if selected_desc != "":
				catalog_parts.append(selected_desc)
		main.adventure_catalog_label.text = "  ".join(catalog_parts)

	main.adventure_objective_label.text = _render_finite_adventure_objective_bbcode()

	if main._finite_adventure_report.is_empty() or not bool(main._finite_adventure_report.get("available", false)):
		main.adventure_report_label.text = "[i]No adventure report yet.[/i]"
	else:
		var format_name: String = str(main._finite_adventure_report.get("format", "text"))
		var file_hint: String = str(main._finite_adventure_report.get("file_name_hint", "")).strip_edges()
		var content: String = main._bbcode_escape(str(main._finite_adventure_report.get("content", "")).strip_edges())
		var header: String = "[b]Report[/b] %s (%s)" % [format_name, file_hint if file_hint != "" else "--"]
		if format_name == "json" or format_name == "markdown":
			main.adventure_report_label.text = "%s\n[code]%s[/code]" % [header, content]
		else:
			main.adventure_report_label.text = "%s\n%s" % [header, content]
	_refresh_finite_adventure_actions()

func _refresh_finite_adventure_actions() -> void:
	var enabled: bool = bool(main._finite_adventure_state.get("enabled", false))
	var status: String = str(main._finite_adventure_state.get("status", "not_started"))
	var checkpoint_available: bool = bool(main._finite_adventure_state.get("checkpoint_available", false))
	var replay_supported: bool = bool(main._finite_adventure_state.get("replay_supported", false))
	var selected_catalog_campaign: String = _selected_finite_adventure_catalog_campaign_id()
	var has_campaign: bool = str(main._finite_adventure_state.get("campaign_id", "")).strip_edges() != "" or str(main._finite_adventure_state.get("default_campaign_id", "")).strip_edges() != "" or selected_catalog_campaign != "" or main.adventure_campaign_input.text.strip_edges() != ""
	var has_summary: bool = bool(main._finite_adventure_summary.get("available", false))
	var active: bool = status == "active"
	var can_resume_from_summary: bool = status == "completed" or status == "abandoned" or status == "not_started"

	main.adventure_catalog_select.disabled = (not enabled) or active or main.adventure_catalog_select.item_count <= 1
	main.adventure_catalog_button.disabled = not enabled
	main.adventure_campaign_input.editable = enabled and not active
	main.adventure_start_button.disabled = (not enabled) or active or (not has_campaign)
	main.adventure_status_button.disabled = not enabled
	main.adventure_abandon_button.disabled = (not enabled) or (not active)
	main.adventure_checkpoint_button.disabled = (not enabled) or (not active)
	main.adventure_restore_button.disabled = (not enabled) or (not checkpoint_available)
	main.adventure_reset_button.disabled = (not enabled) or active or (not has_campaign)
	main.adventure_replay_button.disabled = (not enabled) or (not replay_supported) or (not can_resume_from_summary) or (not has_campaign)
	main.adventure_summary_text_button.disabled = (not enabled) or (not has_summary)
	main.adventure_summary_md_button.disabled = (not enabled) or (not has_summary)
	main.adventure_summary_json_button.disabled = (not enabled) or (not has_summary)

func _on_adventure_start_pressed() -> void:
	var campaign_id: String = main.adventure_campaign_input.text.strip_edges()
	if campaign_id == "":
		campaign_id = _selected_finite_adventure_catalog_campaign_id()
	if campaign_id == "":
		campaign_id = str(main._finite_adventure_state.get("default_campaign_id", "")).strip_edges()
	if campaign_id == "":
		_send_adventure_command("adventure start")
		return
	_send_adventure_command("adventure start %s" % campaign_id)
	main.adventure_campaign_input.text = ""

func _request_finite_adventure_catalog() -> void:
	if not main._is_connected_to_game_server():
		return
	main._finite_adventure_catalog_requested = true
	_send_adventure_command("adventure list")

func _refresh_finite_adventure_catalog_picker() -> void:
	var current_selected_id: String = _selected_finite_adventure_catalog_campaign_id()
	main.adventure_catalog_select.clear()
	main.adventure_catalog_select.add_item("(choose campaign)")
	main.adventure_catalog_select.set_item_metadata(0, "")
	var selected_index: int = 0
	for entry in main._finite_adventure_catalog:
		if typeof(entry) != TYPE_DICTIONARY:
			continue
		var body: Dictionary = entry as Dictionary
		var campaign_id: String = str(body.get("campaign_id", "")).strip_edges()
		var campaign_name: String = str(body.get("name", campaign_id)).strip_edges()
		var is_default: bool = bool(body.get("is_default", false))
		var label: String = campaign_name
		if campaign_id != "" and campaign_id != campaign_name:
			label = "%s (%s)" % [campaign_name, campaign_id]
		if is_default:
			label += " [default]"
		main.adventure_catalog_select.add_item(label)
		var item_index: int = main.adventure_catalog_select.item_count - 1
		main.adventure_catalog_select.set_item_metadata(item_index, campaign_id)
		if current_selected_id != "" and campaign_id == current_selected_id:
			selected_index = item_index
		elif current_selected_id == "" and is_default:
			selected_index = item_index
	main.adventure_catalog_select.select(selected_index)

func _finite_adventure_catalog_entry(campaign_id: String) -> Dictionary:
	var wanted: String = campaign_id.strip_edges()
	if wanted == "":
		return {}
	for entry in main._finite_adventure_catalog:
		if typeof(entry) != TYPE_DICTIONARY:
			continue
		var body: Dictionary = entry as Dictionary
		if str(body.get("campaign_id", "")).strip_edges() == wanted:
			return body
	return {}

func _selected_finite_adventure_catalog_campaign_id() -> String:
	var idx: int = main.adventure_catalog_select.get_selected()
	if idx < 0:
		return ""
	return str(main.adventure_catalog_select.get_item_metadata(idx)).strip_edges()

func _on_adventure_catalog_selected(index: int) -> void:
	if index < 0:
		return
	var campaign_id: String = str(main.adventure_catalog_select.get_item_metadata(index)).strip_edges()
	if campaign_id != "":
		main.adventure_campaign_input.text = campaign_id
	_refresh_finite_adventure_panel()

func _render_finite_adventure_objective_bbcode() -> String:
	var status: String = str(main._finite_adventure_state.get("status", "not_started"))
	if status != "active":
		if status == "completed":
			return "[color=green]Adventure complete. Review summary or replay when ready.[/color]"
		if status == "abandoned":
			return "[color=yellow]Adventure abandoned. You can restore, reset, or replay.[/color]"
		return "[i]No active adventure objective.[/i]"

	var active_value: Variant = main._latest_quests_payload.get("active", [])
	if typeof(active_value) != TYPE_ARRAY or (active_value as Array).is_empty():
		var current_node: String = str(main._finite_adventure_state.get("current_node", "")).strip_edges()
		if current_node != "":
			return "[color=aqua]Adventure active at node '%s'. Quest details pending.[/color]" % main._bbcode_escape(current_node)
		return "[color=aqua]Adventure active. Awaiting quest/objective details.[/color]"

	var first_variant: Variant = (active_value as Array)[0]
	if typeof(first_variant) != TYPE_DICTIONARY:
		return "[color=aqua]Adventure active. Objective data unavailable.[/color]"

	var quest: Dictionary = first_variant as Dictionary
	var title: String = main._bbcode_escape(str(quest.get("title", "Unnamed Quest")))
	var state_text: String = main._bbcode_escape(str(quest.get("state", "unknown")))
	var stage_text: String = ""
	var stages_value: Variant = quest.get("stages", [])
	if typeof(stages_value) == TYPE_ARRAY:
		for stage_variant in stages_value as Array:
			if typeof(stage_variant) != TYPE_DICTIONARY:
				continue
			var stage: Dictionary = stage_variant as Dictionary
			var stage_state: String = str(stage.get("state", "")).strip_edges().to_lower()
			if stage_state in ["active", "ready_to_complete", ""]:
				var description: String = str(stage.get("description", "")).strip_edges()
				if description != "":
					stage_text = main._bbcode_escape(description)
					break
	var parts: PackedStringArray = []
	parts.append("[b]Active Objective[/b]: %s [%s]" % [title, state_text])
	if stage_text != "":
		parts.append(stage_text)
	var current_node: String = str(main._finite_adventure_state.get("current_node", "")).strip_edges()
	if current_node != "":
		parts.append("[color=gray]Campaign node: %s[/color]" % main._bbcode_escape(current_node))
	return "\n".join(parts)

func _maybe_log_finite_adventure_state_change(previous_state: Dictionary, next_state: Dictionary) -> void:
	var previous_status: String = str(previous_state.get("status", "not_started"))
	var next_status: String = str(next_state.get("status", "not_started"))
	var previous_campaign: String = str(previous_state.get("campaign_id", "")).strip_edges()
	var next_campaign: String = str(next_state.get("campaign_id", "")).strip_edges()
	if previous_state.is_empty() and next_state.is_empty():
		return
	if previous_status != next_status or previous_campaign != next_campaign:
		var campaign_label: String = next_campaign if next_campaign != "" else str(next_state.get("default_campaign_id", "")).strip_edges()
		if campaign_label == "":
			campaign_label = "(unspecified)"
		match next_status:
			"active":
				main._append_log("[color=green]Adventure started: %s[/color]" % campaign_label)
			"completed":
				main._append_log("[color=green]Adventure completed: %s[/color]" % campaign_label)
			"abandoned":
				main._append_log("[color=yellow]Adventure abandoned: %s[/color]" % campaign_label)
			"not_started":
				if not previous_state.is_empty():
					main._append_log("[color=aqua]Adventure reset to ready state.[/color]")
			_:
				main._append_log("[color=aqua]Adventure status: %s (%s)[/color]" % [next_status, campaign_label])

	var previous_checkpoint: bool = bool(previous_state.get("checkpoint_available", false))
	var next_checkpoint: bool = bool(next_state.get("checkpoint_available", false))
	if not previous_checkpoint and next_checkpoint:
		var checkpoint_node: String = str(next_state.get("checkpoint_node", "")).strip_edges()
		if checkpoint_node == "":
			main._append_log("[color=aqua]Adventure checkpoint saved.[/color]")
		else:
			main._append_log("[color=aqua]Adventure checkpoint saved at %s.[/color]" % checkpoint_node)

func _maybe_log_finite_adventure_summary_change(previous_summary: Dictionary, next_summary: Dictionary) -> void:
	var previous_available: bool = bool(previous_summary.get("available", false))
	var next_available: bool = bool(next_summary.get("available", false))
	if not next_available:
		return
	var previous_status: String = str(previous_summary.get("status", ""))
	var next_status: String = str(next_summary.get("status", ""))
	var previous_outcome: String = str(previous_summary.get("outcome", ""))
	var next_outcome: String = str(next_summary.get("outcome", ""))
	if (not previous_available) or previous_status != next_status or previous_outcome != next_outcome:
		var campaign_name: String = str(next_summary.get("campaign_name", "")).strip_edges()
		if campaign_name == "":
			campaign_name = str(next_summary.get("campaign_id", "(unknown)"))
		main._append_log("[color=aqua]Adventure summary updated: %s (%s/%s)[/color]" % [
			campaign_name,
			next_status if next_status != "" else "--",
			next_outcome if next_outcome != "" else "--"
		])

func _send_adventure_command(command: String) -> void:
	main.network_lifecycle._send_command_immediate(command)
