# scripts/ui/inspectors/ConnectionEditor.gd
class_name ConnectionEditor
extends RefCounted

signal connection_created(src, dir, target, twoway, reverse_dir)
# Same as `connection_created`, but the form stays open with the target cleared so
# the author can connect the next room from the same source. A separate signal
# rather than a flag on the first one: the two callers differ in what happens to
# the *form*, and the side that owns the form should be the side that decides.
signal connection_created_and_continue(src, dir, target, twoway, reverse_dir)
signal target_selected(target_id) # New signal to report the current target

const DIRECTION_ITEMS = Constants.AUTHORABLE_DIRECTIONS

# Data References
var conn_hierarchy: Dictionary = {}
var conn_src_id: String = ""
var conn_src_name: String = ""
var conn_cur_reg_filename: String = ""

# GUI References
var conn_dir_option: OptionButton
var conn_dir_custom_edit: LineEdit
var conn_reg_opt: OptionButton
var conn_room_opt: OptionButton
var conn_twoway: CheckBox
var conn_rev_row: HBoxContainer
var conn_rev_label: Label
# The room-name halves of the two direction rows. Both rows read
# `Connect <room> [dir] to <room>`; these are the widgets for the leading name,
# filled in by `_update_connection_info` because they follow the target choice.
var conn_dir_label: Label
var conn_rev_room_label: Label
var conn_rev_option: OptionButton
var conn_rev_custom_edit: LineEdit
var conn_info_label: RichTextLabel
var region_mgr: RegionManager

# Whether the reverse direction still tracks the forward direction's compass
# inverse automatically, or the author has taken it over -- a mismatched pair
# (an "opening" back out through "out") has no compass inverse to suggest at
# all, so this is what lets that stay a deliberate choice instead of silently
# producing a one-way link the "Reciprocal" checkbox implied wouldn't happen.
var _rev_dir_auto: bool = true
var _updating_rev_field: bool = false

