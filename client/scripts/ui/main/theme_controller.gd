# scripts/ui/main/theme_controller.gd
# ThemeController: extracted from main_controller.gd as part of the P8
# file-splitting pass. main.tscn is untouched -- this holds a reference
# back to the Main control (`main`) and reaches its @onready nodes and
# shared state through it, since GDScript keeps one script per node.
extends RefCounted
class_name ThemeController

var main: MainController
# Set once the player picks a theme with `theme use`; the content set's
# declared pack is a default, not an override of the player's choice.
var player_chose_theme := false

func _init(main_ref: MainController) -> void:
	main = main_ref

func _maybe_handle_local_theme_command(cmd: String) -> bool:
	var lowered: String = cmd.strip_edges().to_lower()
	if lowered == "theme list":
		var ids: PackedStringArray = []
		for key: Variant in main._theme_catalog.keys():
			ids.append(str(key))
		ids.sort()
		main._append_log("[color=aqua]Themes: %s[/color]" % ", ".join(ids))
		return true
	if not lowered.begins_with("theme use "):
		return false
	var theme_id: String = cmd.strip_edges().substr(10).strip_edges().to_lower()
	if theme_id == "":
		main._append_log("[color=orange]Usage: theme use <theme_id>[/color]")
		return true
	if not main._theme_catalog.has(theme_id):
		main._append_log("[color=orange]Unknown theme: %s[/color]" % theme_id)
		return true
	player_chose_theme = true
	_apply_theme(theme_id)
	return true

## The theme pack the connected content set declares (sent in `hello`).
## Applied unless the player has chosen one; a pack this client does not
## ship leaves the current theme in place and says so.
func apply_content_set_theme(presentation: Dictionary) -> void:
	var theme_id := str(presentation.get("theme_pack", "")).strip_edges().to_lower()
	if theme_id == "" or player_chose_theme or theme_id == main._active_theme_id:
		return
	if not main._theme_catalog.has(theme_id):
		main._append_log("[color=orange]This world asks for theme pack '%s', which this client does not have; keeping '%s'.[/color]" % [theme_id, main._active_theme_id])
		return
	_apply_theme(theme_id)

func _load_theme_catalog() -> void:
	main._theme_catalog.clear()
	var dir: DirAccess = DirAccess.open(main.THEME_PACK_DIR)
	if dir == null:
		main._append_log("[color=orange]Theme directory missing: %s[/color]" % main.THEME_PACK_DIR)
		return
	dir.list_dir_begin()
	var file_name: String = dir.get_next()
	while file_name != "":
		if not dir.current_is_dir() and file_name.get_extension().to_lower() == "json":
			var path: String = "%s/%s" % [main.THEME_PACK_DIR, file_name]
			var file: FileAccess = FileAccess.open(path, FileAccess.READ)
			if file != null:
				var raw: String = file.get_as_text()
				file.close()
				var parsed: Variant = JSON.parse_string(raw)
				if typeof(parsed) == TYPE_DICTIONARY:
					var pack: Dictionary = parsed as Dictionary
					var validation_errors: PackedStringArray = _validate_theme_pack(pack, file_name)
					if validation_errors.is_empty():
						var theme_id: String = str(pack.get("theme_id", "")).to_lower()
						main._theme_catalog[theme_id] = pack
					else:
						main._append_log("[color=orange]Theme skipped (%s): %s[/color]" % [
							file_name,
							"; ".join(validation_errors)
						])
		file_name = dir.get_next()
	dir.list_dir_end()
	if main._theme_catalog.is_empty():
		main._append_log("[color=orange]No theme packs loaded.[/color]")

func _apply_theme(theme_id: String) -> void:
	if not main._theme_catalog.has(theme_id):
		return
	var pack: Dictionary = main._theme_catalog.get(theme_id, {}) as Dictionary
	var ui: Dictionary = pack.get("ui_strings", {}) as Dictionary
	var lexicon: Dictionary = pack.get("lexicon", {}) as Dictionary
	var icon_tokens: Dictionary = pack.get("icon_tokens", {}) as Dictionary

	main.status_title_label.text = str(ui.get("status_title", "Status"))
	main.inventory_title_label.text = str(ui.get("inventory_title", "Inventory"))
	main.collections_title_label.text = str(ui.get("collections_title", "Collections"))
	main.discoveries_title_label.text = str(ui.get("discoveries_title", "Discoveries"))
	main.journal_title_label.text = str(ui.get("journal_title", "Journal"))
	main.nearby_title_label.text = str(ui.get("nearby_title", "Nearby"))
	main.world_state_title_label.text = str(ui.get("world_state_title", "World State"))
	main.network_title_label.text = str(ui.get("network_title", "Network"))
	main.adventure_title_label.text = str(ui.get("adventure_title", "Adventure"))
	main.asset_title_label.text = str(ui.get("asset_title", "Asset Preview"))
	main.connect_button.text = str(ui.get("connect_button", "Connect"))
	main.disconnect_button.text = str(ui.get("disconnect_button", "Disconnect"))
	main.send_button.text = str(ui.get("send_button", "Send"))

	var field_label: String = str(lexicon.get("world_field_id", "world_field"))
	main.field_id_input.text = field_label
	main.command_input.placeholder_text = str(ui.get("command_placeholder", "Type command..."))
	main._theme_icon_tokens = icon_tokens.duplicate(true)
	_apply_theme_style(pack.get("style_tokens", {}) as Dictionary)
	main._active_theme_id = theme_id
	main._append_log("[color=green]Theme active: %s[/color]" % main._active_theme_id)

