# scripts/ui/panels/tabs/PaintTab.gd

class_name PaintTab
extends MarginContainer

signal tool_changed(mode, data)

var paint_key_edit: LineEdit
var paint_val_edit: LineEdit

func setup():
	add_theme_constant_override("margin_left", 5)
	add_theme_constant_override("margin_right", 5)
	add_theme_constant_override("margin_top", 12)
	add_theme_constant_override("margin_bottom", 5)
	
	var pnt_vbox = VBoxContainer.new()
	pnt_vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	pnt_vbox.add_theme_constant_override("separation", 12)
	
	pnt_vbox.add_child(_lbl("Key:", Color.GRAY))
	paint_key_edit = LineEdit.new(); paint_key_edit.text = "biome"; _apply_style(paint_key_edit)
	pnt_vbox.add_child(paint_key_edit)
	pnt_vbox.add_child(_lbl("Value:", Color.GRAY))
	paint_val_edit = LineEdit.new(); paint_val_edit.text = "swamp"; _apply_style(paint_val_edit)
	pnt_vbox.add_child(paint_val_edit)
	pnt_vbox.add_child(HSeparator.new())
	var btn_start_paint = Button.new(); btn_start_paint.text = "Activate Paint Mode"; _apply_style(btn_start_paint, Color(0.2, 0.3, 0.2))
	btn_start_paint.pressed.connect(func(): tool_changed.emit(EditorUIManager.ToolMode.PAINT, {"key": paint_key_edit.text, "val": paint_val_edit.text}))
	pnt_vbox.add_child(btn_start_paint)
	var btn_stop_paint = Button.new(); btn_stop_paint.text = "Stop Painting (ESC)"; _apply_style(btn_stop_paint)
	btn_stop_paint.pressed.connect(func(): tool_changed.emit(EditorUIManager.ToolMode.SELECT, {}))
	pnt_vbox.add_child(btn_stop_paint)
	
	add_child(pnt_vbox)

func _apply_style(node: Control, bg_color = Color(0.15, 0.15, 0.18)):
	var s = StyleBoxFlat.new(); s.bg_color = bg_color; s.set_border_width_all(1); s.border_color = Color(0.4, 0.4, 0.45); s.set_corner_radius_all(4); s.content_margin_left = 8; s.content_margin_right = 8
	if node is Button:
		node.add_theme_stylebox_override("normal", s); node.add_theme_stylebox_override("hover", s.duplicate()); node.add_theme_stylebox_override("pressed", s.duplicate())
		node.get_theme_stylebox("hover").bg_color = bg_color.lightened(0.1); node.get_theme_stylebox("pressed").bg_color = bg_color.darkened(0.1)
	elif node is LineEdit:
		var s2 = s.duplicate(); s2.bg_color = Color(0.08,0.08,0.1); node.add_theme_stylebox_override("normal", s2)

func _lbl(t, c=Color.WHITE): var l=Label.new(); l.text=t; l.modulate=c; return l
