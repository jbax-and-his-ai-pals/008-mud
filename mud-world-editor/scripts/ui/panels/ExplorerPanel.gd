class_name ExplorerPanel
extends VBoxContainer

signal request_load_region(filename)
signal request_jump_to_room(id)
signal request_show_district(region_id, district_id)
signal request_create_modal_open
signal request_district_modal_open
signal request_validate
signal request_validate_region_policy
signal request_auto_layout
signal snap_toggled(enabled)
signal request_context_menu(global_pos, meta)

var search_bar: LineEdit
var explorer_tree: Tree
var snap_checkbox: CheckBox
var expanded_regions: Dictionary = {}
var expanded_districts: Dictionary = {}
var _is_programmatic_selection: bool = false

func setup():
	add_theme_constant_override("separation", 12)
	
	search_bar = LineEdit.new()
	search_bar.placeholder_text = "Filter..."
	_apply_style(search_bar)
	search_bar.text_changed.connect(func(_t): refresh_tree())
	add_child(search_bar)
	
	explorer_tree = Tree.new()
	explorer_tree.size_flags_vertical = SIZE_EXPAND_FILL
	explorer_tree.hide_root = true
	explorer_tree.select_mode = Tree.SELECT_ROW
	explorer_tree.allow_rmb_select = true
	
	explorer_tree.item_selected.connect(_on_tree_select)
	explorer_tree.item_activated.connect(_on_tree_activate)
	explorer_tree.item_collapsed.connect(_on_tree_collapse)
	explorer_tree.gui_input.connect(_on_tree_gui_input)
	
	var tree_style = StyleBoxFlat.new()
	tree_style.bg_color = Color(0.05, 0.05, 0.08)
	explorer_tree.add_theme_stylebox_override("bg", tree_style)
	add_child(explorer_tree)
	
	snap_checkbox = CheckBox.new()
	snap_checkbox.text = "Snap to Grid"
	snap_checkbox.button_pressed = true
	_apply_checkbox_style(snap_checkbox)
	snap_checkbox.toggled.connect(func(b): snap_toggled.emit(b))
	add_child(snap_checkbox)
	
	call_deferred("emit_signal", "snap_toggled", snap_checkbox.button_pressed)
	
	var btn_row = HBoxContainer.new()
	btn_row.add_theme_constant_override("separation", 8)
	var btn_new = Button.new(); btn_new.text="New Region"; btn_new.size_flags_horizontal=3
	btn_new.pressed.connect(func(): request_create_modal_open.emit())
	_apply_style(btn_new)
	btn_row.add_child(btn_new)
	var btn_district = Button.new(); btn_district.text="New District"; btn_district.size_flags_horizontal=3
	btn_district.pressed.connect(func(): request_district_modal_open.emit())
	_apply_style(btn_district)
	btn_row.add_child(btn_district)
	
	var btn_val = Button.new(); btn_val.text="Validate"; btn_val.size_flags_horizontal=3
	btn_val.pressed.connect(func(): request_validate.emit())
	_apply_style(btn_val)
	btn_row.add_child(btn_val)
	add_child(btn_row)

	var btn_policy = Button.new(); btn_policy.text="Validate Region Policy"
	btn_policy.tooltip_text = "Check every region under data/ against the ruleset's biome/region_type/level_band/hazard-coverage policy (fast -- doesn't need a full loadable world)."
	_apply_style(btn_policy, Color(0.2, 0.25, 0.3))
	btn_policy.pressed.connect(func(): request_validate_region_policy.emit())
	add_child(btn_policy)
	
	var btn_layout = Button.new(); btn_layout.text="Auto-Arrange Layout"
	_apply_style(btn_layout, Color(0.2, 0.25, 0.3))
	btn_layout.pressed.connect(func(): request_auto_layout.emit())
	add_child(btn_layout)

# --- INPUT HANDLERS ---

func _on_tree_gui_input(event: InputEvent):
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_RIGHT and event.pressed:
			var pos = event.position
			var item = explorer_tree.get_item_at_position(pos)
			if item:
				if not item.is_selected(0):
					_is_programmatic_selection = true
					item.select(0)
					_is_programmatic_selection = false
				
				var meta = item.get_metadata(0)
				request_context_menu.emit(get_global_mouse_position(), meta)
				get_viewport().set_input_as_handled()

# --- PUBLIC API ---

var _current_hierarchy: Dictionary = {}
var _current_filename: String = ""
var _selected_id: String = ""
var _is_reg_dirty: bool = false
var _dirty_rooms: Dictionary = {}

func update_data(hierarchy: Dictionary, current_file: String, selected_id: String):
	_current_hierarchy = hierarchy
	_current_filename = current_file
	_selected_id = selected_id
	refresh_tree()

