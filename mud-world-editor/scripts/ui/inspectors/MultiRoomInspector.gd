# scripts/ui/inspectors/MultiRoomInspector.gd
class_name MultiRoomInspector
extends RefCounted

signal data_modified

var container: VBoxContainer
var region_mgr: RegionManager
var action_handler: ActionHandler
var selected_ids: Array
var props_box: VBoxContainer
var popup_menu: PopupMenu

# Definition for intersection result
class MixedProp:
	var value
	var is_mixed: bool = false
	func _init(v, m=false): value = v; is_mixed = m

func _init(c: VBoxContainer, r_mgr: RegionManager, handler: ActionHandler):
	container = c
	region_mgr = r_mgr
	action_handler = handler

func build(ids: Array):
	selected_ids = ids
	
	container.add_child(InspectorStyle.create_section_header("MULTI-EDIT (%d Rooms)" % ids.size(), Color.ORANGE))
	
	var card = InspectorStyle.create_card()
	var vbox = card.get_child(0).get_child(0)
	container.add_child(card)
	
	# Tag Addition UI
	var header_box = HBoxContainer.new()
	header_box.add_child(InspectorStyle.lbl("Common Properties", Color.WHITE))
	var spacer = Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header_box.add_child(spacer)
	
	var btn_add = MenuButton.new(); btn_add.text = "+ Tag"
	btn_add.flat = true; btn_add.add_theme_color_override("font_color", InspectorStyle.COLOR_ACCENT)
	header_box.add_child(btn_add)
	vbox.add_child(header_box)
	
	props_box = VBoxContainer.new()
	props_box.add_theme_constant_override("separation", 6)
	vbox.add_child(props_box)
	
	popup_menu = btn_add.get_popup()
	popup_menu.id_pressed.connect(_on_add_tag)
	
	_refresh_props()

func _refresh_props():
	for c in props_box.get_children(): c.queue_free()
	
	# 1. Analyze Intersection
	var prop_counts = {} # key -> count
	var prop_values = {} # key -> first_val
	var prop_mixed = {} # key -> bool
	
	for id in selected_ids:
		if not region_mgr.data.rooms.has(id): continue
		var r = region_mgr.data.rooms[id]
		var p = r.get("properties", {})
		
		for k in p:
			if not prop_counts.has(k):
				prop_counts[k] = 0
				prop_values[k] = p[k]
				prop_mixed[k] = false
			
			prop_counts[k] += 1
			if prop_values[k] != p[k]:
				prop_mixed[k] = true
	
	# 2. Build UI for properties that exist in AT LEAST ONE selected room
	var keys = prop_counts.keys()
	keys.sort()
	
	popup_menu.clear()
	# Populate Add Menu (Common props not present in ALL)
	var common = ["dark", "outdoors", "safe_zone", "noisy", "smell", "weather", "music"]
	for c in common:
		popup_menu.add_item(c)
	popup_menu.add_separator()
	popup_menu.add_item("Custom...")
	
	if keys.is_empty():
		var l = Label.new(); l.text = "No properties found."; l.modulate = Color(1,1,1,0.3)
		props_box.add_child(l)
		return
		
	for k in keys:
		var is_universal = (prop_counts[k] == selected_ids.size())
		var is_mixed = prop_mixed[k]
		var val = prop_values[k]
		
		var row = PanelContainer.new()
		var s = StyleBoxFlat.new(); s.bg_color = Color(0.15, 0.15, 0.17); s.set_corner_radius_all(4)
		row.add_theme_stylebox_override("panel", s)
		var hb = HBoxContainer.new()
		row.add_child(hb)
		
		var lbl_k = Label.new(); lbl_k.text = k + ": "; lbl_k.custom_minimum_size.x = 80
		if not is_universal: lbl_k.modulate = Color(1, 1, 1, 0.5) # Dim if not on all
		hb.add_child(lbl_k)
		
		# Value Editor
		if is_mixed:
			var l_mix = Label.new(); l_mix.text = "<Mixed>"; l_mix.modulate = Color.GOLD
			l_mix.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			hb.add_child(l_mix)
			
			var btn_set = Button.new(); btn_set.text = "Set All"
			InspectorStyle.apply_button_style(btn_set)
			btn_set.pressed.connect(func(): _edit_prop(k, val)) # Set all to the 'first' value found
			hb.add_child(btn_set)
		else:
			if typeof(val) == TYPE_BOOL:
				var chk = CheckBox.new(); chk.button_pressed = val; chk.text = str(val)
				chk.toggled.connect(func(b): _edit_prop(k, b))
				hb.add_child(chk)
			else:
				var ed = LineEdit.new(); ed.text = str(val); ed.size_flags_horizontal = Control.SIZE_EXPAND_FILL
				InspectorStyle.apply_input_style(ed)
				ed.text_submitted.connect(func(t):
					var new_v = t
					if typeof(val) == TYPE_FLOAT: new_v = t.to_float()
					elif typeof(val) == TYPE_INT: new_v = t.to_int()
					_edit_prop(k, new_v)
				)
				hb.add_child(ed)
				
		var btn_del = Button.new(); btn_del.text = "x"; btn_del.flat = true
		btn_del.pressed.connect(func(): _edit_prop(k, null)) # Null = Delete
		hb.add_child(btn_del)
		
		props_box.add_child(row)

func _edit_prop(key: String, new_val):
	var old_vals = {}
	for id in selected_ids:
		if region_mgr.data.rooms.has(id):
			var r = region_mgr.data.rooms[id]
			if r.get("properties", {}).has(key):
				old_vals[id] = r.properties[key]
			else:
				old_vals[id] = null # Marker for "didn't exist"
	
	action_handler.commit_batch_properties(selected_ids, key, new_val, old_vals)
	_refresh_props()

func _on_add_tag(idx):
	var txt = popup_menu.get_item_text(idx)
	if txt == "Custom...":
		return # TODO: Add custom dialog
	
	# Add property to all with default val (true for bools, empty string otherwise)
	var def_val = true
	_edit_prop(txt, def_val)
