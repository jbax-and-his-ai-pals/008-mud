# scripts/scenes/RoomScene.gd
extends Node2D

signal room_selected(room_id)
signal room_double_clicked(room_id)
signal dragged(new_position)
signal right_clicked
signal connection_drag_started(room_id)
signal creation_drag_started(room_id, anchor_pos)
signal drag_started
signal drag_ended
signal label_clicked(room_id)
signal label_drag_started(room_id)
signal label_dragged(room_id)
signal label_drag_ended(room_id)
signal camera_pan_input(event)

var dragging = false
var drag_offset = Vector2()
var _middle_panning = false

var _current_color: Color = Color(0.2, 0.2, 0.2)
var _is_selected: bool = false
var _is_proxy: bool = false
var _is_highlighted: bool = false
var snap_step: int = 0

var _npc_visible: bool = false
var _item_visible: bool = false
var _start_visible: bool = false
var _custom_icon_id: String = ""
var _properties: Dictionary = {}

var _cached_name: String = "Unnamed"
var _cached_id: String = ""
var _preview_name := ""
var _label_arrange_mode := false
var _label_dragging := false
var _label_drag_origin := Vector2.ZERO
var _is_label_drag_source := false
var _is_label_swap_target := false
var _show_technical_id := false

@onready var visual_panel = $VisualPanel

var main_layout: VBoxContainer
var id_label: Label
var name_label: Label
var anchor_container: Control
var panel_style: StyleBoxFlat

func _ready():
	var existing_style = visual_panel.get_theme_stylebox("panel")
	if existing_style and existing_style is StyleBoxFlat:
		panel_style = existing_style.duplicate()
	else:
		panel_style = StyleBoxFlat.new()
	
	panel_style.set_corner_radius_all(6)
	panel_style.set_border_width_all(2)
	panel_style.border_color = Color(0.8, 0.8, 0.8, 0.5)
	panel_style.shadow_size = 4
	panel_style.shadow_offset = Vector2(0, 2)
	panel_style.shadow_color = Color(0, 0, 0, 0.4)
	
	visual_panel.add_theme_stylebox_override("panel", panel_style)
	visual_panel.gui_input.connect(_on_panel_gui_input)
	visual_panel.mouse_entered.connect(_on_mouse_entered)
	visual_panel.mouse_exited.connect(_on_mouse_exited)
	visual_panel.mouse_filter = Control.MOUSE_FILTER_STOP
	visual_panel.draw.connect(_draw_icons)
	
	main_layout = VBoxContainer.new()
	main_layout.name = "MainLayout"
	main_layout.set_anchors_preset(Control.PRESET_FULL_RECT)
	main_layout.offset_left = 4; main_layout.offset_right = -4
	main_layout.offset_top = 4; main_layout.offset_bottom = -4
	main_layout.alignment = BoxContainer.ALIGNMENT_CENTER
	main_layout.mouse_filter = Control.MOUSE_FILTER_IGNORE
	visual_panel.add_child(main_layout)
	
	name_label = visual_panel.get_node_or_null("NameLabel")
	if not name_label: name_label = Label.new(); name_label.name = "NameLabel"
	if name_label.get_parent() != main_layout:
		if name_label.get_parent(): name_label.get_parent().remove_child(name_label)
		main_layout.add_child(name_label)
	
	name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	name_label.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	name_label.add_theme_font_size_override("font_size", 13)
	name_label.modulate = Color(1, 1, 1, 1.0)
	name_label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	name_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	name_label.gui_input.connect(_on_name_label_gui_input)
	
	id_label = visual_panel.get_node_or_null("IDLabel")
	if not id_label: id_label = Label.new(); id_label.name = "IDLabel"
	if id_label.get_parent() != main_layout:
		if id_label.get_parent(): id_label.get_parent().remove_child(id_label)
		main_layout.add_child(id_label)
		
	id_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	id_label.add_theme_font_size_override("font_size", 9)
	id_label.modulate = Color(1, 1, 1, 0.5)
	
	anchor_container = visual_panel.get_node_or_null("AnchorContainer")
	if anchor_container:
		anchor_container.move_to_front()
		anchor_container.visible = false
		anchor_container.mouse_filter = Control.MOUSE_FILTER_IGNORE
		for child in anchor_container.get_children():
			if child is Control:
				child.mouse_filter = Control.MOUSE_FILTER_STOP
				child.tooltip_text = "Drag out to add a connected room"
				child.mouse_default_cursor_shape = Control.CURSOR_CROSS
				child.gui_input.connect(func(ev): _on_anchor_gui_input(ev, child))
				_add_anchor_handle(child)

	if _is_proxy: set_as_proxy(true)
	else: set_node_color(_current_color)
	
	if name_label: name_label.text = _cached_name
	if id_label: id_label.text = _cached_id
	if id_label: id_label.visible = _show_technical_id or _is_proxy
	set_label_arrange_mode(_label_arrange_mode)
	
	update_icons(_npc_visible, _item_visible, _start_visible, _custom_icon_id, _properties)
	_update_border()

