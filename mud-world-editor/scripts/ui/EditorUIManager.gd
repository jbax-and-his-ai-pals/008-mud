# scripts/ui/EditorUIManager.gd
class_name EditorUIManager
extends RefCounted

signal request_load_region(filename)
signal request_jump_to_room(id)
signal request_validate
signal snap_toggled(is_on)
signal request_create_connection(src, dir, target, twoway)
signal request_create_region(name, room_data)
signal context_action(action_id)
signal creation_direction_selected(direction)
signal request_jump_to_error(region_file, room_id)
signal tool_changed(mode, data)
signal request_create_db_entry(type) 
signal request_delete_db_entry(type, id)
signal request_select_db_entry(type, id)
signal request_toggle_world_view(enabled)
signal request_auto_layout
signal request_center_view
signal request_copy
signal request_paste
signal request_save_template(room_id)
signal request_context_menu(global_pos, meta)
signal request_delete_room_confirm(room_id, include_reciprocal)
signal view_mode_changed(mode) # New Signal

enum ToolMode { SELECT, PAINT, STAMP }

var ui_layer: CanvasLayer
var side_panel: SidePanel
var btn_world_view: Button
var opt_view_mode: OptionButton # New Control
var footer_container: VBoxContainer

var creator_modal: CreatorModal
var context_menu: PopupMenu
var creation_menu: PopupMenu
var validation_modal: ValidationModal

# Search Component
var search_modal: SearchModal
var search_data_cache: Dictionary = {}

# Delete Confirmation
var delete_confirm_modal: ConfirmationDialog
var delete_chk_reciprocal: CheckBox
var _pending_delete_id: String = ""

var status_bar: Panel
var lbl_status_tool: Label
var lbl_status_info: Label
var lbl_status_global: Label
var lbl_status_grid: Label
var lbl_status_zoom: Label
var lbl_status_snap: Label
var btn_center_view: Button

const SIDEPANEL_SCRIPT = preload("res://scripts/ui/SidePanel.gd")
const SEARCH_MODAL_SCRIPT = preload("res://scripts/ui/modals/SearchModal.gd")
const VALIDATION_MODAL_SCRIPT = preload("res://scripts/ui/modals/ValidationModal.gd")

func setup(layer: CanvasLayer):
	ui_layer = layer
	
	side_panel = SIDEPANEL_SCRIPT.new()
	var main_vbox = side_panel.setup()
	_forward_side_panel_signals()
	ui_layer.add_child(side_panel)
	
	_setup_footer(main_vbox)
	_setup_status_bar()
	_setup_modals_and_popups()
	
	search_modal = SEARCH_MODAL_SCRIPT.new()
	ui_layer.add_child(search_modal)
	search_modal.setup()
	search_modal.request_jump_to_room.connect(func(f, id): request_jump_to_error.emit(f, id))
	search_modal.request_select_db_entry.connect(func(t, id): request_select_db_entry.emit(t, id))

func _forward_side_panel_signals():
	side_panel.request_load_region.connect(func(f): request_load_region.emit(f))
	side_panel.request_jump_to_room.connect(func(id): request_jump_to_room.emit(id))
	side_panel.snap_toggled.connect(func(b): snap_toggled.emit(b); update_status_snap(b))
	side_panel.request_validate.connect(func(): request_validate.emit())
	side_panel.tool_changed.connect(func(m, d): tool_changed.emit(m, d))
	side_panel.request_create_db_entry.connect(func(t): request_create_db_entry.emit(t))
	side_panel.request_delete_db_entry.connect(func(t, id): request_delete_db_entry.emit(t, id))
	side_panel.request_select_db_entry.connect(func(t, id): request_select_db_entry.emit(t, id))
	side_panel.request_auto_layout.connect(func(): request_auto_layout.emit())
	side_panel.request_create_modal_open.connect(func(): 
		creator_modal.show()
		creator_modal.move_to_front() 
	)
	side_panel.request_context_menu.connect(func(p, m): request_context_menu.emit(p, m))

