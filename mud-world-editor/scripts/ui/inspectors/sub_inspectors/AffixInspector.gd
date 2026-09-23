# scripts/ui/inspectors/sub_inspectors/AffixInspector.gd
#
# Affix authoring: `items/affixes.json` (`engine/items/affix_data.py`).
#
# An affix is a name plus the item types it may sit on, a level floor, and what it
# does: `modifiers` change generated numbers, `equip_stats` add to the wearer's
# stats while worn, `value_mult` scales the price. The file has two libraries
# (`prefixes`, `suffixes`) and string keys beside them
# (`generated_effect_name_pattern`, `generated_description_suffix`) that the editor
# used to delete on save -- those are preserved by the manager, not shown here.
#
# Unknown keys inside an entry are preserved: the engine may read one this form
# does not know yet, and dropping it would be the same defect one level down.

class_name AffixInspector
extends RefCounted

signal database_modified

# `allowed_types` is compared with the generated item's engine class name, so
# these are the engine's classes (checked by schema_parity_smoke.gd) plus "All".
# A family such as Gem reports class Item and would match nothing.
const ITEM_CLASSES := ["All", "Weapon", "Armor", "Consumable", "Container", "Key", "Lockpick",
	"ResourceNode", "Interactive", "Item"]

var container: VBoxContainer
var cur_data: Dictionary
var database_mgr: DatabaseManager
var kind: String
var modifiers_box: VBoxContainer
var stats_box: VBoxContainer


func _init(c: VBoxContainer, db_mgr: DatabaseManager):
	container = c
	database_mgr = db_mgr


func build(id: String, data: Dictionary, affix_kind: String = "prefix"):
	cur_data = data
	kind = affix_kind
	var label := "PREFIX" if kind == "prefix" else "SUFFIX"
	container.add_child(InspectorStyle.create_section_header("%s: %s" % [label, id.to_upper()], Color(0.9, 0.75, 0.55)))
	_build_identity(id)
	_build_effects()
	_build_extras()


func _build_identity(id: String):
	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)

	vbox.add_child(InspectorStyle.lbl("Affix text (its id, and what a player reads):", InspectorStyle.COLOR_TEXT_DIM))
	var name_row := HBoxContainer.new()
	var name_ed := LineEdit.new()
	name_ed.text = id
	name_ed.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(name_ed)
	name_ed.tooltip_text = "Renaming an affix changes the key the generator matches on. Leave it unless you mean to."
	name_row.add_child(name_ed)
	var rename := Button.new()
	rename.text = "Rename"
	rename.pressed.connect(func():
		var wanted := name_ed.text.strip_edges()
		if wanted == "" or wanted == id: return
		if database_mgr.has_entry("affix_" + kind, wanted):
			name_ed.text = id
			return
		if database_mgr.rename_entry("affix_" + kind, id, wanted):
			id = wanted
			database_modified.emit()
	)
	name_row.add_child(rename)
	vbox.add_child(name_row)

	vbox.add_child(InspectorStyle.lbl("May appear on (comma-separated item types):", InspectorStyle.COLOR_TEXT_DIM))
	var types := LineEdit.new()
	var declared = cur_data.get("allowed_types", [])
	types.text = ", ".join(declared) if declared is Array else ""
	types.placeholder_text = ", ".join(ITEM_CLASSES)
	InspectorStyle.apply_input_style(types)
	types.text_changed.connect(func(text):
		var out: Array = []
		for part in text.split(",", false):
			var item_type: String = str(part).strip_edges()
			if item_type != "" and not out.has(item_type): out.append(item_type)
		cur_data["allowed_types"] = out
		database_modified.emit()
	)
	vbox.add_child(types)

	_number(vbox, "Minimum item level", "level_min", true)
	_number(vbox, "Value multiplier", "value_mult", false)


func _build_effects():
	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)
	vbox.add_child(InspectorStyle.create_section_header("WHAT IT DOES", InspectorStyle.COLOR_ACCENT))
	vbox.add_child(InspectorStyle.lbl("Modifiers change the generated item's damage, defense, durability or weight (prefixes only). Worn stats add to the wearer while the item is equipped.", InspectorStyle.COLOR_TEXT_DIM))
	modifiers_box = VBoxContainer.new()
	vbox.add_child(modifiers_box)
	stats_box = VBoxContainer.new()
	vbox.add_child(stats_box)
	_rebuild_map(modifiers_box, "modifiers", "+ Modifier", "stat")
	_rebuild_map(stats_box, "equip_stats", "+ Worn stat", "stat")