func update_dirty_visuals(current_file: String, is_reg_dirty: bool, dirty_rooms: Dictionary):
	_current_filename = current_file
	_is_reg_dirty = is_reg_dirty
	_dirty_rooms = dirty_rooms
	refresh_tree()

func update_layout_btn_text(is_world: bool):
	var btn = get_child(get_child_count()-1) as Button
	if btn: btn.text = "Auto-Arrange World" if is_world else "Auto-Arrange Rooms"

func select_room_item(room_id: String):
	_selected_id = room_id
	# Deferred one frame: selecting an item right after un-collapsing its
	# ancestor (below) doesn't reliably stick the same frame it happens on
	# in Godot's Tree -- the item can visually fail to show as selected
	# until the next redraw, which reads as "the first click did nothing."
	call_deferred("_apply_room_selection", room_id)

func _apply_room_selection(room_id: String):
	var root = explorer_tree.get_root()
	if not root: return

	var sel = explorer_tree.get_selected()
	if sel: sel.deselect(0)

	if not _select_tree_item_by_id(root, room_id):
		# The item wasn't found under the tree as currently built (a stale
		# structure, or a selection that arrived mid-rebuild) -- rebuild and
		# try once more from scratch rather than leaving nothing selected.
		refresh_tree()
		_select_tree_item_by_id(explorer_tree.get_root(), room_id)

# Recursively searches every region/district/room row (the tree can now be
# region -> district -> room, or plain region -> room for a district-less
# region) for the given id, un-collapsing every ancestor along the way so
# the match is actually visible once selected.
func _select_tree_item_by_id(parent: TreeItem, id: String) -> bool:
	for child in parent.get_children():
		var meta = child.get_metadata(0)
		if meta and meta.get("type", "") != "district" and meta.get("id", "") == id:
			var ancestor = child.get_parent()
			while ancestor:
				if ancestor.collapsed: ancestor.collapsed = false
				ancestor = ancestor.get_parent()
			_is_programmatic_selection = true
			child.select(0)
			_is_programmatic_selection = false
			explorer_tree.scroll_to_item(child, true)
			return true
		if _select_tree_item_by_id(child, id):
			return true
	return false

# --- INTERNAL LOGIC ---

func refresh_tree():
	explorer_tree.clear()
	var root = explorer_tree.create_item()
	var filter = search_bar.text.to_lower()
	
	var regions = _current_hierarchy.keys()
	regions.sort()
	
	for rid in regions:
		var r_data = _current_hierarchy[rid]
		var match_reg = filter.is_empty() or rid.to_lower().contains(filter)
		var match_rooms = []
		for r_id in r_data.rooms:
			var r_name = str(r_data.rooms[r_id]).to_lower()
			if match_reg or r_id.to_lower().contains(filter) or r_name.contains(filter):
				match_rooms.append(r_id)
		
		if not match_reg and match_rooms.is_empty(): continue
		
		match_rooms.sort_custom(func(a, b): 
			var name_a = str(r_data.rooms[a])
			var name_b = str(r_data.rooms[b])
			var name_cmp = name_a.nocasecmp_to(name_b)
			if name_cmp != 0: return name_cmp < 0
			return a.nocasecmp_to(b) < 0
		)
		
		var item = explorer_tree.create_item(root)
		
		var display_name = rid.capitalize()
		var is_current = (r_data.filename == _current_filename)
		var is_region_selected = (rid == _selected_id)
		
		if is_current and _is_reg_dirty:
			item.set_text(0, display_name + " (*)")
			item.set_custom_color(0, Color(1.0, 0.9, 0.6))
		else:
			item.set_text(0, display_name)
			item.set_custom_color(0, Color(0.7, 0.8, 1.0))
		
		if is_region_selected:
			item.set_custom_bg_color(0, Color(0.2, 0.3, 0.45))
			item.select(0)
			
		item.set_metadata(0, {"type": "region", "file": r_data.filename, "id": rid})
		item.collapsed = not (expanded_regions.get(rid, false) or filter != "")

		# Group matched rooms by district, same as the graph's own territory
		# view -- a room not in any district falls back to sitting directly
		# under the region, same as every room did before districts existed.
		var districts: Dictionary = r_data.get("districts", {})
		var room_to_district: Dictionary = {}
		var matched_district_ids: Array = []
		for district_id in districts:
			var members: Array = districts[district_id].get("members", districts[district_id].get("rooms", []))
			var has_match := false
			for member_variant in members:
				var member_id := str(member_variant)
				if match_rooms.has(member_id):
					room_to_district[member_id] = str(district_id)
					has_match = true
			if has_match: matched_district_ids.append(str(district_id))
		matched_district_ids.sort_custom(func(a, b):
			return str(districts[a].get("name", a)).nocasecmp_to(str(districts[b].get("name", b))) < 0
		)

		var district_items: Dictionary = {}
		for district_id in matched_district_ids:
			var district: Dictionary = districts[district_id]
			var d_item = explorer_tree.create_item(item)
			d_item.set_text(0, str(district.get("name", district_id)))
			d_item.set_selectable(0, true)
			var d_color := Color.from_string(str(district.get("color", "#5d83a6")), Color("5d83a6"))
			d_item.set_custom_color(0, d_color.lightened(0.4))
			d_item.set_metadata(0, {"type": "district", "file": r_data.filename, "region": rid, "id": district_id})
			d_item.collapsed = not (expanded_districts.get(district_id, true) or filter != "")
			district_items[district_id] = d_item

		for r_id in match_rooms:
			var parent_item = district_items.get(room_to_district.get(r_id, ""), item)
			var r_item = explorer_tree.create_item(parent_item)
			var r_name = str(r_data.rooms[r_id])

			if is_current and _dirty_rooms.has(r_id):
				r_item.set_text(0, r_name + " (*)")
				r_item.set_custom_color(0, Color(1.0, 0.9, 0.6))
			else:
				r_item.set_text(0, r_name)

			if r_id == _selected_id and is_current:
				r_item.set_custom_color(0, Color.GREEN)
				r_item.set_custom_bg_color(0, Color(0.15, 0.25, 0.35))
				r_item.select(0)

			r_item.set_tooltip_text(0, r_id)
			r_item.set_metadata(0, {"type": "room", "file": r_data.filename, "id": r_id})

