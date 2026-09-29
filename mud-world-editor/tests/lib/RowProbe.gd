# tests/lib/RowProbe.gd
#
# Finds the rows an inspector built, by what they are rather than by the names
# `EffectRows` / `ConditionRows` give them, so the same check can be pointed at an
# older inspector and fail for the right reason. Not a `class_name`: preload it.
extends RefCounted


# The row whose first child is a picker currently showing `key`.
static func effect_row(holder: Node, key: String) -> HBoxContainer:
	for row in _all(holder, "HBoxContainer"):
		if row.get_child_count() < 2:
			continue
		var picker = row.get_child(0)
		if picker is OptionButton and picker.selected >= 0 and picker.get_item_text(picker.selected) == key:
			return row
	return null


# The control that holds an effect's value: the picker's neighbour.
static func value_widget(holder: Node, key: String) -> Control:
	var row := effect_row(holder, key)
	return row.get_child(1) if row != null else null


# Every button with this text, in tree order (a dialogue inspector has one
# "+ Effect" for the node and one per choice).
static func buttons(holder: Node, text: String) -> Array:
	var found: Array = []
	for candidate in _all(holder, "Button"):
		if (candidate as Button).text == text:
			found.append(candidate)
	return found


# The first picker whose first entry is `none_label`: the condition kind picker.
static func condition_picker(holder: Node, none_label: String) -> OptionButton:
	for picker in _all(holder, "OptionButton"):
		if (picker as OptionButton).item_count > 0 and (picker as OptionButton).get_item_text(0) == none_label:
			return picker
	return null


# A text box whose content is `text` exactly.
static func line_showing(holder: Node, text: String) -> LineEdit:
	for line in _all(holder, "LineEdit"):
		if (line as LineEdit).text == text:
			return line
	return null


# Types into a box the way a person does: the change signal fires.
static func type_into(line: LineEdit, value: String) -> void:
	line.text = value
	line.text_changed.emit(value)


static func _all(node: Node, type_name: String) -> Array:
	var found: Array = []
	if node.is_class(type_name):
		found.append(node)
	for child in node.get_children():
		if child.is_queued_for_deletion():
			continue
		found.append_array(_all(child, type_name))
	return found
