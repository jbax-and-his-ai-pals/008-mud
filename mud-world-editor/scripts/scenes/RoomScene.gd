# scripts/scenes/RoomScene.gd
extends Node2D

signal room_selected(room_id)
signal dragged(new_position)
signal right_clicked
signal connection_drag_started(room_id)
signal creation_drag_started(room_id, anchor_pos)
signal drag_started
signal drag_ended

var dragging = false
var drag_offset = Vector2()

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
	name_label.add_theme_font_size_override("font_size", 13)
	name_label.modulate = Color(1, 1, 1, 1.0)
	name_label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	
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
				child.gui_input.connect(func(ev): _on_anchor_gui_input(ev, child))

	if _is_proxy: set_as_proxy(true)
	else: set_node_color(_current_color)
	
	if name_label: name_label.text = _cached_name
	if id_label: id_label.text = _cached_id
	
	update_icons(_npc_visible, _item_visible, _start_visible, _custom_icon_id, _properties)
	_update_border()

func get_connection_anchor_point(dir: String) -> Vector2:
	var pos = visual_panel.position
	var size = visual_panel.size
	var c = pos + (size / 2.0)
	var d = dir.to_lower()
	
	if d in ["up", "down", "in", "out", "climb", "dive"]: return to_global(c)
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
	if name_label: name_label.text = name_text
	if id_label: id_label.text = id_text

func set_as_proxy(is_proxy: bool):
	_is_proxy = is_proxy
	if is_node_ready() and visual_panel:
		if is_proxy:
			modulate.a = 0.9
			set_node_color(Color(0.15, 0.25, 0.35)) 
			if id_label: id_label.modulate = Color(0.6, 0.8, 1.0)
		else:
			modulate.a = 1.0
			if id_label: id_label.modulate = Color(1, 1, 1, 0.5)
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
