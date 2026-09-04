# scripts/ui/inspectors/sub_inspectors/ItemInspector.gd

class_name ItemInspector
extends RefCounted

signal database_modified

var container: VBoxContainer
var cur_data: Dictionary
var props_box: VBoxContainer

func build(c: VBoxContainer, data: Dictionary):
	container = c
	cur_data = data
	_build_details()
	_build_properties()

func _build_details():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Details"))
	
	var card = InspectorStyle.create_card(); var vbox = card.get_child(0).get_child(0)
	container.add_child(card)
	
	# Type
	var hb = HBoxContainer.new()
	hb.add_child(InspectorStyle.lbl("Type:", InspectorStyle.COLOR_TEXT_DIM))
	var type_opt = OptionButton.new()
	var item_types = ["Weapon", "Armor", "Consumable", "Treasure", "Gem", "Junk", "Key", "Tool", "Item", "Material"]
	for t in item_types: type_opt.add_item(t)
	var current_type = cur_data.get("type", "Item")
	var idx = item_types.find(current_type)
	if idx != -1: type_opt.selected = idx
	else:
		type_opt.add_item(current_type)
		type_opt.select(type_opt.item_count - 1)
	type_opt.item_selected.connect(func(i): cur_data.type = type_opt.get_item_text(i); database_modified.emit())
	type_opt.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_button_style(type_opt)
	hb.add_child(type_opt)
	vbox.add_child(hb)
	
	# Weight & Value
	var hb2 = HBoxContainer.new()
	_add_spin_field(hb2, "Weight", "weight", 0.0)
	_add_spin_field(hb2, "Value", "value", 0)
	vbox.add_child(hb2)
	
	# Stackable
	var chk = CheckBox.new(); chk.text = "Stackable"
	chk.button_pressed = cur_data.get("stackable", false)
	chk.toggled.connect(func(b): cur_data.stackable = b; database_modified.emit())
	vbox.add_child(chk)

func _add_spin_field(parent, label, key, default):
	var vb = VBoxContainer.new(); vb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vb.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var sb = SpinBox.new(); sb.value = cur_data.get(key, default)
	sb.value_changed.connect(func(v): cur_data[key] = v; database_modified.emit())
	InspectorStyle.apply_input_style(sb)
	vb.add_child(sb); parent.add_child(vb)

func _build_properties():
	container.add_child(HSeparator.new())
	var hb = HBoxContainer.new()
	hb.add_child(InspectorStyle.create_sub_header("Item Properties"))
	var spacer = Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; hb.add_child(spacer)
	var btn_add = Button.new(); btn_add.text = "+ Prop"; InspectorStyle.apply_button_style(btn_add)
	
	var pp = PopupMenu.new()
	pp.add_item("String"); pp.add_item("Number"); pp.add_item("Bool"); pp.add_item("Equip Slot")
	pp.id_pressed.connect(_add_item_prop)
	btn_add.pressed.connect(func(): pp.position = Vector2i(btn_add.get_screen_position()) + Vector2i(0, 30); pp.popup())
	container.add_child(pp)
	
	hb.add_child(btn_add); container.add_child(hb)
	
	props_box = VBoxContainer.new(); props_box.add_theme_constant_override("separation", 6)
	container.add_child(props_box)
	
	if not cur_data.has("properties"): cur_data["properties"] = {}
	_refresh_props()

func _add_item_prop(id):
	var k = "new_prop"
	var v = ""
	if id == 1: v = 0
	elif id == 2: v = false
	elif id == 3: k = "equip_slot"; v = []
	cur_data.properties[k] = v
	database_modified.emit()
	_refresh_props()

func _refresh_props():
	for c in props_box.get_children(): c.queue_free()
	var props = cur_data.properties
	for key in props:
		var val = props[key]
		var panel = PanelContainer.new()
		var style = StyleBoxFlat.new(); style.bg_color = Color(0.25, 0.25, 0.28); style.set_corner_radius_all(6)
		style.content_margin_left = 10; style.content_margin_right = 10; style.content_margin_top = 4; style.content_margin_bottom = 4
		panel.add_theme_stylebox_override("panel", style)
		
		var hb = HBoxContainer.new(); panel.add_child(hb)
		
		if key == "equip_slot":
			var l = Label.new(); l.text = "Equip Slots"; l.modulate = Color.CYAN; hb.add_child(l)
		else:
			var ed_k = LineEdit.new(); ed_k.text = key; ed_k.custom_minimum_size.x = 120
			InspectorStyle.apply_input_style(ed_k)
			ed_k.text_submitted.connect(func(t): 
				if t != key and not props.has(t):
					props[t] = val; props.erase(key); database_modified.emit(); _refresh_props()
			)
			hb.add_child(ed_k)
		
		var spacer = Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; hb.add_child(spacer)
		
		if key == "equip_slot" and typeof(val) == TYPE_ARRAY:
			var btn_slots = MenuButton.new(); btn_slots.text = "Select Slots..."
			if not val.is_empty(): btn_slots.text = ",".join(val)
			InspectorStyle.apply_button_style(btn_slots)
			var popup = btn_slots.get_popup()
			popup.hide_on_checkable_item_selection = false
			var slots = ["head", "body", "legs", "feet", "main_hand", "off_hand", "neck", "hands", "ring"]
			for s in slots:
				popup.add_check_item(s)
				popup.set_item_checked(popup.item_count-1, val.has(s))
			popup.index_pressed.connect(func(idx):
				var s_name = slots[idx]
				if val.has(s_name): val.erase(s_name)
				else: val.append(s_name)
				popup.set_item_checked(idx, val.has(s_name))
				btn_slots.text = ",".join(val) if not val.is_empty() else "Select Slots..."
				database_modified.emit()
			)
			hb.add_child(btn_slots)
		elif typeof(val) == TYPE_BOOL:
			var chk = CheckBox.new(); chk.button_pressed = val; chk.text = "True" if val else "False"
			chk.toggled.connect(func(b): props[key] = b; chk.text = "True" if b else "False"; database_modified.emit())
			hb.add_child(chk)
		elif typeof(val) == TYPE_FLOAT or typeof(val) == TYPE_INT:
			var sb = SpinBox.new(); sb.step = 0.1; sb.allow_greater = true; sb.allow_lesser = true
			sb.value = val; sb.custom_minimum_size.x = 80
			InspectorStyle.apply_input_style(sb); sb.value_changed.connect(func(v): props[key] = v; database_modified.emit())
			hb.add_child(sb)
		else:
			var ed_v = LineEdit.new(); ed_v.text = str(val); ed_v.custom_minimum_size.x = 150
			InspectorStyle.apply_input_style(ed_v); ed_v.text_changed.connect(func(t): props[key] = t; database_modified.emit())
			hb.add_child(ed_v)
			
		var btn_x = Button.new(); btn_x.text = "×"; btn_x.flat = true
		btn_x.add_theme_color_override("font_color", Color(0.6, 0.6, 0.6))
		btn_x.add_theme_color_override("font_hover_color", Color.RED)
		btn_x.pressed.connect(func(): props.erase(key); database_modified.emit(); _refresh_props())
		hb.add_child(btn_x)
		
		props_box.add_child(panel)