# Same idea, one tier up: the forward direction starts out following the
# room-position geometry (same suggestion the old district-placement wizard
# used) as the target room changes, until the author picks one themselves.
var _dir_auto: bool = true
var _updating_dir_field: bool = false

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

	# --- TARGET UI ---
	parent_container.add_child(_lbl("Target Region:", Color.GRAY))
	conn_reg_opt = OptionButton.new(); conn_reg_opt.size_flags_horizontal = Control.SIZE_EXPAND_FILL; _apply_style(conn_reg_opt)
	conn_reg_opt.item_selected.connect(_on_conn_region_changed)
	parent_container.add_child(conn_reg_opt)

	parent_container.add_child(_lbl("Target Room:", Color.GRAY))
	conn_room_opt = OptionButton.new(); conn_room_opt.size_flags_horizontal = Control.SIZE_EXPAND_FILL; _apply_style(conn_room_opt)
	conn_room_opt.item_selected.connect(func(_i): _update_connection_info())
	parent_container.add_child(conn_room_opt)

	parent_container.add_child(HSeparator.new())

	# --- RECIPROCAL ---
	# Above the two direction rows rather than between them: the checkbox decides
	# whether there *is* a second row, so reading it after the first row meant
	# reading the form in the wrong order -- and it split the two rows, which are
	# a pair of the same shape and belong together.
	conn_twoway = CheckBox.new(); conn_twoway.text = "Reciprocal (two-way)"; conn_twoway.button_pressed = true
	conn_twoway.toggled.connect(func(_b): _update_connection_info())
	_apply_style(conn_twoway)
	parent_container.add_child(conn_twoway)

	# --- CONNECT / RETURN ---
	# Both rows are built the same way and read the same way:
	#
	#     Connect   <target room>   [direction]   to   <this room>
	#     Return    <this room>     [direction]   to   <target room>
	#
	# The room names are set in `_update_connection_info`, since they change with
	# the target selection; the label widgets are kept so that can happen without
	# rebuilding the row.
	parent_container.add_child(_lbl("Connect", Color.GRAY))
	var connect_row = HBoxContainer.new(); connect_row.add_theme_constant_override("separation", 8)
	conn_dir_label = _room_label()
	connect_row.add_child(conn_dir_label)
	conn_dir_option = OptionButton.new(); conn_dir_option.size_flags_horizontal = Control.SIZE_EXPAND_FILL; _apply_style(conn_dir_option)
	_populate_direction_dropdown(conn_dir_option)
	conn_dir_option.item_selected.connect(func(_i):
		if not _updating_dir_field: _dir_auto = false
		_on_forward_dir_changed()
	)
	connect_row.add_child(conn_dir_option)
	conn_dir_custom_edit = LineEdit.new(); conn_dir_custom_edit.placeholder_text = "custom"
	conn_dir_custom_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	conn_dir_custom_edit.text_changed.connect(func(t):
		if not _updating_dir_field: _dir_auto = false
		_sync_auto_reverse(t); _update_connection_info()
	)
	_apply_style(conn_dir_custom_edit)
	connect_row.add_child(conn_dir_custom_edit)
	parent_container.add_child(connect_row)

	# Only relevant (and only shown) once both a target room and reciprocal
	# are chosen -- otherwise there's nothing to return from yet.
	conn_rev_label = _lbl("Return", Color.GRAY)
	parent_container.add_child(conn_rev_label)
	conn_rev_row = HBoxContainer.new(); conn_rev_row.add_theme_constant_override("separation", 8)
	conn_rev_room_label = _room_label()
	conn_rev_row.add_child(conn_rev_room_label)
	conn_rev_option = OptionButton.new(); conn_rev_option.size_flags_horizontal = Control.SIZE_EXPAND_FILL; _apply_style(conn_rev_option)
	_populate_direction_dropdown(conn_rev_option)
	conn_rev_option.item_selected.connect(func(_i):
		if not _updating_rev_field:
			_rev_dir_auto = false
			conn_rev_custom_edit.visible = str(conn_rev_option.get_item_metadata(conn_rev_option.selected)) == ""
		_update_connection_info()
	)
	conn_rev_row.add_child(conn_rev_option)
	conn_rev_custom_edit = LineEdit.new(); conn_rev_custom_edit.placeholder_text = "custom"
	conn_rev_custom_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	conn_rev_custom_edit.text_changed.connect(func(_t):
		if not _updating_rev_field: _rev_dir_auto = false
		_update_connection_info()
	)
	_apply_style(conn_rev_custom_edit)
	conn_rev_row.add_child(conn_rev_custom_edit)
	parent_container.add_child(conn_rev_row)

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

	# Connects this pair and immediately offers the next one from the same source,
	# which is how a room with four exits gets authored: the source and direction
	# are chosen once, and only the target changes between connections.
	var btn_another = Button.new(); btn_another.text = "Connect another"
	btn_another.size_flags_horizontal = 3
	btn_another.tooltip_text = "Apply this connection and keep the form open for the next target"
	btn_another.pressed.connect(func(): _on_connect_confirm(true))
	_apply_style(btn_another, Color(0.2, 0.3, 0.35))
	btn_box.add_child(btn_another)

	var btn_close = Button.new(); btn_close.text = "Cancel"; btn_close.size_flags_horizontal = 3
	btn_close.pressed.connect(func(): target_selected.emit(""))
	_apply_style(btn_close, Color(0.3, 0.1, 0.1))
	btn_box.add_child(btn_close)

	parent_container.add_child(margin_c)

	_dir_auto = (dir == "")
	if dir != "":
		var matched = _select_direction_value(conn_dir_option, dir)
		conn_dir_custom_edit.visible = not matched
		if not matched: conn_dir_custom_edit.text = dir
	else:
		conn_dir_option.select(0)
		conn_dir_custom_edit.visible = false
	_sync_auto_reverse(_get_forward_direction())
	_populate_connection_data(target_id)

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
		# The room's display name, falling back to its id. `rooms[<id>]` is the room
		# object, not a string, so passing it straight to `add_item` is a type error
		# -- and the list reads wrong the moment a room object is more than its name.
		var room_entry = rooms[r_id]
		var room_name := str(r_id)
		if room_entry is Dictionary:
			room_name = str(room_entry.get("name", r_id))
		conn_room_opt.add_item(room_name)
		conn_room_opt.set_item_metadata(conn_room_opt.item_count - 1, r_id)

	_update_connection_info()

