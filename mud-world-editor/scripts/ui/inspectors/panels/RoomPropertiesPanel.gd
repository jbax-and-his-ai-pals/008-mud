# scripts/ui/inspectors/panels/RoomPropertiesPanel.gd
class_name RoomPropertiesPanel
extends RefCounted

signal data_modified

# Data
var cur_props: Dictionary

# UI
var props_box: VBoxContainer
var flow_container: HFlowContainer
var creation_tag: PanelContainer = null
var popup_menu: PopupMenu # New property to hold a direct reference

const COMMON_PROPS = {
	"Dark": {"key": "dark", "val": true},
	"Outdoors": {"key": "outdoors", "val": true},
	"Safe Zone": {"key": "safe_zone", "val": true},
	"Noisy": {"key": "noisy", "val": true},
	"Start Node": {"key": "is_start_node", "val": true},
	"Icon": {"key": "icon", "val": "none"},
	"Smell": {"key": "smell", "val": "damp earth"},
	"Weather": {"key": "weather", "val": "clear"},
	"Music": {"key": "music", "val": "default_theme"}
}

func build(parent_container: VBoxContainer, properties_data: Dictionary):
	cur_props = properties_data
	
	var header_box = HBoxContainer.new()
	header_box.add_child(InspectorStyle.create_section_header("PROPERTIES"))
	var spacer = Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header_box.add_child(spacer)
	
	var btn_add = MenuButton.new(); btn_add.text = "+ Tag"; btn_add.flat = true
	btn_add.add_theme_color_override("font_color", InspectorStyle.COLOR_ACCENT)
	btn_add.add_theme_color_override("font_hover_color", Color.WHITE)
	header_box.add_child(btn_add)
	parent_container.add_child(header_box)
	
	var card = InspectorStyle.create_card()
	var vbox = card.get_child(0).get_child(0)
	parent_container.add_child(card)
	
	popup_menu = btn_add.get_popup() # Store the reference here
	popup_menu.id_pressed.connect(_on_add_tag_selected)
	
	props_box = VBoxContainer.new()
	vbox.add_child(props_box)
	_refresh_props()

func _on_add_tag_selected(id):
	var item_text = popup_menu.get_item_text(id) # Use the stored reference
	if item_text == "Custom...":
		_show_creation_tag()
	else:
		var key = COMMON_PROPS[item_text].key
		var val = COMMON_PROPS[item_text].val
		if not cur_props.has(key):
			cur_props[key] = val
			data_modified.emit()
			_refresh_props()

func _show_creation_tag():
	if is_instance_valid(creation_tag): return # Already adding one
	
	creation_tag = PanelContainer.new()
	var style = StyleBoxFlat.new(); style.bg_color = Color(0.3, 0.3, 0.35); style.set_corner_radius_all(12)
	style.content_margin_left = 6; style.content_margin_right = 6; style.content_margin_top = 2; style.content_margin_bottom = 2
	creation_tag.add_theme_stylebox_override("panel", style)
	
	var hb = HBoxContainer.new(); creation_tag.add_child(hb)
	
	var key_edit = LineEdit.new(); key_edit.placeholder_text = "key"; key_edit.name = "KeyEdit"
	InspectorStyle.apply_input_style(key_edit); hb.add_child(key_edit)
	
	var type_select = OptionButton.new(); type_select.name = "TypeSelect"
	type_select.add_item("String"); type_select.add_item("Number"); type_select.add_item("Bool")
	InspectorStyle.apply_button_style(type_select); hb.add_child(type_select)
	
	var val_edit = LineEdit.new(); val_edit.placeholder_text = "value"; val_edit.name = "ValueEdit"
	InspectorStyle.apply_input_style(val_edit); hb.add_child(val_edit)
	
	var confirm_btn = Button.new(); confirm_btn.text = "✔"
	InspectorStyle.apply_button_style(confirm_btn, InspectorStyle.COLOR_SUCCESS); hb.add_child(confirm_btn)
	
	var cancel_btn = Button.new(); cancel_btn.text = "✖"
	InspectorStyle.apply_button_style(cancel_btn, InspectorStyle.COLOR_DANGER); hb.add_child(cancel_btn)
	
	flow_container.add_child(creation_tag)
	key_edit.grab_focus()
	
	confirm_btn.pressed.connect(_finalize_new_prop)
	cancel_btn.pressed.connect(_cancel_new_prop)
	key_edit.text_submitted.connect(func(_t): _finalize_new_prop())
	val_edit.text_submitted.connect(func(_t): _finalize_new_prop())

