# scripts/scenes/QuestNode.gd
extends Control

signal selected(stage_idx)
signal dragged(new_pos)
signal drag_ended

var stage_index: int = -1
var stage_data: Dictionary = {}

var dragging = false
var drag_offset = Vector2()
var _is_selected = false

func setup(idx: int, data: Dictionary):
	stage_index = idx
	stage_data = data
	
	var panel = PanelContainer.new()
	var style = StyleBoxFlat.new()
	style.bg_color = Color(0.1, 0.1, 0.15)
	style.set_corner_radius_all(8)
	style.set_border_width_all(2)
	style.border_color = Color(0.4, 0.4, 0.8)
	panel.add_theme_stylebox_override("panel", style)
	panel.mouse_filter = Control.MOUSE_FILTER_PASS
	
	var margin = MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 8)
	margin.add_theme_constant_override("margin_right", 8)
	margin.add_theme_constant_override("margin_top", 6)
	margin.add_theme_constant_override("margin_bottom", 6)
	panel.add_child(margin)
	
	var vbox = VBoxContainer.new()
	margin.add_child(vbox)
	
	var lbl_id = Label.new()
	lbl_id.text = data.get("id", "stage_%d" % idx)
	lbl_id.add_theme_font_size_override("font_size", 14)
	lbl_id.modulate = Color.CYAN
	vbox.add_child(lbl_id)
	
	var lbl_type = Label.new()
	lbl_type.text = data.get("type", "EVENT")
	lbl_type.add_theme_font_size_override("font_size", 10)
	lbl_type.modulate = Color(0.7, 0.7, 0.7)
	vbox.add_child(lbl_type)
	
	add_child(panel)
	custom_minimum_size = Vector2(140, 60)
	
	# Input Handling
	gui_input.connect(_on_gui_input)

func set_selected(val: bool):
	_is_selected = val
	var p = get_child(0) as PanelContainer
	var s = p.get_theme_stylebox("panel") as StyleBoxFlat
	s.border_color = Color.GOLD if val else Color(0.4, 0.4, 0.8)

func _on_gui_input(event):
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			if event.pressed:
				dragging = true
				drag_offset = get_global_mouse_position() - global_position
				selected.emit(stage_index)
			else:
				if dragging:
					dragging = false
					drag_ended.emit()
	
	if event is InputEventMouseMotion and dragging:
		global_position = get_global_mouse_position() - drag_offset
		dragged.emit(global_position)
