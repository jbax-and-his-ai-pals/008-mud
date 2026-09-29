# scripts/ui/inspectors/panels/EffectRows.gd
class_name EffectRows
extends RefCounted

## The editor for an `effects` mapping: a dialogue choice's or node's, or a
## knowledge topic response's. All three mean the same thing by it
## (`engine/dialogue/effects.py`), so they share one editor.
##
## Why this is shared
## ------------------
## `DialogueInspector` and `KnowledgeInspector` each carried a copy of the row
## builder, and the copies had drifted: the dialogue one's "+ Effect" wrote
## `set_flag` over an existing `set_flag` (silently losing it), and both let
## changing an effect's key carry its old value across (a flag name became the
## amount of `give_gold`), turned the text `true` into the string "true" (so
## `advance_quest: true` -- "every active quest" -- could not be authored), and
## turned any digits into a number even for a flag whose name is "42".
##
## What each value is
## ------------------
## `DialogueSchema.effect_kind` says: a whole number gets a SpinBox; an id gets a
## text box with a suggestion list; anything shaped as an object or a list (the
## list forms of `set_flag` and `give_item`, `give_rewards`) is edited as JSON,
## because the engine accepts them and the box must not flatten them. A value the
## box cannot hold faithfully falls back to text, so what was authored is what is
## shown.
##
## Widget names are part of the contract with `effect_condition_rows_smoke.gd`:
## `EffectRow_<key>` holds `EffectPicker`, `EffectValue` and `EffectRemove`.

const NAME_ADD := "AddEffect"
const NAME_PICKER := "EffectPicker"
const NAME_VALUE := "EffectValue"
const NAME_REMOVE := "EffectRemove"
const COLOR_BAD := Color(1.0, 0.6, 0.6)


## Header, "+ Effect" and one row per effect under `parent`. `owner` is the
## dictionary that holds (or will hold) the `effects` key; `on_changed` is called
## after every edit so the caller can mark its data dirty.
static func build(parent: VBoxContainer, owner: Dictionary, label_text: String,
		database_mgr: DatabaseManager, on_changed: Callable) -> void:
	var rows := VBoxContainer.new()
	rows.name = "EffectRows"
	rows.add_theme_constant_override("separation", 4)

	var header := HBoxContainer.new()
	var label := InspectorStyle.lbl(label_text, InspectorStyle.COLOR_TEXT_DIM)
	label.add_theme_font_size_override("font_size", 11)
	header.add_child(label)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var add := Button.new()
	add.text = "+ Effect"
	add.name = NAME_ADD
	InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var chosen := _next_unused_key(_effects_of(owner))
		if chosen == "":
			return
		_set_effect(owner, chosen, DialogueSchema.default_effect_value(chosen))
		on_changed.call()
		_refill(rows, owner, database_mgr, on_changed)
	)
	header.add_child(add)
	parent.add_child(header)
	parent.add_child(rows)
	_refill(rows, owner, database_mgr, on_changed)


# --- the mapping -------------------------------------------------------------

static func _effects_of(owner: Dictionary) -> Dictionary:
	var effects = owner.get("effects")
	return effects if effects is Dictionary else {}


# Written back through the owner every time: an emptied mapping is removed from
# it (the validator has nothing to say about an absent key, and canonical JSON
# should not carry `"effects": {}`), so a reference held across edits would point
# at a dictionary the owner no longer has.
static func _set_effect(owner: Dictionary, key: String, value) -> void:
	var effects := _effects_of(owner)
	effects[key] = value
	owner["effects"] = effects


static func _erase_effect(owner: Dictionary, key: String) -> void:
	var effects := _effects_of(owner)
	effects.erase(key)
	if effects.is_empty():
		owner.erase("effects")


# `set_flag` first: it is what most conversations need and what "+ Effect" has
# always started with. After that, the schema's own order.
static func _next_unused_key(effects: Dictionary) -> String:
	if not effects.has("set_flag"):
		return "set_flag"
	for candidate in DialogueSchema.effect_keys():
		if not effects.has(str(candidate)):
			return str(candidate)
	return ""


# --- rows --------------------------------------------------------------------

static func _refill(rows: VBoxContainer, owner: Dictionary, database_mgr: DatabaseManager,
		on_changed: Callable) -> void:
	# Removed as well as freed: `queue_free` alone leaves the old rows in the tree
	# until the frame ends, so a rebuild would briefly show both sets.
	for child in rows.get_children():
		rows.remove_child(child)
		child.queue_free()
	var effects := _effects_of(owner)
	if effects.is_empty():
		rows.add_child(InspectorStyle.lbl("None.", InspectorStyle.COLOR_TEXT_DIM))
		return
	for key in effects.keys():
		rows.add_child(_effect_row(rows, owner, str(key), database_mgr, on_changed))


