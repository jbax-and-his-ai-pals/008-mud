# scripts/ui/inspectors/ConnectionEditor.gd
class_name ConnectionEditor
extends RefCounted

signal connection_created(src, dir, target, twoway, reverse_dir)
signal target_selected(target_id) # New signal to report the current target

# Data References
var conn_hierarchy: Dictionary = {}
var conn_src_id: String = ""
var conn_src_name: String = ""
var conn_cur_reg_filename: String = ""

# GUI References
var conn_dir_edit: LineEdit
var conn_rev_dir_edit: LineEdit
var conn_rev_row: HBoxContainer
var conn_reg_opt: OptionButton
var conn_room_opt: OptionButton
var conn_twoway: CheckBox
var conn_summary_label: Label
var conn_info_label: RichTextLabel
var region_mgr: RegionManager

# Whether the reverse-direction field still tracks the forward direction's
# compass inverse automatically, or the author has taken it over by typing
# their own value -- a mismatched pair (an "opening" back out through
# "out") has no compass inverse to suggest at all, so this is what lets
# that stay a deliberate choice instead of silently producing a one-way
# link the "Two-way Link" checkbox implied wouldn't happen.
var _rev_dir_auto: bool = true
var _updating_rev_field: bool = false

func _init(mgr: RegionManager):
	region_mgr = mgr

