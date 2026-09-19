# scripts/ui/inspectors/sub_inspectors/CollectionInspector.gd
#
# Collection authoring: `collections.json` (`engine/core/collection_manager.py`),
# a generic "gather one of everything on this list" reward contract -- a
# named set of items plus an XP/gold reward for completing it.

class_name CollectionInspector
extends RefCounted

signal database_modified

var container: VBoxContainer
var cur_data: Dictionary
var database_mgr: DatabaseManager
var items_box: VBoxContainer


func _init(c: VBoxContainer, db_mgr: DatabaseManager):
	container = c
	database_mgr = db_mgr


func build(id: String, data: Dictionary):
	cur_data = data
	container.add_child(InspectorStyle.create_section_header("COLLECTION: %s" % id.to_upper(), Color(0.6, 0.75, 0.95)))
	_build_identity()
	_build_items()
	_build_rewards()
	_build_extras()


func _build_identity():
	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)

	vbox.add_child(InspectorStyle.lbl("Name:", InspectorStyle.COLOR_TEXT_DIM))
	var name_ed := LineEdit.new(); name_ed.text = str(cur_data.get("name", ""))
	InspectorStyle.apply_input_style(name_ed)
	name_ed.text_changed.connect(func(text): cur_data["name"] = text; database_modified.emit())
	vbox.add_child(name_ed)

	vbox.add_child(InspectorStyle.lbl("Description:", InspectorStyle.COLOR_TEXT_DIM))
	var desc_ed := TextEdit.new(); desc_ed.custom_minimum_size.y = 54
	desc_ed.text = str(cur_data.get("description", ""))
	InspectorStyle.apply_input_style(desc_ed)
	desc_ed.text_changed.connect(func(): cur_data["description"] = desc_ed.text; database_modified.emit())
	vbox.add_child(desc_ed)


func _build_items():
	container.add_child(HSeparator.new())
	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.create_sub_header("Items (one of each required)"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var add := Button.new(); add.text = "+ Item"
	InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var list: Array = _as_string_list(cur_data.get("items", []))
		list.append("")
		cur_data["items"] = list
		database_modified.emit()
		_refresh_items()
	)
	header.add_child(add)
	container.add_child(header)

	items_box = VBoxContainer.new()
	items_box.add_theme_constant_override("separation", 4)
	container.add_child(items_box)
	_refresh_items()


func _refresh_items():
	for child in items_box.get_children(): child.queue_free()
	var items: Array = _as_string_list(cur_data.get("items", []))
	if items.is_empty():
		items_box.add_child(InspectorStyle.lbl("Nothing yet -- a collection with no items cannot be completed.", InspectorStyle.COLOR_TEXT_DIM))
		return
	for index in range(items.size()):
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
		var line := LineEdit.new(); line.text = str(items[index])
		line.placeholder_text = "item template id"
		line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_input_style(line)
		var captured_index := index
		line.text_changed.connect(func(text):
			items[captured_index] = str(text).strip_edges()
			cur_data["items"] = items
			database_modified.emit()
		)
		row.add_child(line)
		InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_item_ids())
		var remove := Button.new(); remove.text = "×"
		InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			items.remove_at(captured_index)
			cur_data["items"] = items
			database_modified.emit()
			_refresh_items()
		)
		row.add_child(remove)
		items_box.add_child(row)


func _build_rewards():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Reward"))
	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)

	var rewards = cur_data.get("rewards")
	if not (rewards is Dictionary):
		rewards = {}
		cur_data["rewards"] = rewards

	var xp_row := HBoxContainer.new(); xp_row.add_theme_constant_override("separation", 6)
	xp_row.add_child(InspectorStyle.lbl("XP", InspectorStyle.COLOR_TEXT_DIM))
	var xp := SpinBox.new(); xp.min_value = 0; xp.max_value = 100000; xp.step = 1
	xp.value = int(rewards.get("xp", 0))
	InspectorStyle.apply_input_style(xp)
	xp.value_changed.connect(func(value): rewards["xp"] = int(value); database_modified.emit())
	xp_row.add_child(xp)
	vbox.add_child(xp_row)

	var gold_row := HBoxContainer.new(); gold_row.add_theme_constant_override("separation", 6)
	gold_row.add_child(InspectorStyle.lbl("Gold", InspectorStyle.COLOR_TEXT_DIM))
	var gold := SpinBox.new(); gold.min_value = 0; gold.max_value = 100000; gold.step = 1
	gold.value = int(rewards.get("gold", 0))
	InspectorStyle.apply_input_style(gold)
	gold.value_changed.connect(func(value): rewards["gold"] = int(value); database_modified.emit())
	gold_row.add_child(gold)
	vbox.add_child(gold_row)


func _build_extras():
	var known := ["name", "description", "items", "rewards"]
	var extras: Array = []
	for key in cur_data:
		if not known.has(str(key)): extras.append(key)
	extras.sort()
	if extras.is_empty(): return
	var note := Label.new()
	note.text = "Other collection fields (kept as authored): %s" % ", ".join(extras)
	note.add_theme_font_size_override("font_size", 11)
	note.modulate = Color(0.7, 0.72, 0.6)
	container.add_child(note)


func _as_string_list(value) -> Array:
	if value is Array:
		var out: Array = []
		for entry in value: out.append(str(entry))
		return out
	return []
