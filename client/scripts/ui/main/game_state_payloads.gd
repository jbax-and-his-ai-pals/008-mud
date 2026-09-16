# scripts/ui/main/game_state_payloads.gd
# GameStatePayloadsController: extracted from main_controller.gd as part of the P8
# file-splitting pass. main.tscn is untouched -- this holds a reference
# back to the Main control (`main`) and reaches its @onready nodes and
# shared state through it, since GDScript keeps one script per node.
extends RefCounted
class_name GameStatePayloadsController

var main: MainController

func _init(main_ref: MainController) -> void:
	main = main_ref

func _handle_asset_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		main._append_log("[color=red]Invalid asset payload[/color]")
		return

	var body: Dictionary = payload as Dictionary
	if not body.has("asset_id") or not body.has("revision") or not body.has("checksum_sha256"):
		main._append_log("[color=red]Asset payload missing required metadata.[/color]")
		return

	var asset_type: String = str(body.get("asset_type", ""))
	if asset_type != "svg_1bit":
		main._append_log("[color=yellow]Unsupported asset type: %s[/color]" % asset_type)
		return

	var alt_text: String = str(body.get("alt_text", "Decorative image"))
	var asset_id: String = str(body.get("asset_id", ""))
	main._asset_revisions[asset_id] = int(body.get("revision", 0))
	main.authoring_locks._refresh_authoring_status(asset_id)
	main.asset_alt_text.text = alt_text
	if bool(main._client_capabilities.get("screen_reader_mode", false)):
		main.asset_texture.texture = null
		main._append_log("[color=yellow]Screen-reader mode: showing alt text only.[/color]")
		return

	var svg_text: String = str(body.get("svg", ""))
	var checksum: String = str(body.get("checksum_sha256", ""))
	if checksum != main._sha256_hex(svg_text):
		main.asset_texture.texture = null
		main._append_log("[color=red]Asset checksum mismatch.[/color]")
		return

	var violations := main.svg_renderer._validate_svg_1bit(svg_text)
	if violations.size() > 0:
		for v in violations:
			main._append_log("[color=orange]SVG 1-bit policy violation: %s[/color]" % v)
		main.asset_texture.texture = null
		main._append_log("[color=red]Rejected SVG asset due to 1-bit policy violations.[/color]")
		return

	var texture: Texture2D = main.svg_renderer.render_svg_texture(svg_text, Vector2i(160, 160))
	if texture == null:
		main.asset_texture.texture = null
		main._append_log("[color=red]Failed to render SVG asset.[/color]")
		return
	main.asset_texture.texture = texture
	main._append_log("[color=aqua]Rendered SVG asset (%s r%s).[/color]" % [str(body.get("asset_id", "unknown")), str(body.get("revision", "?"))])

func _handle_world_state_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	if str(body.get("system", "")) not in ["blight", "world_field", "world_effects"]:
		return

	var cells_variant: Variant = body.get("cells", [])
	if typeof(cells_variant) != TYPE_ARRAY:
		return
	var cells: Array = cells_variant as Array
	var summary: String = _summarize_field_cells(cells)
	var field_id: String = str(body.get("field_id", "blight"))
	var polarity: String = str(body.get("polarity", "negative"))
	main._world_effects_cells_preview[field_id] = summary
	main.atmosphere_layer.apply_world_state(field_id, polarity, cells)
	_render_world_effects_panel()
	main._append_log("[color=teal]World state updated: %s (%s) %s[/color]" % [field_id, polarity, summary])

func _handle_world_effects_status_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	main._world_effects_status = (payload as Dictionary).duplicate(true)
	var providers_value: Variant = main._world_effects_status.get("available_providers", [])
	if typeof(providers_value) == TYPE_ARRAY:
		main._operator_catalog_value_options["World Effects:Use Provider"] = (providers_value as Array).duplicate()
	_render_world_effects_panel()
	main.operator_console._refresh_operator_values()
	main.operator_console._update_operator_palette_state()