func build_ui(parent_container: Control, src_id: String, src_name: String, hierarchy: Dictionary, cur_filename: String, target_id: String = "", dir: String = ""):
	conn_src_id = src_id
	conn_src_name = src_name
	conn_hierarchy = hierarchy
	conn_cur_reg_filename = cur_filename
	
	_clear_box(parent_container)
	
	var header = _lbl("NEW CONNECTION", Color.CYAN)
	header.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	parent_container.add_child(header)
	parent_container.add_child(HSeparator.new())
	
	var src_lbl = _lbl("From: " + src_name, Color.GREEN)
	src_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	parent_container.add_child(src_lbl)
	parent_container.add_child(HSeparator.new())
	
	# --- COMPASS UI ---
	var center_container = CenterContainer.new()
	parent_container.add_child(center_container)
	
	var nav_vbox = VBoxContainer.new()
	nav_vbox.add_theme_constant_override("separation", 8)
	center_container.add_child(nav_vbox)
	
	# 1. Cardinal Directions
	var compass = GridContainer.new()
	compass.columns = 3
	compass.add_theme_constant_override("h_separation", 6)
	compass.add_theme_constant_override("v_separation", 6)
	nav_vbox.add_child(compass)
	
	var compass_map = [
		{"l": "↖", "v": "northwest"}, {"l": "↑", "v": "north"}, {"l": "↗", "v": "northeast"},
		{"l": "←", "v": "west"},      {"l": "•", "v": ""},      {"l": "→", "v": "east"},
		{"l": "↙", "v": "southwest"}, {"l": "↓", "v": "south"}, {"l": "↘", "v": "southeast"}
	]
	
	for item in compass_map:
		if item.v == "":
			var lbl = Label.new(); lbl.text = "•"; lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; lbl.vertical_alignment = VERTICAL_ALIGNMENT_CENTER; lbl.modulate = Color(1, 1, 1, 0.3)
			compass.add_child(lbl)
		else:
			var btn = Button.new(); btn.text = item.l; btn.tooltip_text = item.v.capitalize(); 
			btn.custom_minimum_size = Vector2(40, 40); btn.alignment = HORIZONTAL_ALIGNMENT_CENTER
			_apply_style(btn); btn.add_theme_font_size_override("font_size", 18) 
			btn.pressed.connect(func(): _set_direction(item.v))
			compass.add_child(btn)
	
	# 2. Vertical Directions
	var vertical_grid = GridContainer.new()
	vertical_grid.columns = 2
	vertical_grid.add_theme_constant_override("h_separation", 8)
	vertical_grid.add_theme_constant_override("v_separation", 8)
	nav_vbox.add_child(vertical_grid)
	
	var verticals = ["up", "down", "in", "out", "climb", "dive"]
	for d in verticals:
		var btn = Button.new(); btn.text = d.capitalize(); 
		btn.custom_minimum_size = Vector2(65, 35); btn.alignment = HORIZONTAL_ALIGNMENT_CENTER
		_apply_style(btn); btn.pressed.connect(func(): _set_direction(d))
		vertical_grid.add_child(btn)

	# --- MANUAL ENTRY ---
	parent_container.add_child(_lbl("Direction:", Color.GRAY))
	var dir_hbox = HBoxContainer.new()
	conn_dir_edit = LineEdit.new()
	conn_dir_edit.placeholder_text = "Custom Direction..."
	conn_dir_edit.alignment = HORIZONTAL_ALIGNMENT_CENTER
	conn_dir_edit.size_flags_horizontal = 3
	conn_dir_edit.text = dir
	conn_dir_edit.text_changed.connect(func(t): _on_forward_dir_edited(t))
	_apply_style(conn_dir_edit)
	dir_hbox.add_child(conn_dir_edit)
	parent_container.add_child(dir_hbox)

	parent_container.add_child(HSeparator.new())

	# --- TARGET UI ---
	parent_container.add_child(_lbl("Target Region:", Color.GRAY))
	conn_reg_opt = OptionButton.new(); conn_reg_opt.size_flags_horizontal = Control.SIZE_EXPAND_FILL; _apply_style(conn_reg_opt)
	conn_reg_opt.item_selected.connect(_on_conn_region_changed)
	parent_container.add_child(conn_reg_opt)

	parent_container.add_child(_lbl("Target Room:", Color.GRAY))
	conn_room_opt = OptionButton.new(); conn_room_opt.size_flags_horizontal = Control.SIZE_EXPAND_FILL; _apply_style(conn_room_opt)
	conn_room_opt.item_selected.connect(func(_i): _update_connection_info())
	parent_container.add_child(conn_room_opt)

	conn_twoway = CheckBox.new(); conn_twoway.text = "Two-way Link"; conn_twoway.button_pressed = true
	_apply_style(conn_twoway)
	parent_container.add_child(conn_twoway)

	# The reverse direction only matters for a two-way link, and only needs
	# an author's attention when it isn't a plain compass inverse -- most of
	# the time it's filled in automatically and never touched.
	conn_rev_row = HBoxContainer.new()
	conn_rev_row.add_theme_constant_override("separation", 8)
	var rev_lbl = _lbl("Return via:", Color.GRAY); rev_lbl.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	conn_rev_row.add_child(rev_lbl)
	conn_rev_dir_edit = LineEdit.new()
	conn_rev_dir_edit.placeholder_text = "(no reciprocal -- one-way only)"
	conn_rev_dir_edit.alignment = HORIZONTAL_ALIGNMENT_CENTER
	conn_rev_dir_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	conn_rev_dir_edit.text_changed.connect(func(_t):
		if not _updating_rev_field:
			_rev_dir_auto = false
			_update_connection_info()
	)
	_apply_style(conn_rev_dir_edit)
	conn_rev_row.add_child(conn_rev_dir_edit)
	parent_container.add_child(conn_rev_row)
	conn_twoway.toggled.connect(func(b): conn_rev_row.visible = b; _update_connection_info())

	conn_summary_label = Label.new()
	conn_summary_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	conn_summary_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	conn_summary_label.modulate = Color(0.65, 0.85, 1.0)
	parent_container.add_child(conn_summary_label)

	# --- INFO & WARNINGS ---
	conn_info_label = RichTextLabel.new(); conn_info_label.fit_content = true; conn_info_label.bbcode_enabled = true
	_apply_style(conn_info_label, Color.TRANSPARENT); parent_container.add_child(conn_info_label)
	
	parent_container.add_child(HSeparator.new())
	
	# --- BUTTONS ---
	var btn_box = HBoxContainer.new()
	btn_box.add_theme_constant_override("separation", 10)
	var margin_c = MarginContainer.new() 
	margin_c.add_theme_constant_override("margin_left", 2)
	margin_c.add_theme_constant_override("margin_right", 2)
	margin_c.add_child(btn_box)
	
	var btn = Button.new(); btn.text = "Connect"; btn.size_flags_horizontal = 3
	btn.pressed.connect(_on_connect_confirm); _apply_style(btn, Color(0.2, 0.35, 0.2))
	btn_box.add_child(btn)
	
	var btn_close = Button.new(); btn_close.text = "Cancel"; btn_close.size_flags_horizontal = 3
	btn_close.pressed.connect(func(): target_selected.emit(""))
	_apply_style(btn_close, Color(0.3, 0.1, 0.1))
	btn_box.add_child(btn_close)
	
	parent_container.add_child(margin_c)

	conn_rev_row.visible = conn_twoway.button_pressed
	_sync_auto_reverse(dir)
	_populate_connection_data(target_id)

	if target_id == "":
		conn_dir_edit.grab_focus()

