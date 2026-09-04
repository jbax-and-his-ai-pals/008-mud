# scripts/ui/modals/SearchModal.gd

class_name SearchModal
extends AcceptDialog

signal request_jump_to_room(region, room_id)
signal request_select_db_entry(type, id)

var search_input: LineEdit
var search_scroll: ScrollContainer
var search_results_box: VBoxContainer
var search_data_cache: Dictionary = {}
var selected_search_card: PanelContainer = null
var selected_search_meta = null 

func setup():
	title = "Global Search"
	min_size = Vector2i(600, 500)
	
	var main_vb = VBoxContainer.new()
	main_vb.add_theme_constant_override("separation", 12)
	add_child(main_vb)
	
	# Header & Input
	var input_panel = PanelContainer.new()
	var ip_style = StyleBoxFlat.new()
	ip_style.bg_color = Color(0.12, 0.12, 0.14)
	ip_style.set_corner_radius_all(4)
	ip_style.content_margin_left = 10; ip_style.content_margin_right = 10
	ip_style.content_margin_top = 10; ip_style.content_margin_bottom = 10
	input_panel.add_theme_stylebox_override("panel", ip_style)
	main_vb.add_child(input_panel)
	
	search_input = LineEdit.new()
	search_input.placeholder_text = "Type to search rooms, NPCs, items..."
	search_input.clear_button_enabled = true
	_apply_style(search_input)
	var si_style = search_input.get_theme_stylebox("normal").duplicate()
	si_style.content_margin_top = 8; si_style.content_margin_bottom = 8
	si_style.bg_color = Color(0.08, 0.08, 0.1)
	search_input.add_theme_stylebox_override("normal", si_style)
	input_panel.add_child(search_input)
	
	# Results Scroll Area
	var scroll_bg = PanelContainer.new()
	scroll_bg.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var sb_style = StyleBoxFlat.new()
	sb_style.bg_color = Color(0.08, 0.08, 0.1)
	sb_style.set_border_width_all(1)
	sb_style.border_color = Color(0.2, 0.2, 0.22)
	sb_style.set_corner_radius_all(4)
	scroll_bg.add_theme_stylebox_override("panel", sb_style)
	main_vb.add_child(scroll_bg)
	
	search_scroll = ScrollContainer.new()
	search_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll_bg.add_child(search_scroll)
	
	# List Content
	search_results_box = VBoxContainer.new()
	search_results_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	search_results_box.add_theme_constant_override("separation", 4)
	
	var m = MarginContainer.new() 
	m.add_theme_constant_override("margin_left", 4); m.add_theme_constant_override("margin_right", 4)
	m.add_theme_constant_override("margin_top", 4); m.add_theme_constant_override("margin_bottom", 4)
	m.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	m.add_child(search_results_box)
	search_scroll.add_child(m)

	# Signals
	search_input.text_changed.connect(_on_search_text_changed)
	search_input.text_submitted.connect(func(_t): 
		_confirm_search()
		if search_results_box.get_child_count() > 0: hide() 
	)
	confirmed.connect(_confirm_search)

func show_modal():
	popup_centered()
	search_input.grab_focus()
	search_input.text = ""
	_clear_search_results()

func cache_search_data(world_data: Dictionary, npcs: Dictionary, items: Dictionary):
	search_data_cache.clear()
	search_data_cache["world"] = world_data
	search_data_cache["npcs"] = npcs
	search_data_cache["items"] = items

func _clear_search_results():
	for c in search_results_box.get_children(): c.queue_free()
	selected_search_card = null
	selected_search_meta = null

func _on_search_text_changed(text):
	_clear_search_results()
	if text.length() < 2: return
	
	var term = text.to_lower()
	var world = search_data_cache.get("world", {})
	var count = 0
	const MAX_RESULTS = 50 
	
	# Search Rooms
	for rid in world:
		var r_data = world[rid]
		var region_name = r_data.get("name", rid.capitalize())
		var rooms = r_data.get("rooms", {})
		for room_id in rooms:
			var r_name = rooms[room_id].get("name", "").to_lower()
			if term in room_id.to_lower() or term in r_name:
				_create_search_card(
					rooms[room_id].get("name", "Unnamed"),
					"Room • %s • %s" % [region_name, room_id],
					"📍", Color(0.2, 0.6, 0.8),
					{"type": "room", "region": rid, "id": room_id}
				)
				count += 1
				if count >= MAX_RESULTS: return
	
	# Search NPCs
	var npcs = search_data_cache.get("npcs", {})
	for nid in npcs:
		if term in nid.to_lower() or term in npcs[nid].get("name", "").to_lower():
			_create_search_card(
				npcs[nid].get("name", "Unnamed"),
				"NPC • " + nid,
				"👤", Color(0.8, 0.4, 0.4),
				{"type": "db", "kind": "npc", "id": nid}
			)
			count += 1
			if count >= MAX_RESULTS: return