func _validate_theme_pack(pack: Dictionary, source_name: String) -> PackedStringArray:
	var errors: PackedStringArray = []
	var theme_id: String = str(pack.get("theme_id", "")).strip_edges().to_lower()
	if theme_id == "":
		errors.append("%s missing theme_id" % source_name)
	var display_name: String = str(pack.get("display_name", "")).strip_edges()
	if display_name == "":
		errors.append("%s missing display_name" % source_name)
	if pack.has("ui_strings") and typeof(pack.get("ui_strings")) != TYPE_DICTIONARY:
		errors.append("%s ui_strings must be dictionary" % source_name)
	if pack.has("lexicon") and typeof(pack.get("lexicon")) != TYPE_DICTIONARY:
		errors.append("%s lexicon must be dictionary" % source_name)
	if pack.has("style_tokens") and typeof(pack.get("style_tokens")) != TYPE_DICTIONARY:
		errors.append("%s style_tokens must be dictionary" % source_name)
	if pack.has("icon_tokens") and typeof(pack.get("icon_tokens")) != TYPE_DICTIONARY:
		errors.append("%s icon_tokens must be dictionary" % source_name)
	return errors

func _icon_token(key: String, fallback: String) -> String:
	var value: String = str(main._theme_icon_tokens.get(key, fallback))
	if value.strip_edges() == "":
		return fallback
	return value

func _apply_theme_style(style_tokens: Dictionary) -> void:
	var accent: Color = _parse_theme_color(style_tokens.get("accent_color", "#BFE6FF"), main.THEME_DEFAULT_ACCENT)
	var text_color: Color = _parse_theme_color(style_tokens.get("text_color", "#E6E6E6"), main.THEME_DEFAULT_TEXT)
	var spacing: int = clamp(int(style_tokens.get("ui_density", main.THEME_DEFAULT_DENSITY)), 2, 20)
	main.root_vbox.add_theme_constant_override("separation", spacing)

	main.status_title_label.self_modulate = accent
	main.inventory_title_label.self_modulate = accent
	main.collections_title_label.self_modulate = accent
	main.discoveries_title_label.self_modulate = accent
	main.journal_title_label.self_modulate = accent
	main.nearby_title_label.self_modulate = accent
	main.world_state_title_label.self_modulate = accent
	main.network_title_label.self_modulate = accent
	main.adventure_title_label.self_modulate = accent
	main.asset_title_label.self_modulate = accent

	main.status_primary_label.self_modulate = text_color
	main.status_vitals_label.self_modulate = text_color
	main.status_effects_label.self_modulate = text_color
	main.inventory_summary_label.self_modulate = text_color
	main.collections_summary_label.self_modulate = text_color
	main.discoveries_summary_label.self_modulate = text_color
	main.journal_summary_label.self_modulate = text_color
	main.nearby_location_label.self_modulate = text_color
	main.nearby_exits_label.self_modulate = text_color
	main.nearby_interactions_label.self_modulate = text_color
	main.world_state_label.self_modulate = text_color
	main.network_summary_label.self_modulate = text_color
	main.network_detail_label.self_modulate = text_color
	main.adventure_state_label.self_modulate = text_color
	main.adventure_summary_label.self_modulate = text_color
	main.adventure_catalog_label.self_modulate = text_color
	main.adventure_report_label.self_modulate = text_color
	main.asset_alt_text.self_modulate = text_color

func _parse_theme_color(value: Variant, fallback: Color) -> Color:
	if typeof(value) == TYPE_COLOR:
		return value as Color
	if typeof(value) == TYPE_STRING:
		var s: String = str(value)
		if s.is_valid_html_color():
			return Color.html(s)
	return fallback

func _apply_text_scale(scale: float) -> void:
	var clamped: float = clamp(scale, main.TEXT_SCALE_MIN, main.TEXT_SCALE_MAX)
	main._client_capabilities["text_scale"] = clamped
	var window: Window = main.get_window()
	window.content_scale_factor = clamped