func set_target(region_id: String, room_id: String):
	# 1. Select Region
	var region_found = false
	for i in range(conn_reg_opt.item_count):
		if conn_reg_opt.get_item_metadata(i) == region_id:
			conn_reg_opt.select(i)
			_on_conn_region_changed(i)
			region_found = true
			break
	if not region_found: return
	# 2. Select Room
	var room_found = false
	for i in range(conn_room_opt.item_count):
		if conn_room_opt.get_item_metadata(i) == room_id:
			conn_room_opt.select(i)
			room_found = true
			break
	if room_found:
		_update_connection_info()

func _populate_connection_data(target_id_raw: String):
	conn_reg_opt.clear()
	var regions = conn_hierarchy.keys()
	regions.sort()
	
	var selected_idx = -1
	var idx = 0
	var cur_reg_id = ""
	
	for r in regions:
		if conn_hierarchy[r].filename == conn_cur_reg_filename:
			cur_reg_id = r
			break
			
	for r in regions:
		conn_reg_opt.add_item(r.capitalize()) 
		conn_reg_opt.set_item_metadata(idx, r)
		if r == cur_reg_id:
			selected_idx = idx
		idx += 1
		
	var target_reg = cur_reg_id
	var target_room = target_id_raw
	if ":" in target_id_raw:
		var parts = target_id_raw.split(":")
		target_reg = parts[0]
		target_room = parts[1]
	
	for i in range(conn_reg_opt.item_count):
		if conn_reg_opt.get_item_metadata(i) == target_reg:
			selected_idx = i
			break
	
	if selected_idx != -1:
		conn_reg_opt.select(selected_idx)
	
	_on_conn_region_changed(selected_idx)
	
	if target_room != "":
		for i in range(conn_room_opt.item_count):
			if conn_room_opt.get_item_metadata(i) == target_room:
				conn_room_opt.select(i)
				break
	
	_update_connection_info()

func _on_conn_region_changed(idx):
	conn_room_opt.clear()
	if idx == -1: return
	
	var reg_id = conn_reg_opt.get_item_metadata(idx)
	var data = conn_hierarchy.get(reg_id, {})
	var rooms = data.get("rooms", {})
	
	var room_keys = rooms.keys()
	room_keys.sort()
	
	for r_id in room_keys:
		conn_room_opt.add_item(rooms[r_id])
		conn_room_opt.set_item_metadata(conn_room_opt.item_count - 1, r_id)
	
	_update_connection_info()

# Applying a compass/vertical button sets the outbound direction and, as
# long as the reverse field hasn't been taken over manually, its compass
# inverse too -- so the common case (north <-> south) needs one click, and
# an author who's typed a custom reverse (the "opening" <-> "out" case)
# never has their choice clobbered by a later outbound click.
func _set_direction(direction: String):
	conn_dir_edit.text = direction
	_sync_auto_reverse(direction)
	_update_connection_info()

func _on_forward_dir_edited(direction: String):
	_sync_auto_reverse(direction)
	_update_connection_info()

func _sync_auto_reverse(direction: String):
	if not _rev_dir_auto: return
	var inv = str(Constants.INV_DIR_MAP.get(direction.strip_edges().to_lower(), ""))
	_updating_rev_field = true
	conn_rev_dir_edit.text = inv
	_updating_rev_field = false

