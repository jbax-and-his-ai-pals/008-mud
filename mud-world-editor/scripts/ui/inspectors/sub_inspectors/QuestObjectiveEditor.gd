# scripts/ui/inspectors/sub_inspectors/QuestObjectiveEditor.gd
#
# One quest objective, edited against `QuestSchema` -- the engine's vocabulary.
#
# Three things this does that the inspector it replaces did not:
#
#   * it writes `type`, `target_template_id`, `required_quantity` and the rest of
#     the engine's field names, so a stage added here can actually be completed;
#   * it offers the types the engine routes (`QuestSchema.TYPES`) plus any type
#     the content already uses, marked when the editor does not know it;
#   * it shows every other key the objective carries as an editable value, so a
#     field this table has not caught up with is visible rather than silently
#     kept or silently dropped.
#
# It renders into whatever container it is given and reports edits through
# `changed`; it owns no state beyond the dictionary it was handed.

class_name QuestObjectiveEditor
extends RefCounted

signal changed
# Structural edits (adding or removing a choice, picking a different type) change
# which rows should exist, so the owner re-renders rather than this editor
# rebuilding itself underneath the widget that was just clicked.
signal rebuild_requested

const ROW_LABEL_WIDTH := 210

var database_mgr: DatabaseManager
var objective: Dictionary
var container: VBoxContainer


func _init(parent: VBoxContainer, data: Dictionary, db_mgr: DatabaseManager):
	container = parent
	objective = data
	database_mgr = db_mgr


func build():
	var type_id := str(objective.get("type", ""))
	_add_type_row(type_id)
	_add_note(type_id)
	_add_field_rows(type_id)
	_add_choices_editor(type_id)
	_add_extra_rows()


# --- rows ---------------------------------------------------------------------

func _add_type_row(type_id: String):
	var row := _row()
	var picker := OptionButton.new()
	var ids := QuestSchema.type_ids()
	if type_id != "" and not QuestSchema.has_type(type_id):
		ids.append(type_id)  # content is ahead of the editor; keep it selectable
	for index in range(ids.size()):
		picker.add_item(_type_label(str(ids[index])))
		picker.set_item_metadata(index, ids[index])
		if str(ids[index]) == type_id:
			picker.select(index)
	if type_id == "":
		picker.select(0)
	picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(picker)
	picker.item_selected.connect(func(index):
		objective["type"] = str(picker.get_item_metadata(index))
		changed.emit()
	)
	row.add_child(picker)


func _type_label(type_id: String) -> String:
	if not QuestSchema.has_type(type_id):
		return "%s  (not a type the editor knows)" % type_id
	return "%s  [%s]" % [QuestSchema.label_for(type_id), type_id]


func _add_note(type_id: String):
	var note := Label.new()
	note.text = QuestSchema.note_for(type_id)
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	note.add_theme_font_size_override("font_size", 11)
	note.modulate = Color(0.65, 0.68, 0.74)
	container.add_child(note)


func _add_field_rows(type_id: String):
	var fields := QuestSchema.authored_fields(type_id)
	for key in fields:
		var kind := str(fields[key])
		var value = objective.get(key)
		if kind == "choices":
			continue  # its own section, below
		_add_value_row(key, kind, value)


func _add_value_row(key: String, kind: String, value):
	var row := _row(key)
	match kind:
		"bool":
			var check := CheckBox.new()
			check.button_pressed = bool(value) if value != null else false
			check.toggled.connect(func(pressed): _apply(key, pressed))
			row.add_child(check)
		"int":
			var spin := SpinBox.new()
			spin.min_value = 0
			spin.max_value = 100000
			spin.step = 1
			spin.value = int(value) if value != null else 0
			spin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			InspectorStyle.apply_input_style(spin)
			spin.value_changed.connect(func(entered): _apply(key, int(entered)))
			row.add_child(spin)
		"npc_id", "item_id":
			var line := LineEdit.new()
			line.text = str(value) if value != null else ""
			line.placeholder_text = "npc template id" if kind == "npc_id" else "item template id"
			line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			InspectorStyle.apply_input_style(line)
			line.text_changed.connect(func(text): _apply(key, text.strip_edges()))
			row.add_child(line)
			InspectorStyle.add_suggestion_button(row, line, func():
				return database_mgr.get_npc_ids() if kind == "npc_id" else database_mgr.get_item_ids()
			)
		"string_list":
			var list := LineEdit.new()
			list.text = ", ".join(_as_string_list(value))
			list.placeholder_text = "comma separated ids"
			list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			InspectorStyle.apply_input_style(list)
			list.text_changed.connect(func(text):
				var ids: Array = []
				for part in text.split(","):
					var trimmed: String = str(part).strip_edges()
					if trimmed != "": ids.append(trimmed)
				_apply(key, ids)
			)
			row.add_child(list)
		_:
			# `json` and anything unmodelled: the value as JSON, so dicts and
			# lists are editable without inventing a widget per shape.
			var text := LineEdit.new()
			text.text = JSON.stringify(value) if value != null else ""
			text.placeholder_text = "JSON value"
			text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			InspectorStyle.apply_input_style(text)
			text.text_changed.connect(func(entered): _set_json(key, entered, text))
			row.add_child(text)


