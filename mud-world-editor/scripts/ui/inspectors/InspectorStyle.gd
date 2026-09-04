# scripts/ui/inspectors/InspectorStyle.gd
class_name InspectorStyle
extends RefCounted

const COLOR_BG_MAIN = Color(0.12, 0.12, 0.14)
const COLOR_BG_CARD = Color(0.18, 0.18, 0.20)
const COLOR_ACCENT = Color(0.3, 0.5, 0.7)
const COLOR_DANGER = Color(0.7, 0.3, 0.3)
const COLOR_SUCCESS = Color(0.3, 0.6, 0.4)
const COLOR_TEXT_DIM = Color(0.6, 0.6, 0.65)

static func create_card() -> PanelContainer:
	var pc = PanelContainer.new()
	var style = StyleBoxFlat.new()
	style.bg_color = COLOR_BG_CARD
	style.set_corner_radius_all(6)
	style.set_border_width_all(1)
	style.border_color = Color(0.25, 0.25, 0.28)
	pc.add_theme_stylebox_override("panel", style)
	
	var margin = MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 12)
	margin.add_theme_constant_override("margin_right", 12)
	margin.add_theme_constant_override("margin_top", 12)
	margin.add_theme_constant_override("margin_bottom", 12)
	pc.add_child(margin)
	
	var vbox = VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 10)
	margin.add_child(vbox)
	
	return pc

static func create_section_header(text: String, color: Color = Color.WHITE) -> Label:
	var l = Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", 12)
	l.add_theme_color_override("font_color", color)
	l.uppercase = true
	return l

static func create_sub_header(text: String) -> Label:
	var l = Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", 14)
	l.add_theme_color_override("font_color", Color(0.8, 0.8, 0.8))
	return l

static func apply_input_style(node: Control):
	var s = StyleBoxFlat.new()
	s.bg_color = Color(0.1, 0.1, 0.12)
	s.set_border_width_all(1)
	s.border_color = Color(0.3, 0.3, 0.35)
	s.set_corner_radius_all(4)
	s.content_margin_left = 8
	
	if node is LineEdit or node is SpinBox:
		node.add_theme_stylebox_override("normal", s)
		node.add_theme_stylebox_override("focus", s.duplicate()) 
	elif node is TextEdit:
		node.add_theme_stylebox_override("normal", s)

static func apply_button_style(btn: Button, bg: Color = Color(0.25, 0.25, 0.3)):
	var s = StyleBoxFlat.new()
	s.bg_color = bg
	s.set_corner_radius_all(4)
	s.content_margin_left = 10; s.content_margin_right = 10
	s.content_margin_top = 4; s.content_margin_bottom = 4
	
	var h = s.duplicate(); h.bg_color = bg.lightened(0.1)
	var p = s.duplicate(); p.bg_color = bg.darkened(0.1)
	
	btn.add_theme_stylebox_override("normal", s)
	btn.add_theme_stylebox_override("hover", h)
	btn.add_theme_stylebox_override("pressed", p)

static func lbl(t, c=Color.WHITE) -> Label:
	var l = Label.new(); l.text=t; l.modulate=c; return l

static func add_suggestion_button(parent: Control, target: LineEdit, getter: Callable):
	var b = MenuButton.new(); b.text=" v "
	apply_button_style(b)
	b.about_to_popup.connect(func():
		var p = b.get_popup(); p.clear()
		for x in getter.call(): p.add_item(x)
		
		# Clean up old signals to avoid stacking
		var conn = p.id_pressed.get_connections()
		for c in conn: p.id_pressed.disconnect(c.callable)
			
		p.id_pressed.connect(func(id): 
			target.text = p.get_item_text(p.get_item_index(id))
			target.text_submitted.emit(target.text)
			target.text_changed.emit(target.text)
		)
	)
	parent.add_child(b)
