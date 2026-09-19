# scripts/ui/modals/ContentLibraryDialog.gd
#
# A focused editing workspace for game content.  The map's left Explorer and
# right inspector stay dedicated to region design while this dialog keeps a
# collection, its index, and its editor together in one place.
class_name ContentLibraryDialog
extends ConfirmationDialog

signal request_create_entry(type: String)
signal request_delete_entry(type: String, id: String)
signal database_modified(type: String, id: String)
signal database_saved

var database_mgr: DatabaseManager
var world_mgr: WorldManager
var cached_npcs: Dictionary = {}
var cached_items: Dictionary = {}
var cached_magic: Dictionary = {}
var cached_quests: Dictionary = {}
var cached_recipes: Dictionary = {}
var cached_dialogues: Dictionary = {}
var cached_templates: Dictionary = {}
var cached_titles: Dictionary = {}
var cached_dirty: Dictionary = {}

var category_box: VBoxContainer
var entry_list: ItemList
var search_input: LineEdit
var editor_box: VBoxContainer
var empty_state: Label
var save_button: Button
var delete_button: Button
var create_button: Button
var tab_background_picker: ColorPickerButton
var tab_text_picker: ColorPickerButton
var appearance_dialog: ConfirmationDialog
var appearance_category := ""
var appearance_original_color := Color.WHITE
var appearance_original_text_color := Color.WHITE
var appearance_pending_color := Color.WHITE
var appearance_pending_text_color := Color.WHITE
var category := "npc"
var selected_id := ""
var current_editor: RefCounted
var category_colors: Dictionary = {}
var category_text_colors: Dictionary = {}
var collapsed_magic_groups: Dictionary = {}
var collapsed_item_groups: Dictionary = {}
var spell_groups_button: Button
var spell_groups_dialog: ConfirmationDialog

const DATABASE_INSPECTOR_SCRIPT = preload("res://scripts/ui/inspectors/DatabaseInspector.gd")
const QUEST_INSPECTOR_SCRIPT = preload("res://scripts/ui/inspectors/QuestInspector.gd")
const RECIPE_INSPECTOR_SCRIPT = preload("res://scripts/ui/inspectors/sub_inspectors/RecipeInspector.gd")
const DIALOGUE_INSPECTOR_SCRIPT = preload("res://scripts/ui/inspectors/sub_inspectors/DialogueInspector.gd")
const TITLE_INSPECTOR_SCRIPT = preload("res://scripts/ui/inspectors/sub_inspectors/TitleInspector.gd")

const CATEGORIES := [
	{"key": "npc", "label": "NPCs", "color": Color.LIGHT_GREEN},
	{"key": "monster", "label": "Monsters", "color": Color.SALMON},
	{"key": "item", "label": "Items", "color": Color.AQUAMARINE},
	{"key": "gem", "label": "Gems", "color": Color(0.45, 0.9, 0.95)},
	# The category key stays `magic` -- it is the cache name, the dirty-flag key,
	# and the name of persisted editor state (`magic_groups.json`). What an author
	# reads is "Abilities": a set whose abilities are device charges should not be
	# told it is authoring spells.
	{"key": "magic", "label": "Abilities", "color": Color.VIOLET},
	{"key": "quest", "label": "Quests", "color": Color.GOLD},
	{"key": "recipe", "label": "Recipes", "color": Color(0.7, 0.85, 0.5)},
	{"key": "dialogue", "label": "Dialogue", "color": Color(0.86, 0.75, 0.95)},
	{"key": "title", "label": "Titles", "color": Color(0.95, 0.8, 0.4)},
	{"key": "template", "label": "Templates", "color": Color(0.85, 0.72, 0.35)}
]

func setup(db_mgr: DatabaseManager, w_mgr: WorldManager):
	database_mgr = db_mgr
	world_mgr = w_mgr
	_load_category_appearance()
	title = "Content Library"
	min_size = Vector2i(1080, 680)
	exclusive = false
	get_ok_button().hide()
	get_cancel_button().hide()
	_build_ui()

func show_library():
	popup_centered(_library_size())
	search_input.grab_focus()