## The anchors are bare hit areas on each edge; without something drawn on them
## an author hovering a room saw nothing to drag from. A small round "+" handle
## in the middle of each makes them findable (shown with the anchors, on hover).
func _add_anchor_handle(anchor: Control) -> void:
	if anchor.has_node("Handle"):
		return
	var handle := Label.new()
	handle.name = "Handle"
	handle.text = "+"
	handle.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	handle.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	handle.add_theme_font_size_override("font_size", 13)
	handle.add_theme_color_override("font_color", Color(0.06, 0.1, 0.16))
	var dot := StyleBoxFlat.new()
	dot.bg_color = Color(0.56, 0.81, 1.0)
	dot.border_color = Color(1, 1, 1, 0.9)
	dot.set_border_width_all(1)
	dot.set_corner_radius_all(8)
	handle.add_theme_stylebox_override("normal", dot)
	handle.mouse_filter = Control.MOUSE_FILTER_IGNORE
	handle.size = Vector2(16, 16)
	handle.position = (anchor.size - handle.size) / 2.0
	anchor.add_child(handle)


func get_connection_anchor_point(dir: String) -> Vector2:
	var pos = visual_panel.position
	var size = visual_panel.size
	var c = pos + (size / 2.0)
	var d = dir.to_lower()
	
	if d in ["up", "down", "in", "out", "enter", "exit", "inside", "outside", "climb", "descend", "surface", "dive"]: return to_global(c)
	if d in ["north", "n"]: return to_global(Vector2(c.x, pos.y))
	if d in ["south", "s"]: return to_global(Vector2(c.x, pos.y + size.y))
	if d in ["east", "e"]: return to_global(Vector2(pos.x + size.x, c.y))
	if d in ["west", "w"]: return to_global(Vector2(pos.x, c.y))
	if d in ["northeast", "ne"]: return to_global(Vector2(pos.x + size.x, pos.y))
	if d in ["northwest", "nw"]: return to_global(Vector2(pos.x, pos.y))
	if d in ["southeast", "se"]: return to_global(Vector2(pos.x + size.x, pos.y + size.y))
	if d in ["southwest", "sw"]: return to_global(Vector2(pos.x, pos.y + size.y))
	return to_global(c)

func set_info(name_text: String, id_text: String):
	_cached_name = name_text
	_cached_id = id_text
	if name_label: name_label.text = _preview_name if _preview_name != "" else name_text
	if id_label: id_label.text = id_text

func set_show_technical_id(visible: bool):
	_show_technical_id = visible
	# A proxy's second line is always the linked room's own name, never a raw
	# id -- it stays on regardless of this debug toggle.
	if id_label: id_label.visible = visible or _is_proxy

func set_label_arrange_mode(enabled: bool):
	_label_arrange_mode = enabled
	if not is_node_ready() or not name_label: return
	name_label.mouse_filter = Control.MOUSE_FILTER_STOP if enabled else Control.MOUSE_FILTER_IGNORE
	name_label.tooltip_text = "Click to rename • drag onto another label to swap" if enabled else ""
	_update_label_arrange_style()

func set_label_swap_target(active: bool):
	_is_label_swap_target = active
	_update_label_arrange_style()

func set_label_drag_source(active: bool):
	_is_label_drag_source = active
	_update_label_arrange_style()

func set_label_preview(preview_name: String):
	_preview_name = preview_name
	if name_label: name_label.text = preview_name if preview_name != "" else _cached_name

func _update_label_arrange_style():
	if not is_node_ready() or not name_label: return
	if not _label_arrange_mode:
		name_label.modulate = Color.WHITE
		name_label.remove_theme_stylebox_override("normal")
		return
	var color := Color("60e6ff") # Available label
	if _is_label_drag_source: color = Color("5cf29a") # Label being carried
	elif _is_label_swap_target: color = Color("5cf29a") # Swap destination
	name_label.modulate = color.lightened(0.22)
	var chip := StyleBoxFlat.new()
	chip.bg_color = Color(color.r, color.g, color.b, 0.16)
	chip.border_color = color
	chip.set_border_width_all(2)
	chip.set_corner_radius_all(3)
	chip.content_margin_left = 5
	chip.content_margin_right = 5
	chip.content_margin_top = 2
	chip.content_margin_bottom = 2
	name_label.add_theme_stylebox_override("normal", chip)

func _on_name_label_gui_input(event: InputEvent):
	if not _label_arrange_mode: return
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if event.pressed:
			_label_dragging = true
			_label_drag_origin = get_global_mouse_position()
			emit_signal("label_drag_started", _cached_id)
		else:
			if _label_dragging:
				var was_click := get_global_mouse_position().distance_to(_label_drag_origin) < 8.0
				_label_dragging = false
				if was_click: emit_signal("label_clicked", _cached_id)
				else: emit_signal("label_drag_ended", _cached_id)
	if event is InputEventMouseMotion and _label_dragging:
		emit_signal("label_dragged", _cached_id)