func _on_tree_select():
	if _is_programmatic_selection: return
	var item = explorer_tree.get_selected()
	if not item: return
	var meta = item.get_metadata(0)
	
	# Guard against null metadata (e.g. root item or intermediate state)
	if meta == null: return
	
	if meta.type == "region": 
		request_load_region.emit(meta.file)
	elif meta.type == "district":
		request_load_region.emit(meta.file)
		request_show_district.emit(meta.region, meta.id)
	else:
		request_load_region.emit(meta.file)
		request_jump_to_room.emit(meta.id)

func _on_tree_activate():
	var item = explorer_tree.get_selected()
	if not item: return
	var meta = item.get_metadata(0)
	if meta and meta.type == "region": 
		item.collapsed = !item.collapsed
		_on_tree_collapse(item)

func _on_tree_collapse(item):
	var meta = item.get_metadata(0)
	if meta and meta.type == "region": expanded_regions[meta.id] = not item.collapsed
	elif meta and meta.type == "district": expanded_districts[meta.id] = not item.collapsed

func _apply_style(node: Control, bg_color = Color(0.15, 0.15, 0.18)):
	var s = StyleBoxFlat.new(); s.bg_color = bg_color; s.set_border_width_all(1); s.border_color = Color(0.4, 0.4, 0.45); s.set_corner_radius_all(4)
	s.content_margin_left = 8; s.content_margin_right = 8; s.content_margin_top = 4; s.content_margin_bottom = 4
	if node is Button:
		node.add_theme_stylebox_override("normal", s)
		node.add_theme_stylebox_override("hover", s.duplicate())
		node.add_theme_stylebox_override("pressed", s.duplicate())
		node.get_theme_stylebox("hover").bg_color = bg_color.lightened(0.1)
		node.get_theme_stylebox("pressed").bg_color = bg_color.darkened(0.1)
	elif node is LineEdit:
		var s2 = s.duplicate(); s2.bg_color = Color(0.08, 0.08, 0.1); node.add_theme_stylebox_override("normal", s2)

func _apply_checkbox_style(node: CheckBox):
	node.add_theme_color_override("font_color", Color(0.8, 0.8, 0.8))
	node.add_theme_color_override("font_hover_color", Color.WHITE)
	node.add_theme_color_override("font_pressed_color", Color(0.6, 1.0, 0.6))
	node.add_theme_constant_override("hseparation", 8) 
	var s = StyleBoxFlat.new(); s.bg_color = Color(0.15, 0.15, 0.18)
	s.set_border_width_all(1); s.border_color = Color(0.4, 0.4, 0.45); s.set_corner_radius_all(4)
	s.content_margin_left=4; s.content_margin_right=4
	var s_unchecked = s.duplicate(); s_unchecked.bg_color = Color(0.25, 0.1, 0.1)
	var s_checked = s.duplicate(); s_checked.bg_color = Color(0.1, 0.3, 0.15)
	node.add_theme_stylebox_override("normal", s_unchecked)
	node.add_theme_stylebox_override("pressed", s_checked)
	node.add_theme_stylebox_override("hover", s_unchecked.duplicate())
	node.get_theme_stylebox("hover").bg_color = s_unchecked.bg_color.lightened(0.1)