func show_entry(type: String, entry_id: String):
	if type == "npc":
		var entry: Dictionary = cached_npcs.get(entry_id, {})
		category = "monster" if not bool(entry.get("friendly", true)) else "npc"
	else:
		category = type
	selected_id = entry_id
	_update_category_buttons()
	_refresh_entries()
	_build_editor()
	popup_centered(_library_size())

func update_data(npcs: Dictionary, items: Dictionary, templates: Dictionary, magic: Dictionary, quests: Dictionary, recipes: Dictionary, dialogues: Dictionary, titles: Dictionary, dirty_flags: Dictionary):
	cached_npcs = npcs
	cached_items = items
	cached_templates = templates
	cached_magic = magic
	cached_quests = quests
	cached_recipes = recipes
	cached_dialogues = dialogues
	cached_titles = titles
	cached_dirty = dirty_flags
	_refresh_entries()
	_refresh_save_state()

func _build_ui():
	var root := VBoxContainer.new()
	root.size_flags_vertical = Control.SIZE_EXPAND_FILL
	root.add_theme_constant_override("separation", 10)
	add_child(root)

	var eyebrow := HBoxContainer.new()
	var intro := Label.new()
	intro.text = "Browse, edit, and save game content without leaving the map workspace."
	intro.modulate = InspectorStyle.COLOR_TEXT_DIM
	eyebrow.add_child(intro)
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; eyebrow.add_child(spacer)
	var status := Label.new(); status.text = "CONTENT LIBRARY"; status.modulate = Color(0.45, 0.85, 0.7)
	status.add_theme_font_size_override("font_size", 11); eyebrow.add_child(status)
	root.add_child(eyebrow)
	root.add_child(HSeparator.new())

	var columns := HBoxContainer.new()
	columns.size_flags_vertical = Control.SIZE_EXPAND_FILL
	columns.add_theme_constant_override("separation", 12)
	root.add_child(columns)

	var rail_card := _make_panel(Color(0.07, 0.09, 0.14))
	rail_card.custom_minimum_size.x = 138
	category_box = VBoxContainer.new(); category_box.add_theme_constant_override("separation", 6)
	rail_card.add_child(_margin_wrap(category_box, 10))
	columns.add_child(rail_card)
	var rail_header := HBoxContainer.new()
	var collections := Label.new(); collections.text = "COLLECTIONS"; collections.modulate = InspectorStyle.COLOR_TEXT_DIM
	collections.add_theme_font_size_override("font_size", 10); rail_header.add_child(collections)
	category_box.add_child(rail_header)
	for spec in CATEGORIES:
		var key := str(spec.key)
		var tab_row := Control.new(); tab_row.set_meta("category_key", key)
		tab_row.custom_minimum_size.y = 32
		var button := Button.new()
		button.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		button.text = str(spec.label)
		button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		button.toggle_mode = true
		button.button_pressed = key == category
		button.pressed.connect(func(): _select_category(key))
		_apply_category_style(button, key, key == category)
		tab_row.add_child(button)
		var appearance := Button.new(); appearance.name = "Appearance"; appearance.text = "⚙"; appearance.flat = true
		appearance.set_anchors_preset(Control.PRESET_TOP_RIGHT)
		appearance.position = Vector2(-28, 2)
		appearance.size = Vector2(26, 26)
		appearance.z_index = 1
		appearance.tooltip_text = "Customize " + str(spec.label) + " tab"
		appearance.visible = key == category
		appearance.pressed.connect(func(): _show_tab_appearance())
		tab_row.add_child(appearance)
		category_box.add_child(tab_row)

	var index_column := VBoxContainer.new()
	index_column.custom_minimum_size.x = 290
	index_column.add_theme_constant_override("separation", 8)
	columns.add_child(index_column)
	search_input = LineEdit.new()
	search_input.placeholder_text = "Search this collection…"
	search_input.clear_button_enabled = true
	InspectorStyle.apply_input_style(search_input)
	search_input.text_changed.connect(func(_text): _refresh_entries())
	index_column.add_child(search_input)
	entry_list = ItemList.new()
	entry_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	entry_list.add_theme_stylebox_override("panel", _make_style(Color(0.045, 0.055, 0.08)))
	entry_list.item_selected.connect(_on_entry_selected)
	index_column.add_child(entry_list)
	create_button = Button.new(); create_button.text = "+ Create " + _category_label(category).trim_suffix("s")
	create_button.pressed.connect(func(): request_create_entry.emit(category))
	_apply_button_style(create_button, Color(0.14, 0.39, 0.25), false)
	index_column.add_child(create_button)
	spell_groups_button = Button.new(); spell_groups_button.text = "Manage Ability Groups"
	spell_groups_button.pressed.connect(_show_spell_groups)
	_apply_button_style(spell_groups_button, Color(0.23, 0.19, 0.42), false)
	spell_groups_button.visible = false
	index_column.add_child(spell_groups_button)

	var editor_card := _make_panel(Color(0.065, 0.08, 0.12))
	editor_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	columns.add_child(editor_card)
	var editor_margin := MarginContainer.new()
	editor_margin.add_theme_constant_override("margin_left", 12)
	editor_margin.add_theme_constant_override("margin_right", 12)
	editor_margin.add_theme_constant_override("margin_top", 10)
	editor_margin.add_theme_constant_override("margin_bottom", 10)
	editor_card.add_child(editor_margin)
	var editor_scroll := ScrollContainer.new(); editor_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	editor_margin.add_child(editor_scroll)
	editor_box = VBoxContainer.new(); editor_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	editor_box.add_theme_constant_override("separation", 12)
	editor_scroll.add_child(editor_box)
	empty_state = Label.new()
	empty_state.text = "Select an entry to inspect and edit it."
	empty_state.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	empty_state.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	empty_state.size_flags_vertical = Control.SIZE_EXPAND_FILL
	empty_state.modulate = InspectorStyle.COLOR_TEXT_DIM
	editor_box.add_child(empty_state)

	root.add_child(HSeparator.new())
	var footer := HBoxContainer.new(); footer.add_theme_constant_override("separation", 10)
	footer.alignment = BoxContainer.ALIGNMENT_CENTER
	var close_button := Button.new(); close_button.text = "Close"; close_button.custom_minimum_size.x = 145
	close_button.pressed.connect(func(): hide())
	_apply_button_style(close_button, Color(0.2, 0.25, 0.32), false)
	footer.add_child(close_button)
	delete_button = Button.new(); delete_button.text = "Delete Entry"; delete_button.disabled = true
	delete_button.custom_minimum_size.x = 145
	delete_button.pressed.connect(_delete_selected)
	_apply_button_style(delete_button, Color(0.42, 0.14, 0.15), false)
	footer.add_child(delete_button)
	save_button = Button.new(); save_button.text = "SAVE CHANGES"; save_button.disabled = true; save_button.custom_minimum_size.x = 145
	save_button.pressed.connect(_save_database)
	_apply_button_style(save_button, Color(0.12, 0.42, 0.26), false)
	footer.add_child(save_button)
	root.add_child(footer)