func _setup_footer(main_vbox: VBoxContainer):
	main_vbox.add_child(HSeparator.new())
	footer_container = VBoxContainer.new()
	main_vbox.add_child(footer_container)
	
	# View Mode Dropdown
	var hb_view = HBoxContainer.new()
	var lbl_v = Label.new(); lbl_v.text = "Color By:"; lbl_v.add_theme_font_size_override("font_size", 10); lbl_v.modulate = Color(0.7,0.7,0.7)
	hb_view.add_child(lbl_v)
	
	opt_view_mode = OptionButton.new()
	opt_view_mode.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	opt_view_mode.add_item("Default")
	opt_view_mode.add_item("Biome")
	opt_view_mode.add_item("Zone")
	opt_view_mode.add_item("Danger")
	opt_view_mode.add_item("Terrain")
	_apply_style(opt_view_mode, Color(0.1, 0.1, 0.12))
	opt_view_mode.item_selected.connect(func(idx): view_mode_changed.emit(opt_view_mode.get_item_text(idx)))
	hb_view.add_child(opt_view_mode)
	footer_container.add_child(hb_view)
	
	footer_container.add_child(HSeparator.new())
	
	btn_world_view = Button.new()
	btn_world_view.text = "🌍  WORLD MAP"; btn_world_view.toggle_mode = true
	btn_world_view.custom_minimum_size.y = 40; btn_world_view.alignment = HORIZONTAL_ALIGNMENT_CENTER
	_apply_style(btn_world_view, Color(0.2, 0.2, 0.25))
	
	btn_world_view.toggled.connect(func(b): 
		btn_world_view.text = "🔙  REGION VIEW" if b else "🌍  WORLD MAP"
		request_toggle_world_view.emit(b)
		side_panel.update_layout_btn_text(b)
	)
	footer_container.add_child(btn_world_view)
	side_panel.gui_input.connect(_on_panel_gui_input)

# Helper to sync button state without emitting signals
func set_world_view_button_state(active: bool):
	btn_world_view.set_pressed_no_signal(active)
	btn_world_view.text = "🔙  REGION VIEW" if active else "🌍  WORLD MAP"
	side_panel.update_layout_btn_text(active)

func _setup_status_bar():
	status_bar = Panel.new()
	status_bar.anchor_top = 0.96; status_bar.anchor_bottom = 1.0; status_bar.anchor_right = 1.0
	var style = StyleBoxFlat.new(); style.bg_color = Color(0.08, 0.08, 0.1); style.border_width_top = 1; style.border_color = Color(0.3, 0.3, 0.35)
	status_bar.add_theme_stylebox_override("panel", style)
	ui_layer.add_child(status_bar)
	
	var hbox = HBoxContainer.new(); hbox.set_anchors_preset(15); hbox.offset_left = 10; hbox.offset_right = -10
	status_bar.add_child(hbox)
	
	var btn_copy = Button.new(); btn_copy.text = "Copy"; _apply_style(btn_copy)
	btn_copy.pressed.connect(func(): request_copy.emit())
	hbox.add_child(btn_copy)
	
	var btn_paste = Button.new(); btn_paste.text = "Paste"; _apply_style(btn_paste)
	btn_paste.pressed.connect(func(): request_paste.emit())
	hbox.add_child(btn_paste)
	hbox.add_child(VSeparator.new())
	
	lbl_status_tool = Label.new(); lbl_status_tool.text = "TOOL: SELECT"; lbl_status_tool.custom_minimum_size.x = 200; lbl_status_tool.clip_text = true; lbl_status_tool.add_theme_font_size_override("font_size", 12)
	hbox.add_child(lbl_status_tool); hbox.add_child(VSeparator.new())
	
	lbl_status_info = Label.new(); lbl_status_info.text = "No Region Loaded"; lbl_status_info.size_flags_horizontal = 3; lbl_status_info.horizontal_alignment = 1; lbl_status_info.add_theme_color_override("font_color", Color.LIGHT_GRAY); lbl_status_info.add_theme_font_size_override("font_size", 12)
	hbox.add_child(lbl_status_info); hbox.add_child(VSeparator.new())
	
	var btn_search = Button.new(); btn_search.text = "🔍"; _apply_style(btn_search)
	btn_search.pressed.connect(show_search_modal)
	hbox.add_child(btn_search); hbox.add_child(VSeparator.new())
	
	lbl_status_global = Label.new(); lbl_status_global.text = "XY: 0, 0"; lbl_status_global.custom_minimum_size.x = 140; lbl_status_global.add_theme_font_override("font", ThemeDB.get_fallback_font())
	hbox.add_child(lbl_status_global); hbox.add_child(VSeparator.new())
	
	lbl_status_grid = Label.new(); lbl_status_grid.text = "G: 0, 0"; lbl_status_grid.custom_minimum_size.x = 80; lbl_status_grid.add_theme_font_override("font", ThemeDB.get_fallback_font())
	hbox.add_child(lbl_status_grid); hbox.add_child(VSeparator.new())
	
	lbl_status_snap = Label.new(); lbl_status_snap.text = "SNAP: OFF"; lbl_status_snap.custom_minimum_size.x = 80; lbl_status_snap.add_theme_font_size_override("font_size", 12); lbl_status_snap.modulate = Color(1, 1, 1, 0.5)
	hbox.add_child(lbl_status_snap); hbox.add_child(VSeparator.new())
	
	lbl_status_zoom = Label.new(); lbl_status_zoom.text = "100%"; lbl_status_zoom.custom_minimum_size.x = 50; lbl_status_zoom.horizontal_alignment = 2
	hbox.add_child(lbl_status_zoom)
	
	btn_center_view = Button.new(); btn_center_view.text = "⌖"; btn_center_view.tooltip_text = "Recenter View (F)"; _apply_style(btn_center_view)
	btn_center_view.pressed.connect(func(): request_center_view.emit()); hbox.add_child(btn_center_view)