func set_as_proxy(is_proxy: bool):
	_is_proxy = is_proxy
	if is_node_ready() and visual_panel:
		if is_proxy:
			modulate.a = 0.9
			set_node_color(Color(0.15, 0.25, 0.35))
			if id_label:
				id_label.modulate = Color(0.6, 0.8, 1.0)
				# A cross-region link always shows the linked room's name on
				# this second, smaller line -- unlike the technical-id line
				# on a normal room, it is not behind the debug toggle.
				id_label.visible = true
		else:
			modulate.a = 1.0
			if id_label:
				id_label.modulate = Color(1, 1, 1, 0.5)
				id_label.visible = _show_technical_id
	_update_border()

func set_node_color(color: Color):
	_current_color = color
	if is_node_ready() and panel_style:
		panel_style.bg_color = color
		_update_border()

func update_icons(has_npcs: bool, has_items: bool, is_start: bool, custom_icon_id: String, properties: Dictionary):
	_npc_visible = has_npcs
	_item_visible = has_items
	_start_visible = is_start
	_custom_icon_id = custom_icon_id
	_properties = properties
	if not is_node_ready(): return
	visual_panel.queue_redraw()

func _draw_icons():
	var flags = {"start": _start_visible, "npc": _npc_visible, "item": _item_visible}
	RoomIconRenderer.draw_icons(visual_panel, _properties, flags, _current_color)

func set_selected(selected: bool):
	_is_selected = selected
	z_index = 10 if _is_selected else 0
	_update_border()

func set_highlighted(is_highlighted: bool):
	_is_highlighted = is_highlighted
	z_index = 5 if _is_highlighted else (10 if _is_selected else 0)
	_update_border()

func _update_border():
	if not is_node_ready() or not panel_style: return
	
	if _is_highlighted:
		panel_style.border_color = Color(0.2, 0.8, 1.0)
		panel_style.set_border_width_all(4)
	elif _is_selected:
		panel_style.border_color = Color(1.0, 0.7, 0.1)
		panel_style.set_border_width_all(3)
	elif _is_proxy:
		panel_style.border_color = Color(0.3, 0.5, 0.7, 0.8)
		panel_style.set_border_width_all(2)
	else:
		panel_style.border_color = Color(0.8, 0.8, 0.8, 0.2)
		panel_style.set_border_width_all(1)

func _on_mouse_entered():
	if panel_style: panel_style.bg_color = _current_color.lightened(0.15)
	if anchor_container: anchor_container.visible = true
	if not _is_selected and not _is_highlighted: z_index = 5

func _on_mouse_exited():
	if panel_style: panel_style.bg_color = _current_color
	if anchor_container: anchor_container.visible = false
	if not _is_selected and not _is_highlighted: z_index = 0

func _on_panel_gui_input(event):
	# The room card normally absorbs every mouse event over it (mouse_filter
	# STOP, so drags/clicks on the card don't also drag the map underneath),
	# but middle-button panning is a navigation action that should work no
	# matter what's under the cursor -- so it's forwarded up rather than
	# swallowed here, regardless of label-arrange mode or anything else
	# below.
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_MIDDLE:
		_middle_panning = event.pressed
		emit_signal("camera_pan_input", event)
		return
	if event is InputEventMouseMotion and _middle_panning:
		emit_signal("camera_pan_input", event)
		return
	if _label_arrange_mode:
		# The label itself owns editing/swapping in this mode; prevent accidental
		# map movement while an author is arranging presentation.
		if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
			emit_signal("room_selected", _cached_id)
		return
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			if event.pressed:
				# Allow Ctrl OR Shift to start connection drag
				if event.ctrl_pressed or event.shift_pressed: 
					emit_signal("connection_drag_started", _cached_id)
				else: 
					dragging = true
					drag_offset = get_global_mouse_position() - global_position
					emit_signal("room_selected", _cached_id)
					emit_signal("drag_started")
					if event.double_click:
						emit_signal("room_double_clicked", _cached_id)
			else: 
				if dragging: 
					dragging = false
					emit_signal("drag_ended")
		elif event.button_index == MOUSE_BUTTON_RIGHT and event.pressed: 
			emit_signal("right_clicked")

	if event is InputEventMouseMotion and dragging:
		var raw_pos = get_global_mouse_position() - drag_offset
		global_position = raw_pos.snapped(Vector2(snap_step, snap_step)) if snap_step > 0 else raw_pos
		emit_signal("dragged", global_position)

func _on_anchor_gui_input(event: InputEvent, anchor_node: Control):
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		var anchor_global_pos = anchor_node.get_global_rect().get_center()
		emit_signal("creation_drag_started", _cached_id, anchor_global_pos)

func set_passive(enabled: bool):
	if enabled:
		if visual_panel: visual_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
		if anchor_container: 
			anchor_container.visible = false
			for c in anchor_container.get_children():
				if c is Control: c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	else:
		if visual_panel: visual_panel.mouse_filter = Control.MOUSE_FILTER_STOP