func _select_category(next_category: String):
	if category == next_category: return
	category = next_category
	selected_id = ""
	_update_category_buttons()
	_refresh_entries()
	_clear_editor()
	_refresh_create_button()
	spell_groups_button.visible = category == "magic"

func _update_category_buttons():
	for child in category_box.get_children():
		if not child.has_meta("category_key"): continue
		var key := str(child.get_meta("category_key"))
		var tab_button := child.get_child(0) as Button
		var appearance_button := child.get_node_or_null("Appearance") as Button
		tab_button.button_pressed = key == category
		_apply_category_style(tab_button, key, key == category)
		if appearance_button: appearance_button.visible = key == category

func _refresh_entries():
	if not is_instance_valid(entry_list): return
	var keep_selected := selected_id
	entry_list.clear()
	var query := search_input.text.strip_edges().to_lower() if is_instance_valid(search_input) else ""
	var entries := _get_current_entries()
	var ids: Array = entries.keys()
	ids.sort_custom(func(a, b):
		if category == "magic":
			var school_order := _magic_school(entries[a]).nocasecmp_to(_magic_school(entries[b]))
			if school_order != 0: return school_order < 0
		if category == "item":
			var type_order := _item_group(entries[a]).nocasecmp_to(_item_group(entries[b]))
			if type_order != 0: return type_order < 0
		return _entry_label(entries[a], str(a)).nocasecmp_to(_entry_label(entries[b], str(b))) < 0
	)
	var selected_index := -1
	var current_school := ""
	var current_item_type := ""
	for entry_id_variant in ids:
		var entry_id := str(entry_id_variant)
		var entry: Dictionary = entries[entry_id]
		var label := _entry_label(entry, entry_id)
		if not query.is_empty() and not (label.to_lower().contains(query) or entry_id.to_lower().contains(query)):
			continue
		if category == "magic":
			var school := _magic_school(entry)
			if school != current_school:
				current_school = school
				var is_collapsed := bool(collapsed_magic_groups.get(school, false))
				var header_index := entry_list.add_item(("▶  " if is_collapsed else "▼  ") + school.to_upper())
				entry_list.set_item_metadata(header_index, {"magic_group_header": school})
				entry_list.set_item_custom_fg_color(header_index, category_text_colors.get("magic", Color.VIOLET).lightened(0.2))
			if bool(collapsed_magic_groups.get(school, false)): continue
		if category == "item":
			var item_type := _item_group(entry)
			if item_type != current_item_type:
				current_item_type = item_type
				var is_item_type_collapsed := bool(collapsed_item_groups.get(item_type, false))
				var item_header_index := entry_list.add_item(("▶  " if is_item_type_collapsed else "▼  ") + item_type.to_upper())
				entry_list.set_item_metadata(item_header_index, {"item_type_header": item_type})
				entry_list.set_item_custom_fg_color(item_header_index, category_text_colors.get("item", Color.CYAN).lightened(0.2))
			if bool(collapsed_item_groups.get(item_type, false)): continue
		var index := entry_list.add_item(label)
		entry_list.set_item_metadata(index, entry_id)
		entry_list.set_item_tooltip(index, entry_id)
		if _is_entry_dirty(entry_id):
			entry_list.set_item_custom_fg_color(index, Color(1.0, 0.86, 0.45))
		if entry_id == keep_selected: selected_index = index
	if selected_index >= 0:
		entry_list.select(selected_index)
	elif not selected_id.is_empty():
		selected_id = ""
		_clear_editor()

