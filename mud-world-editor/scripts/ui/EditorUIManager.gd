# scripts/ui/EditorUIManager.gd
class_name EditorUIManager
extends RefCounted

signal request_load_region(filename)
signal request_jump_to_room(id)
signal request_show_district(region_id, district_id)
signal request_validate
signal request_acknowledge_validation_warning(warning_id)
signal request_reset_ignored_validation_warnings
signal label_arrange_mode_changed(enabled)
signal request_room_label_rename(room_id, new_name)
signal technical_ids_visibility_changed(enabled)
signal request_validate_region_policy
signal request_open_creator_modal
signal request_open_district_modal
signal snap_toggled(is_on)
signal request_create_connection(src, dir, target, twoway)
signal request_create_region(name, room_data)
signal request_place_district(definition)
signal request_district_connection_setup
signal request_district_endpoint_focus(endpoint)
signal request_district_back_to_placement
signal request_district_direction_selected(direction)
signal request_district_confirm(direction)
signal request_district_cancel
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
var district_modal
var district_toolbar: Panel
var district_toolbar_label: Label
var district_direction: OptionButton
var district_confirm: Button
var district_back: Button
var district_discard: Button
var district_source_card: Label
var district_target_card: Label
var district_connection_row: HBoxContainer
var district_connection_summary: Label
var _district_workflow_phase := ""
var context_menu: PopupMenu
var creation_menu: PopupMenu
var validation_modal: ValidationModal
var region_policy_modal: AcceptDialog
var region_policy_label: RichTextLabel

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
var btn_arrange_labels: Button
var btn_technical_ids: Button
var label_edit_dialog: ConfirmationDialog
var label_edit_input: LineEdit
var _label_edit_room_id := ""

const SIDEPANEL_SCRIPT = preload("res://scripts/ui/SidePanel.gd")
const SEARCH_MODAL_SCRIPT = preload("res://scripts/ui/modals/SearchModal.gd")
const VALIDATION_MODAL_SCRIPT = preload("res://scripts/ui/modals/ValidationModal.gd")
const DISTRICT_MODAL_SCRIPT = preload("res://scripts/ui/modals/DistrictModal.gd")

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
	side_panel.request_show_district.connect(func(rid, did): request_show_district.emit(rid, did))
	side_panel.snap_toggled.connect(func(b): snap_toggled.emit(b); update_status_snap(b))
	side_panel.request_validate.connect(func(): request_validate.emit())
	side_panel.request_validate_region_policy.connect(func(): request_validate_region_policy.emit())
	side_panel.tool_changed.connect(func(m, d): tool_changed.emit(m, d))
	side_panel.request_create_db_entry.connect(func(t): request_create_db_entry.emit(t))
	side_panel.request_delete_db_entry.connect(func(t, id): request_delete_db_entry.emit(t, id))
	side_panel.request_select_db_entry.connect(func(t, id): request_select_db_entry.emit(t, id))
	side_panel.request_auto_layout.connect(func(): request_auto_layout.emit())
	side_panel.request_create_modal_open.connect(func():
		request_open_creator_modal.emit()
		creator_modal.show()
		creator_modal.move_to_front()
	)
	side_panel.request_district_modal_open.connect(func(): request_open_district_modal.emit())
	side_panel.request_context_menu.connect(func(p, m): request_context_menu.emit(p, m))

func _setup_footer(main_vbox: VBoxContainer):
	main_vbox.add_child(HSeparator.new())
	# Explorer content sits inside SidePanel's tab margin (5px on each side).
	# Mirror that inset here so the footer controls share the exact same edges as
	# Validate Region Policy and Auto-Arrange Layout above them.
	var footer_margin := MarginContainer.new()
	footer_margin.add_theme_constant_override("margin_left", 5)
	footer_margin.add_theme_constant_override("margin_right", 5)
	main_vbox.add_child(footer_margin)
	footer_container = VBoxContainer.new()
	footer_margin.add_child(footer_container)
	
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
	btn_arrange_labels = Button.new(); btn_arrange_labels.text = "Arrange Labels"; btn_arrange_labels.toggle_mode = true; btn_arrange_labels.tooltip_text = "Click a room label to edit; drag one label onto another to swap."; _apply_style(btn_arrange_labels, Color("554a26"))
	btn_arrange_labels.toggled.connect(func(enabled): label_arrange_mode_changed.emit(enabled))
	hbox.add_child(btn_arrange_labels)
	btn_technical_ids = Button.new(); btn_technical_ids.text = "Technical IDs"; btn_technical_ids.toggle_mode = true; btn_technical_ids.tooltip_text = "Show opaque room IDs on map nodes for debugging and scripting."; _apply_style(btn_technical_ids, Color("303747"))
	btn_technical_ids.toggled.connect(func(enabled): technical_ids_visibility_changed.emit(enabled))
	hbox.add_child(btn_technical_ids)
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
	district_modal = DISTRICT_MODAL_SCRIPT.new(); ui_layer.add_child(district_modal); district_modal.setup()
	district_modal.request_place_district.connect(func(definition): request_place_district.emit(definition))
	_setup_district_toolbar()

