# scripts/ui/inspectors/sub_inspectors/NPCInspector.gd

class_name NPCInspector
extends RefCounted

signal database_modified

var container: VBoxContainer
var cur_data: Dictionary
var loot_box: VBoxContainer

func build(c: VBoxContainer, data: Dictionary):
	container = c
	cur_data = data
	_build_stats()
	_build_loot_table()

func _build_stats():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Combat Stats"))
	
	var card = InspectorStyle.create_card(); var vbox = card.get_child(0).get_child(0)
	container.add_child(card)
	
	# Basic
	var hb_basic = HBoxContainer.new()
	vbox.add_child(hb_basic)
	_add_spin_field(hb_basic, "Level", "level", 1)
	_add_spin_field(hb_basic, "Health", "health", 10)
	_add_spin_field(hb_basic, "Mana", "max_mana", 0)
	
	# Attributes Grid
	vbox.add_child(InspectorStyle.lbl("Attributes:", InspectorStyle.COLOR_TEXT_DIM))
	var grid = GridContainer.new(); grid.columns = 2
	grid.add_theme_constant_override("h_separation", 20)
	vbox.add_child(grid)
	
	if not cur_data.has("stats"): cur_data["stats"] = {}
	var stats = cur_data.stats
	
	var attr_keys = ["strength", "dexterity", "constitution", "agility", "intelligence", "wisdom", "spell_power", "magic_resist"]
	for k in attr_keys:
		_add_stat_row(grid, k.capitalize(), k, stats)

func _add_spin_field(parent, label, key, default):
	var vb = VBoxContainer.new(); vb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vb.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var sb = SpinBox.new(); sb.value = cur_data.get(key, default)
	sb.value_changed.connect(func(v): cur_data[key] = v; database_modified.emit())
	InspectorStyle.apply_input_style(sb)
	vb.add_child(sb); parent.add_child(vb)

func _add_stat_row(parent, label, key, stats_dict):
	var hb = HBoxContainer.new(); hb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var l = Label.new(); l.text = label; l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	hb.add_child(l)
	var sb = SpinBox.new(); sb.value = stats_dict.get(key, 0); sb.custom_minimum_size.x = 70
	sb.value_changed.connect(func(v): stats_dict[key] = v; database_modified.emit())
	InspectorStyle.apply_input_style(sb)
	hb.add_child(sb)
	parent.add_child(hb)

func _build_loot_table():
	container.add_child(HSeparator.new())
	var hb = HBoxContainer.new()
	hb.add_child(InspectorStyle.create_sub_header("Loot Table"))
	var spacer = Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; hb.add_child(spacer)
	var btn_add = Button.new(); btn_add.text = "+ Drop"; InspectorStyle.apply_button_style(btn_add)
	btn_add.pressed.connect(_add_loot_entry)
	hb.add_child(btn_add); container.add_child(hb)
	
	loot_box = VBoxContainer.new(); loot_box.add_theme_constant_override("separation", 6)
	container.add_child(loot_box)
	
	if not cur_data.has("loot_table"): cur_data["loot_table"] = {}
	_refresh_loot_table()

func _refresh_loot_table():
	for c in loot_box.get_children(): c.queue_free()
	var table = cur_data.loot_table
	
	for item_id in table:
		var entry = table[item_id]
		var pc = PanelContainer.new()
		var style = StyleBoxFlat.new(); style.bg_color = Color(0.15, 0.15, 0.17); style.set_corner_radius_all(4)
		pc.add_theme_stylebox_override("panel", style)
		
		var m = MarginContainer.new(); m.add_theme_constant_override("margin_left", 5); m.add_theme_constant_override("margin_right", 5)
		pc.add_child(m)
		var hb = HBoxContainer.new(); m.add_child(hb)
		
		# Item ID / Gold
		var lbl_id = Label.new(); lbl_id.text = item_id
		if item_id == "gold_value": lbl_id.modulate = Color.GOLD
		lbl_id.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		hb.add_child(lbl_id)
		
		# Chance
		hb.add_child(InspectorStyle.lbl("Chance:", Color.GRAY))
		var sb_c = SpinBox.new(); sb_c.step = 0.05; sb_c.max_value = 1.0
		sb_c.value = entry.get("chance", 0.0)
		sb_c.custom_minimum_size.x = 60
		InspectorStyle.apply_input_style(sb_c)
		sb_c.value_changed.connect(func(v): entry["chance"] = v; database_modified.emit())
		hb.add_child(sb_c)
		
		# Qty (Range)
		var qty = entry.get("quantity", [1, 1])
		if typeof(qty) != TYPE_ARRAY: qty = [qty, qty]
		
		hb.add_child(InspectorStyle.lbl("Qty:", Color.GRAY))
		var sb_min = SpinBox.new(); sb_min.value = qty[0]; sb_min.custom_minimum_size.x = 50
		InspectorStyle.apply_input_style(sb_min)
		var sb_max = SpinBox.new(); sb_max.value = qty[1]; sb_max.custom_minimum_size.x = 50
		InspectorStyle.apply_input_style(sb_max)
		
		var update_qty = func(_v): entry["quantity"] = [sb_min.value, sb_max.value]; database_modified.emit()
		sb_min.value_changed.connect(update_qty)
		sb_max.value_changed.connect(update_qty)
		
		# Delete
		var btn_del = Button.new(); btn_del.text = "X"; btn_del.flat = true
		btn_del.pressed.connect(func(): table.erase(item_id); database_modified.emit(); _refresh_loot_table())
		hb.add_child(btn_del)
		
		loot_box.add_child(pc)

func _add_loot_entry():
	var popup = PopupMenu.new()
	popup.add_item("Item from DB")
	popup.add_item("Gold Value")
	popup.id_pressed.connect(func(id):
		if id == 1:
			cur_data.loot_table["gold_value"] = {"chance": 0.5, "quantity": [1, 10]}
		else:
			var k = "new_item_" + str(randi() % 100)
			cur_data.loot_table[k] = {"chance": 0.1, "quantity": [1, 1]}
		_refresh_loot_table()
		database_modified.emit()
	)
	container.add_child(popup)
	popup.position = Vector2i(container.get_global_mouse_position())
	popup.popup()
