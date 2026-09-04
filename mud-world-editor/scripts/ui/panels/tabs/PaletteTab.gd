# scripts/ui/panels/tabs/PaletteTab.gd

class_name PaletteTab
extends MarginContainer

signal tool_changed(mode, data)

var palette_list: ItemList
var btn_stop_palette: Button
var _cached_npcs: Dictionary = {}
var _cached_items: Dictionary = {}

func setup():
	add_theme_constant_override("margin_left", 5)
	add_theme_constant_override("margin_right", 5)
	add_theme_constant_override("margin_top", 12)
	add_theme_constant_override("margin_bottom", 5)
	
	var pal_vbox = VBoxContainer.new()
	pal_vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	pal_vbox.add_theme_constant_override("separation", 12)
	
	pal_vbox.add_child(_lbl("Content Stamper:", Color.GRAY))
	palette_list = ItemList.new()
	palette_list.size_flags_vertical = 3
	palette_list.add_theme_stylebox_override("bg", StyleBoxFlat.new())
	palette_list.get_theme_stylebox("bg").bg_color = Color(0.05, 0.05, 0.08)
	
	palette_list.item_clicked.connect(func(idx, pos, btn):
		if btn == MOUSE_BUTTON_LEFT:
			tool_changed.emit(EditorUIManager.ToolMode.STAMP, palette_list.get_item_metadata(idx))
	)
	pal_vbox.add_child(palette_list)
	
	btn_stop_palette = Button.new()
	btn_stop_palette.text = "Select Item to Stamp"
	btn_stop_palette.disabled = true
	_apply_style(btn_stop_palette, Color(0.1, 0.1, 0.12))
	btn_stop_palette.pressed.connect(func(): tool_changed.emit(EditorUIManager.ToolMode.SELECT, {}))
	pal_vbox.add_child(btn_stop_palette)
	
	add_child(pal_vbox)

func update_data(npcs, items):
	_cached_npcs = npcs
	_cached_items = items
	_refresh_palette()

func update_stamp_button_state(is_stamping: bool):
	var text = "Stop Stamping (ESC)" if is_stamping else "Select Item to Stamp"
	var col = Color(0.3, 0.1, 0.1) if is_stamping else Color(0.1, 0.1, 0.12)
	
	if btn_stop_palette:
		btn_stop_palette.text = text
		btn_stop_palette.disabled = not is_stamping
		_apply_style(btn_stop_palette, col)
	
	if not is_stamping: palette_list.deselect_all()

func _refresh_palette():
	palette_list.clear()
	# NPCs
	var n_keys = _cached_npcs.keys()
	n_keys.sort()
	for n in n_keys: 
		var idx=palette_list.add_item("NPC: "+n)
		palette_list.set_item_metadata(idx, {"type":"npc","id":n})
		palette_list.set_item_icon(idx, _get_color_icon(Color.SALMON))
	
	# Items
	var i_keys = _cached_items.keys()
	i_keys.sort()
	for i in i_keys: 
		var idx=palette_list.add_item("Item: "+i)
		palette_list.set_item_metadata(idx, {"type":"item","id":i})
		palette_list.set_item_icon(idx, _get_color_icon(Color.AQUAMARINE))

func _apply_style(node: Control, bg_color = Color(0.15, 0.15, 0.18)):
	var s = StyleBoxFlat.new(); s.bg_color = bg_color; s.set_border_width_all(1); s.border_color = Color(0.4, 0.4, 0.45); s.set_corner_radius_all(4); s.content_margin_left = 8; s.content_margin_right = 8
	if node is Button:
		node.add_theme_stylebox_override("normal", s); node.add_theme_stylebox_override("hover", s.duplicate()); node.add_theme_stylebox_override("pressed", s.duplicate())
		node.get_theme_stylebox("hover").bg_color = bg_color.lightened(0.1); node.get_theme_stylebox("pressed").bg_color = bg_color.darkened(0.1)
		var dis = s.duplicate(); dis.bg_color = bg_color.darkened(0.2); dis.border_color = Color(0.3, 0.3, 0.3); node.add_theme_stylebox_override("disabled", dis)

func _lbl(t, c=Color.WHITE): var l=Label.new(); l.text=t; l.modulate=c; return l
func _get_color_icon(col: Color) -> ImageTexture:
	var img = Image.create(16, 16, false, Image.FORMAT_RGBA8); img.fill(col); return ImageTexture.create_from_image(img)
