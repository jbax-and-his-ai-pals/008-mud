# scripts/ui/docks/dock_panel.gd
#
# One info panel in a dock (Pack, Character, Equipment...): a titled card that can be collapsed,
# nudged up or down, sent to the other side, or dragged by its title to any position in either
# dock. The content is any Control; the card only owns the frame. Reached through `preload`.
extends PanelContainer

signal changed                       # collapsed, or asked to move: the owner saves the layout
signal move_requested(direction: String)   # "up" | "down" | "side"

var panel_id: String = ""
var title_text: String = ""
var body: Control
var collapsed: bool = false

var _title: Label
var _collapse_button: Button


func setup(id: String, title: String, content: Control, start_collapsed: bool = false) -> void:
	panel_id = id
	title_text = title
	body = content
	name = "Dock_" + id
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var box := VBoxContainer.new()
	box.name = "Box"
	box.add_theme_constant_override("separation", 2)
	add_child(box)

	var header := HBoxContainer.new()
	header.name = "Header"
	header.add_theme_constant_override("separation", 2)
	header.mouse_filter = Control.MOUSE_FILTER_PASS
	box.add_child(header)
	_title = Label.new()
	_title.text = title
	_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_title.mouse_filter = Control.MOUSE_FILTER_PASS
	_title.add_theme_color_override("font_color", Color(0.93, 0.8, 0.45))
	_title.tooltip_text = "Drag to move this panel"
	header.add_child(_title)
	for spec in [["▲", "Move up", "up"], ["▼", "Move down", "down"], ["⇄", "Send to the other side", "side"]]:
		var button := _tool_button(spec[0], spec[1])
		var direction: String = spec[2]
		button.pressed.connect(func() -> void: move_requested.emit(direction))
		header.add_child(button)
	_collapse_button = _tool_button("–", "Collapse or expand")
	_collapse_button.pressed.connect(func() -> void: set_collapsed(not collapsed, true))
	header.add_child(_collapse_button)

	body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.add_child(body)
	set_collapsed(start_collapsed, false)


func set_collapsed(value: bool, announce: bool) -> void:
	collapsed = value
	body.visible = not collapsed
	_collapse_button.text = "+" if collapsed else "–"
	if announce:
		changed.emit()


func _tool_button(text: String, tip: String) -> Button:
	var button := Button.new()
	button.text = text
	button.tooltip_text = tip
	button.flat = true
	button.focus_mode = Control.FOCUS_NONE
	button.custom_minimum_size = Vector2(22, 0)
	button.add_theme_font_size_override("font_size", 12)
	return button


# --- drag by the title ---------------------------------------------------------------

func _get_drag_data(at_position: Vector2) -> Variant:
	var header: Control = get_node("Box/Header") if has_node("Box/Header") else null
	if header == null or at_position.y > header.size.y + 4:
		return null
	var preview := Label.new()
	preview.text = "  " + title_text
	preview.add_theme_color_override("font_color", Color(1, 1, 1))
	set_drag_preview(preview)
	return {"dock_panel": self}