func _populate_direction_dropdown(opt: OptionButton):
	opt.clear()
	for d in DIRECTION_ITEMS:
		opt.add_item(d.capitalize())
		opt.set_item_metadata(opt.item_count - 1, d)
	opt.add_item("Custom...")
	opt.set_item_metadata(opt.item_count - 1, "")

# Selects the item whose metadata matches `value`; falls back to the
# trailing "Custom..." entry (and returns false) when there's no match,
# including when `value` is empty.
func _select_direction_value(opt: OptionButton, value: String) -> bool:
	var v := value.strip_edges().to_lower()
	if v != "":
		for i in range(opt.item_count - 1):
			if opt.get_item_metadata(i) == v:
				opt.select(i)
				return true
	opt.select(opt.item_count - 1)
	return false

func _get_forward_direction() -> String:
	if conn_dir_option.selected == -1: return ""
	var val := str(conn_dir_option.get_item_metadata(conn_dir_option.selected))
	return val if val != "" else conn_dir_custom_edit.text.strip_edges().to_lower()

func _get_reverse_direction() -> String:
	if conn_rev_option.selected == -1: return ""
	var val := str(conn_rev_option.get_item_metadata(conn_rev_option.selected))
	return val if val != "" else conn_rev_custom_edit.text.strip_edges().to_lower()

func _on_forward_dir_changed():
	var val := str(conn_dir_option.get_item_metadata(conn_dir_option.selected))
	conn_dir_custom_edit.visible = (val == "")
	if val != "": _sync_auto_reverse(val)
	_update_connection_info()

# As long as the reverse field hasn't been taken over manually, it tracks
# the forward direction's compass inverse -- so the common case (north <->
# south) needs no extra input, and a custom forward direction with no known
# inverse lands on "Custom..." with an empty field, prompting the author to
# choose one instead of silently staying blank.
func _sync_auto_reverse(direction: String):
	if not _rev_dir_auto: return
	var inv := str(Constants.INV_DIR_MAP.get(direction.strip_edges().to_lower(), ""))
	_updating_rev_field = true
	var matched := _select_direction_value(conn_rev_option, inv)
	conn_rev_custom_edit.visible = not matched
	if not matched: conn_rev_custom_edit.text = ""
	_updating_rev_field = false

# Suggests a forward direction from real room-position geometry, the same
# way the old district-placement wizard picked a default -- as long as the
# author hasn't chosen one themselves. Only meaningful for a same-region
# target: a cross-region target's position lives in a different region's
# own coordinate space, so there's no geometry to compare.
func _suggest_direction_from_geometry():
	if not _dir_auto: return
	if conn_room_opt.selected == -1 or conn_reg_opt.selected == -1: return
	var target_reg = conn_reg_opt.get_item_metadata(conn_reg_opt.selected)
	if target_reg != region_mgr.data.get("region_id", ""): return
	var target_id = conn_room_opt.get_item_metadata(conn_room_opt.selected)
	if not region_mgr.data.rooms.has(conn_src_id) or not region_mgr.data.rooms.has(target_id): return
	var src_pos := _room_editor_pos(region_mgr.data.rooms[conn_src_id])
	var target_pos := _room_editor_pos(region_mgr.data.rooms[target_id])
	var delta := target_pos - src_pos
	if delta.length_squared() < 1.0: return
	var suggested := _classify_direction(delta)
	_updating_dir_field = true
	var matched := _select_direction_value(conn_dir_option, suggested)
	conn_dir_custom_edit.visible = not matched
	_updating_dir_field = false
	_sync_auto_reverse(suggested)

func _room_editor_pos(room: Dictionary) -> Vector2:
	var raw = room.get("_editor_pos", [0, 0])
	return Vector2(float(raw[0]), float(raw[1])) if raw is Array and raw.size() >= 2 else Vector2.ZERO

