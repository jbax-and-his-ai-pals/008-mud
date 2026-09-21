# scripts/ui/inspectors/panels/RoomConnectionsPanel.gd
class_name RoomConnectionsPanel
extends RefCounted

signal data_modified
signal request_connection_form(id, name)
# Asking to remove an exit, with `also_reciprocal` saying whether the author
# wants the far end removed too. The panel reports the request rather than
# performing it: removing a *second* room's exit is an edit to content this panel
# does not own and cannot undo, so the decision belongs where the undo stack is.
signal request_delete_connection(source_id, direction, target, also_reciprocal)
# Asking to re-shape how an exit is drawn. `curve_action` is "" for a delete, or
# "cycle"/"straight" for the bow controls. One signal for both because they are
# both "change the editor-only layout of this exit", and they need the same
# commit path for undo.
signal request_curve_change(source_id, direction, curve_action)

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
			"up","down","climb","descend","surface","dive": style.border_color = Color(0.7, 0.4, 0.8)
			_: style.border_color = Color(0.4, 0.8, 0.5)
			
	pc.add_theme_stylebox_override("panel", style)
	
	var m = MarginContainer.new()
	m.add_theme_constant_override("margin_left", 8); m.add_theme_constant_override("margin_right", 8)
	m.add_theme_constant_override("margin_top", 4); m.add_theme_constant_override("margin_bottom", 4)
	pc.add_child(m)
	
	var hb = HBoxContainer.new(); hb.add_theme_constant_override("separation", 10); m.add_child(hb)
	
	var l_dir = Label.new(); l_dir.text = dir.to_upper(); l_dir.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	l_dir.size_flags_vertical = Control.SIZE_EXPAND_FILL
	l_dir.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT; l_dir.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	l_dir.add_theme_font_size_override("font_size", 12)
	if is_ext: l_dir.modulate = Color(0.9, 0.8, 0.5)
	hb.add_child(l_dir)

	var is_two_way = false
	if not is_ext and region_mgr.data.rooms.has(target):
		var t_exits = region_mgr.data.rooms[target].get("exits", {})
		if t_exits.values().has(cur_id): is_two_way = true

	# --- CURVE CONTROL ---
	# Only for the directions drawn as a curve, because only those have a side to
	# choose and a distance to bow. Without this the bow is decided by the
	# perpendicular of the line between the two rooms, so moving a room flips it --
	# and an "in" that pointed one way last week points the other way now, for no
	# authored reason.
	if _is_curved_direction(dir):
		# Kept in one container so the two controls read as a pair: direction, then
		# distance. Both are the same interaction (click to cycle, shift-click to
		# clear), which is why they look alike.
		var curve_box = HBoxContainer.new()
		curve_box.add_theme_constant_override("separation", 2)

		var curve := _current_curve(dir)
		var btn_curve = Button.new()
		btn_curve.text = "◜" if curve == "left" else ("◝" if curve == "right" else "↷")
		btn_curve.flat = true
		btn_curve.tooltip_text = "Bows %s. Click to reverse; shift-click for the automatic side." % (
			curve if curve != "" else "automatically"
		)
		btn_curve.add_theme_font_size_override("font_size", 14)
		btn_curve.add_theme_color_override("font_color", InspectorStyle.COLOR_TEXT_DIM if curve == "" else Color(0.6, 0.8, 1.0))
		btn_curve.add_theme_color_override("font_hover_color", Color.WHITE)
		btn_curve.pressed.connect(func():
			request_curve_change.emit(cur_id, dir, "straight" if Input.is_key_pressed(KEY_SHIFT) else "cycle")
		)
		curve_box.add_child(btn_curve)

		var amount := _current_curve_amount(dir)
		var btn_amount = Button.new()
		# One glyph per step, sized to suggest the distance rather than labelled:
		# the tooltip carries the word, and the row stays narrow.
		btn_amount.text = {"tight": "◟", "normal": "◜", "wide": "⌒"}.get(amount, "◜")
		btn_amount.flat = true
		btn_amount.tooltip_text = "Bow distance: %s. Click to cycle; shift-click for the default." % amount
		btn_amount.add_theme_font_size_override("font_size", 14)
		btn_amount.add_theme_color_override(
			"font_color",
			InspectorStyle.COLOR_TEXT_DIM if amount == CURVE_AMOUNT_DEFAULT else Color(0.6, 0.8, 1.0),
		)
		btn_amount.add_theme_color_override("font_hover_color", Color.WHITE)
		btn_amount.pressed.connect(func():
			request_curve_change.emit(cur_id, dir, "amount_default" if Input.is_key_pressed(KEY_SHIFT) else "amount")
		)
		curve_box.add_child(btn_amount)

		hb.add_child(curve_box)

	var arrow = Label.new(); arrow.text = "⇄" if is_two_way else "→"
	arrow.modulate = InspectorStyle.COLOR_SUCCESS if is_two_way else Color(1,1,1,0.3)
	if is_ext: arrow.modulate = Color(0.9, 0.8, 0.5)
	arrow.add_theme_font_size_override("font_size", 20)
	arrow.size_flags_vertical = Control.SIZE_EXPAND_FILL
	arrow.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	hb.add_child(arrow)

	var vb_t = VBoxContainer.new(); vb_t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vb_t.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb_t.alignment = BoxContainer.ALIGNMENT_CENTER
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
	vb_t.add_child(l_name); hb.add_child(vb_t)
	
	var btn_del = Button.new(); btn_del.text = "🗑"; btn_del.flat = true
	btn_del.add_theme_color_override("font_color", Color(0.6, 0.3, 0.3))
	btn_del.add_theme_color_override("font_hover_color", Color(1.0, 0.4, 0.4))

	# Reciprocity is the default here because it is what the author means almost
	# every time: a connection is normally a pair, and deleting one end of a pair
	# leaves a half-link that still draws and still points at this room. So the
	# plain click removes both ends, and the one-way removal -- the case that needs
	# a deliberate choice -- is the modifier.
	var reciprocal_dir := _find_reciprocal_exit(dir, target)
	if reciprocal_dir != "":
		btn_del.tooltip_text = "Remove this connection both ways (%s ⇄ %s)" % [dir, reciprocal_dir]
		btn_del.pressed.connect(func(): request_delete_connection.emit(cur_id, dir, target, true))
	else:
		btn_del.tooltip_text = "Remove this one-way connection"
		btn_del.pressed.connect(func(): request_delete_connection.emit(cur_id, dir, target, false))
	hb.add_child(btn_del)

	# Only shown when there IS a pair to break, so the button is not offering a
	# choice that does not exist. Removing one end of a pair is the unusual case,
	# which is why it is smaller and quieter than the delete it sits beside.
	if reciprocal_dir != "":
		var btn_one_way = Button.new(); btn_one_way.text = "⤳"
		btn_one_way.flat = true
		btn_one_way.tooltip_text = "Remove only this side, leaving %s's '%s' exit pointing here" % [t_name, reciprocal_dir]
		btn_one_way.add_theme_color_override("font_color", Color(0.55, 0.5, 0.35))
		btn_one_way.add_theme_color_override("font_hover_color", Color(0.9, 0.8, 0.5))
		btn_one_way.pressed.connect(func(): request_delete_connection.emit(cur_id, dir, target, false))
		hb.add_child(btn_one_way)

	return pc


