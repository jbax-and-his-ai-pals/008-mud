# scripts/ui/SidePanel.gd
class_name SidePanel
extends Panel

# Signals
signal request_load_region(filename)
signal request_jump_to_room(id)
signal request_show_district(region_id, district_id)
signal snap_toggled(is_on)
signal show_districts_toggled(is_on)
signal request_validate
signal request_validate_region_policy
signal request_validate_content
signal request_run_release_gate
signal request_edit_ruleset
signal request_show_contracts
signal request_edit_contracts
signal request_edit_combat_vocabulary
signal request_choose_content_set
signal tool_changed(mode, data)
signal request_create_db_entry(type) 
signal request_delete_db_entry(type, id)
signal request_select_db_entry(type, id)
signal request_auto_layout
signal request_create_modal_open
signal request_district_modal_open
signal request_context_menu(global_pos, meta)
signal request_open_content_library

# Tabs
var explorer_panel: ExplorerPanel
var templates_tab: TemplatesTab
var palette_tab: PaletteTab
var paint_tab: PaintTab

const DB_TAB_SCRIPT = preload("res://scripts/ui/panels/tabs/DatabaseTab.gd")
const TMPL_TAB_SCRIPT = preload("res://scripts/ui/panels/tabs/TemplatesTab.gd")
const PAL_TAB_SCRIPT = preload("res://scripts/ui/panels/tabs/PaletteTab.gd")
const PNT_TAB_SCRIPT = preload("res://scripts/ui/panels/tabs/PaintTab.gd")

const EXPANDED_ANCHOR_RIGHT := 0.20
const COLLAPSED_WIDTH := 28.0

var main_vbox: VBoxContainer
var collapse_btn: Button
var collapsed := false

func setup():
	anchor_right = EXPANDED_ANCHOR_RIGHT
	anchor_bottom = 0.96
	var style = StyleBoxFlat.new()
	style.bg_color = Color(0.1, 0.1, 0.12, 0.95)
	style.set_border_width_all(1)
	style.border_color = Color(0.3, 0.3, 0.35, 0.95)
	add_theme_stylebox_override("panel", style)

	var vbox = VBoxContainer.new()
	vbox.set_anchors_preset(Control.PRESET_FULL_RECT)
	vbox.offset_left=10; vbox.offset_top=10; vbox.offset_right=-10; vbox.offset_bottom=-10
	add_child(vbox)
	main_vbox = vbox

	var tabs = TabContainer.new()
	tabs.size_flags_vertical = 3
	vbox.add_child(tabs)

	_setup_explorer_tab(tabs)
	_setup_content_library_tab(tabs)
	_setup_templates_tab(tabs)
	_setup_palette_tab(tabs)
	_setup_paint_tab(tabs)
	_setup_collapse_toggle()

	return vbox

# A small arrow tab flush with the panel's right edge, so it stays reachable
# at both the full width and the collapsed strip -- anchored to this Panel's
# own edge (not the viewport), it tracks whichever width is currently set.
func _setup_collapse_toggle():
	collapse_btn = Button.new()
	collapse_btn.text = "◀"
	collapse_btn.tooltip_text = "Collapse panel"
	collapse_btn.anchor_left = 1.0; collapse_btn.anchor_right = 1.0
	collapse_btn.anchor_top = 0.45; collapse_btn.anchor_bottom = 0.55
	collapse_btn.offset_left = 0.0; collapse_btn.offset_right = 20.0
	collapse_btn.focus_mode = Control.FOCUS_NONE
	var style := StyleBoxFlat.new(); style.bg_color = Color(0.2, 0.2, 0.24)
	style.corner_radius_top_right = 4; style.corner_radius_bottom_right = 4
	collapse_btn.add_theme_stylebox_override("normal", style)
	collapse_btn.add_theme_stylebox_override("hover", style)
	collapse_btn.add_theme_stylebox_override("pressed", style)
	collapse_btn.pressed.connect(func(): set_collapsed(not collapsed))
	add_child(collapse_btn)

func set_collapsed(c: bool):
	collapsed = c
	main_vbox.visible = not collapsed
	collapse_btn.text = "▶" if collapsed else "◀"
	collapse_btn.tooltip_text = "Expand panel" if collapsed else "Collapse panel"
	if collapsed:
		anchor_right = 0.0
		offset_right = COLLAPSED_WIDTH
	else:
		anchor_right = EXPANDED_ANCHOR_RIGHT
		offset_right = 0.0

func update_stamp_button_state(is_stamping: bool):
	templates_tab.update_stamp_button_state(is_stamping)
	palette_tab.update_stamp_button_state(is_stamping)

func update_db_lists(npcs: Dictionary, items: Dictionary, templates: Dictionary, magic: Dictionary, quests: Dictionary, dirty_flags: Dictionary):
	palette_tab.update_data(npcs, items)
	templates_tab.update_templates(templates)

func refresh_explorer(h, c, s): explorer_panel.update_data(h, c, s) 
func select_room_item(id): explorer_panel.select_room_item(id)
func update_dirty_visuals(cur, dirty, rooms): explorer_panel.update_dirty_visuals(cur, dirty, rooms)
func update_layout_btn_text(is_world: bool): explorer_panel.update_layout_btn_text(is_world)
func set_content_validation_running(running: bool): explorer_panel.set_content_validation_running(running)
func set_release_gate_running(running: bool): explorer_panel.set_release_gate_running(running)

