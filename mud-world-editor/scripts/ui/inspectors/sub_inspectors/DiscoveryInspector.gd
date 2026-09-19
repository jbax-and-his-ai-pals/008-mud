# scripts/ui/inspectors/sub_inspectors/DiscoveryInspector.gd
#
# Discovery authoring: `discoveries.json` (`engine/core/discovery_manager.py`),
# the portable field-journal entries P4's advancement ledger pays XP for and
# titles/dialogue can gate on (`{"kind": "discovery", "discovery_id": ...}`).
#
# A discovery fires the first time the player picks up, gathers, or is given
# an item matching either trigger list; the engine requires at least one.

class_name DiscoveryInspector
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
	container.add_child(InspectorStyle.create_section_header("DISCOVERY: %s" % id.to_upper(), Color(0.55, 0.85, 0.75)))
	_build_identity()
	_build_item_triggers()
	_build_tag_triggers()
	_build_extras()


func _build_identity():
	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)

	vbox.add_child(InspectorStyle.lbl("Name (the field-journal entry):", InspectorStyle.COLOR_TEXT_DIM))
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


func _build_item_triggers():
	container.add_child(HSeparator.new())
	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.create_sub_header("Triggering items"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var add := Button.new(); add.text = "+ Item"
	InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var list: Array = _as_string_list(cur_data.get("item_ids", []))
		list.append("")
		cur_data["item_ids"] = list
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
	var items: Array = _as_string_list(cur_data.get("item_ids", []))
	if items.is_empty():
		items_box.add_child(InspectorStyle.lbl("None -- add an item, or trigger by tag below.", InspectorStyle.COLOR_TEXT_DIM))
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
			cur_data["item_ids"] = items
			database_modified.emit()
		)
		row.add_child(line)
		InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_item_ids())
		var remove := Button.new(); remove.text = "×"
		InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			items.remove_at(captured_index)
			if items.is_empty(): cur_data.erase("item_ids")
			else: cur_data["item_ids"] = items
			database_modified.emit()
			_refresh_items()
		)
		row.add_child(remove)
		items_box.add_child(row)


func _build_tag_triggers():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Triggering item tags"))
	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)
	vbox.add_child(InspectorStyle.lbl("Any item carrying one of these tags also fires this discovery (comma separated):", InspectorStyle.COLOR_TEXT_DIM))
	var tags_ed := LineEdit.new()
	tags_ed.text = ", ".join(_as_string_list(cur_data.get("item_tags", [])))
	tags_ed.placeholder_text = "field_material, gem"
	InspectorStyle.apply_input_style(tags_ed)
	tags_ed.text_changed.connect(func(text):
		var tags: Array = []
		for part in text.split(","):
			var trimmed: String = str(part).strip_edges()
			if trimmed != "": tags.append(trimmed)
		if tags.is_empty(): cur_data.erase("item_tags")
		else: cur_data["item_tags"] = tags
		database_modified.emit()
	)
	vbox.add_child(tags_ed)


func _build_extras():
	var known := ["name", "description", "item_ids", "item_tags"]
	var extras: Array = []
	for key in cur_data:
		if not known.has(str(key)): extras.append(key)
	extras.sort()
	if extras.is_empty(): return
	var note := Label.new()
	note.text = "Other discovery fields (kept as authored): %s" % ", ".join(extras)
	note.add_theme_font_size_override("font_size", 11)
	note.modulate = Color(0.7, 0.72, 0.6)
	container.add_child(note)


func _as_string_list(value) -> Array:
	if value is Array:
		var out: Array = []
		for entry in value: out.append(str(entry))
		return out
	return []