## The direction the target room uses to point back at this room, or "".
## Same-region only: a cross-region exit's reciprocal lives in another region's
## file, which this panel has not loaded, so claiming to have found one would be a
## guess. A cross-region exit therefore always offers the one-way removal.
func _find_reciprocal_exit(dir: String, target: String) -> String:
	if ":" in str(target):
		return ""
	if not region_mgr.data.rooms.has(target):
		return ""
	var target_exits: Dictionary = region_mgr.data.rooms[target].get("exits", {})
	for other_dir in target_exits:
		if str(target_exits[other_dir]) == str(cur_id) and str(other_dir) != str(dir):
			return str(other_dir)
	return ""


## Directions the graph draws as a bow rather than a straight line. Mirrors the
## list in `GraphRenderer.draw_graph`; the renderer decides which it is, so this
## only has to agree well enough to know when to offer the control.
const CURVED_DIRECTIONS := ["up", "down", "climb", "descend", "surface", "dive", "in", "out", "enter", "exit", "inside", "outside"]

## How far a curved connection bows, as a fraction of the automatic bow. Three
## steps rather than a slider: a slider in a scrolling inspector is a control the
## author has to aim at, and "how far does this bow" is a choice between a few
## readable options, not a measurement. The middle step is the default, so
## clearing the override returns to exactly what the renderer would have drawn.
const CURVE_AMOUNTS := ["tight", "normal", "wide"]
const CURVE_AMOUNT_DEFAULT := "normal"
const CURVE_AMOUNT_SCALE := {"tight": 0.5, "normal": 1.0, "wide": 1.6}


## The next bow distance after `current`. Exposed as a function rather than left
## inline in the click handler so the cycle can be asserted without a widget.
##
## `normal` is what the renderer draws with no override at all, so the cycle
## returns to it by returning "" -- an override saying "the same as no override"
## is a key with no meaning, and it would survive every save from then on.
##
## Anything unrecognised -- including the empty string a fresh exit has -- is read
## as `normal` rather than as the start of the cycle. "Cycle from whatever you have"
## and "start at the beginning" are different questions, and only the first one is
## being asked here.
static func next_curve_amount(current: String) -> String:
	var at: int = CURVE_AMOUNTS.find(current)
	var from := current if at != -1 else CURVE_AMOUNT_DEFAULT
	var following: String = str(CURVE_AMOUNTS[(CURVE_AMOUNTS.find(from) + 1) % CURVE_AMOUNTS.size()])
	return "" if following == CURVE_AMOUNT_DEFAULT else following


## How far a bow is scaled, for a stored amount. 1.0 for "no override".
static func curve_scale_for(amount: String) -> float:
	return float(CURVE_AMOUNT_SCALE.get(amount, 1.0))

var _curve_amount := CURVE_AMOUNT_DEFAULT

func _is_curved_direction(dir: String) -> bool:
	return dir.to_lower() in CURVED_DIRECTIONS


## The authored bow for this exit: "left", "right", or "" for the automatic side.
func _current_curve(dir: String) -> String:
	var layout = cur_room_layout().get(dir, {})
	if layout is Dictionary:
		return str(layout.get("curve", ""))
	return ""


## The authored bow distance for this exit: "tight", "normal", "wide".
func _current_curve_amount(dir: String) -> String:
	var layout = cur_room_layout().get(dir, {})
	if layout is Dictionary:
		return str(layout.get("curve_amount", CURVE_AMOUNT_DEFAULT))
	return CURVE_AMOUNT_DEFAULT


## This room's `_editor_exit_layout`, which is where editor-only exit drawing
## state lives. Safe when absent -- the key is optional and only present once an
## author has overridden something.
func cur_room_layout() -> Dictionary:
	if not region_mgr.data.rooms.has(cur_id):
		return {}
	var layout = region_mgr.data.rooms[cur_id].get("_editor_exit_layout", {})
	return layout if layout is Dictionary else {}
