# scripts/ui/docks/dock_column.gd
#
# A vertical stack of dock panels that accepts a panel dragged from either dock and drops it at
# the position under the mouse. While a panel is being dragged, the column shows where it would
# land: the panel is lifted out of the layout and an outlined box of its size takes the slot, so
# the other panels move to show the result. Reached through `preload`.
extends VBoxContainer

signal layout_changed

const GROUP := "dock_columns"
const SEPARATION := 6

var _preview: PanelContainer
var _dragged: Control


func _ready() -> void:
	add_to_group(GROUP)


func _can_drop_data(at_position: Vector2, data: Variant) -> bool:
	if not (data is Dictionary and (data as Dictionary).has("dock_panel")):
		return false
	show_preview_at(at_position.y, (data as Dictionary)["dock_panel"])
	return true


func _drop_data(at_position: Vector2, data: Variant) -> void:
	var panel: Control = (data as Dictionary)["dock_panel"]
	if panel == null:
		return
	place(panel, slot_at(at_position.y, panel))


func _notification(what: int) -> void:
	if what == NOTIFICATION_DRAG_END or what == NOTIFICATION_MOUSE_EXIT:
		# the mouse left this column, or the drag ended (dropped, or cancelled): no box here
		clear_preview()
	if what == NOTIFICATION_DRAG_END:
		for card in get_children():
			card.visible = true
		_dragged = null


## The slot a panel dropped at height `y` (in this column) would take, counting only the other
## panels: 0 is the top. The preview box and the dragged panel are not counted. Positions are the
## ones on screen, box included, so the slot under the mouse is the one the box already holds.
func slot_at(y: float, panel: Control) -> int:
	var slot := 0
	for child in get_children():
		if child == panel or child == _preview or not (child is Control):
			continue
		if y < child.position.y + child.size.y * 0.5:
			return slot
		slot += 1
	return slot


func show_preview_at(y: float, panel: Control) -> void:
	for column in get_tree().get_nodes_in_group(GROUP):
		if column != self:
			column.clear_preview()
	_dragged = panel
	var slot := slot_at(y, panel)
	if _preview == null:
		_preview = _make_preview()
	var height: float = float(panel.get_meta("drag_height", 60.0))
	_preview.custom_minimum_size = Vector2(0, height)
	if _preview.get_parent() == self and _slot_of_preview(panel) == slot:
		return
	if _preview.get_parent() != null:
		_preview.get_parent().remove_child(_preview)
	add_child(_preview)
	var others: Array = []
	for child in get_children():
		if child != panel and child != _preview:
			others.append(child)
	move_child(_preview, others[slot].get_index() if slot < others.size() else get_child_count() - 1)


func clear_preview() -> void:
	if _preview != null and _preview.get_parent() != null:
		_preview.get_parent().remove_child(_preview)


## Where the preview box currently sits, counted among the other panels.
func _slot_of_preview(panel: Control) -> int:
	var slot := 0
	for child in get_children():
		if child == _preview:
			return slot
		if child != panel:
			slot += 1
	return slot


func _make_preview() -> PanelContainer:
	var box := PanelContainer.new()
	box.name = "DropPreview"
	box.mouse_filter = Control.MOUSE_FILTER_PASS
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.93, 0.8, 0.45, 0.10)
	style.border_color = Color(0.93, 0.8, 0.45, 0.85)
	style.set_border_width_all(2)
	style.set_corner_radius_all(10)
	style.anti_aliasing = true
	box.add_theme_stylebox_override("panel", style)
	# dropping onto the box itself is dropping at its slot
	box.set_drag_forwarding(Callable(),
		func(pos: Vector2, data: Variant) -> bool: return _can_drop_data(pos + box.position, data),
		func(pos: Vector2, data: Variant) -> void: _drop_data(pos + box.position, data))
	var label := Label.new()
	label.text = "Drop here"
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.mouse_filter = Control.MOUSE_FILTER_PASS
	label.add_theme_color_override("font_color", Color(0.93, 0.8, 0.45, 0.9))
	box.add_child(label)
	return box


## Puts `panel` in this column at `slot` (counting only the other panels), leaving whatever column
## it came from.
func place(panel: Control, slot: int) -> void:
	for column in get_tree().get_nodes_in_group(GROUP):
		column.clear_preview()
	var old_parent := panel.get_parent()
	if old_parent != null:
		old_parent.remove_child(panel)
	add_child(panel)
	panel.visible = true
	move_child(panel, clampi(slot, 0, get_child_count() - 1))
	layout_changed.emit()
