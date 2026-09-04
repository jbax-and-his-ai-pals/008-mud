# scripts/ui/inspectors/panels/RoomConnectionsPanel.gd
class_name RoomConnectionsPanel
extends RefCounted

signal data_modified
signal request_connection_form(id, name)

# Data
var cur_exits: Dictionary
var cur_id: String
var cur_name: String
var region_mgr: RegionManager
var world_mgr: WorldManager
var world_data_cache: Dictionary

# UI
var exits_box: VBoxContainer

func build(parent_container: VBoxContainer, id: String, name: String, exits_data: Dictionary, r_mgr: RegionManager, w_mgr: WorldManager):
	cur_id = id
	cur_name = name
	cur_exits = exits_data
	region_mgr = r_mgr
	world_mgr = w_mgr
	world_data_cache = world_mgr.get_all_world_data()
	
	parent_container.add_child(InspectorStyle.create_section_header("CONNECTIONS"))
	var card = InspectorStyle.create_card()
	var vbox = card.get_child(0).get_child(0)
	parent_container.add_child(card)
	
	exits_box = VBoxContainer.new()
	exits_box.add_theme_constant_override("separation", 6)
	vbox.add_child(exits_box)
	_refresh_exits()
	
	vbox.add_child(HSeparator.new())
	
	var m = MarginContainer.new(); m.add_theme_constant_override("margin_bottom", 4)
	var btn = Button.new(); btn.text = "🔗 Link New Connection"; btn.alignment = HORIZONTAL_ALIGNMENT_CENTER
	btn.pressed.connect(func(): request_connection_form.emit(cur_id, cur_name))
	InspectorStyle.apply_button_style(btn, Color(0.2, 0.25, 0.3))
	m.add_child(btn)
	vbox.add_child(m)

func _refresh_exits():
	for c in exits_box.get_children(): c.queue_free()
	var keys = cur_exits.keys(); keys.sort()
	
	if keys.is_empty():
		var l = Label.new(); l.text = "No connections."; l.modulate = Color(1,1,1,0.3); l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		exits_box.add_child(l)
		return

	for dir in keys:
		var target = cur_exits[dir]
		var row = _create_exit_row(dir, target)
		exits_box.add_child(row)

func _create_exit_row(dir, target) -> PanelContainer:
	var is_ext = ":" in target
	var pc = PanelContainer.new()
	var style = StyleBoxFlat.new(); style.bg_color = Color(0.12, 0.12, 0.14); style.set_corner_radius_all(4)
	
	if is_ext: style.border_width_bottom = 2; style.border_color = Color(0.8, 0.6, 0.2)
	else:
		style.border_width_left = 3
		match dir:
			"north","south","east","west": style.border_color = Color(0.3, 0.6, 0.9)
			"up","down","climb","dive": style.border_color = Color(0.7, 0.4, 0.8)
			_: style.border_color = Color(0.4, 0.8, 0.5)
			
	pc.add_theme_stylebox_override("panel", style)
	
	var m = MarginContainer.new()
	m.add_theme_constant_override("margin_left", 8); m.add_theme_constant_override("margin_right", 8)
	m.add_theme_constant_override("margin_top", 4); m.add_theme_constant_override("margin_bottom", 4)
	pc.add_child(m)
	
	var hb = HBoxContainer.new(); hb.add_theme_constant_override("separation", 10); m.add_child(hb)
	
	var l_dir = Label.new(); l_dir.text = dir.to_upper(); l_dir.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	l_dir.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT; l_dir.add_theme_font_size_override("font_size", 12)
	if is_ext: l_dir.modulate = Color(0.9, 0.8, 0.5)
	hb.add_child(l_dir)
	
	var is_two_way = false
	if not is_ext and region_mgr.data.rooms.has(target):
		var t_exits = region_mgr.data.rooms[target].get("exits", {})
		if t_exits.values().has(cur_id): is_two_way = true
	
	var arrow = Label.new(); arrow.text = "⇄" if is_two_way else "→"
	arrow.modulate = InspectorStyle.COLOR_SUCCESS if is_two_way else Color(1,1,1,0.3)
	if is_ext: arrow.modulate = Color(0.9, 0.8, 0.5)
	hb.add_child(arrow)
	
	var vb_t = VBoxContainer.new(); vb_t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vb_t.add_theme_constant_override("separation", 0)
	
	var t_name = target
	if is_ext:
		var parts = target.split(":")
		var target_region_id = parts[0]
		var target_room_id = parts[1]
		if world_data_cache.has(target_region_id) and world_data_cache[target_region_id].rooms.has(target_room_id):
			t_name = world_data_cache[target_region_id].rooms[target_room_id].get("name", "Unnamed")
	elif region_mgr.data.rooms.has(target): 
		t_name = region_mgr.data.rooms[target].get("name", "Unnamed")
	
	var l_name = Label.new(); l_name.text = t_name; l_name.clip_text = true; l_name.add_theme_font_size_override("font_size", 14)
	var l_id = Label.new(); l_id.text = target; l_id.clip_text = true; l_id.add_theme_font_size_override("font_size", 10); l_id.modulate = Color(1,1,1,0.5)
	vb_t.add_child(l_name); vb_t.add_child(l_id); hb.add_child(vb_t)
	
	var btn_del = Button.new(); btn_del.text = "🗑"; btn_del.flat = true
	btn_del.add_theme_color_override("font_color", Color(0.6, 0.3, 0.3))
	btn_del.add_theme_color_override("font_hover_color", Color(1.0, 0.4, 0.4))
	btn_del.pressed.connect(func(): cur_exits.erase(dir); data_modified.emit(); _refresh_exits())
	hb.add_child(btn_del)
	
	return pc