func _handle_world_effects_providers_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	main._world_effects_status = (payload as Dictionary).duplicate(true)
	var providers_value: Variant = main._world_effects_status.get("available_providers", [])
	if typeof(providers_value) == TYPE_ARRAY:
		main._operator_catalog_value_options["World Effects:Use Provider"] = (providers_value as Array).duplicate()
	if typeof(providers_value) == TYPE_ARRAY:
		var providers: Array = providers_value as Array
		var names: PackedStringArray = PackedStringArray()
		for p in providers:
			names.append(str(p))
		main._append_log("[color=aqua]World-effects providers: %s[/color]" % ", ".join(names))
	_render_world_effects_panel()
	main.operator_console._refresh_operator_values()
	main.operator_console._update_operator_palette_state()

func _render_world_effects_panel() -> void:
	var lines: PackedStringArray = PackedStringArray()
	var mode: String = str(main._world_effects_status.get("mode", "unknown"))
	var provider: String = str(main._world_effects_status.get("active_provider", "unknown"))
	lines.append("Mode=%s  Provider=%s" % [mode, provider])
	var keys: Array = main._world_effects_cells_preview.keys()
	keys.sort()
	for key_variant in keys:
		var key: String = str(key_variant)
		lines.append("%s: %s" % [key, str(main._world_effects_cells_preview.get(key, "no cells"))])
	main.world_state_label.text = "\n".join(lines)

func _handle_status_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	var name: String = str(body.get("name", "Player"))
	var identity_parts: PackedStringArray = PackedStringArray([name])
	if main._game_status_field_enabled("level") and body.has("level"):
		identity_parts.append("Level %d" % int(body.get("level", 0)))
	if main._game_status_field_enabled("experience") and body.has("experience"):
		identity_parts.append("XP %d" % int(body.get("experience", 0)))
	main.status_primary_label.text = "  ".join(identity_parts)

	var health: Dictionary = body.get("health", {}) as Dictionary
	var hp_cur: int = int(health.get("current", 0))
	var hp_max: int = int(health.get("max", 0))

	# Color-independent critical-state indicators.
	# These text markers communicate urgency without relying on color alone,
	# supporting high-contrast and screen-reader modes.
	var hp_prefix: String = ""
	var vital_parts: PackedStringArray = PackedStringArray(["%sHP %d/%d" % [hp_prefix, hp_cur, hp_max]])
	if hp_max > 0:
		if hp_cur <= 0:
			hp_prefix = "[DEAD] "
		elif float(hp_cur) / float(hp_max) < 0.25:
			hp_prefix = "[CRIT] "
	if main._game_status_field_enabled("mana") and body.has("mana"):
		var mana: Dictionary = body.get("mana", {}) as Dictionary
		var mp_cur: int = int(mana.get("current", 0))
		var mp_max: int = int(mana.get("max", 0))
		var mp_suffix: String = " [OOM]" if mp_max > 0 and mp_cur <= 0 else ""
		vital_parts.append("MP %d/%d%s" % [mp_cur, mp_max, mp_suffix])
	main.status_vitals_label.text = "  ".join(vital_parts)

	var effects: Array = body.get("effects", []) as Array
	if effects.is_empty():
		main.status_effects_label.text = "%s none" % main.theme_controller._icon_token("status_effect", "Effects:")
	else:
		var effect_names: PackedStringArray = []
		for effect_value in effects:
			effect_names.append(str(effect_value))
		main.status_effects_label.text = "%s %s" % [main.theme_controller._icon_token("status_effect", "Effects:"), ", ".join(effect_names)]