func _get_current_entries() -> Dictionary:
	match category:
		"npc": return _filter_characters(false)
		"monster": return _filter_characters(true)
		"item": return cached_items
		"gem": return _filter_gems()
		"magic": return cached_magic
		"quest": return cached_quests
		"recipe": return cached_recipes
		"dialogue": return cached_dialogues
		"title": return cached_titles
		"template": return cached_templates
	return {}

func _filter_characters(want_monsters: bool) -> Dictionary:
	var result: Dictionary = {}
	for entry_id in cached_npcs:
		var entry: Dictionary = cached_npcs[entry_id]
		if (not bool(entry.get("friendly", true))) == want_monsters:
			result[entry_id] = entry
	return result

func _filter_gems() -> Dictionary:
	var result: Dictionary = {}
	for entry_id in cached_items:
		var entry: Dictionary = cached_items[entry_id]
		if str(entry.get("type", "")).to_lower() == "gem":
			result[entry_id] = entry
	return result

func _on_entry_selected(index: int):
	_select_entry_at(index)

func _select_entry_at(index: int):
	if index < 0 or index >= entry_list.item_count: return
	var metadata = entry_list.get_item_metadata(index)
	if metadata is Dictionary and metadata.has("magic_group_header"):
		var group_name := str(metadata.magic_group_header)
		collapsed_magic_groups[group_name] = not bool(collapsed_magic_groups.get(group_name, false))
		_refresh_entries()
		return
	if metadata is Dictionary and metadata.has("item_type_header"):
		var item_type := str(metadata.item_type_header)
		collapsed_item_groups[item_type] = not bool(collapsed_item_groups.get(item_type, false))
		_refresh_entries()
		return
	selected_id = str(metadata)
	_build_editor()

