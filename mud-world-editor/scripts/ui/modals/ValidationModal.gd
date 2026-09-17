# scripts/ui/modals/ValidationModal.gd
class_name ValidationModal
extends Control

signal request_jump_to_error(file, room)
signal request_acknowledge_warning(warning_id)
signal request_reset_ignored_warnings

var results_tree: Tree
var title_label: Label
var acknowledge_button: Button
var reset_button: Button

func setup():
	hide()
	
	# 1. Full Screen Configuration
	# Explicitly anchor to fill the viewport to ensure background covers everything
	anchor_left = 0.0
	anchor_top = 0.0
	anchor_right = 1.0
	anchor_bottom = 1.0
	offset_left = 0
	offset_top = 0
	offset_right = 0
	offset_bottom = 0
	
	z_index = 100
	mouse_filter = Control.MOUSE_FILTER_STOP
	
	# 2. Dimmer Background
	var dimmer = ColorRect.new()
	dimmer.set_anchors_preset(Control.PRESET_FULL_RECT)
	dimmer.color = Color(0, 0, 0, 0.6)
	dimmer.mouse_filter = Control.MOUSE_FILTER_STOP
	dimmer.gui_input.connect(func(ev):
		if ev is InputEventMouseButton and ev.button_index == MOUSE_BUTTON_LEFT and ev.pressed:
			hide()
	)
	add_child(dimmer)
	
	# 3. Centering Layout
	var center_container = CenterContainer.new()
	center_container.set_anchors_preset(Control.PRESET_FULL_RECT)
	# Let clicks pass through the container to the dimmer
	center_container.mouse_filter = Control.MOUSE_FILTER_IGNORE 
	add_child(center_container)
	
	# 4. Window Panel
	var window = PanelContainer.new()
	window.custom_minimum_size = Vector2(900, 560)
	window.mouse_filter = Control.MOUSE_FILTER_STOP # Catch clicks inside window
	
	var style = StyleBoxFlat.new()
	style.bg_color = Color(0.15, 0.15, 0.18)
	style.set_border_width_all(2)
	style.border_color = Color(0.4, 0.6, 1.0)
	style.shadow_size = 8
	style.shadow_color = Color(0, 0, 0, 0.5)
	style.content_margin_left = 20; style.content_margin_right = 20
	style.content_margin_top = 20; style.content_margin_bottom = 20
	window.add_theme_stylebox_override("panel", style)
	
	center_container.add_child(window)
	
	# 5. Content
	var vbox = VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 12)
	window.add_child(vbox)
	
	title_label = Label.new()
	title_label.text = "World Validation Results"
	title_label.add_theme_font_size_override("font_size", 18)
	title_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vbox.add_child(title_label)
	vbox.add_child(HSeparator.new())
	
	# Tree Area
	var tree_bg = PanelContainer.new()
	tree_bg.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var t_style = StyleBoxFlat.new()
	t_style.bg_color = Color(0.1, 0.1, 0.12)
	t_style.set_border_width_all(1)
	t_style.border_color = Color(0.3, 0.3, 0.35)
	tree_bg.add_theme_stylebox_override("panel", t_style)
	vbox.add_child(tree_bg)
	
	results_tree = Tree.new()
	results_tree.hide_root = true
	results_tree.columns = 1
	results_tree.set_column_expand(0, true)
	results_tree.item_activated.connect(_on_item_activated)
	tree_bg.add_child(results_tree)
	
	# Footer
	var footer := HBoxContainer.new()
	footer.add_theme_constant_override("separation", 10)
	vbox.add_child(footer)
	acknowledge_button = Button.new()
	acknowledge_button.text = "Acknowledge Warning"
	acknowledge_button.disabled = true
	_apply_button_style(acknowledge_button)
	acknowledge_button.pressed.connect(_on_acknowledge_pressed)
	footer.add_child(acknowledge_button)
	reset_button = Button.new()
	reset_button.text = "Reset Ignored Warnings"
	_apply_button_style(reset_button)
	reset_button.pressed.connect(func(): request_reset_ignored_warnings.emit())
	footer.add_child(reset_button)
	var footer_spacer := Control.new()
	footer_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	footer.add_child(footer_spacer)
	var btn_close = Button.new()
	btn_close.text = "Close"
	btn_close.custom_minimum_size.x = 100
	btn_close.size_flags_horizontal = Control.SIZE_SHRINK_END
	_apply_button_style(btn_close)
	btn_close.pressed.connect(func(): hide())
	footer.add_child(btn_close)
	results_tree.item_selected.connect(_on_item_selected)

