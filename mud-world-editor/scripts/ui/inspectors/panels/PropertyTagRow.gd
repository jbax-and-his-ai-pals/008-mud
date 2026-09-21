# scripts/ui/inspectors/panels/PropertyTagRow.gd
class_name PropertyTagRow
extends RefCounted

## One row of an inspector's property list, and the rule for which properties get
## a row at all.
##
## Why this is shared rather than duplicated
## ----------------------------------------
## A property whose value is a Dictionary or an Array cannot be edited in a
## LineEdit. `str(val)` renders it as GDScript's debug form -- not JSON, not
## parseable -- and the submit handler then writes that string back over the
## object. A room carrying `properties.hidden_exits`, which `effects.py` and
## `interactive.py` read as a real traversable link, silently became a string the
## first time an author touched any row in the panel.
##
## `RegionInspector` guarded against this; `RoomPropertiesPanel` did not, so the
## same panel shape had two behaviours and only one of them was safe. Six shipped
## rooms carry a nested property, three of them `weather_hazard_multipliers` on
## the room, so this was reachable from the editor's ordinary use.
##
## The rule now lives here. A panel does not decide for itself which values it can
## edit inline; it asks, and it renders what it is told -- including the ones it
## must leave alone, which are shown rather than hidden so the author can see that
## the value survives.

## True when `value` can be edited through a single LineEdit without loss.
##
## Dictionaries and Arrays are the only types that cannot: everything else has a
## faithful one-line text form. Deliberately a positive test of the two shapes
## rather than `typeof(val) in [...]`, so a new Variant type defaults to editable
## rather than silently vanishing from every panel.
static func is_inline_editable(value: Variant) -> bool:
	var t := typeof(value)
	return t != TYPE_DICTIONARY and t != TYPE_ARRAY


## The keys of `properties` that a panel may render as editable rows, in the
## dictionary's own order so the list does not reshuffle between refreshes.
static func editable_keys(properties: Dictionary) -> Array:
	var keys: Array = []
	for key in properties:
		if is_inline_editable(properties[key]):
			keys.append(key)
	return keys


## The keys whose values are structured and must be left to a dedicated editor.
static func nested_keys(properties: Dictionary) -> Array:
	var keys: Array = []
	for key in properties:
		if not is_inline_editable(properties[key]):
			keys.append(key)
	return keys


## Build one editable row: `label: [value] [x]`.
##
## `props` is the dictionary the row writes back into -- the room's or region's own
## `properties`, not a copy -- so an edit reaches the data the moment it is
## submitted, which is what the inspectors rely on.
static func build_row(
	key: String,
	value: Variant,
	props: Dictionary,
	on_modified: Callable,
	on_refresh: Callable,
	allow_delete: bool = true
) -> PanelContainer:
	var panel := PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.25, 0.25, 0.28)
	style.set_corner_radius_all(12)
	style.content_margin_left = 10
	style.content_margin_right = 6
	style.content_margin_top = 2
	style.content_margin_bottom = 2
	panel.add_theme_stylebox_override("panel", style)

	var hb := HBoxContainer.new()
	panel.add_child(hb)

	var lbl := Label.new()
	lbl.text = key + ": "
	lbl.modulate = Color(0.7, 0.9, 1.0)
	lbl.add_theme_font_size_override("font_size", 12)
	hb.add_child(lbl)

	if typeof(value) == TYPE_BOOL:
		var btn := Button.new()
		btn.text = str(value).to_upper()
		btn.flat = true
		btn.add_theme_font_size_override("font_size", 12)
		btn.add_theme_color_override(
			"font_color",
			InspectorStyle.COLOR_SUCCESS if value else InspectorStyle.COLOR_DANGER
		)
		btn.pressed.connect(func() -> void:
			props[key] = !value
			on_modified.call()
			on_refresh.call()
		)
		hb.add_child(btn)
	else:
		var ed := LineEdit.new()
		ed.text = str(value)
		ed.flat = true
		ed.expand_to_text_length = true
		ed.custom_minimum_size.x = 30
		ed.add_theme_font_size_override("font_size", 12)
		ed.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
		ed.text_submitted.connect(func(t: String) -> void:
			# The type is read when the row is built, not when it is submitted:
			# `props[key]` may already have been replaced by a refresh, and a
			# numeric field must stay numeric.
			if typeof(value) == TYPE_FLOAT or typeof(value) == TYPE_INT:
				if t.is_valid_float():
					# An integer field keeps an integer, so a room's `level_min`
					# does not become `3.0` and fail the number gate.
					props[key] = int(float(t)) if typeof(value) == TYPE_INT else t.to_float()
			else:
				props[key] = t
			on_modified.call()
			on_refresh.call()
		)
		hb.add_child(ed)

	if allow_delete:
		var del := Button.new()
		del.text = "×"
		del.flat = true
		del.add_theme_font_size_override("font_size", 14)
		del.add_theme_color_override("font_color", Color(0.5, 0.5, 0.5))
		del.add_theme_color_override("font_hover_color", Color(1, 0.5, 0.5))
		del.pressed.connect(func() -> void:
			props.erase(key)
			on_modified.call()
			on_refresh.call()
		)
		hb.add_child(del)

	return panel


## Build the read-only note for one structured property.
##
## The value is shown, not hidden: an author editing the room needs to know the
## object is there and that this panel is not the place to change it. The text
## field itself is `editable = false` -- the editor's convention for a value that
## is displayed but not typed into -- so it cannot take focus and cannot be
## written back by accident.
static func build_nested_row(key: String, value: Variant, where: String) -> PanelContainer:
	var panel := PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.2, 0.2, 0.23)
	style.set_corner_radius_all(12)
	style.content_margin_left = 10
	style.content_margin_right = 6
	style.content_margin_top = 2
	style.content_margin_bottom = 2
	panel.add_theme_stylebox_override("panel", style)

	var hb := HBoxContainer.new()
	panel.add_child(hb)

	var lbl := Label.new()
	lbl.text = key + ": "
	lbl.modulate = Color(0.7, 0.9, 1.0)
	lbl.add_theme_font_size_override("font_size", 12)
	hb.add_child(lbl)

	var shown := LineEdit.new()
	shown.text = JSON.stringify(value)
	shown.editable = false
	shown.flat = true
	shown.custom_minimum_size.x = 30
	shown.tooltip_text = "Structured value (%s). Edited in %s, preserved here as-is." % [
		_describe(value), where,
	]
	shown.add_theme_font_size_override("font_size", 11)
	shown.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
	shown.modulate = InspectorStyle.COLOR_TEXT_DIM
	hb.add_child(shown)

	return panel


## A short word for what a structured value is, for the note beside it.
static func _describe(value: Variant) -> String:
	match typeof(value):
		TYPE_DICTIONARY:
			return "%d key%s" % [value.size(), "" if value.size() == 1 else "s"]
		TYPE_ARRAY:
			return "%d entr%s" % [value.size(), "y" if value.size() == 1 else "ies"]
		_:
			return "structured"


## Add every structured property of `properties` to `parent` as a read-only row,
## and say where each one can be edited instead.
##
## Returns how many were added, so a caller can decide whether the section is worth
## a heading at all.
static func add_nested_rows(
	parent: Control,
	properties: Dictionary,
	where: String,
	heading: String = "STRUCTURED (not editable here)"
) -> int:
	var keys := nested_keys(properties)
	if keys.is_empty():
		return 0

	parent.add_child(InspectorStyle.create_sub_header(heading))
	for key in keys:
		parent.add_child(build_nested_row(key, properties[key], where))
	return keys.size()