func _build_editor():
	_clear_editor()
	var entries := _get_current_entries()
	if selected_id.is_empty() or not entries.has(selected_id): return
	delete_button.disabled = false
	var storage_type := _storage_type()
	var entry: Dictionary = entries[selected_id]
	if category == "gem":
		var note := InspectorStyle.create_section_header("GEM TYPE TEMPLATE", Color(0.45, 0.9, 0.95))
		editor_box.add_child(note)
		var help := InspectorStyle.lbl("Generated gems roll their own size and quality. Edit this template's rarity, base value, and generation biases below.", InspectorStyle.COLOR_TEXT_DIM)
		help.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		editor_box.add_child(help)
	if storage_type == "quest":
		var quest_editor = QUEST_INSPECTOR_SCRIPT.new(editor_box, database_mgr, world_mgr)
		current_editor = quest_editor
		quest_editor.database_modified.connect(_mark_current_dirty)
		quest_editor.build(selected_id, entry)
	else:
		var inspector = DATABASE_INSPECTOR_SCRIPT.new(editor_box)
		current_editor = inspector
		inspector.set_db_manager(database_mgr)
		inspector.database_modified.connect(_mark_current_dirty)
		if storage_type == "dialogue":
			var dialogue_inspector = DIALOGUE_INSPECTOR_SCRIPT.new(editor_box, database_mgr)
			current_editor = dialogue_inspector
			dialogue_inspector.database_modified.connect(_mark_current_dirty)
			dialogue_inspector.build(selected_id, entry)
			return
		if storage_type == "recipe":
			var recipe_inspector = RECIPE_INSPECTOR_SCRIPT.new(editor_box, database_mgr)
			current_editor = recipe_inspector
			recipe_inspector.database_modified.connect(_mark_current_dirty)
			recipe_inspector.build(selected_id, entry)
			return
		if storage_type == "title":
			var title_inspector = TITLE_INSPECTOR_SCRIPT.new(editor_box, database_mgr)
			current_editor = title_inspector
			title_inspector.database_modified.connect(_mark_current_dirty)
			title_inspector.build(selected_id, entry)
			return
		inspector.build(storage_type, selected_id, entry)

func _clear_editor():
	if not is_instance_valid(editor_box): return
	for child in editor_box.get_children(): child.queue_free()
	current_editor = null
	if is_instance_valid(delete_button): delete_button.disabled = true
	if not selected_id.is_empty(): return
	empty_state = Label.new()
	empty_state.text = "Select an entry to inspect and edit it."
	empty_state.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	empty_state.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	empty_state.size_flags_vertical = Control.SIZE_EXPAND_FILL
	empty_state.modulate = InspectorStyle.COLOR_TEXT_DIM
	editor_box.add_child(empty_state)

func _mark_current_dirty():
	if selected_id.is_empty(): return
	var storage_type := _storage_type()
	# DatabaseInspector updates its own current ID after a rename.
	if current_editor != null:
		var edited_id = current_editor.get("cur_id")
		if edited_id != null: selected_id = str(edited_id)
	database_mgr.mark_dirty(storage_type, selected_id)
	database_modified.emit(storage_type, selected_id)
	_refresh_save_state()

func _delete_selected():
	if selected_id.is_empty(): return
	request_delete_entry.emit(_storage_type(), selected_id)
	selected_id = ""
	_clear_editor()

func _save_database():
	if not _has_unsaved_changes(): return
	var result := database_mgr.save_all()
	if not result.get("ok", true):
		# Keep the panel's own dirty state: the write failed, so the work is still
		# only in memory, and Save has to stay available to retry.
		_show_save_error(result.get("errors", []))
		return
	database_saved.emit()
	_refresh_save_state()

func _show_save_error(errors: Array) -> void:
	var dialog := AcceptDialog.new()
	dialog.title = "Some content files could not be saved"
	dialog.dialog_text = "\n".join(errors) if not errors.is_empty() else "The save did not complete."
	dialog.min_size = Vector2i(520, 180)
	add_child(dialog)
	dialog.popup_centered()
	dialog.confirmed.connect(dialog.queue_free)
	dialog.canceled.connect(dialog.queue_free)

func _has_unsaved_changes() -> bool:
	if database_mgr.magic_groups_dirty: return true
	for type in cached_dirty:
		if not cached_dirty[type].is_empty(): return true
	return false

func _refresh_save_state():
	if not is_instance_valid(save_button): return
	var dirty := _has_unsaved_changes()
	save_button.disabled = not dirty
	save_button.tooltip_text = "Save all content-library changes." if dirty else "No unsaved content changes."