func _setup_modals_and_popups():
	creator_modal = CreatorModal.new(); ui_layer.add_child(creator_modal); creator_modal.setup()
	creator_modal.request_create_region.connect(func(n,d): request_create_region.emit(n,d))
	context_menu = PopupMenu.new(); ui_layer.add_child(context_menu); context_menu.id_pressed.connect(func(id): context_action.emit(id))
	creation_menu = PopupMenu.new(); ui_layer.add_child(creation_menu)
	for i in range(12): creation_menu.add_item("", i) 
	
	validation_modal = VALIDATION_MODAL_SCRIPT.new()
	ui_layer.add_child(validation_modal)
	validation_modal.setup()
	validation_modal.request_jump_to_error.connect(func(f, r): request_jump_to_error.emit(f, r))

	delete_confirm_modal = ConfirmationDialog.new()
	delete_confirm_modal.title = "Confirm Deletion"
	delete_confirm_modal.min_size = Vector2i(300, 150)
	var del_vbox = VBoxContainer.new(); del_vbox.alignment = BoxContainer.ALIGNMENT_CENTER
	delete_confirm_modal.add_child(del_vbox)
	var lbl = Label.new(); lbl.text = "Are you sure you want to delete this room?"; lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	del_vbox.add_child(lbl)
	delete_chk_reciprocal = CheckBox.new(); delete_chk_reciprocal.text = "Remove incoming references?"
	delete_chk_reciprocal.button_pressed = true; delete_chk_reciprocal.tooltip_text = "If checked, doors leading TO this room from neighbors will also be removed."
	del_vbox.add_child(delete_chk_reciprocal)
	ui_layer.add_child(delete_confirm_modal)
	delete_confirm_modal.confirmed.connect(func(): request_delete_room_confirm.emit(_pending_delete_id, delete_chk_reciprocal.button_pressed))

func show_delete_room_prompt(id: String):
	_pending_delete_id = id
	delete_confirm_modal.popup_centered()

func show_search_modal():
	search_modal.show_modal()

func cache_search_data(world_data, npcs, items):
	search_data_cache.clear()
	search_data_cache["world"] = world_data
	search_data_cache["npcs"] = npcs
	search_data_cache["items"] = items
	search_modal.cache_search_data(world_data, npcs, items)

