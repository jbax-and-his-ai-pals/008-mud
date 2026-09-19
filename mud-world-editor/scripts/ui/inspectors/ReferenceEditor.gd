# scripts/ui/inspectors/ReferenceEditor.gd
#
# One editor for "what item does this content want?", used everywhere content
# wants one.
#
# An authored item reference is the same shape in four places now -- a recipe
# ingredient, a vendor's buy order, an item's own salvage output, a salvage rule
# -- and it always means the same three things:
#
#   {"item_id": "item_iron_ingot"}                      one exact template
#   {"item_family": "salvaged_part", "min_material_quality": 2}
#   {"capability": "crafting_material"}
#
# `item_id` wins when more than one is present, which is why this writes exactly
# one: two references on one entry is dead weight the engine silently ignores.
#
# The material-grade floor is only shown for the kinds the engine reads it on. A
# template reference is one exact thing, so a floor beside it would be a second,
# contradictory answer to the same question.

class_name ReferenceEditor
extends RefCounted

signal changed

# The three kinds, in the engine's resolution order (`engine/items/references.py`).
const KINDS := ["item_id", "item_family", "capability"]

# The kinds a material-grade floor means anything for.
const GRADE_FLOOR_KINDS := ["item_family", "capability"]

const PLACEHOLDERS := {
	"item_id": "item template id",
	"item_family": "item family from this set's contracts",
	"capability": "capability a family declares (e.g. crafting_material)",
}

var kind_picker: OptionButton
var reference_field: LineEdit
var grade_floor: SpinBox
var row: HBoxContainer

# What the row is currently writing, in a dictionary because the kind changes: a
# captured local would be a snapshot, and the reference field would keep writing
# the kind the row started with.
var _current := {"kind": "item_id"}


# Build the row inside `parent` and start editing `entry` in place.
# `suggestions_for` is called with a kind and returns the values that kind knows,
# so the picker offers the content set's own vocabulary rather than a fixed list.
func build(parent: Control, entry: Dictionary, suggestions_for: Callable) -> HBoxContainer:
	var initial: String = _kind_of(entry)
	_current["kind"] = initial

	row = HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)

	kind_picker = OptionButton.new()
	# Named so a test (and a future inspector) can find the reference kind
	# without guessing which OptionButton on the panel it is.
	kind_picker.name = "ReferenceKindPicker"
	for kind in KINDS:
		kind_picker.add_item(kind)
	kind_picker.selected = KINDS.find(initial)
	kind_picker.tooltip_text = "what this names"
	kind_picker.custom_minimum_size.x = 110
	InspectorStyle.apply_input_style(kind_picker)
	row.add_child(kind_picker)

	reference_field = LineEdit.new()
	reference_field.text = str(entry.get(initial, ""))
	reference_field.placeholder_text = str(PLACEHOLDERS.get(initial, ""))
	reference_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(reference_field)
	reference_field.text_changed.connect(
		func(text): _write(entry, str(_current["kind"]), str(text).strip_edges())
	)
	row.add_child(reference_field)
	InspectorStyle.add_suggestion_button(
		row, reference_field,
		func(): return suggestions_for.call(str(_current["kind"]))
	)

	grade_floor = SpinBox.new()
	grade_floor.min_value = 0; grade_floor.max_value = 99; grade_floor.step = 1
	grade_floor.value = int(entry.get("min_material_quality", 0))
	grade_floor.tooltip_text = "lowest material grade that counts (0 = any)"
	grade_floor.custom_minimum_size.x = 60
	grade_floor.editable = GRADE_FLOOR_KINDS.has(initial)
	InspectorStyle.apply_input_style(grade_floor)
	grade_floor.value_changed.connect(func(value):
		if int(value) <= 0: entry.erase("min_material_quality")
		else: entry["min_material_quality"] = int(value)
		changed.emit()
	)
	row.add_child(grade_floor)

	kind_picker.item_selected.connect(func(selected_index):
		var chosen: String = str(KINDS[selected_index])
		_current["kind"] = chosen
		var typed := reference_field.text.strip_edges()
		# A family and a template are different vocabularies, so a typed value
		# only carries across when the new kind actually knows it. Otherwise the
		# field empties rather than keeping a value that would save as an invalid
		# reference.
		var carried := typed if _is_known(suggestions_for, chosen, typed) else ""
		_write(entry, chosen, carried)
		reference_field.text = carried
		reference_field.placeholder_text = str(PLACEHOLDERS.get(chosen, ""))
		grade_floor.editable = GRADE_FLOOR_KINDS.has(chosen)
		# A floor on a template reference is a second answer to a question the
		# engine only asks once, so it goes away with the kind.
		if not grade_floor.editable:
			grade_floor.value = 0
			entry.erase("min_material_quality")
	)

	parent.add_child(row)
	return row


# Which of the three references this entry names. `item_id` is asked first
# because the engine resolves it first.
static func _kind_of(entry: Dictionary) -> String:
	for kind in KINDS:
		if str(entry.get(kind, "")).strip_edges() != "":
			return kind
	return "item_id"


# Write one reference and clear the other two. An entry naming two things is not
# an error the engine reports -- it resolves the first and ignores the rest -- so
# the editor keeps entries unambiguous instead.
func _write(entry: Dictionary, kind: String, value: String):
	for other in KINDS:
		if other != kind:
			entry.erase(other)
	if value == "": entry.erase(kind)
	else: entry[kind] = value
	changed.emit()


func _is_known(suggestions_for: Callable, kind: String, value: String) -> bool:
	if value == "":
		return false
	var known = suggestions_for.call(kind)
	return known is Array and known.has(value)
