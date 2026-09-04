# scripts/ui/panels/tabs/DatabaseTab.gd
class_name DatabaseTab
extends MarginContainer

signal request_select_db_entry(type, id)
signal request_create_db_entry(type)
signal request_delete_db_entry(type, id)
signal request_context_menu(global_pos, meta)

var database_tree: Tree
var db_filter_opt: OptionButton

var _cached_npcs: Dictionary = {}
var _cached_items: Dictionary = {}
var _cached_magic: Dictionary = {}
var _cached_quests: Dictionary = {}
var _cached_dirty: Dictionary = {}

func setup():
	add_theme_constant_override("margin_left", 5)
	add_theme_constant_override("margin_right", 5)
	add_theme_constant_override("margin_top", 12)
	add_theme_constant_override("margin_bottom", 5)
	
	var db_vbox = VBoxContainer.new()
	db_vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	db_vbox.add_theme_constant_override("separation", 12)
	
	var db_head = HBoxContainer.new()
	db_filter_opt = OptionButton.new()
	db_filter_opt.add_item("NPCs")
	db_filter_opt.add_item("Items")
	db_filter_opt.add_item("Magic")
	db_filter_opt.add_item("Quests")
	_apply_style(db_filter_opt)
	db_filter_opt.item_selected.connect(func(_i): _refresh_db_list())
	db_head.add_child(db_filter_opt)
	db_vbox.add_child(db_head)
	
	database_tree = Tree.new()
	database_tree.size_flags_vertical = Control.SIZE_EXPAND_FILL
	database_tree.hide_root = true
	database_tree.select_mode = Tree.SELECT_ROW
	database_tree.allow_rmb_select = true
	
	var tree_style = StyleBoxFlat.new()
	tree_style.bg_color = Color(0.05, 0.05, 0.08)
	database_tree.add_theme_stylebox_override("bg", tree_style)
	
	database_tree.item_selected.connect(_on_item_selected)
	database_tree.gui_input.connect(_on_tree_gui_input)
	
	db_vbox.add_child(database_tree)
	
	var db_btns = HBoxContainer.new()
	var btn_mk_db = Button.new(); btn_mk_db.text="Create"; btn_mk_db.size_flags_horizontal=3
	_apply_style(btn_mk_db, Color(0.2,0.3,0.2))
	btn_mk_db.pressed.connect(func(): request_create_db_entry.emit(_get_current_db_type()))
	db_btns.add_child(btn_mk_db)
	
	var btn_del_db = Button.new(); btn_del_db.text="Delete"; btn_del_db.size_flags_horizontal=3
	_apply_style(btn_del_db, Color(0.3,0.1,0.1))
	btn_del_db.pressed.connect(_on_delete_pressed)
	db_btns.add_child(btn_del_db)
	
	db_vbox.add_child(db_btns)
	add_child(db_vbox)

func update_data(npcs, items, magic, quests, dirty_flags):
	_cached_npcs = npcs
	_cached_items = items
	_cached_magic = magic
	_cached_quests = quests
	_cached_dirty = dirty_flags
	_refresh_db_list()

func _get_current_db_type() -> String:
	match db_filter_opt.selected:
		0: return "npc"
		1: return "item"
		2: return "magic"
		3: return "quest"
	return "npc"

func _refresh_db_list():
	database_tree.clear()
	var root = database_tree.create_item()
	var mode = db_filter_opt.selected
	var type_key = _get_current_db_type()
	var data_source = {}
	
	match mode:
		0: data_source = _cached_npcs
		1: data_source = _cached_items
		2: data_source = _cached_magic
		3: data_source = _cached_quests
	
	var groups = {}
	for id in data_source:
		var entry = data_source[id]
		var fname = entry.get("_filename", "custom.json")
		var group_name = fname.get_file().replace(".json", "").to_upper()
		
		if not groups.has(group_name): groups[group_name] = []
		groups[group_name].append(id)
	
	var group_keys = groups.keys()
	group_keys.sort()
	
	for g_name in group_keys:
		var group_item = database_tree.create_item(root)
		group_item.set_text(0, g_name)
		group_item.set_selectable(0, false)
		group_item.set_custom_color(0, Color(0.7, 0.7, 0.7))
		group_item.set_custom_bg_color(0, Color(0.12, 0.12, 0.15))
		
		var ids = groups[g_name]
		ids.sort()
		
		for id in ids:
			var entry = data_source[id]
			var item = database_tree.create_item(group_item)
			
			var display_text = id
			if _cached_dirty.has(type_key) and _cached_dirty[type_key].has(id):
				display_text += " (*)"
				item.set_custom_color(0, Color(1.0, 0.9, 0.6)) # Dirty color
				
			item.set_text(0, display_text)
			item.set_metadata(0, {"id": id})
			_color_item(item, entry, mode)

func _color_item(item: TreeItem, entry: Dictionary, mode: int):
	# Only color icon if not dirty-colored text, or keep text dirty and icon typed
	var col = Color.WHITE
	if mode == 0: # NPC
		if entry.get("friendly", true): col = Color.LIGHT_GREEN
		else: col = Color.SALMON
	elif mode == 1: # Item
		var type = entry.get("type", "Item")
		match type:
			"Weapon": col = Color.SALMON
			"Armor": col = Color.CORNFLOWER_BLUE
			"Consumable": col = Color.LIGHT_GREEN
			"Treasure", "Gem": col = Color.GOLD
			"Junk": col = Color.WEB_GRAY
			"Key", "Tool": col = Color.SANDY_BROWN
			_: col = Color.AQUAMARINE
	elif mode == 2: col = Color.VIOLET
	elif mode == 3: col = Color.GOLD
	
	item.set_icon(0, _get_color_icon(col))

func _on_item_selected():
	var item = database_tree.get_selected()
	if not item: return
	var meta = item.get_metadata(0)
	if meta and meta.has("id"):
		request_select_db_entry.emit(_get_current_db_type(), meta.id)

func _on_delete_pressed():
	var item = database_tree.get_selected()
	if not item: return
	var meta = item.get_metadata(0)
	if meta and meta.has("id"):
		request_delete_db_entry.emit(_get_current_db_type(), meta.id)

func _on_tree_gui_input(event):
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_RIGHT and event.pressed:
		var pos = event.position
		var item = database_tree.get_item_at_position(pos)
		if item:
			var meta = item.get_metadata(0)
			if meta and meta.has("id"):
				item.select(0) 
				var type = _get_current_db_type()
				var global_pos = database_tree.get_global_position() + pos
				var context_meta = {"type": "db_entry", "kind": type, "id": meta.id}
				request_context_menu.emit(global_pos, context_meta)
				get_viewport().set_input_as_handled()

func _apply_style(node: Control, bg_color = Color(0.15, 0.15, 0.18)):
	var s = StyleBoxFlat.new(); s.bg_color = bg_color; s.set_border_width_all(1); s.border_color = Color(0.4, 0.4, 0.45); s.set_corner_radius_all(4); s.content_margin_left = 8; s.content_margin_right = 8
	if node is Button:
		node.add_theme_stylebox_override("normal", s); node.add_theme_stylebox_override("hover", s.duplicate()); node.add_theme_stylebox_override("pressed", s.duplicate())
		node.get_theme_stylebox("hover").bg_color = bg_color.lightened(0.1); node.get_theme_stylebox("pressed").bg_color = bg_color.darkened(0.1)

func _get_color_icon(col: Color) -> ImageTexture:
	var img = Image.create(16, 16, false, Image.FORMAT_RGBA8); img.fill(col); return ImageTexture.create_from_image(img)