func _setup_district_toolbar():
	# Plain Panel keeps the draft bar at a predictable height; a PanelContainer
	# would expand around the inactive connection step and leave a dead zone.
	district_toolbar = Panel.new(); district_toolbar.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	# Leave enough room for a concise error explanation without ever pushing the
	# action row out of the panel.
	district_toolbar.offset_left = -360; district_toolbar.offset_right = 360; district_toolbar.offset_top = -304; district_toolbar.offset_bottom = -20
	var style := StyleBoxFlat.new(); style.bg_color = Color("18283b"); style.border_color = Color("5b9bd5"); style.set_border_width_all(1); style.set_corner_radius_all(8); style.shadow_color = Color(0, 0, 0, 0.5); style.shadow_size = 10; style.content_margin_left = 16; style.content_margin_right = 16; style.content_margin_top = 10; style.content_margin_bottom = 10
	district_toolbar.add_theme_stylebox_override("panel", style); ui_layer.add_child(district_toolbar)
	var box := VBoxContainer.new(); box.set_anchors_preset(Control.PRESET_FULL_RECT); box.offset_left = 16; box.offset_right = -16; box.offset_top = 14; box.offset_bottom = -16; box.add_theme_constant_override("separation", 8); district_toolbar.add_child(box)
	district_toolbar_label = Label.new(); district_toolbar_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; district_toolbar_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(district_toolbar_label)
	district_connection_row = HBoxContainer.new(); district_connection_row.add_theme_constant_override("separation", 10); box.add_child(district_connection_row)
	district_source_card = _district_endpoint_label("◌  District port\nChoose a ghost room", Color("a5dfc5")); district_connection_row.add_child(district_source_card)
	var arrow_box := VBoxContainer.new(); arrow_box.alignment = BoxContainer.ALIGNMENT_CENTER; district_connection_row.add_child(arrow_box)
	district_direction = OptionButton.new(); district_direction.tooltip_text = "Reciprocal connection directions"; district_direction.custom_minimum_size.x = 128
	district_direction.add_item("Choose reciprocal directions…"); district_direction.set_item_metadata(0, "")
	for pair in [["north ↔ south", "north"], ["south ↔ north", "south"], ["east ↔ west", "east"], ["west ↔ east", "west"], ["northeast ↔ southwest", "northeast"], ["northwest ↔ southeast", "northwest"], ["southeast ↔ northwest", "southeast"], ["southwest ↔ northeast", "southwest"], ["up ↔ down", "up"], ["down ↔ up", "down"]]:
		district_direction.add_item(pair[0]); district_direction.set_item_metadata(district_direction.item_count - 1, pair[1])
	district_direction.item_selected.connect(func(index): request_district_direction_selected.emit(str(district_direction.get_item_metadata(index))))
	arrow_box.add_child(district_direction)
	district_target_card = _district_endpoint_label("◎  Town destination\nChoose a room", Color("a9d6f5")); district_connection_row.add_child(district_target_card)
	district_connection_summary = Label.new(); district_connection_summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; district_connection_summary.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; district_connection_summary.add_theme_font_size_override("font_size", 12); district_connection_summary.modulate = Color("d3e8fb"); box.add_child(district_connection_summary)
	var spacer := Control.new(); spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL; box.add_child(spacer)
	var controls := HBoxContainer.new(); controls.add_theme_constant_override("separation", 10); box.add_child(controls)
	district_discard = Button.new(); district_discard.text = "Cancel"; _apply_style(district_discard, Color("5a3d48")); _pad_district_action(district_discard); district_discard.pressed.connect(func(): request_district_cancel.emit()); controls.add_child(district_discard)
	district_back = Button.new(); district_back.text = "Move District"; _apply_style(district_back, Color("3f4c60")); _pad_district_action(district_back); district_back.pressed.connect(func(): request_district_back_to_placement.emit()); controls.add_child(district_back)
	var horizontal_spacer := Control.new(); horizontal_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; controls.add_child(horizontal_spacer)
	district_confirm = Button.new(); district_confirm.text = "Choose Connection"; _apply_style(district_confirm, Color("23744d")); _pad_district_action(district_confirm); district_confirm.pressed.connect(_on_district_primary); controls.add_child(district_confirm)
	district_toolbar.hide()