static func _effect_row(rows: VBoxContainer, owner: Dictionary, key: String,
		database_mgr: DatabaseManager, on_changed: Callable) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.name = "EffectRow_%s" % key
	row.add_theme_constant_override("separation", 6)

	var picker := OptionButton.new()
	picker.name = NAME_PICKER
	var keys: Array = DialogueSchema.effect_keys()
	if not DialogueSchema.has_effect(key):
		keys.append(key)   # an effect this editor does not know stays visible and editable
	for candidate in keys:
		picker.add_item(str(candidate))
	picker.select(maxi(0, keys.find(key)))
	picker.custom_minimum_size.x = 210
	InspectorStyle.apply_button_style(picker)
	picker.item_selected.connect(func(selected):
		var chosen := str(keys[selected])
		var effects := _effects_of(owner)
		if chosen == key or effects.has(chosen):
			# One of each: a second `give_item` would replace the first.
			_refill(rows, owner, database_mgr, on_changed)
			return
		var value = effects.get(key)
		_erase_effect(owner, key)
		_set_effect(owner, chosen, value if _carries_over(key, chosen, value) else DialogueSchema.default_effect_value(chosen))
		on_changed.call()
		_refill(rows, owner, database_mgr, on_changed)
	)
	row.add_child(picker)

	var value = _effects_of(owner).get(key)
	var widget := _value_widget(owner, key, value, on_changed)
	row.add_child(widget)
	if widget is LineEdit and not (value is Dictionary or value is Array):
		_add_suggestions(row, widget, DialogueSchema.effect_kind(key), database_mgr)

	var remove := Button.new()
	remove.text = "×"
	remove.name = NAME_REMOVE
	InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
	remove.pressed.connect(func():
		_erase_effect(owner, key)
		on_changed.call()
		_refill(rows, owner, database_mgr, on_changed)
	)
	row.add_child(remove)
	return row


# Changing an effect's key keeps its value only where the two mean the same kind
# of thing. Otherwise a flag name would become `give_gold`'s amount, or `true`
# an item id.
static func _carries_over(from_key: String, to_key: String, value) -> bool:
	if value is Dictionary or value is Array or typeof(value) == TYPE_BOOL:
		return false
	return DialogueSchema.effect_kind(from_key) == DialogueSchema.effect_kind(to_key)


# --- values ------------------------------------------------------------------

static func _is_whole(value) -> bool:
	if typeof(value) == TYPE_INT:
		return true
	return typeof(value) == TYPE_FLOAT and value == floor(value)


static func _value_widget(owner: Dictionary, key: String, value, on_changed: Callable) -> Control:
	var shape := DialogueSchema.effect_shape(key)
	if DialogueSchema.effect_kind(key) == "int" and _is_whole(value) and int(value) >= 1:
		var spin := SpinBox.new()
		spin.name = NAME_VALUE
		spin.min_value = 1
		spin.max_value = 1000000
		spin.step = 1
		spin.rounded = true
		spin.value = int(value)
		spin.tooltip_text = shape
		spin.custom_minimum_size.x = 130
		spin.value_changed.connect(func(amount):
			_set_effect(owner, key, int(amount))
			on_changed.call()
		)
		return spin

	var line := LineEdit.new()
	line.name = NAME_VALUE
	line.text = JSON.stringify(value) if (value is Dictionary or value is Array) else str(value)
	line.placeholder_text = shape
	line.tooltip_text = shape
	line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(line)
	line.text_changed.connect(func(text):
		var trimmed := str(text).strip_edges()
		if trimmed == "":
			_erase_effect(owner, key)
			line.modulate = Color.WHITE
			on_changed.call()
			return
		var parsed := parse_text(key, trimmed)
		if not parsed.get("ok", false):
			line.modulate = COLOR_BAD
			return
		line.modulate = Color.WHITE
		_set_effect(owner, key, parsed["value"])
		on_changed.call()
	)
	return line


## What a typed line means for this effect: `{"ok": bool, "value": ...}`.
##   {...} / [...]  JSON (the list and object forms); malformed JSON is refused
##   true           a bool, for the effects that take it (advance/complete quest)
##   digits         a whole number, only where the effect's value is a number
##   anything else  text -- so a flag called "42" stays "42"
static func parse_text(key: String, trimmed: String) -> Dictionary:
	if trimmed.begins_with("{") or trimmed.begins_with("["):
		# `parse`, not `parse_string`: that one logs an engine error for every
		# keystroke that is not valid JSON yet.
		var json := JSON.new()
		if json.parse(trimmed) != OK or json.data == null:
			return {"ok": false}
		return {"ok": true, "value": json.data}
	if trimmed == "true" and DialogueSchema.effect_accepts_true(key):
		return {"ok": true, "value": true}
	if DialogueSchema.effect_kind(key) == "int" and trimmed.is_valid_int():
		return {"ok": true, "value": int(trimmed)}
	return {"ok": true, "value": trimmed}


static func _add_suggestions(row: HBoxContainer, line: LineEdit, kind: String, database_mgr: DatabaseManager) -> void:
	match kind:
		"item_id": InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_item_ids())
		"quest_id": InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_ids("quest"))
		"recipe_id": InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_recipe_ids())