func _classify_direction(delta: Vector2) -> String:
	var x_ratio: float = abs(delta.x) / max(abs(delta.y), 0.001)
	var y_ratio: float = abs(delta.y) / max(abs(delta.x), 0.001)
	if x_ratio < 0.45:
		return "south" if delta.y > 0.0 else "north"
	elif y_ratio < 0.45:
		return "east" if delta.x > 0.0 else "west"
	elif delta.x > 0.0:
		return "southeast" if delta.y > 0.0 else "northeast"
	else:
		return "southwest" if delta.y > 0.0 else "northwest"

func _update_connection_info():
	if not conn_info_label: return
	_suggest_direction_from_geometry()
	conn_info_label.text = ""
	var dir = _get_forward_direction()
	var rev_dir = _get_reverse_direction()
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

	var show_return_row: bool = conn_twoway.button_pressed and target_room_name != ""
	conn_rev_row.visible = show_return_row
	conn_rev_label.visible = show_return_row

	# Both rows name their rooms: "Connect <target> [dir] to <this room>" and
	# "Return <this room> [dir] to <target>". Same shape, so the pair reads as a
	# pair. The trailing "to <room>" is the row's own label, which is why the
	# direction dropdowns are the same widget in both.
	var src_display := conn_src_name if conn_src_name != "" else conn_src_id
	if conn_dir_label:
		conn_dir_label.text = target_room_name if target_room_name != "" else "…"
	if conn_rev_room_label:
		conn_rev_room_label.text = src_display

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

	var lines: Array = []
	if dir != "" and target_room_name != "":
		lines.append("[color=gray]%s connects %s to %s.[/color]" % [src_display, dir.capitalize(), target_room_name])
		if show_return_row and rev_dir != "":
			lines.append("[color=gray]%s connects %s to %s.[/color]" % [target_room_name, rev_dir.capitalize(), src_display])
	else:
		lines.append("[color=gray]Choose a target room and a direction.[/color]")
	lines.append_array(msgs)
	conn_info_label.text = "\n".join(lines)

func _on_connect_confirm(and_continue: bool = false):
	var dir = _get_forward_direction()
	if dir.strip_edges() == "": return
	if conn_room_opt.selected == -1: return
	var target_room = conn_room_opt.get_item_metadata(conn_room_opt.selected)
	var target_reg = conn_reg_opt.get_item_metadata(conn_reg_opt.selected)
	var final_target = target_reg + ":" + target_room
	var rev_dir = _get_reverse_direction() if conn_twoway.button_pressed else ""

	target_selected.emit("") # Clear highlight after connecting
	if and_continue:
		connection_created_and_continue.emit(conn_src_id, dir, final_target, conn_twoway.button_pressed, rev_dir)
		_reset_for_next_target()
		return

	connection_created.emit(conn_src_id, dir, final_target, conn_twoway.button_pressed, rev_dir)

	conn_dir_option.select(0)
	conn_dir_custom_edit.visible = false
	conn_dir_custom_edit.text = ""
	_rev_dir_auto = true
	_sync_auto_reverse(_get_forward_direction())
	conn_info_label.text = "[color=green]Connection Created.[/color]"


## Clear the target so the next one can be picked, keeping everything else.
##
## The direction, the reciprocal choice and the custom direction are all kept:
## the point of connecting another is that *only* the far room changes. The
## auto-suggested reverse is kept in step with the direction that survived.
func _reset_for_next_target():
	conn_room_opt.select(-1)
	conn_info_label.text = "[color=gray]Pick the next target room.[/color]"
	# Re-emit an empty target so the map drops the previous pair's preview line
	# and waits for the next click.
	target_selected.emit("")
	_update_connection_info()

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

## A room name's place in a direction row. Fixed-width and clipped so a long name
## cannot push the dropdowns out of the panel, and mid-aligned so the two rows
## line up whether or not either name is the longer one.
func _room_label() -> Label:
	var l := Label.new()
	l.custom_minimum_size.x = 96
	l.clip_text = true
	l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	l.add_theme_font_size_override("font_size", 12)
	l.modulate = Color(0.85, 0.9, 1.0)
	return l
func _clear_box(b): for c in b.get_children(): c.queue_free()
