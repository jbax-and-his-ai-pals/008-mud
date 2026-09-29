# scripts/ui/inspectors/panels/ConditionRows.gd
class_name ConditionRows
extends RefCounted

## The editor for one condition: a kind picker, that kind's fields, and a JSON box
## for what the editor does not model. A dialogue choice's `condition` and a
## title's `condition` / `requirements` are the same predicate language
## (`engine/conditions.py`), so they share one editor.
##
## Why this is shared
## ------------------
## `DialogueInspector` and `TitleInspector` each carried a copy, and the copies
## had drifted. A condition with no `kind` -- an `all` / `any` / `not`
## composite, which is how a real gate is written -- got a box to edit it in the
## dialogue inspector and a bare, empty picker in the title inspector, so an
## author could not see or change a composite title gate at all.
##
## Storage differs (a choice's `condition` is a key; a title requirement is an
## array element), so the editor takes callbacks rather than a holder:
## `on_kind_changed(kind)` (`""` means "no condition") and `on_replaced(dict)`
## for a whole-condition JSON edit. The caller assigns; this never has the
## container, and a `{}` never reaches it -- the validator reports a condition
## object with no `kind` as an error.
##
## Widget names are part of the contract with `effect_condition_rows_smoke.gd`:
## `ConditionPicker`, `ConditionField_<field>` and `ConditionExtras`.

const NAME_PICKER := "ConditionPicker"
const NAME_EXTRAS := "ConditionExtras"
const COLOR_BAD := Color(1.0, 0.6, 0.6)


## `condition` is what the caller holds now (a Dictionary, or anything else for
## "none"). `none_label` is the picker's first entry, which the caller words for
## its own context ("(always offered)", "(none)").
static func build(parent: VBoxContainer, condition, database_mgr: DatabaseManager, label_text: String,
		none_label: String, on_changed: Callable, on_kind_changed: Callable, on_replaced: Callable) -> void:
	var current: Dictionary = condition if condition is Dictionary else {}
	var current_kind := str(current.get("kind", ""))

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	row.add_child(InspectorStyle.lbl(label_text, InspectorStyle.COLOR_TEXT_DIM))
	var picker := OptionButton.new()
	picker.name = NAME_PICKER
	var kinds: Array = [none_label] + DialogueSchema.condition_kinds()
	if current_kind != "" and not DialogueSchema.has_condition_kind(current_kind):
		kinds.append(current_kind)   # a kind this editor does not know stays visible
	for kind in kinds:
		picker.add_item(str(kind))
	var index := kinds.find(current_kind) if current_kind != "" else 0
	picker.select(index if index >= 0 else 0)
	InspectorStyle.apply_button_style(picker)
	picker.item_selected.connect(func(selected):
		var chosen := str(kinds[selected])
		on_kind_changed.call("" if chosen == none_label else chosen)
	)
	row.add_child(picker)
	parent.add_child(row)

	if current_kind == "":
		# No kind but something there: a composite (all / any / not), or a
		# condition written by hand. Shown whole, editable as JSON.
		if not current.is_empty():
			parent.add_child(_json_row("    condition", current, [], on_changed, on_replaced))
		return

	var note := Label.new()
	note.text = DialogueSchema.condition_note(current_kind)
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	note.add_theme_font_size_override("font_size", 11)
	note.modulate = Color(0.68, 0.7, 0.78)
	parent.add_child(note)

	var fields := DialogueSchema.condition_fields(current_kind)
	for field in fields:
		parent.add_child(_field_row(current, str(field), str(fields[field]), database_mgr, on_changed))

	# Any key the schema does not name (a field added to the engine since) stays
	# visible and editable.
	var extras: Array = []
	for key in current:
		if str(key) != "kind" and not fields.has(str(key)):
			extras.append(key)
	if not extras.is_empty():
		parent.add_child(_json_row("    other fields", current, extras, on_changed, on_replaced))


static func _field_row(condition: Dictionary, key: String, kind: String, database_mgr: DatabaseManager,
		on_changed: Callable) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.name = "ConditionField_%s" % key
	row.add_theme_constant_override("separation", 6)
	row.add_child(InspectorStyle.lbl("    " + key.replace("_", " "), InspectorStyle.COLOR_TEXT_DIM))
	var line := LineEdit.new()
	line.name = "ConditionValue"
	line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if kind == "int":
		line.text = str(int(condition.get(key, 0)))
	else:
		line.text = str(condition.get(key, ""))
	line.placeholder_text = kind
	InspectorStyle.apply_input_style(line)
	line.text_changed.connect(func(text):
		var trimmed := str(text).strip_edges()
		if trimmed == "":
			condition.erase(key)
		elif kind == "int" and trimmed.is_valid_int():
			condition[key] = int(trimmed)
		else:
			condition[key] = trimmed
		on_changed.call()
	)
	row.add_child(line)
	match kind:
		"item_id": InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_item_ids())
		"npc_id": InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_npc_ids())
		"quest_id": InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_ids("quest"))
		"recipe_id": InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_recipe_ids())
	return row


# `keys` empty: the whole condition, replaced through `on_replaced`. Otherwise
# only those keys, edited in place.
static func _json_row(label_text: String, condition: Dictionary, keys: Array, on_changed: Callable,
		on_replaced: Callable) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.name = NAME_EXTRAS
	row.add_theme_constant_override("separation", 6)
	row.add_child(InspectorStyle.lbl(label_text, InspectorStyle.COLOR_TEXT_DIM))
	var line := LineEdit.new()
	line.name = "ConditionExtrasValue"
	var subset := {}
	if keys.is_empty():
		for key in condition:
			subset[key] = condition[key]
	else:
		for key in keys:
			subset[key] = condition[key]
	line.text = JSON.stringify(subset)
	line.tooltip_text = "Composite conditions (all/any/not) and fields the editor does not model are edited here."
	line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(line)
	line.text_changed.connect(func(text):
		var json := JSON.new()   # `parse` does not log an error per half-typed keystroke
		if json.parse(str(text).strip_edges()) != OK or typeof(json.data) != TYPE_DICTIONARY:
			line.modulate = COLOR_BAD
			return
		var parsed: Dictionary = json.data
		line.modulate = Color.WHITE
		if keys.is_empty():
			on_replaced.call(parsed)
		else:
			for key in keys:
				condition.erase(key)
			for key in parsed:
				condition[key] = parsed[key]
			on_changed.call()
	)
	row.add_child(line)
	return row