func populate_and_show(errors: Array, ignored_count: int = 0):
	results_tree.clear()
	acknowledge_button.disabled = true
	reset_button.disabled = ignored_count == 0
	var root = results_tree.create_item()
	
	if errors.is_empty():
		title_label.text = "Validation Successful" if ignored_count == 0 else "Validation Successful (%d acknowledged warning(s) hidden)" % ignored_count
		var item = results_tree.create_item(root)
		item.set_text(0, "No errors found! The world is consistent.")
		item.set_custom_color(0, Color.GREEN)
	else:
		title_label.text = "Validation Issues Found (%d)" % errors.size()
		if ignored_count > 0: title_label.text += " · %d acknowledged hidden" % ignored_count
		# Icons
		var err_icon = get_theme_icon("error", "EditorIcons") 
		if not err_icon: err_icon = get_theme_icon("Error", "EditorIcons") 
		var warn_icon = get_theme_icon("warning", "EditorIcons")
		if not warn_icon: warn_icon = get_theme_icon("Warning", "EditorIcons")
		
		var regions = {}
		
		for e_str in errors:
			# Format: "[RegionID] RoomID -> ... message"
			var parts = e_str.split("] ")
			var region_id = parts[0].trim_prefix("[")
			
			if not regions.has(region_id):
				regions[region_id] = results_tree.create_item(root)
				regions[region_id].set_text(0, "Region: " + region_id.capitalize())
				regions[region_id].set_custom_color(0, Color.GOLD)
				regions[region_id].set_selectable(0, false)
			
			var err_item = results_tree.create_item(regions[region_id])
			var msg = parts[1] if parts.size() > 1 else e_str
			var room_id = msg.substr(0, msg.find(" "))
			var summary_text: String = msg
			var detail_text: String = ""
			var colon: int = msg.find(": ")
			if colon >= 0:
				summary_text = msg.substr(0, colon)
				detail_text = msg.substr(colon + 2)
			err_item.set_text(0, summary_text)
			err_item.set_tooltip_text(0, msg)
			
			if "One-way" in msg:
				err_item.set_icon(0, warn_icon)
				err_item.set_custom_color(0, Color.ORANGE)
			else:
				err_item.set_icon(0, err_icon)
				err_item.set_custom_color(0, Color.SALMON)
				
			err_item.set_metadata(0, {"file": region_id + ".json", "room": room_id, "warning_id": e_str if "One-way" in msg else ""})
			# Keep the full explanation visible instead of forcing a narrow second
			# column to truncate it. This line is still actionable on activation.
			if detail_text != "":
				var detail_item = results_tree.create_item(err_item)
				detail_item.set_text(0, "↳ " + detail_text)
				detail_item.set_custom_color(0, Color(0.75, 0.78, 0.84))
				detail_item.set_tooltip_text(0, detail_text)
				detail_item.set_metadata(0, {"file": region_id + ".json", "room": room_id, "warning_id": e_str if "One-way" in msg else ""})
	
	show()
	move_to_front()

func _on_item_selected():
	var item := results_tree.get_selected()
	var data = item.get_metadata(0) if item else {}
	acknowledge_button.disabled = not (data is Dictionary and str(data.get("warning_id", "")) != "")

func _on_acknowledge_pressed():
	var item := results_tree.get_selected()
	if not item: return
	var data = item.get_metadata(0)
	if data is Dictionary and str(data.get("warning_id", "")) != "": request_acknowledge_warning.emit(str(data.warning_id))

func _on_item_activated():
	var item = results_tree.get_selected()
	if item and item.get_metadata(0):
		var data = item.get_metadata(0)
		request_jump_to_error.emit(data.file, data.room)
		hide()

func _apply_button_style(btn: Button):
	var s = StyleBoxFlat.new()
	s.bg_color = Color(0.2, 0.25, 0.3)
	s.set_border_width_all(1)
	s.border_color = Color(0.4, 0.4, 0.45)
	s.set_corner_radius_all(4)
	s.content_margin_top = 5; s.content_margin_bottom = 5
	btn.add_theme_stylebox_override("normal", s)
	btn.add_theme_stylebox_override("hover", s.duplicate())
	btn.add_theme_stylebox_override("pressed", s.duplicate())
	btn.get_theme_stylebox("hover").bg_color = Color(0.25, 0.3, 0.35)