func _handle_combat_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	var active: bool = bool(body.get("active", false))
	main.combat_title_label.text = "Encounter" if active else "Encounter (clear)"
	if not active:
		main.combat_summary_label.text = "No active encounter."
		main.combat_targets_label.text = "[i]Explore carefully; hostile creatures will appear here.[/i]"
		return

	var targets: Array = body.get("targets", []) as Array
	var lines: PackedStringArray = []
	for target_value in targets:
		if typeof(target_value) != TYPE_DICTIONARY:
			continue
		var target: Dictionary = target_value as Dictionary
		var name: String = str(target.get("name", "Unknown target"))
		var current: String = " [b](target)[/b]" if bool(target.get("current_target", false)) else ""
		lines.append("• [url=cmd:attack %s]%s[/url]%s — HP %d/%d" % [name, main._bbcode_escape(name), current, int(target.get("health", 0)), int(target.get("max_health", 0))])

	var actions: Array = body.get("suggested_actions", []) as Array
	main.combat_summary_label.text = "Choose an action: %s" % ", ".join(actions)
	if not actions.is_empty():
		lines.append("[color=gray]Suggested: %s[/color]" % main._bbcode_escape(", ".join(actions)))
	var recent: Array = body.get("recent_actions", []) as Array
	if not recent.is_empty():
		lines.append("[color=gray]Recent: %s[/color]" % main._bbcode_escape(str(recent[recent.size() - 1])))
	main.combat_targets_label.text = "\n".join(lines) if not lines.is_empty() else "[i]No targets remain in sight.[/i]"

func _handle_inventory_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	var slots_used: int = int(body.get("slots_used", 0))
	var slots_max: int = int(body.get("slots_max", 0))
	var total_weight: float = main._to_float(body.get("total_weight", 0.0))
	var max_weight: float = main._to_float(body.get("max_weight", 0.0))
	main.inventory_summary_label.text = "Slots %d/%d  Weight %.1f/%.1f" % [slots_used, slots_max, total_weight, max_weight]

	var items_variant: Variant = body.get("items", [])
	if typeof(items_variant) != TYPE_ARRAY:
		main.inventory_list_label.text = "[i]%s[/i]" % main.theme_controller._icon_token("inventory_none", "No inventory data.")
		return

	var lines: PackedStringArray = []
	for equipped_value in body.get("equipped", []) as Array:
		if typeof(equipped_value) != TYPE_DICTIONARY:
			continue
		var equipped: Dictionary = equipped_value as Dictionary
		var equipped_attachments: Array = equipped.get("attachments", []) as Array
		var equipped_suffix: String = ""
		if not equipped_attachments.is_empty():
			equipped_suffix = " [color=cyan](%s)[/color]" % main._bbcode_escape(", ".join(equipped_attachments))
		lines.append("[color=gray]Equipped — %s:[/color] %s%s" % [
			main._bbcode_escape(str(equipped.get("slot", "slot")).replace("_", " ")),
			main._bbcode_escape(str(equipped.get("name", "Unknown item"))),
			equipped_suffix,
		])
	var items: Array = items_variant as Array
	for item_variant in items:
		if typeof(item_variant) != TYPE_DICTIONARY:
			continue
		var item: Dictionary = item_variant as Dictionary
		var item_name: String = str(item.get("name", "Unknown"))
		var attachment_suffix: String = ""
		var attachments: Array = item.get("attachments", []) as Array
		if not attachments.is_empty():
			attachment_suffix = " [color=cyan](%s)[/color]" % main._bbcode_escape(", ".join(attachments))
		lines.append(
			"%s %d: [url=cmd:look %s]%s[/url]%s x%d (%.1f wt)" % [
				main.theme_controller._icon_token("inventory_item_prefix", "-"),
				int(item.get("slot_index", -1)),
				item_name,
				item_name,
				attachment_suffix,
				int(item.get("quantity", 0)),
				main._to_float(item.get("weight_total", 0.0)),
			]
		)
	if lines.is_empty():
		main.inventory_list_label.text = "[i]%s[/i]" % main.theme_controller._icon_token("inventory_empty", "Inventory empty.")
		return
	main.inventory_list_label.text = "\n".join(lines)

