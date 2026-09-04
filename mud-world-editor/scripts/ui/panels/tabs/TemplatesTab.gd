# scripts/ui/panels/tabs/TemplatesTab.gd

class_name TemplatesTab
extends MarginContainer

signal tool_changed(mode, data)
signal request_delete_db_entry(type, id)
signal request_context_menu(global_pos, meta)

var template_list: ItemList
var btn_stop_template: Button
var _cached_templates: Dictionary = {}

func setup():
	add_theme_constant_override("margin_left", 5)
	add_theme_constant_override("margin_right", 5)
	add_theme_constant_override("margin_top", 12)
	add_theme_constant_override("margin_bottom", 5)
	
	var t_vbox = VBoxContainer.new()
	t_vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	t_vbox.add_theme_constant_override("separation", 12)
	
	t_vbox.add_child(_lbl("Room Prefabs:", Color.GRAY))
	
	template_list = ItemList.new()
	template_list.size_flags_vertical = 3
	template_list.add_theme_stylebox_override("bg", StyleBoxFlat.new())
	template_list.get_theme_stylebox("bg").bg_color = Color(0.05, 0.05, 0.08)
	
	template_list.item_clicked.connect(func(idx, pos, btn):
		if btn == MOUSE_BUTTON_LEFT:
			tool_changed.emit(EditorUIManager.ToolMode.STAMP, {"type": "room_template", "id": template_list.get_item_metadata(idx)})
		elif btn == MOUSE_BUTTON_RIGHT:
			var id = template_list.get_item_metadata(idx)
			var global_pos = template_list.get_global_position() + pos
			var meta = {"type": "db_entry", "kind": "template", "id": id}
			request_context_menu.emit(global_pos, meta)
	)
	t_vbox.add_child(template_list)
	
	var btn_del = Button.new()
	btn_del.text = "Delete Template"
	_apply_style(btn_del, Color(0.3, 0.1, 0.1))
	btn_del.pressed.connect(func():
		if not template_list.is_anything_selected(): return
		var idx = template_list.get_selected_items()[0]
		request_delete_db_entry.emit("template", template_list.get_item_metadata(idx))
	)
	t_vbox.add_child(btn_del)
	
	btn_stop_template = Button.new()
	btn_stop_template.text = "Select Item to Stamp"
	btn_stop_template.disabled = true
	_apply_style(btn_stop_template, Color(0.1, 0.1, 0.12))
	btn_stop_template.pressed.connect(func(): tool_changed.emit(EditorUIManager.ToolMode.SELECT, {}))
	t_vbox.add_child(btn_stop_template)
	
	add_child(t_vbox)

func update_templates(templates):
	_cached_templates = templates
	_refresh_templates()

func update_stamp_button_state(is_stamping: bool):
	var text = "Stop Stamping (ESC)" if is_stamping else "Select Item to Stamp"
	var col = Color(0.3, 0.1, 0.1) if is_stamping else Color(0.1, 0.1, 0.12)
	
	if btn_stop_template:
		btn_stop_template.text = text
		btn_stop_template.disabled = not is_stamping
		_apply_style(btn_stop_template, col)
	
	if not is_stamping: template_list.deselect_all()

func _refresh_templates():
	template_list.clear()
	var t_keys = _cached_templates.keys()
	t_keys.sort()
	for t in t_keys:
		var idx = template_list.add_item(t)
		template_list.set_item_metadata(idx, t)
		template_list.set_item_icon(idx, _get_color_icon(Color.GOLD))

func _apply_style(node: Control, bg_color = Color(0.15, 0.15, 0.18)):
	var s = StyleBoxFlat.new(); s.bg_color = bg_color; s.set_border_width_all(1); s.border_color = Color(0.4, 0.4, 0.45); s.set_corner_radius_all(4); s.content_margin_left = 8; s.content_margin_right = 8
	if node is Button:
		node.add_theme_stylebox_override("normal", s); node.add_theme_stylebox_override("hover", s.duplicate()); node.add_theme_stylebox_override("pressed", s.duplicate())
		node.get_theme_stylebox("hover").bg_color = bg_color.lightened(0.1); node.get_theme_stylebox("pressed").bg_color = bg_color.darkened(0.1)
		var dis = s.duplicate(); dis.bg_color = bg_color.darkened(0.2); dis.border_color = Color(0.3, 0.3, 0.3); node.add_theme_stylebox_override("disabled", dis)

func _lbl(t, c=Color.WHITE): var l=Label.new(); l.text=t; l.modulate=c; return l
func _get_color_icon(col: Color) -> ImageTexture:
	var img = Image.create(16, 16, false, Image.FORMAT_RGBA8); img.fill(col); return ImageTexture.create_from_image(img)