func _update_connection_info():
	if not conn_info_label: return
	conn_info_label.text = ""
	var dir = conn_dir_edit.text.strip_edges().to_lower()
	var rev_dir = conn_rev_dir_edit.text.strip_edges().to_lower()
	var msgs = []

	var full_target_id = ""
	if conn_reg_opt.selected != -1 and conn_room_opt.selected != -1:
		var target_reg = conn_reg_opt.get_item_metadata(conn_reg_opt.selected)
		var target_room = conn_room_opt.get_item_metadata(conn_room_opt.selected)
		if target_reg == region_mgr.data.region_id:
			full_target_id = target_room
		else:
			full_target_id = target_reg + ":" + target_room
	target_selected.emit(full_target_id)

	var target_reg = conn_reg_opt.get_item_metadata(conn_reg_opt.selected) if conn_reg_opt.selected != -1 else ""
	var target_room_name := conn_room_opt.get_item_text(conn_room_opt.selected) if conn_room_opt.selected != -1 else ""
	var cur_reg_id = region_mgr.data.get("region_id", "")
	var same_region: bool = target_reg == cur_reg_id

	if conn_twoway.button_pressed and target_room_name != "":
		if dir != "" and rev_dir != "":
			var src_display := conn_src_name if conn_src_name != "" else conn_src_id
			conn_summary_label.text = "%s connects %s to %s\n%s connects %s to %s" % [
				src_display, dir.capitalize(), target_room_name, target_room_name, rev_dir.capitalize(), src_display,
			]
			conn_summary_label.visible = true
		else:
			conn_summary_label.visible = false
	else:
		conn_summary_label.visible = false

	if region_mgr.data.rooms.has(conn_src_id):
		var src_exits = region_mgr.data.rooms[conn_src_id].get("exits", {})
		if dir != "" and src_exits.has(dir):
			msgs.append("[color=salmon]⚠ Source has exit '%s' -> %s (Overwrite)[/color]" % [dir, src_exits[dir]])

	if conn_room_opt.selected != -1 and conn_twoway.button_pressed:
		if same_region:
			if rev_dir == "":
				msgs.append("[color=orange]⚠ No reverse direction set -- this will be a one-way exit only.[/color]")
			else:
				var target_id = conn_room_opt.get_item_metadata(conn_room_opt.selected)
				if region_mgr.data.rooms.has(target_id) and region_mgr.data.rooms[target_id].get("exits", {}).has(rev_dir):
					msgs.append("[color=orange]⚠ Target has exit '%s' -> %s (Overwrite)[/color]" % [rev_dir, region_mgr.data.rooms[target_id].exits[rev_dir]])
		else:
			msgs.append("[color=gray]Cross-region: add the return exit from the other region.[/color]")

	if msgs.is_empty():
		conn_info_label.text = "[color=gray]Connection looks clear.[/color]"
	else:
		conn_info_label.text = "\n".join(msgs)

func _on_connect_confirm():
	var dir = conn_dir_edit.text
	if dir.strip_edges() == "": return
	if conn_room_opt.selected == -1: return
	var target_room = conn_room_opt.get_item_metadata(conn_room_opt.selected)
	var target_reg = conn_reg_opt.get_item_metadata(conn_reg_opt.selected)
	var final_target = target_reg + ":" + target_room
	var rev_dir = conn_rev_dir_edit.text.strip_edges() if conn_twoway.button_pressed else ""

	target_selected.emit("") # Clear highlight after connecting
	connection_created.emit(conn_src_id, dir, final_target, conn_twoway.button_pressed, rev_dir)

	conn_dir_edit.text = ""
	conn_info_label.text = "[color=green]Connection Created.[/color]"

func _apply_style(node: Control, bg_color = Color(0.15,0.15,0.18)):
	var s=StyleBoxFlat.new(); s.bg_color=bg_color; s.set_border_width_all(1); s.border_color=Color(0.4,0.4,0.45); s.set_corner_radius_all(4); s.content_margin_left=8
	if node is Button:
		if node is CheckBox:
			s.content_margin_left = 4; s.content_margin_right = 4; node.alignment = HORIZONTAL_ALIGNMENT_LEFT
			var s_unchecked = s.duplicate(); s_unchecked.bg_color = Color(0.25, 0.1, 0.1); s_unchecked.border_color = Color(0.5, 0.3, 0.3)
			var s_checked = s.duplicate(); s_checked.bg_color = Color(0.1, 0.3, 0.15); s_checked.border_color = Color(0.3, 0.6, 0.4)
			node.add_theme_stylebox_override("normal", s_unchecked)
			node.add_theme_stylebox_override("pressed", s_checked)
			node.add_theme_stylebox_override("hover", s_unchecked.duplicate()) 
			node.add_theme_stylebox_override("hover_pressed", s_checked.duplicate()) 
			node.get_theme_stylebox("hover").bg_color = s_unchecked.bg_color.lightened(0.1)
			node.get_theme_stylebox("hover_pressed").bg_color = s_checked.bg_color.lightened(0.1)
			node.add_theme_stylebox_override("focus", s_unchecked.duplicate())
		else:
			node.add_theme_stylebox_override("normal", s)
			node.add_theme_stylebox_override("hover", s.duplicate())
			node.add_theme_stylebox_override("pressed", s.duplicate())
			node.add_theme_stylebox_override("focus", s.duplicate())
			node.get_theme_stylebox("hover").bg_color = bg_color.lightened(0.1)
			node.get_theme_stylebox("pressed").bg_color = bg_color.darkened(0.1)
			node.get_theme_stylebox("focus").bg_color = bg_color.lightened(0.05)
	elif node is LineEdit or node is TextEdit: s.bg_color=Color(0.08,0.08,0.1); node.add_theme_stylebox_override("normal", s)

func _lbl(t,c=Color.WHITE): var l=Label.new(); l.text=t; l.modulate=c; return l
func _clear_box(b): for c in b.get_children(): c.queue_free()