func _handle_crafting_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	var stations: Array = body.get("stations", []) as Array
	main.crafting_summary_label.text = "Stations: %s" % (", ".join(stations) if not stations.is_empty() else "none nearby")
	var lines: PackedStringArray = []
	for recipe_value in body.get("recipes", []) as Array:
		if typeof(recipe_value) != TYPE_DICTIONARY:
			continue
		var recipe: Dictionary = recipe_value as Dictionary
		var recipe_id: String = str(recipe.get("recipe_id", ""))
		var ingredients: PackedStringArray = []
		for ingredient_value in recipe.get("ingredients", []) as Array:
			if typeof(ingredient_value) != TYPE_DICTIONARY:
				continue
			var ingredient: Dictionary = ingredient_value as Dictionary
			ingredients.append("%d/%d %s" % [int(ingredient.get("have", 0)), int(ingredient.get("need", 0)), main._bbcode_escape(str(ingredient.get("name", "material")))])
		var state: String = "[color=green]Ready[/color]" if bool(recipe.get("craftable", false)) else "[color=orange]%s[/color]" % main._bbcode_escape(str(recipe.get("blocker", "Unavailable")))
		var practice: String = "%s craft%s — %s · %s quality · material %s" % [str(recipe.get("craft_count", 0)), "" if int(recipe.get("craft_count", 0)) == 1 else "s", main._bbcode_escape(str(recipe.get("familiarity_label", "Unpracticed"))), main._bbcode_escape(str(recipe.get("quality_label", "Standard"))), str(recipe.get("material_quality_score", 0))]
		lines.append("[url=cmd:craft %s]%s[/url] — %s\n    %s\n    %s · %s" % [recipe_id, main._bbcode_escape(str(recipe.get("name", recipe_id))), state, ", ".join(ingredients), main._bbcode_escape(str(recipe.get("station_display", "Handcrafting"))), practice])
	main.crafting_list_label.text = "\n".join(lines) if not lines.is_empty() else "[i]No recipes are known.[/i]"

func _handle_collections_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	var lines: PackedStringArray = []
	var active_count: int = 0
	var completed_count: int = 0
	for collection_value in body.get("collections", []) as Array:
		if typeof(collection_value) != TYPE_DICTIONARY:
			continue
		var collection: Dictionary = collection_value as Dictionary
		if not bool(collection.get("discovered", false)):
			continue
		active_count += 1
		var name: String = main._bbcode_escape(str(collection.get("name", "Collection")))
		var turned_in_count: int = int(collection.get("turned_in_count", 0))
		var required_count: int = int(collection.get("required_count", 0))
		var completed: bool = bool(collection.get("completed", false))
		if completed:
			completed_count += 1
		var state: String = "[color=green]Complete[/color]" if completed else "%d/%d donated" % [turned_in_count, required_count]
		var items: PackedStringArray = []
		for item_value in collection.get("items", []) as Array:
			if typeof(item_value) != TYPE_DICTIONARY:
				continue
			var item: Dictionary = item_value as Dictionary
			var marker: String = "[x]" if bool(item.get("turned_in", false)) else "[+]" if bool(item.get("in_inventory", false)) else "[ ]"
			items.append("%s %s" % [marker, main._bbcode_escape(str(item.get("name", "Unknown item")))])
		lines.append("[url=cmd:collection %s]%s[/url] — %s\n    %s" % [str(collection.get("collection_id", "")), name, state, ", ".join(items)])
	main.collections_summary_label.text = "Active %d  Complete %d" % [active_count, completed_count]
	main.collections_list_label.text = "\n".join(lines) if not lines.is_empty() else "[i]Find a collectible item to begin a ledger.[/i]"

func _handle_discoveries_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	var entries: Array = body.get("discoveries", []) as Array
	var lines: PackedStringArray = []
	for entry_value in entries:
		if typeof(entry_value) != TYPE_DICTIONARY:
			continue
		var entry: Dictionary = entry_value as Dictionary
		var discovery_id: String = str(entry.get("discovery_id", ""))
		var name: String = main._bbcode_escape(str(entry.get("name", discovery_id)))
		var description: String = main._bbcode_escape(str(entry.get("description", "")))
		lines.append("[url=cmd:discoveries]%s[/url]\n    %s" % [name, description])
	main.discoveries_summary_label.text = "%d discovered  •  %d authored" % [lines.size(), int(body.get("total_authored", lines.size()))]
	main.discoveries_list_label.text = "\n".join(lines) if not lines.is_empty() else "[i]Explore, gather, craft, or acquire unusual things to make entries.[/i]"

