# scripts/ui/inspectors/sub_inspectors/ItemSetInspector.gd
#
# Item-set authoring: `items/sets.json` (`engine/items/set_manager.py`).
#
# A set is a name, the items that belong to it, and bonuses that unlock at a count
# of worn pieces: `{"2": {"type": "stat_mod", "modifiers": {"strength": 5}}}`. The
# bonus tables in the shipped set are the reason this exists -- two of its members
# were renamed away and nothing could put them back, because the file had no
# surface at all.
#
# The count keys are strings because the engine reads them that way, and the form
# keeps them strings: `{"2": ...}` is what `set_manager` indexes.

class_name ItemSetInspector
extends RefCounted

signal database_modified

var container: VBoxContainer
var cur_data: Dictionary
var database_mgr: DatabaseManager
var items_box: VBoxContainer
var bonuses_box: VBoxContainer


func _init(c: VBoxContainer, db_mgr: DatabaseManager):
	container = c
	database_mgr = db_mgr


func build(id: String, data: Dictionary):
	cur_data = data
	container.add_child(InspectorStyle.create_section_header("ITEM SET: %s" % id.to_upper(), Color(0.85, 0.72, 0.35)))
	_build_identity(id)
	_build_members()
	_build_bonuses()
	_build_extras()


func _build_identity(id: String):
	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)
	vbox.add_child(InspectorStyle.lbl("Set id: %s (the key items and bonuses are written against)" % id, InspectorStyle.COLOR_TEXT_DIM))
	vbox.add_child(InspectorStyle.lbl("Name (what a player sees):", InspectorStyle.COLOR_TEXT_DIM))
	var name_ed := LineEdit.new()
	name_ed.text = str(cur_data.get("name", ""))
	InspectorStyle.apply_input_style(name_ed)
	name_ed.text_changed.connect(func(text): cur_data["name"] = text; database_modified.emit())
	vbox.add_child(name_ed)


func _build_members():
	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)
	vbox.add_child(InspectorStyle.create_section_header("MEMBERS", InspectorStyle.COLOR_ACCENT))
	vbox.add_child(InspectorStyle.lbl("Item template ids. A member that does not exist is a set piece nobody can ever wear -- the reference gate reports it.", InspectorStyle.COLOR_TEXT_DIM))
	items_box = VBoxContainer.new()
	vbox.add_child(items_box)
	_rebuild_items()


func _rebuild_items():
	for child in items_box.get_children():
		items_box.remove_child(child)
		child.queue_free()
	if not (cur_data.get("items") is Array): cur_data["items"] = []
	var rows := VBoxContainer.new()
	items_box.add_child(rows)
	var index := 0
	for item_id in (cur_data["items"] as Array):
		_add_item_row(rows, index, str(item_id))
		index += 1
	var add := Button.new()
	add.text = "+ Member"
	InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS)
	add.pressed.connect(func():
		cur_data["items"].append("")
		database_modified.emit()
		_rebuild_items()
	)
	items_box.add_child(add)


func _add_item_row(rows: VBoxContainer, index: int, item_id: String):
	var row := HBoxContainer.new()
	var field := LineEdit.new()
	field.text = item_id
	field.placeholder_text = "item_..."
	field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(field)
	field.text_submitted.connect(func(text):
		if index < cur_data["items"].size():
			cur_data["items"][index] = text.strip_edges()
			database_modified.emit()
	)
	row.add_child(field)
	var known := database_mgr.has_entry("item", item_id) if item_id != "" else false
	var marker := InspectorStyle.lbl("✓" if known else ("?" if item_id != "" else ""), InspectorStyle.COLOR_SUCCESS if known else InspectorStyle.COLOR_TEXT_DIM)
	marker.tooltip_text = "This content set has that item." if known else "No item with that id in this content set."
	row.add_child(marker)
	var remove := Button.new()
	remove.text = "×"
	remove.pressed.connect(func():
		if index < cur_data["items"].size():
			cur_data["items"].remove_at(index)
			database_modified.emit()
			_rebuild_items()
	)
	row.add_child(remove)
	rows.add_child(row)


func _build_bonuses():
	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)
	vbox.add_child(InspectorStyle.create_section_header("BONUSES", InspectorStyle.COLOR_ACCENT))
	vbox.add_child(InspectorStyle.lbl("One row per number of worn pieces. The count is the key the engine reads, so it stays a string.", InspectorStyle.COLOR_TEXT_DIM))
	bonuses_box = VBoxContainer.new()
	vbox.add_child(bonuses_box)
	_rebuild_bonuses()