func set_district_workflow(phase: String, port: String = "", target: String = "", port_name: String = "", target_name: String = "", active_endpoint: String = "source", title: String = "", direction: String = "north", connection_errors: Array = [], footprint_valid: bool = true):
	_district_workflow_phase = phase
	if phase == "": district_toolbar.hide(); return
	district_toolbar.show(); district_toolbar.move_to_front()
	if phase == "placement":
		district_toolbar_label.text = "Place District"
		_select_district_direction(direction)
		district_connection_row.show(); district_connection_row.modulate = Color(1, 1, 1, 0.38); district_direction.disabled = true
		district_connection_summary.hide()
		district_back.hide(); district_discard.text = "Cancel"
		district_confirm.text = "Confirm Placement"; district_confirm.disabled = false
	else:
		district_connection_row.show()
		district_connection_row.modulate = Color.WHITE; district_direction.disabled = false
		_select_district_direction(direction)
		var source_text := ("%s\n%s" % [port_name, port]) if port_name != "" else (port if port != "" else "choose a ghost room")
		var target_text := ("%s\n%s" % [target_name, target]) if target_name != "" else (target if target != "" else "choose a Town room")
		district_toolbar_label.text = title if title != "" else "Select connection endpoint"
		district_source_card.text = "◌  District port\n%s" % source_text
		district_target_card.text = "◎  Town destination\n%s" % target_text
		_style_endpoint_card(district_source_card, Color("a5dfc5"), active_endpoint == "source")
		_style_endpoint_card(district_target_card, Color("a9d6f5"), active_endpoint == "target")
		district_back.show(); district_discard.text = "Cancel"
		var direction_ready := str(district_direction.get_item_metadata(district_direction.selected)) != ""
		if port != "" and target != "" and direction_ready:
			var forward := str(district_direction.get_item_metadata(district_direction.selected))
			var reverse := str(Constants.INV_DIR_MAP.get(forward, ""))
			var source_name := port_name if port_name != "" else port
			var destination_name := target_name if target_name != "" else target
			# Read the chosen pair left-to-right: district port first, town room second.
			district_connection_summary.text = "%s connects %s to %s\n%s connects %s to %s" % [source_name, forward, destination_name, destination_name, reverse, source_name]
			if not connection_errors.is_empty():
				var displayed_errors: Array = connection_errors.slice(0, 2)
				if connection_errors.size() > displayed_errors.size(): displayed_errors.append("+%d more obstruction(s)." % (connection_errors.size() - displayed_errors.size()))
				district_connection_summary.text += "\n⚠ " + "\n⚠ ".join(displayed_errors)
				district_connection_summary.modulate = Color("ff9a9a")
			else:
				district_connection_summary.modulate = Color("d3e8fb")
			district_connection_summary.show()
		else:
			district_connection_summary.hide()
		district_confirm.text = "Confirm Connection"; district_confirm.disabled = port == "" or target == "" or not direction_ready or not footprint_valid or not connection_errors.is_empty()

func _on_district_primary():
	if _district_workflow_phase == "placement": request_district_connection_setup.emit()
	elif _district_workflow_phase == "connection": request_district_confirm.emit(str(district_direction.get_item_metadata(district_direction.selected)))

func _select_district_direction(direction: String):
	for index in range(district_direction.item_count):
		if str(district_direction.get_item_metadata(index)) == direction:
			district_direction.select(index)
			return
	district_direction.select(1) # North ↔ South is the stable fallback.

func _pad_district_action(button: Button):
	button.custom_minimum_size.y = 38
	for state_name in ["normal", "hover", "pressed"]:
		var action_style = button.get_theme_stylebox(state_name)
		if action_style is StyleBoxFlat:
			action_style.content_margin_left = 14
			action_style.content_margin_right = 14
			action_style.content_margin_top = 7
			action_style.content_margin_bottom = 7

func _district_endpoint_label(text: String, color: Color) -> Label:
	var label := Label.new(); label.text = text; label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; label.custom_minimum_size = Vector2(190, 45); label.size_flags_horizontal = Control.SIZE_EXPAND_FILL; label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER; label.add_theme_font_size_override("font_size", 12); label.modulate = color; label.mouse_filter = Control.MOUSE_FILTER_STOP
	label.gui_input.connect(func(event): if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed: request_district_endpoint_focus.emit("source" if label == district_source_card else "target"))
	_style_endpoint_card(label, color, false)
	return label

