# scripts/ui/docks/dock_column.gd
#
# A vertical stack of dock panels that accepts a panel dragged from either dock and drops it at
# the position under the mouse. Reached through `preload`.
extends VBoxContainer

signal layout_changed


func _can_drop_data(_at_position: Vector2, data: Variant) -> bool:
	return data is Dictionary and (data as Dictionary).has("dock_panel")


func _drop_data(at_position: Vector2, data: Variant) -> void:
	var panel: Control = (data as Dictionary)["dock_panel"]
	if panel == null:
		return
	var index := get_child_count()
	for child in get_children():
		if child == panel:
			continue
		if at_position.y < child.position.y + child.size.y * 0.5:
			index = child.get_index()
			break
	place(panel, index)


## Puts `panel` in this column at `index` (counting the panel itself out), leaving whatever
## column it came from.
func place(panel: Control, index: int) -> void:
	var old_parent := panel.get_parent()
	if old_parent == self and panel.get_index() < index:
		index -= 1   # the panel's own slot closes up when it is lifted out
	if old_parent != null:
		old_parent.remove_child(panel)
	add_child(panel)
	move_child(panel, clampi(index, 0, get_child_count() - 1))
	layout_changed.emit()