# `choices` is the one shape where the editor can prevent a concrete validation
# failure: every outcome must declare `next_stage` or `complete` (content_set.py),
# and a hand-written map gets that wrong quietly.
func _add_choices_editor(type_id: String):
	var fields := QuestSchema.authored_fields(type_id)
	if str(fields.get("choices", "")) != "choices":
		return
	var header := HBoxContainer.new()
	var label := InspectorStyle.lbl("Choices", InspectorStyle.COLOR_TEXT_DIM)
	header.add_child(label)
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var add := Button.new(); add.text = "+ Outcome"
	InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var choices: Dictionary = objective.get("choices", {})
		var outcome := "outcome_%d" % (choices.size() + 1)
		choices[outcome] = {"complete": true}
		objective["choices"] = choices
		changed.emit()
		rebuild_requested.emit()
	)
	header.add_child(add)
	container.add_child(header)

	var choices: Dictionary = objective.get("choices", {}) if objective.get("choices") is Dictionary else {}
	if choices.is_empty():
		var empty := Label.new()
		empty.text = "No outcomes yet -- this type needs at least one."
		empty.add_theme_font_size_override("font_size", 11)
		empty.modulate = Color(0.8, 0.6, 0.4)
		container.add_child(empty)
		return

	for outcome in choices:
		var branch = choices[outcome]
		if not (branch is Dictionary):
			branch = {}
			choices[outcome] = branch
		container.add_child(_choice_row(str(outcome), branch, choices))


func _choice_row(outcome: String, branch: Dictionary, choices: Dictionary) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)

	var name := LineEdit.new()
	name.text = outcome
	name.custom_minimum_size.x = ROW_LABEL_WIDTH
	InspectorStyle.apply_input_style(name)
	row.add_child(name)

	var target := LineEdit.new()
	target.placeholder_text = "next stage index"
	target.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(target)
	var completes := CheckBox.new()
	completes.text = "completes the quest"
	var next_value = branch.get("next_stage")
	if next_value != null:
		target.text = str(int(next_value))
	completes.button_pressed = bool(branch.get("complete", false)) and next_value == null
	if completes.button_pressed:
		target.editable = false
	target.text_changed.connect(func(text):
		var trimmed: String = str(text).strip_edges()
		if trimmed == "":
			branch.erase("next_stage")
		elif trimmed.is_valid_int():
			branch["next_stage"] = int(trimmed)
		changed.emit()
	)
	completes.toggled.connect(func(pressed):
		target.editable = not pressed
		if pressed:
			branch.erase("next_stage")
			target.text = ""
			branch["complete"] = true
		else:
			branch.erase("complete")
		changed.emit()
	)
	# Renaming an outcome writes the new key and drops the old one.
	name.text_submitted.connect(func(text):
		var renamed: String = str(text).strip_edges()
		if renamed == "" or renamed == outcome or choices.has(renamed):
			name.text = outcome
			return
		choices[renamed] = branch
		choices.erase(outcome)
		changed.emit()
		rebuild_requested.emit()
	)
	row.add_child(target)
	row.add_child(completes)

	var remove := Button.new(); remove.text = "X"
	InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
	remove.pressed.connect(func():
		choices.erase(outcome)
		changed.emit()
		rebuild_requested.emit()
	)
	row.add_child(remove)
	return row


func _add_extra_rows():
	var extras := QuestSchema.extra_keys(objective)
	if extras.is_empty():
		return
	var header := Label.new()
	header.text = "Fields the editor does not model (kept as authored)"
	header.add_theme_font_size_override("font_size", 11)
	header.modulate = Color(0.7, 0.72, 0.6)
	container.add_child(header)
	for key in extras:
		_add_value_row(str(key), "json", objective[key])


# --- helpers ------------------------------------------------------------------

func _row(label_text: String = "") -> HBoxContainer:
	var box := HBoxContainer.new()
	box.add_theme_constant_override("separation", 6)
	if label_text != "":
		var label := InspectorStyle.lbl(_pretty(label_text), InspectorStyle.COLOR_TEXT_DIM)
		label.custom_minimum_size.x = ROW_LABEL_WIDTH
		label.clip_text = true
		label.tooltip_text = label_text
		box.add_child(label)
	container.add_child(box)
	return box


func _pretty(key: String) -> String:
	return key.replace("_", " ").capitalize()


func _apply(key: String, value):
	# An emptied field is removed rather than written as "" or 0: the engine
	# treats a missing optional key as absent, and a blank string is a different
	# thing that a validator will complain about.
	if value is String and str(value) == "":
		objective.erase(key)
	elif value is Array and (value as Array).is_empty():
		objective.erase(key)
	else:
		objective[key] = value
	changed.emit()


func _set_json(key: String, text: String, field: LineEdit):
	var trimmed: String = str(text).strip_edges()
	if trimmed == "":
		objective.erase(key)
		field.modulate = Color.WHITE
		changed.emit()
		return
	var parsed = JSON.parse_string(trimmed)
	if parsed == null:
		field.modulate = Color(1.0, 0.6, 0.6)  # invalid; keep the text, do not write it
		return
	field.modulate = Color.WHITE
	objective[key] = parsed
	changed.emit()


func _as_string_list(value) -> Array:
	if value is Array:
		var out: Array = []
		for entry in value:
			out.append(str(entry))
		return out
	return []