func _style_endpoint_card(label: Label, color: Color, active: bool):
	var style := StyleBoxFlat.new(); style.bg_color = color.darkened(0.68) if active else Color("101c2d"); style.border_color = color.lightened(0.25) if active else color.darkened(0.35); style.set_border_width_all(3 if active else 1); style.set_corner_radius_all(5); style.content_margin_left = 10; style.content_margin_right = 10; style.content_margin_top = 5; style.content_margin_bottom = 5
	label.add_theme_stylebox_override("normal", style)
	context_menu = PopupMenu.new(); ui_layer.add_child(context_menu); context_menu.id_pressed.connect(func(id): context_action.emit(id))
	creation_menu = PopupMenu.new(); ui_layer.add_child(creation_menu)
	for i in range(12): creation_menu.add_item("", i) 
	
	validation_modal = VALIDATION_MODAL_SCRIPT.new()
	ui_layer.add_child(validation_modal)
	validation_modal.setup()
	validation_modal.request_jump_to_error.connect(func(f, r): request_jump_to_error.emit(f, r))
	validation_modal.request_acknowledge_warning.connect(func(warning_id): request_acknowledge_validation_warning.emit(warning_id))
	validation_modal.request_reset_ignored_warnings.connect(func(): request_reset_ignored_validation_warnings.emit())
	label_edit_dialog = ConfirmationDialog.new()
	label_edit_dialog.title = "Edit Room Label"
	label_edit_dialog.min_size = Vector2i(380, 130)
	label_edit_input = LineEdit.new()
	label_edit_input.placeholder_text = "Room name"
	label_edit_input.set_anchors_preset(Control.PRESET_FULL_RECT)
	label_edit_input.offset_left = 18; label_edit_input.offset_right = -18; label_edit_input.offset_top = 16; label_edit_input.offset_bottom = -48
	label_edit_dialog.add_child(label_edit_input)
	label_edit_dialog.confirmed.connect(func():
		var new_name := label_edit_input.text.strip_edges()
		if _label_edit_room_id != "" and new_name != "": request_room_label_rename.emit(_label_edit_room_id, new_name)
		_label_edit_room_id = ""
	)
	ui_layer.add_child(label_edit_dialog)

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

	region_policy_modal = AcceptDialog.new()
	region_policy_modal.title = "Region Policy Check"
	region_policy_modal.min_size = Vector2i(560, 420)
	var rp_scroll = ScrollContainer.new(); rp_scroll.custom_minimum_size = Vector2(540, 380)
	region_policy_label = RichTextLabel.new()
	region_policy_label.bbcode_enabled = true
	region_policy_label.fit_content = true
	region_policy_label.custom_minimum_size = Vector2(520, 0)
	rp_scroll.add_child(region_policy_label)
	region_policy_modal.add_child(rp_scroll)
	ui_layer.add_child(region_policy_modal)

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

func show_validation_results(errors: Array, ignored_count: int = 0):
	validation_modal.populate_and_show(errors, ignored_count)

func show_room_label_editor(room_id: String, current_name: String):
	_label_edit_room_id = room_id
	label_edit_input.text = current_name
	label_edit_dialog.popup_centered()
	label_edit_input.grab_focus()
	label_edit_input.select_all()

func show_region_policy_results(ok: bool, issues: Array, run_error: String = ""):
	if run_error != "":
		region_policy_modal.title = "Region Policy Check -- Could Not Run"
		region_policy_label.text = "[color=orange]%s[/color]" % run_error.replace("[", "[lb]")
	elif ok:
		region_policy_modal.title = "Region Policy Check -- Passed"
		region_policy_label.text = "[color=lime]No policy issues found across every region under data/regions/.[/color]"
	else:
		region_policy_modal.title = "Region Policy Check -- %d Issue(s)" % issues.size()
		var lines: Array = []
		for issue in issues:
			var color = "salmon" if issue.get("severity", "error") == "error" else "orange"
			var path = String(issue.get("path", "")).replace("[", "[lb]")
			var message = String(issue.get("message", "")).replace("[", "[lb]")
			lines.append("[color=%s]%s[/color] -- %s" % [color, message, path])
		region_policy_label.text = "\n".join(lines)
	region_policy_modal.popup_centered()

func is_mouse_over_ui() -> bool:
	# Input can be delivered during the first frame while optional popups are
	# still being assembled, so every modal here must be treated as optional.
	if is_instance_valid(creator_modal) and creator_modal.visible: return true
	if is_instance_valid(district_modal) and district_modal.visible: return true
	if is_instance_valid(search_modal) and search_modal.visible: return true
	if is_instance_valid(validation_modal) and validation_modal.visible: return true
	if is_instance_valid(delete_confirm_modal) and delete_confirm_modal.visible: return true
	var m = ui_layer.get_viewport().get_mouse_position()
	if is_instance_valid(district_toolbar) and district_toolbar.visible and district_toolbar.get_global_rect().has_point(m): return true
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
