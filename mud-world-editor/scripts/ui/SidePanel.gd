# scripts/ui/SidePanel.gd
class_name SidePanel
extends Panel

# Signals
signal request_load_region(filename)
signal request_jump_to_room(id)
signal snap_toggled(is_on)
signal request_validate
signal tool_changed(mode, data)
signal request_create_db_entry(type) 
signal request_delete_db_entry(type, id)
signal request_select_db_entry(type, id)
signal request_auto_layout
signal request_create_modal_open
signal request_context_menu(global_pos, meta)

# Tabs
var explorer_panel: ExplorerPanel
var database_tab: DatabaseTab
var templates_tab: TemplatesTab
var palette_tab: PaletteTab
var paint_tab: PaintTab

const DB_TAB_SCRIPT = preload("res://scripts/ui/panels/tabs/DatabaseTab.gd")
const TMPL_TAB_SCRIPT = preload("res://scripts/ui/panels/tabs/TemplatesTab.gd")
const PAL_TAB_SCRIPT = preload("res://scripts/ui/panels/tabs/PaletteTab.gd")
const PNT_TAB_SCRIPT = preload("res://scripts/ui/panels/tabs/PaintTab.gd")

func setup():
	anchor_right = 0.20
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
	
	var tabs = TabContainer.new()
	tabs.size_flags_vertical = 3 
	vbox.add_child(tabs)
	
	_setup_explorer_tab(tabs)
	_setup_database_tab(tabs)
	_setup_templates_tab(tabs)
	_setup_palette_tab(tabs)
	_setup_paint_tab(tabs)
	
	return vbox

func update_stamp_button_state(is_stamping: bool):
	templates_tab.update_stamp_button_state(is_stamping)
	palette_tab.update_stamp_button_state(is_stamping)

func update_db_lists(npcs: Dictionary, items: Dictionary, templates: Dictionary, magic: Dictionary, quests: Dictionary, dirty_flags: Dictionary):
	database_tab.update_data(npcs, items, magic, quests, dirty_flags)
	palette_tab.update_data(npcs, items)
	templates_tab.update_templates(templates)

func refresh_explorer(h, c, s): explorer_panel.update_data(h, c, s) 
func select_room_item(id): explorer_panel.select_room_item(id)
func update_dirty_visuals(cur, dirty, rooms): explorer_panel.update_dirty_visuals(cur, dirty, rooms)
func update_layout_btn_text(is_world: bool): explorer_panel.update_layout_btn_text(is_world)

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
	explorer_panel.request_create_modal_open.connect(func(): request_create_modal_open.emit())
	explorer_panel.request_validate.connect(func(): request_validate.emit())
	explorer_panel.request_auto_layout.connect(func(): request_auto_layout.emit())
	explorer_panel.snap_toggled.connect(func(b): snap_toggled.emit(b))
	explorer_panel.request_context_menu.connect(func(p, m): request_context_menu.emit(p, m))
	margin.add_child(explorer_panel)
	tabs.add_child(margin)

func _setup_database_tab(tabs: TabContainer):
	var margin = _create_tab_margin("Database")
	database_tab = DB_TAB_SCRIPT.new()
	database_tab.setup()
	database_tab.request_select_db_entry.connect(func(t, i): request_select_db_entry.emit(t, i))
	database_tab.request_create_db_entry.connect(func(t): request_create_db_entry.emit(t))
	database_tab.request_delete_db_entry.connect(func(t, i): request_delete_db_entry.emit(t, i))
	database_tab.request_context_menu.connect(func(p, m): request_context_menu.emit(p, m))
	margin.add_child(database_tab)
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