func _rebuild_bonuses():
	for child in bonuses_box.get_children():
		bonuses_box.remove_child(child)
		child.queue_free()
	if not (cur_data.get("bonuses") is Dictionary): cur_data["bonuses"] = {}
	var rows := VBoxContainer.new()
	bonuses_box.add_child(rows)
	for count in (cur_data["bonuses"] as Dictionary).keys():
		_add_bonus_row(rows, str(count))
	var add := Button.new()
	add.text = "+ Bonus tier"
	InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS)
	add.pressed.connect(func():
		var next := str((cur_data["bonuses"] as Dictionary).size() + 2)
		while cur_data["bonuses"].has(next):
			next = str(int(next) + 1)
		cur_data["bonuses"][next] = {"type": "stat_mod", "modifiers": {}}
		database_modified.emit()
		_rebuild_bonuses()
	)
	bonuses_box.add_child(add)


func _add_bonus_row(rows: VBoxContainer, count: String):
	var bonus = cur_data["bonuses"].get(count, {})
	if not (bonus is Dictionary):
		bonus = {}
		cur_data["bonuses"][count] = bonus
	var card := InspectorStyle.create_card()
	var box: VBoxContainer = card.get_child(0).get_child(0)
	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.lbl("At", InspectorStyle.COLOR_TEXT_DIM))
	var pieces := SpinBox.new()
	pieces.min_value = 1
	pieces.max_value = 99
	pieces.value = float(int(count)) if count.is_valid_int() else 2
	InspectorStyle.apply_input_style(pieces)
	header.add_child(pieces)
	header.add_child(InspectorStyle.lbl("worn pieces:", InspectorStyle.COLOR_TEXT_DIM))
	var effect := LineEdit.new()
	effect.text = str(bonus.get("type", "stat_mod"))
	effect.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(effect)
	effect.tooltip_text = "The engine's effect kind for this tier (the shipped set uses stat_mod)."
	effect.text_changed.connect(func(text): bonus["type"] = text.strip_edges(); database_modified.emit())
	header.add_child(effect)
	var remove := Button.new()
	remove.text = "×"
	remove.pressed.connect(func():
		cur_data["bonuses"].erase(count)
		database_modified.emit()
		_rebuild_bonuses()
	)
	header.add_child(remove)
	box.add_child(header)

	var modifiers: Dictionary = bonus.get("modifiers", {}) if bonus.get("modifiers") is Dictionary else {}
	bonus["modifiers"] = modifiers
	var grid := GridContainer.new()
	grid.columns = 3
	box.add_child(grid)
	for stat in modifiers.keys():
		_add_modifier_row(grid, modifiers, str(stat))
	var add := Button.new()
	add.text = "+ Stat"
	add.pressed.connect(func():
		modifiers[""] = 0
		database_modified.emit()
		_rebuild_bonuses()
	)
	box.add_child(add)

	# The count is the key: changing it renames the entry, keeping its position.
	pieces.value_changed.connect(func(value):
		var wanted := str(int(value))
		if wanted == count or cur_data["bonuses"].has(wanted):
			return
		var rebuilt := {}
		for existing in cur_data["bonuses"]:
			if str(existing) == count: rebuilt[wanted] = cur_data["bonuses"][existing]
			else: rebuilt[existing] = cur_data["bonuses"][existing]
		cur_data["bonuses"].clear(); cur_data["bonuses"].merge(rebuilt)
		count = wanted
		database_modified.emit()
	)


func _add_modifier_row(grid: GridContainer, modifiers: Dictionary, stat: String):
	var name_ed := LineEdit.new()
	name_ed.text = stat
	name_ed.placeholder_text = "stat"
	InspectorStyle.apply_input_style(name_ed)
	name_ed.text_submitted.connect(func(text):
		var wanted: String = str(text).strip_edges()
		if wanted == "" or wanted == stat or modifiers.has(wanted):
			name_ed.text = stat
			return
		var value = modifiers.get(stat, 0)
		var rebuilt := {}
		for existing in modifiers:
			if str(existing) == stat: rebuilt[wanted] = value
			else: rebuilt[existing] = modifiers[existing]
		modifiers.clear(); modifiers.merge(rebuilt)
		database_modified.emit()
	)
	grid.add_child(name_ed)
	var value := SpinBox.new()
	value.min_value = -999
	value.max_value = 999
	value.value = float(modifiers.get(stat, 0))
	InspectorStyle.apply_input_style(value)
	value.value_changed.connect(func(number): modifiers[stat] = int(number); database_modified.emit())
	grid.add_child(value)
	var remove := Button.new()
	remove.text = "×"
	remove.pressed.connect(func(): modifiers.erase(stat); database_modified.emit(); _rebuild_bonuses())
	grid.add_child(remove)


func _build_extras():
	var known := ["_filename", "name", "items", "bonuses"]
	var extras: Array = []
	for key in cur_data:
		if not known.has(key): extras.append(str(key))
	if extras.is_empty(): return
	var note := InspectorStyle.lbl("Other fields (kept as authored): %s" % ", ".join(extras), InspectorStyle.COLOR_TEXT_DIM)
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	container.add_child(note)