func _refresh_create_button():
	if not is_instance_valid(create_button): return
	create_button.text = "+ Create Ability" if category == "magic" else "+ Create " + _category_label(category).trim_suffix("s")
	create_button.disabled = category == "template"
	create_button.tooltip_text = "Room templates are created from a room's Save as Template action." if category == "template" else "Create a new " + _category_label(category).trim_suffix("s").to_lower() + "."

func _storage_type() -> String:
	if category == "monster": return "npc"
	if category == "gem": return "item"
	return category

func _category_label(key: String) -> String:
	for spec in CATEGORIES:
		if spec.key == key: return str(spec.label)
	return key.capitalize()

func _entry_label(entry: Dictionary, fallback: String) -> String:
	return str(entry.get("name", fallback)).capitalize()

func _item_group(entry: Dictionary) -> String:
	# Prefer an explicit, meaningful item type.  Older content often used the
	# generic "Item" type, so use its existing property/source-file context as
	# a non-destructive fallback rather than lumping unrelated things together.
	var type_name := str(entry.get("type", "")).strip_edges()
	if not type_name.is_empty() and type_name.to_lower() != "item":
		return type_name.capitalize()
	var properties: Dictionary = entry.get("properties", {})
	var property_category := str(properties.get("category", "")).strip_edges()
	if not property_category.is_empty():
		return property_category.capitalize()
	var source := str(entry.get("_filename", "")).get_file().trim_suffix(".json").to_lower()
	var source_groups := {
		"affixes": "Affixes",
		"casino": "Casino Rules",
		"collection_items": "Collections",
		"materials": "Materials",
		"misc_items": "Miscellaneous",
		"quest_items": "Quest Items",
		"sets": "Item Sets",
		"tools": "Tools",
	}
	return str(source_groups.get(source, "Miscellaneous"))

func _magic_school(entry: Dictionary) -> String:
	var group_id := str(entry.get("magic_group", "")).strip_edges()
	if not group_id.is_empty() and database_mgr.magic_groups.has(group_id):
		return str(database_mgr.magic_groups[group_id].get("name", group_id))
	var source := str(entry.get("_filename", "")).get_file().replace(".json", "")
	match source:
		"buff_spells", "restoration_spells": return "Restoration"
		"debuff_spells": return "Curses"
		"elemental_spells": return "Elemental"
		"offensive_spells": return "Evocation"
		"summoning_spells": return "Conjuration"
		"utility_spells": return "Utility"
	return "General"

func _show_spell_groups():
	if not is_instance_valid(spell_groups_dialog):
		spell_groups_dialog = ConfirmationDialog.new()
		spell_groups_dialog.title = "Manage Ability Groups"
		spell_groups_dialog.min_size = Vector2i(460, 420)
		add_child(spell_groups_dialog)
	spell_groups_dialog.get_ok_button().text = "Done"
	for child in spell_groups_dialog.get_children(): child.queue_free()
	var box := VBoxContainer.new(); box.add_theme_constant_override("separation", 8)
	spell_groups_dialog.add_child(box)
	var help := Label.new(); help.text = "Ability groups are shared definitions. Abilities select one from a controlled list."
	help.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; help.modulate = InspectorStyle.COLOR_TEXT_DIM; box.add_child(help)
	var groups: Array = database_mgr.magic_groups.keys(); groups.sort()
	for group_id_variant in groups:
		var group_id := str(group_id_variant)
		var row := HBoxContainer.new()
		var name := LineEdit.new(); name.text = str(database_mgr.magic_groups[group_id].get("name", group_id)); name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_input_style(name)
		name.text_changed.connect(func(text):
			database_mgr.magic_groups[group_id]["name"] = text.strip_edges() if not text.strip_edges().is_empty() else group_id
			database_mgr.mark_magic_groups_dirty(); _refresh_entries(); _refresh_save_state()
		)
		row.add_child(name)
		var remove := Button.new(); remove.text = "×"; remove.tooltip_text = "Remove group"
		remove.disabled = group_id == "general"
		remove.pressed.connect(func(): database_mgr.magic_groups.erase(group_id); database_mgr.mark_magic_groups_dirty(); _show_spell_groups(); _refresh_entries(); _refresh_save_state())
		row.add_child(remove); box.add_child(row)
	var add_row := HBoxContainer.new()
	var new_name := LineEdit.new(); new_name.placeholder_text = "New group name"; new_name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(new_name); add_row.add_child(new_name)
	var add := Button.new(); add.text = "+ Add"
	add.pressed.connect(func():
		var display := new_name.text.strip_edges()
		if display.is_empty(): return
		var group_id := _slugify(display)
		if database_mgr.magic_groups.has(group_id): return
		database_mgr.magic_groups[group_id] = {"name": display}
		database_mgr.mark_magic_groups_dirty(); _show_spell_groups(); _refresh_entries(); _refresh_save_state()
	)
	add_row.add_child(add); box.add_child(add_row)
	spell_groups_dialog.popup_centered()