func _handle_relationships_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	var entries: Array = body.get("relationships", []) as Array
	var lines: PackedStringArray = []
	for entry_value in entries:
		if typeof(entry_value) != TYPE_DICTIONARY:
			continue
		var entry: Dictionary = entry_value as Dictionary
		var next_value: Variant = entry.get("next_milestone", null)
		var next_text: String = "" if next_value == null else " — next %d/100" % int(next_value)
		lines.append("[url=cmd:relationships]%s[/url] — %s (%d/100)%s" % [main._bbcode_escape(str(entry.get("name", "Unknown"))), main._bbcode_escape(str(entry.get("tier", "Relationship"))), int(entry.get("score", 0)), next_text])
	main.relationships_summary_label.text = "%d known bond(s)" % lines.size()
	main.relationships_list_label.text = "\n".join(lines) if not lines.is_empty() else "[i]Gifts, orders, and commissions can build bonds.[/i]"

func _handle_quests_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	main._latest_quests_payload = body.duplicate(true)
	var active: Array = body.get("active", []) as Array
	var completed: Array = body.get("completed", []) as Array
	var archived: Array = body.get("archived", []) as Array
	main.journal_summary_label.text = "Active %d  Completed %d  Archived %d" % [active.size(), completed.size(), archived.size()]

	var lines: PackedStringArray = []
	var active_prefix: String = main.theme_controller._icon_token("quest_active_prefix", "A:")
	var completed_prefix: String = main.theme_controller._icon_token("quest_completed_prefix", "C:")
	var archived_prefix: String = main.theme_controller._icon_token("quest_archived_prefix", "R:")
	for quest_variant in active:
		if typeof(quest_variant) != TYPE_DICTIONARY:
			continue
		var quest: Dictionary = quest_variant as Dictionary
		var title: String = str(quest.get("title", "Unnamed Quest"))
		var objective: Dictionary = quest.get("objective", {}) as Dictionary
		var objective_text: String = str(objective.get("summary", "Complete the objective."))
		var alternatives: Array = objective.get("alternatives", []) as Array
		if alternatives.size() > 1:
			var route_text: PackedStringArray = []
			for alternative in alternatives:
				route_text.append(str(alternative))
			objective_text = "Choose one: " + "  OR  ".join(route_text)
		var progress_current: Variant = objective.get("progress_current", null)
		var progress_required: Variant = objective.get("progress_required", null)
		if progress_current != null and progress_required != null:
			objective_text += " (%d/%d)" % [int(progress_current), int(progress_required)]
		var hint: String = str(objective.get("location_hint", "")).strip_edges()
		if hint != "":
			objective_text += " — %s" % hint
		if bool(objective.get("ready_to_turn_in", false)):
			objective_text = "[color=yellow]Ready to turn in:[/color] " + objective_text
		lines.append("%s [url=cmd:journal]%s[/url] [%s]\n    %s" % [active_prefix, main._bbcode_escape(title), str(quest.get("state", "unknown")), main._bbcode_escape(objective_text)])
	for quest_variant in completed:
		if typeof(quest_variant) != TYPE_DICTIONARY:
			continue
		var quest: Dictionary = quest_variant as Dictionary
		var title: String = str(quest.get("title", "Unnamed Quest"))
		lines.append("%s [url=cmd:journal %s]%s[/url]" % [completed_prefix, title, title])
	for quest_variant in archived:
		if typeof(quest_variant) != TYPE_DICTIONARY:
			continue
		var quest: Dictionary = quest_variant as Dictionary
		var title: String = str(quest.get("title", "Unnamed Quest"))
		lines.append("%s [url=cmd:journal %s]%s[/url]" % [archived_prefix, title, title])

	if lines.is_empty():
		main.journal_list_label.text = "[i]%s[/i]" % main.theme_controller._icon_token("quest_none", "No quests tracked.")
		main.finite_adventure_ui._refresh_finite_adventure_panel()
		return
	main.journal_list_label.text = "\n".join(lines)
	main.finite_adventure_ui._refresh_finite_adventure_panel()