## A stat → number map, rendered as rows. Both of this file's effect shapes are
## that, so they share one builder rather than two nearly identical ones.
func _rebuild_map(box: VBoxContainer, key: String, add_label: String, placeholder: String):
	for child in box.get_children():
		box.remove_child(child)
		child.queue_free()
	var declared = cur_data.get(key, {})
	if not (declared is Dictionary):
		declared = {}
		cur_data[key] = declared
	var rows := VBoxContainer.new()
	box.add_child(rows)
	for stat in (declared as Dictionary).keys():
		_add_row(rows, key, str(stat), placeholder)
	var add := Button.new()
	add.text = add_label
	InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS)
	add.pressed.connect(func():
		if not (cur_data.get(key) is Dictionary): cur_data[key] = {}
		cur_data[key][""] = 0
		database_modified.emit()
		_rebuild_map(box, key, add_label, placeholder)
	)
	box.add_child(add)


func _add_row(rows: VBoxContainer, key: String, stat: String, placeholder: String):
	var row := HBoxContainer.new()
	var name_ed := LineEdit.new()
	name_ed.text = stat
	name_ed.placeholder_text = placeholder
	name_ed.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(name_ed)
	name_ed.text_submitted.connect(func(text):
		var wanted: String = str(text).strip_edges()
		var table: Dictionary = cur_data.get(key, {})
		if wanted == "" or wanted == stat or table.has(wanted):
			name_ed.text = stat
			return
		var value = table.get(stat, 0)
		var rebuilt := {}
		for existing in table:
			if str(existing) == stat: rebuilt[wanted] = value
			else: rebuilt[existing] = table[existing]
		table.clear(); table.merge(rebuilt)
		stat = wanted
		database_modified.emit()
	)
	row.add_child(name_ed)
	var value := SpinBox.new()
	value.min_value = -999
	value.max_value = 999
	value.step = 1
	value.value = float(cur_data.get(key, {}).get(stat, 0))
	InspectorStyle.apply_input_style(value)
	value.value_changed.connect(func(number):
		if cur_data.get(key) is Dictionary: cur_data[key][stat] = int(number)
		database_modified.emit()
	)
	row.add_child(value)
	var remove := Button.new()
	remove.text = "×"
	remove.pressed.connect(func():
		if cur_data.get(key) is Dictionary: cur_data[key].erase(stat)
		database_modified.emit()
		_rebuild_map(rows.get_parent(), key, "Add", placeholder)
	)
	row.add_child(remove)
	rows.add_child(row)


func _number(parent: VBoxContainer, label: String, key: String, whole: bool):
	var row := VBoxContainer.new()
	row.add_child(InspectorStyle.lbl(label + ":", InspectorStyle.COLOR_TEXT_DIM))
	if whole:
		var spin := SpinBox.new()
		spin.min_value = 0
		spin.max_value = 999
		spin.step = 1
		spin.value = float(cur_data.get(key, 0))
		InspectorStyle.apply_input_style(spin)
		spin.value_changed.connect(func(value): cur_data[key] = int(value); database_modified.emit())
		row.add_child(spin)
	else:
		var field := LineEdit.new()
		field.text = str(cur_data.get(key, 1.0))
		InspectorStyle.apply_input_style(field)
		field.text_changed.connect(func(text):
			if text.is_valid_float():
				cur_data[key] = float(text)
				field.set_meta("input_error", "")
				database_modified.emit()
			else:
				field.set_meta("input_error", "%s must be a number." % label)
		)
		row.add_child(field)
	parent.add_child(row)


func _build_extras():
	var known := ["_filename", "allowed_types", "level_min", "value_mult", "modifiers", "equip_stats"]
	var extras: Array = []
	for key in cur_data:
		if not known.has(key): extras.append(str(key))
	if extras.is_empty(): return
	var note := InspectorStyle.lbl("Other fields (kept as authored): %s" % ", ".join(extras), InspectorStyle.COLOR_TEXT_DIM)
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	container.add_child(note)