func _slugify(text: String) -> String:
	var result := ""
	for character in text.to_lower():
		result += character if character.is_valid_identifier() else "_"
	return result.strip_edges().replace(" ", "_")

func _is_entry_dirty(entry_id: String) -> bool:
	return cached_dirty.get(_storage_type(), {}).has(entry_id)

func _make_panel(color: Color) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", _make_style(color))
	return panel

func _make_style(color: Color) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = color
	style.border_color = Color(0.22, 0.34, 0.48)
	style.set_border_width_all(1)
	style.set_corner_radius_all(6)
	return style

func _margin_wrap(child: Control, margin: int) -> MarginContainer:
	var box := MarginContainer.new()
	box.add_theme_constant_override("margin_left", margin)
	box.add_theme_constant_override("margin_right", margin)
	box.add_theme_constant_override("margin_top", margin)
	box.add_theme_constant_override("margin_bottom", margin)
	box.add_child(child)
	return box

func _apply_button_style(button: Button, color: Color, selected: bool):
	var normal := _make_style(color.lightened(0.08) if selected else color)
	normal.border_color = color.lightened(0.3)
	normal.content_margin_left = 10; normal.content_margin_right = 10
	button.add_theme_stylebox_override("normal", normal)
	button.add_theme_color_override("font_color", Color(0.92, 0.95, 1.0))
	button.add_theme_color_override("font_hover_color", Color.WHITE)
	button.add_theme_stylebox_override("hover", normal.duplicate())
	button.get_theme_stylebox("hover").bg_color = normal.bg_color.lightened(0.12)
	button.add_theme_stylebox_override("pressed", normal.duplicate())
	button.get_theme_stylebox("pressed").bg_color = normal.bg_color.darkened(0.12)
	var disabled := normal.duplicate(); disabled.bg_color = normal.bg_color.darkened(0.35)
	button.add_theme_stylebox_override("disabled", disabled)
	button.add_theme_color_override("font_disabled_color", Color(0.45, 0.49, 0.55))

func _apply_category_style(button: Button, key: String, selected: bool):
	var color: Color = category_colors.get(key, Color(0.35, 0.55, 0.72))
	var text_color: Color = category_text_colors.get(key, Color(0.9, 0.94, 1.0))
	var background := color.darkened(0.48) if selected else Color(0.09, 0.11, 0.16)
	var style := _make_style(background)
	style.border_color = color.lightened(0.12) if selected else color.darkened(0.25)
	style.set_border_width_all(2 if selected else 1)
	style.content_margin_left = 10; style.content_margin_right = 10
	button.add_theme_stylebox_override("normal", style)
	button.add_theme_stylebox_override("hover", style.duplicate())
	button.get_theme_stylebox("hover").bg_color = background.lightened(0.12)
	button.add_theme_stylebox_override("pressed", style.duplicate())
	button.get_theme_stylebox("pressed").bg_color = background.darkened(0.12)
	button.add_theme_color_override("font_color", text_color)
	button.add_theme_color_override("font_hover_color", Color.WHITE)

func _small_label(text: String) -> Label:
	var label := Label.new(); label.text = text; label.custom_minimum_size.x = 38
	label.modulate = InspectorStyle.COLOR_TEXT_DIM
	return label