func _create_search_card(title: String, subtitle: String, icon: String, color: Color, meta: Dictionary):
	var pc = PanelContainer.new()
	pc.mouse_filter = Control.MOUSE_FILTER_STOP
	pc.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	
	var style = StyleBoxFlat.new()
	style.bg_color = Color(0.15, 0.15, 0.17)
	style.set_border_width_all(1)
	style.border_color = Color(0.25, 0.25, 0.28)
	style.set_corner_radius_all(4)
	style.content_margin_left = 8; style.content_margin_right = 8
	style.content_margin_top = 6; style.content_margin_bottom = 6
	pc.add_theme_stylebox_override("panel", style)
	
	var hb = HBoxContainer.new()
	hb.add_theme_constant_override("separation", 12)
	pc.add_child(hb)
	
	# Icon Box
	var icon_box = PanelContainer.new()
	var ib_style = StyleBoxFlat.new()
	ib_style.bg_color = color.darkened(0.7)
	ib_style.set_border_width_all(1)
	ib_style.border_color = color
	ib_style.set_corner_radius_all(4)
	icon_box.add_theme_stylebox_override("panel", ib_style)
	icon_box.custom_minimum_size = Vector2(32, 32)
	
	var l_icon = Label.new()
	l_icon.text = icon
	l_icon.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l_icon.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	icon_box.add_child(l_icon)
	hb.add_child(icon_box)
	
	# Text
	var vb_text = VBoxContainer.new()
	vb_text.alignment = BoxContainer.ALIGNMENT_CENTER
	var l_title = Label.new(); l_title.text = title
	l_title.add_theme_font_size_override("font_size", 14)
	var l_sub = Label.new(); l_sub.text = subtitle
	l_sub.add_theme_font_size_override("font_size", 11)
	l_sub.modulate = Color(0.7, 0.7, 0.75)
	vb_text.add_child(l_title); vb_text.add_child(l_sub)
	hb.add_child(vb_text)
	
	# Store Metadata
	pc.set_meta("search_data", meta)
	
	# Input Handling
	pc.gui_input.connect(func(ev):
		if ev is InputEventMouseButton and ev.button_index == MOUSE_BUTTON_LEFT and ev.pressed:
			_select_search_card(pc)
			if ev.double_click: _confirm_search()
	)
	# Hover visual
	pc.mouse_entered.connect(func(): if pc != selected_search_card: style.bg_color = Color(0.2, 0.2, 0.22))
	pc.mouse_exited.connect(func(): if pc != selected_search_card: style.bg_color = Color(0.15, 0.15, 0.17))
	
	search_results_box.add_child(pc)

func _select_search_card(card: PanelContainer):
	if selected_search_card and is_instance_valid(selected_search_card):
		var old_style = selected_search_card.get_theme_stylebox("panel")
		old_style.bg_color = Color(0.15, 0.15, 0.17)
		old_style.border_color = Color(0.25, 0.25, 0.28)
	
	selected_search_card = card
	selected_search_meta = card.get_meta("search_data")
	
	var new_style = card.get_theme_stylebox("panel")
	new_style.bg_color = Color(0.25, 0.25, 0.35)
	new_style.border_color = Color(0.4, 0.6, 1.0)

func _confirm_search():
	if not selected_search_meta and search_results_box.get_child_count() > 0:
		_select_search_card(search_results_box.get_child(0))
	
	if selected_search_meta:
		var meta = selected_search_meta
		if meta.type == "room":
			request_jump_to_room.emit(meta.region + ".json", meta.id)
		elif meta.type == "db":
			request_select_db_entry.emit(meta.kind, meta.id)
		hide()

func _apply_style(node: Control, bg_color = Color(0.15, 0.15, 0.18)):
	var s = StyleBoxFlat.new(); s.bg_color = bg_color; s.set_border_width_all(1); s.border_color = Color(0.4, 0.4, 0.45); s.set_corner_radius_all(4); s.content_margin_left = 8; s.content_margin_right = 8
	if node is LineEdit:
		var s2 = s.duplicate(); s2.bg_color = Color(0.08,0.08,0.1); node.add_theme_stylebox_override("normal", s2)