func _handle_nearby_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	var location: Dictionary = body.get("location", {}) as Dictionary
	var region_name: String = str(location.get("region_name", "Unknown Region"))
	var room_name: String = str(location.get("room_name", "Unknown Room"))
	main.nearby_location_label.text = "%s / %s" % [region_name, room_name]

	var exits: Array = body.get("exits", []) as Array
	if exits.is_empty():
		main.nearby_exits_label.text = "Exits: none"
	else:
		var exit_names: PackedStringArray = []
		for exit_value in exits:
			var exit_str = str(exit_value)
			exit_names.append("[url=cmd:%s]%s[/url]" % [exit_str, exit_str])
		main.nearby_exits_label.text = "Exits: %s" % ", ".join(exit_names)

	var npc_lines: PackedStringArray = []
	for npc_variant in (body.get("npcs", []) as Array):
		if typeof(npc_variant) != TYPE_DICTIONARY:
			continue
		var npc: Dictionary = npc_variant as Dictionary
		var hostile_flag: bool = bool(npc.get("hostile", false))
		var tag: String = main.theme_controller._icon_token("hostile_tag", "hostile") if hostile_flag else str(npc.get("faction", "neutral"))
		var npc_name: String = str(npc.get("name", "Unknown NPC"))
		var action: String = "attack" if hostile_flag else "look"
		npc_lines.append("[url=cmd:%s %s]%s[/url] [%s]" % [action, npc_name, npc_name, tag])
	if npc_lines.is_empty():
		main.nearby_npcs_label.text = "[i]%s[/i]" % main.theme_controller._icon_token("npc_none", "No nearby NPCs.")
	else:
		main.nearby_npcs_label.text = "\n".join(npc_lines)

	var item_lines: PackedStringArray = []
	for item_variant in (body.get("items", []) as Array):
		if typeof(item_variant) != TYPE_DICTIONARY:
			continue
		var item: Dictionary = item_variant as Dictionary
		var item_name: String = str(item.get("name", "Unknown Item"))
		var portable: bool = bool(item.get("portable", true))
		var action: String = "take" if portable else "look"
		item_lines.append("%s [url=cmd:%s %s]%s[/url]" % [main.theme_controller._icon_token("item_prefix", "-"), action, item_name, item_name])
	if item_lines.is_empty():
		main.nearby_items_label.text = "[i]%s[/i]" % main.theme_controller._icon_token("item_none", "No nearby items.")
	else:
		main.nearby_items_label.text = "\n".join(item_lines)

	var interactions: Array = body.get("interactions", []) as Array
	if interactions.is_empty():
		main.nearby_interactions_label.text = "Try: look, inventory, status"
	else:
		var commands: PackedStringArray = []
		for command_value in interactions:
			commands.append(str(command_value))
		main.nearby_interactions_label.text = "Try: %s" % ", ".join(commands)

func _summarize_field_cells(cells: Array) -> String:
	if cells.is_empty():
		return "stable (no active cells)"

	var max_intensity: float = 0.0
	for cell_variant in cells:
		if typeof(cell_variant) != TYPE_DICTIONARY:
			continue
		var cell: Dictionary = cell_variant as Dictionary
		var value: float = main._to_float(cell.get("value", cell.get("intensity", 0.0)))
		if value > max_intensity:
			max_intensity = value

	var intensity_word: String = "low"
	if max_intensity >= 0.75:
		intensity_word = "severe"
	elif max_intensity >= 0.4:
		intensity_word = "moderate"

	return "%d active cells, %s spread" % [cells.size(), intensity_word]