func update_db_lists(npcs: Dictionary, items: Dictionary, templates: Dictionary, magic: Dictionary, quests: Dictionary, dirty_flags: Dictionary): 
	side_panel.update_db_lists(npcs, items, templates, magic, quests, dirty_flags)
func refresh_explorer(h, c, s): side_panel.refresh_explorer(h, c, s) 
func select_room_item(id): side_panel.select_room_item(id)
func update_dirty_visuals(cur, dirty, rooms): side_panel.update_dirty_visuals(cur, dirty, rooms)
func update_layout_btn_text(is_world: bool): side_panel.update_layout_btn_text(is_world)

func show_context_menu(items: Dictionary):
	context_menu.clear(); for l in items: context_menu.add_item(l, items[l])
	context_menu.position = Vector2(ui_layer.get_viewport().get_mouse_position()); context_menu.popup()

func show_creation_menu(position: Vector2): creation_menu.position = position; creation_menu.popup()

func show_validation_results(errors: Array):
	validation_modal.populate_and_show(errors)

func is_mouse_over_ui() -> bool:
	if creator_modal.visible: return true
	if search_modal.visible: return true
	if validation_modal.visible: return true
	if delete_confirm_modal.visible: return true
	var m = ui_layer.get_viewport().get_mouse_position()
	if side_panel.get_global_rect().has_point(m) or status_bar.get_global_rect().has_point(m): return true
	return false

func _on_panel_gui_input(event: InputEvent):
	if event is InputEventMouseButton and event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN]:
		ui_layer.get_viewport().set_input_as_handled()

func update_tool_display(mode: int, data: Dictionary):
	side_panel.update_stamp_button_state(mode == ToolMode.STAMP)
	match mode:
		ToolMode.SELECT: lbl_status_tool.text = "TOOL: SELECT"; lbl_status_tool.modulate = Color.WHITE
		ToolMode.PAINT: lbl_status_tool.text = "PAINT [%s=%s]" % [data.key, data.val]; lbl_status_tool.modulate = Color.GREEN
		ToolMode.STAMP:
			var txt = "STAMP [%s]" % data.id
			if data.has("type") and data.type == "room_template": txt = "STAMP TEMPLATE [%s]" % data.id
			lbl_status_tool.text = txt; lbl_status_tool.modulate = Color.CYAN

func update_status_info(region_name: String, room_count: int, prefix: String = "", exit_count: int = -1):
	var text = ""
	if prefix != "":
		text = "%s (%s, %d rooms)" % [region_name, prefix, room_count]
	else:
		if exit_count >= 0:
			text = "%s (%d rooms, %d exits)" % [region_name.capitalize(), room_count, exit_count]
		else:
			text = "%s (%d rooms)" % [region_name.capitalize(), room_count] if room_count >= 0 else region_name
	
	lbl_status_info.text = text

func update_status_coords(global_pos: Vector2):
	lbl_status_global.text = "XY: %d, %d" % [int(global_pos.x), int(global_pos.y)]
	lbl_status_grid.text = "G: %d, %d" % [int(round(global_pos.x / 250.0)), int(round(global_pos.y / 250.0))]
func update_status_zoom(zoom_val: Vector2): lbl_status_zoom.text = "Zoom: %d%%" % int(zoom_val.x * 100)
func update_status_snap(enabled: bool): lbl_status_snap.text = "SNAP: ON" if enabled else "SNAP: OFF"; lbl_status_snap.modulate = Color.WHITE if enabled else Color(1, 1, 1, 0.5)

func _apply_style(node: Control, bg_color = Color(0.15, 0.15, 0.18)):
	var s = StyleBoxFlat.new(); s.bg_color = bg_color; s.set_border_width_all(1); s.border_color = Color(0.4, 0.4, 0.45); s.set_corner_radius_all(4); s.content_margin_left = 8; s.content_margin_right = 8
	if node is Button:
		node.add_theme_stylebox_override("normal", s); node.add_theme_stylebox_override("hover", s.duplicate()); node.add_theme_stylebox_override("pressed", s.duplicate())
		node.get_theme_stylebox("hover").bg_color = bg_color.lightened(0.1); node.get_theme_stylebox("pressed").bg_color = bg_color.darkened(0.1)