func _show_tab_appearance():
	if not is_instance_valid(appearance_dialog):
		appearance_dialog = ConfirmationDialog.new()
		appearance_dialog.min_size = Vector2i(340, 210)
		appearance_dialog.get_ok_button().text = "Done"
		appearance_dialog.confirmed.connect(_commit_tab_appearance)
		appearance_dialog.canceled.connect(_cancel_tab_appearance)
		add_child(appearance_dialog)
	appearance_category = category
	appearance_original_color = category_colors.get(category, Color(0.3, 0.5, 0.7))
	appearance_original_text_color = category_text_colors.get(category, Color.WHITE)
	appearance_pending_color = appearance_original_color
	appearance_pending_text_color = appearance_original_text_color
	for child in appearance_dialog.get_children(): child.queue_free()
	appearance_dialog.title = "Customize " + _category_label(category) + " Tab"
	var box := VBoxContainer.new(); box.add_theme_constant_override("separation", 10); appearance_dialog.add_child(box)
	box.add_child(InspectorStyle.lbl("Category Color", InspectorStyle.COLOR_TEXT_DIM))
	tab_background_picker = ColorPickerButton.new(); tab_background_picker.custom_minimum_size = Vector2(0, 32)
	tab_background_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tab_background_picker.color = appearance_pending_color
	_apply_color_swatch(tab_background_picker, appearance_pending_color)
	tab_background_picker.color_changed.connect(func(color):
		appearance_pending_color = color
		_apply_color_swatch(tab_background_picker, color)
		_preview_tab_appearance()
	)
	box.add_child(tab_background_picker)
	box.add_child(InspectorStyle.lbl("Text Color", InspectorStyle.COLOR_TEXT_DIM))
	tab_text_picker = ColorPickerButton.new(); tab_text_picker.custom_minimum_size = Vector2(0, 32)
	tab_text_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tab_text_picker.color = appearance_pending_text_color
	_apply_color_swatch(tab_text_picker, appearance_pending_text_color)
	tab_text_picker.color_changed.connect(func(color):
		appearance_pending_text_color = color
		_apply_color_swatch(tab_text_picker, color)
		_preview_tab_appearance()
	)
	box.add_child(tab_text_picker)
	appearance_dialog.popup_centered()

func _apply_color_swatch(picker: ColorPickerButton, color: Color):
	var normal := _make_style(color)
	normal.border_color = color.lightened(0.28)
	normal.set_border_width_all(1)
	var hover := _make_style(color.lightened(0.08))
	hover.border_color = Color(0.82, 0.92, 1.0)
	hover.set_border_width_all(2)
	picker.add_theme_stylebox_override("normal", normal)
	picker.add_theme_stylebox_override("hover", hover)
	picker.add_theme_stylebox_override("pressed", hover)

func _preview_tab_appearance():
	if appearance_category.is_empty(): return
	category_colors[appearance_category] = appearance_pending_color
	category_text_colors[appearance_category] = appearance_pending_text_color
	_update_category_buttons()

func _commit_tab_appearance():
	if appearance_category.is_empty(): return
	_preview_tab_appearance()
	_save_category_appearance()
	appearance_category = ""

func _cancel_tab_appearance():
	if appearance_category.is_empty(): return
	category_colors[appearance_category] = appearance_original_color
	category_text_colors[appearance_category] = appearance_original_text_color
	_update_category_buttons()
	appearance_category = ""

func _load_category_appearance():
	var config := ConfigFile.new()
	config.load("user://content_library_tabs.cfg")
	for spec in CATEGORIES:
		var key := str(spec.key)
		category_colors[key] = config.get_value("tabs", key + "_color", spec.color)
		category_text_colors[key] = config.get_value("tabs", key + "_text", Color(0.9, 0.94, 1.0))

func _save_category_appearance():
	var config := ConfigFile.new()
	for key in category_colors:
		config.set_value("tabs", key + "_color", category_colors[key])
		config.set_value("tabs", key + "_text", category_text_colors[key])
	config.save("user://content_library_tabs.cfg")

func _library_size() -> Vector2i:
	var viewport_size: Vector2 = get_viewport().get_visible_rect().size
	# At normal desktop widths this lands around half the screen. A practical
	# lower bound keeps the three-pane layout usable on smaller monitors, while
	# the upper bound prevents it from turning into an ultrawide spreadsheet.
	var width := clampi(int(viewport_size.x * 0.5), 1080, 1720)
	var height := clampi(int(viewport_size.y * 0.76), 640, 920)
	return Vector2i(width, height)