func _finalize_new_prop():
	if not is_instance_valid(creation_tag): return
	
	var key = creation_tag.get_node("KeyEdit").text.strip_edges()
	var type_idx = creation_tag.get_node("TypeSelect").selected
	var val_str = creation_tag.get_node("ValueEdit").text.strip_edges()
	
	if key.is_empty() or cur_props.has(key):
		# Visual feedback for error would be good here, but for now we just cancel
		_cancel_new_prop()
		return

	var final_val
	match type_idx:
		0: # String
			final_val = val_str
		1: # Number
			if val_str.is_valid_float(): final_val = val_str.to_float()
			else: final_val = 0.0
		2: # Bool
			final_val = val_str.to_lower() in ["true", "1", "yes", "on"]
	
	cur_props[key] = final_val
	creation_tag.queue_free()
	creation_tag = null
	data_modified.emit()
	_refresh_props()

func _cancel_new_prop():
	if is_instance_valid(creation_tag):
		creation_tag.queue_free()
		creation_tag = null

func _refresh_props():
	if is_instance_valid(flow_container):
		for c in flow_container.get_children():
			if c != creation_tag:
				c.queue_free()
	else:
		for c in props_box.get_children(): c.queue_free()
		flow_container = HFlowContainer.new()
		flow_container.add_theme_constant_override("h_separation", 8)
		flow_container.add_theme_constant_override("v_separation", 8)
		props_box.add_child(flow_container)

	# Update the dropdown menu for adding tags
	popup_menu.clear() # Use the stored reference
	var sorted_common_keys = COMMON_PROPS.keys()
	sorted_common_keys.sort()
	for k in sorted_common_keys:
		if not cur_props.has(COMMON_PROPS[k].key):
			popup_menu.add_item(k)
	popup_menu.add_separator()
	popup_menu.add_item("Custom...")
	
	if cur_props.is_empty():
		var l = Label.new(); l.text = "None."; l.modulate = Color(1,1,1,0.3); l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		flow_container.add_child(l)
		return
	
	for key in cur_props:
		var val = cur_props[key]
		var tag = _create_prop_tag(key, val)
		flow_container.add_child(tag)

func _create_prop_tag(key, val) -> PanelContainer:
	var panel = PanelContainer.new()
	var style = StyleBoxFlat.new(); style.bg_color = Color(0.25, 0.25, 0.28); style.set_corner_radius_all(12)
	style.content_margin_left = 10; style.content_margin_right = 6; style.content_margin_top = 2; style.content_margin_bottom = 2
	panel.add_theme_stylebox_override("panel", style)
	
	var hb = HBoxContainer.new(); panel.add_child(hb)
	
	var lbl = Label.new(); lbl.text = key + ": "; lbl.modulate = Color(0.7, 0.9, 1.0)
	lbl.add_theme_font_size_override("font_size", 12); hb.add_child(lbl)
	
	if typeof(val) == TYPE_BOOL:
		var btn = Button.new(); btn.text = str(val).to_upper(); btn.flat = true
		btn.add_theme_font_size_override("font_size", 12)
		btn.add_theme_color_override("font_color", InspectorStyle.COLOR_SUCCESS if val else InspectorStyle.COLOR_DANGER)
		btn.pressed.connect(func(): cur_props[key] = !val; data_modified.emit(); _refresh_props())
		hb.add_child(btn)
	else:
		var ed = LineEdit.new(); ed.text = str(val); ed.flat = true; ed.expand_to_text_length = true; ed.custom_minimum_size.x = 30
		ed.add_theme_font_size_override("font_size", 12); ed.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
		ed.text_submitted.connect(func(t): 
			if typeof(val) == TYPE_FLOAT or typeof(val) == TYPE_INT:
				cur_props[key] = t.to_float() if t.is_valid_float() else val
			else:
				cur_props[key] = t
			data_modified.emit()
			_refresh_props() # Refresh to ensure type consistency if input was bad
		)
		hb.add_child(ed)
		
	var del = Button.new(); del.text = "×"; del.flat = true
	del.add_theme_font_size_override("font_size", 14); del.add_theme_color_override("font_color", Color(0.5, 0.5, 0.5))
	del.add_theme_color_override("font_hover_color", Color(1, 0.5, 0.5))
	del.pressed.connect(func(): cur_props.erase(key); data_modified.emit(); _refresh_props()); hb.add_child(del)
	return panel
