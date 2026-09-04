# scripts/ui/inspectors/panels/RoomContentPanel.gd
class_name RoomContentPanel
extends RefCounted

signal data_modified

# Data
var cur_data: Dictionary
var database_mgr: DatabaseManager

# UI
var npc_box: VBoxContainer
var item_box: VBoxContainer

func build(parent_container: VBoxContainer, data: Dictionary, db_mgr: DatabaseManager):
	cur_data = data
	database_mgr = db_mgr

	parent_container.add_child(InspectorStyle.create_section_header("CONTENT"))
	var card = InspectorStyle.create_card()
	var vbox = card.get_child(0).get_child(0)
	parent_container.add_child(card)
	
	vbox.add_child(InspectorStyle.lbl("NPCs", InspectorStyle.COLOR_TEXT_DIM))
	npc_box = VBoxContainer.new(); npc_box.add_theme_constant_override("separation", 6)
	vbox.add_child(npc_box)
	
	vbox.add_child(HSeparator.new())
	
	vbox.add_child(InspectorStyle.lbl("Items", InspectorStyle.COLOR_TEXT_DIM))
	item_box = VBoxContainer.new(); item_box.add_theme_constant_override("separation", 6)
	vbox.add_child(item_box)
	
	_refresh_content()

func _refresh_content():
	for c in npc_box.get_children(): c.queue_free()
	for c in item_box.get_children(): c.queue_free()
	
	# NPCs
	if cur_data.has("initial_npcs") and not cur_data.initial_npcs.is_empty():
		var idx = 0
		for n in cur_data.initial_npcs:
			var row = _create_content_row("npc", n, idx)
			npc_box.add_child(row)
			idx += 1
	else:
		var l = Label.new(); l.text="No NPCs."; l.modulate=Color(1,1,1,0.3); l.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER
		l.size_flags_vertical = Control.SIZE_SHRINK_CENTER; npc_box.add_child(l)
		
	var btn_n = Button.new(); btn_n.text="+ Add NPC"; btn_n.alignment = HORIZONTAL_ALIGNMENT_CENTER
	InspectorStyle.apply_button_style(btn_n, Color(0.2, 0.2, 0.25))
	btn_n.pressed.connect(func():
		if not cur_data.has("initial_npcs"): cur_data.initial_npcs = []
		cur_data.initial_npcs.append({"template_id": "villager"})
		data_modified.emit(); _refresh_content()
	)
	npc_box.add_child(btn_n)
	
	# Items
	if cur_data.has("items") and not cur_data.items.is_empty():
		var idx = 0
		for i in cur_data.items:
			var row = _create_content_row("item", i, idx)
			item_box.add_child(row)
			idx += 1
	else:
		var l = Label.new(); l.text="No Items."; l.modulate=Color(1,1,1,0.3); l.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER
		l.size_flags_vertical = Control.SIZE_SHRINK_CENTER; item_box.add_child(l)
		
	var btn_i = Button.new(); btn_i.text="+ Add Item"; btn_i.alignment = HORIZONTAL_ALIGNMENT_CENTER
	InspectorStyle.apply_button_style(btn_i, Color(0.2, 0.2, 0.25))
	btn_i.pressed.connect(func():
		if not cur_data.has("items"): cur_data.items = []
		cur_data.items.append({"item_id": "gold_coin"})
		data_modified.emit(); _refresh_content()
	)
	item_box.add_child(btn_i)

func _create_content_row(type, data, idx) -> PanelContainer:
	var pc = PanelContainer.new()
	var style = StyleBoxFlat.new(); style.bg_color = Color(0.15, 0.15, 0.17); style.set_corner_radius_all(4)
	pc.add_theme_stylebox_override("panel", style)
	
	var m = MarginContainer.new(); m.add_theme_constant_override("margin_left", 5); m.add_theme_constant_override("margin_right", 5)
	pc.add_child(m)
	
	var hb = HBoxContainer.new(); m.add_child(hb)
	var ico = Label.new(); ico.text = "👤" if type == "npc" else "📦"; hb.add_child(ico)
	
	var vb_in = VBoxContainer.new(); vb_in.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vb_in.add_theme_constant_override("separation", 2); hb.add_child(vb_in)
	
	if type == "npc":
		var hb1 = HBoxContainer.new(); hb1.add_child(InspectorStyle.lbl("T:", InspectorStyle.COLOR_TEXT_DIM))
		var ed_t = LineEdit.new(); ed_t.text = data.get("template_id", ""); ed_t.placeholder_text = "Template ID"
		ed_t.size_flags_horizontal = Control.SIZE_EXPAND_FILL; ed_t.flat = true
		InspectorStyle.apply_input_style(ed_t); ed_t.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
		ed_t.text_submitted.connect(func(t): data.template_id = t; data_modified.emit()); hb1.add_child(ed_t)
		InspectorStyle.add_suggestion_button(hb1, ed_t, func(): return database_mgr.get_npc_ids()); vb_in.add_child(hb1)
		
		var hb2 = HBoxContainer.new(); hb2.add_child(InspectorStyle.lbl("I:", InspectorStyle.COLOR_TEXT_DIM))
		var ed_i = LineEdit.new(); ed_i.text = data.get("instance_id", ""); ed_i.placeholder_text = "Instance (Opt)"
		ed_i.size_flags_horizontal = Control.SIZE_EXPAND_FILL; ed_i.flat = true
		InspectorStyle.apply_input_style(ed_i); ed_i.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
		ed_i.text_changed.connect(func(t): data.instance_id = t; data_modified.emit()); hb2.add_child(ed_i); vb_in.add_child(hb2)
	else:
		var hb1 = HBoxContainer.new()
		var ed_id = LineEdit.new(); ed_id.text = data.get("item_id", "")
		ed_id.size_flags_horizontal = Control.SIZE_EXPAND_FILL; ed_id.flat = true
		InspectorStyle.apply_input_style(ed_id); ed_id.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
		ed_id.text_submitted.connect(func(t): data.item_id = t; data_modified.emit()); hb1.add_child(ed_id)
		InspectorStyle.add_suggestion_button(hb1, ed_id, func(): return database_mgr.get_item_ids())
		
		hb1.add_child(InspectorStyle.lbl("x", InspectorStyle.COLOR_TEXT_DIM))
		var sb = SpinBox.new(); sb.value = data.get("quantity", 1); sb.custom_minimum_size.x = 60
		InspectorStyle.apply_input_style(sb); sb.value_changed.connect(func(v): data.quantity = v; data_modified.emit()); hb1.add_child(sb)
		vb_in.add_child(hb1)
	
	var btn_del = Button.new(); btn_del.text = "🗑"; btn_del.flat = true
	btn_del.pressed.connect(func(): 
		if type == "npc": cur_data.initial_npcs.remove_at(idx)
		else: cur_data.items.remove_at(idx)
		data_modified.emit(); _refresh_content()
	)
	hb.add_child(btn_del)
	
	return pc