# --- INTERNAL SETUP ---

func _create_tab_margin(name: String) -> MarginContainer:
	var m = MarginContainer.new()
	m.name = name
	m.add_theme_constant_override("margin_left", 5)
	m.add_theme_constant_override("margin_right", 5)
	m.add_theme_constant_override("margin_top", 12)
	m.add_theme_constant_override("margin_bottom", 5)
	return m

func _setup_explorer_tab(tabs: TabContainer):
	var margin = _create_tab_margin("Explorer")
	explorer_panel = ExplorerPanel.new()
	explorer_panel.setup()
	explorer_panel.request_load_region.connect(func(f): request_load_region.emit(f))
	explorer_panel.request_jump_to_room.connect(func(id): request_jump_to_room.emit(id))
	explorer_panel.request_show_district.connect(func(rid, did): request_show_district.emit(rid, did))
	explorer_panel.request_create_modal_open.connect(func(): request_create_modal_open.emit())
	explorer_panel.request_district_modal_open.connect(func(): request_district_modal_open.emit())
	explorer_panel.request_validate.connect(func(): request_validate.emit())
	explorer_panel.request_validate_region_policy.connect(func(): request_validate_region_policy.emit())
	explorer_panel.request_validate_content.connect(func(): request_validate_content.emit())
	explorer_panel.request_run_release_gate.connect(func(): request_run_release_gate.emit())
	explorer_panel.request_edit_ruleset.connect(func(): request_edit_ruleset.emit())
	explorer_panel.request_show_contracts.connect(func(): request_show_contracts.emit())
	explorer_panel.request_edit_contracts.connect(func(): request_edit_contracts.emit())
	explorer_panel.request_edit_combat_vocabulary.connect(func(): request_edit_combat_vocabulary.emit())
	explorer_panel.request_choose_content_set.connect(func(): request_choose_content_set.emit())
	explorer_panel.request_auto_layout.connect(func(): request_auto_layout.emit())
	explorer_panel.snap_toggled.connect(func(b): snap_toggled.emit(b))
	explorer_panel.show_districts_toggled.connect(func(b): show_districts_toggled.emit(b))
	explorer_panel.request_context_menu.connect(func(p, m): request_context_menu.emit(p, m))
	margin.add_child(explorer_panel)
	tabs.add_child(margin)

func _setup_content_library_tab(tabs: TabContainer):
	var margin = _create_tab_margin("Library")
	var box := VBoxContainer.new()
	box.size_flags_vertical = Control.SIZE_EXPAND_FILL
	box.add_theme_constant_override("separation", 12)
	var title := Label.new(); title.text = "CONTENT LIBRARY"; title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 15); title.modulate = Color(0.55, 0.85, 1.0)
	box.add_child(title)
	var description := Label.new()
	description.text = "Browse and edit NPCs, monsters, items, magic, quests, and room templates in one focused workspace."
	description.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	description.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	description.modulate = Color(0.7, 0.74, 0.8)
	box.add_child(description)
	var spacer := Control.new(); spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL; box.add_child(spacer)
	var open := Button.new(); open.text = "OPEN CONTENT LIBRARY"
	open.custom_minimum_size.y = 42
	var style := StyleBoxFlat.new(); style.bg_color = Color(0.16, 0.32, 0.45); style.set_corner_radius_all(5)
	style.set_border_width_all(1); style.border_color = Color(0.38, 0.68, 0.9)
	open.add_theme_stylebox_override("normal", style); open.add_theme_stylebox_override("hover", style.duplicate())
	open.get_theme_stylebox("hover").bg_color = style.bg_color.lightened(0.12)
	open.pressed.connect(func(): request_open_content_library.emit())
	box.add_child(open)
	margin.add_child(box)
	tabs.add_child(margin)

func _setup_templates_tab(tabs: TabContainer):
	var margin = _create_tab_margin("Templates")
	templates_tab = TMPL_TAB_SCRIPT.new()
	templates_tab.setup()
	templates_tab.tool_changed.connect(func(m, d): tool_changed.emit(m, d))
	templates_tab.request_delete_db_entry.connect(func(t, i): request_delete_db_entry.emit(t, i))
	templates_tab.request_context_menu.connect(func(p, m): request_context_menu.emit(p, m))
	margin.add_child(templates_tab)
	tabs.add_child(margin)

func _setup_palette_tab(tabs: TabContainer):
	var margin = _create_tab_margin("Palette")
	palette_tab = PAL_TAB_SCRIPT.new()
	palette_tab.setup()
	palette_tab.tool_changed.connect(func(m, d): tool_changed.emit(m, d))
	margin.add_child(palette_tab)
	tabs.add_child(margin)

func _setup_paint_tab(tabs: TabContainer):
	var margin = _create_tab_margin("Paint")
	paint_tab = PNT_TAB_SCRIPT.new()
	paint_tab.setup()
	paint_tab.tool_changed.connect(func(m, d): tool_changed.emit(m, d))
	margin.add_child(paint_tab)
	tabs.add_child(margin)
