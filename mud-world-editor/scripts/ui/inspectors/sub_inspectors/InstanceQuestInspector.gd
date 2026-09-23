# scripts/ui/inspectors/sub_inspectors/InstanceQuestInspector.gd
#
# One template from `quests/instances.json`, the input to
# `QuestGenerator.generate_instance_quest`: which creatures fill a generated
# house, who asks for help, where its entrance may appear, and the house's
# shape. Validated by `content_set.py::_validate_instance_quests`.
#
# The stage-based QuestInspector does not fit these: the generator builds the
# quest's single stage itself, and opening an instance template there wrote an
# empty `stages` list into it.

class_name InstanceQuestInspector
extends RefCounted

signal database_modified

var container: VBoxContainer
var database_mgr: DatabaseManager
var cur_id := ""
var cur_data: Dictionary
# Sub-objects created for display are attached only once something is written
# into them, so opening a template without `rewards` does not add `{}`.
var _detached: Dictionary = {}


func _init(c: VBoxContainer, db_mgr: DatabaseManager):
	container = c
	database_mgr = db_mgr


func build(id: String, data: Dictionary):
	cur_id = id
	cur_data = data
	container.add_child(InspectorStyle.create_section_header("INSTANCE QUEST: %s" % id.to_upper(), Color(0.85, 0.6, 0.35)))
	_build_identity()
	_build_objective()
	_build_entry_regions()
	_build_layout()
	_build_rewards()


func _build_identity():
	var hint := InspectorStyle.lbl("The board title and description come from the ruleset's Quest Generation > Instance quests patterns; these two are notes for authors.", InspectorStyle.COLOR_TEXT_DIM)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; container.add_child(hint)
	_text_field(container, "Title", cur_data, "title")
	_text_field(container, "Description", cur_data, "description")
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 8); container.add_child(row)
	row.add_child(InspectorStyle.lbl("Minimum player level", InspectorStyle.COLOR_TEXT_DIM))
	_int_spin(row, cur_data, "level", 1, 100, 1)
	var giver_row := HBoxContainer.new(); container.add_child(giver_row)
	giver_row.add_child(InspectorStyle.lbl("Giver (spawned beside the player)", InspectorStyle.COLOR_TEXT_DIM))
	_npc_picker(giver_row, cur_data, "giver_npc_template_id", "No giver")


func _build_objective():
	container.add_child(InspectorStyle.create_sub_header("Clear the house"))
	var objective := _section("objective")
	var type_note := "Objective: clear_region" if objective.get("type") == "clear_region" else "Objective type '%s' is never completed by the quest tracker; only clear_region is." % str(objective.get("type", ""))
	container.add_child(InspectorStyle.lbl(type_note, InspectorStyle.COLOR_TEXT_DIM if objective.get("type") == "clear_region" else DialogStyle.COLOR_DANGER))
	var rows := _list(container, "Possible target creatures (one is chosen, scaled to the player's level)", "+ Creature")
	var refresh := func(): _refresh_id_list(rows, objective, "possible_target_template_ids", _npc_ids(), "Choose creature")
	(rows.get_meta("add_button") as Button).pressed.connect(func():
		var ids: Array = objective.get("possible_target_template_ids", []) if objective.get("possible_target_template_ids") is Array else []
		ids.append(""); objective["possible_target_template_ids"] = ids; refresh.call(); _modified())
	refresh.call()
	var completion_row := HBoxContainer.new(); container.add_child(completion_row)
	completion_row.add_child(InspectorStyle.lbl("Waiting outside when cleared", InspectorStyle.COLOR_TEXT_DIM))
	_npc_picker(completion_row, objective, "completion_npc_template_id", "Nobody")


func _build_entry_regions():
	container.add_child(InspectorStyle.create_sub_header("Entrance"))
	var hint := InspectorStyle.lbl("The entrance appears in a random outdoor room of one of these regions. With none, the start region is used.", InspectorStyle.COLOR_TEXT_DIM)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; container.add_child(hint)
	var rows := _list(container, "Entry regions", "+ Region")
	var refresh := func(): _refresh_id_list(rows, cur_data, "possible_entry_regions", _region_ids(), "Choose region")
	(rows.get_meta("add_button") as Button).pressed.connect(func():
		var ids: Array = cur_data.get("possible_entry_regions", []) if cur_data.get("possible_entry_regions") is Array else []
		ids.append(""); cur_data["possible_entry_regions"] = ids; refresh.call(); _modified())
	refresh.call()


func _build_layout():
	container.add_child(InspectorStyle.create_sub_header("Generated house"))
	var layout := _section("layout_generation_config")
	_text_field(container, "Region name", layout, "region_name")
	_text_field(container, "Region description", layout, "region_description")
	var rooms := HBoxContainer.new(); rooms.add_theme_constant_override("separation", 8); container.add_child(rooms)
	rooms.add_child(InspectorStyle.lbl("Rooms from", InspectorStyle.COLOR_TEXT_DIM)); _int_spin(rooms, layout, "min_rooms", 1, 50, 3)
	rooms.add_child(InspectorStyle.lbl("to", InspectorStyle.COLOR_TEXT_DIM)); _int_spin(rooms, layout, "max_rooms", 1, 50, 7)
	var names_row := VBoxContainer.new(); container.add_child(names_row)
	names_row.add_child(InspectorStyle.lbl("Room names (comma-separated; one is picked per room)", InspectorStyle.COLOR_TEXT_DIM))
	var names := LineEdit.new(); names.name = "RoomNames"; InspectorStyle.apply_input_style(names)
	names.text = ", ".join(layout.get("possible_room_names", [])) if layout.get("possible_room_names") is Array else ""
	names.text_changed.connect(func(text):
		var values: Array = []
		for value in text.split(","):
			if value.strip_edges() != "": values.append(value.strip_edges())
		if values.is_empty(): layout.erase("possible_room_names")
		else: layout["possible_room_names"] = values
		_modified())
	names_row.add_child(names)
	var count := HBoxContainer.new(); count.add_theme_constant_override("separation", 8); container.add_child(count)
	count.add_child(InspectorStyle.lbl("Creatures from", InspectorStyle.COLOR_TEXT_DIM))
	var pair: Array = layout.get("target_count", []) if layout.get("target_count") is Array and layout.get("target_count").size() == 2 else [2, 4]
	var low := _bare_spin(count, float(pair[0]), 1, 50); low.name = "TargetMin"
	count.add_child(InspectorStyle.lbl("to", InspectorStyle.COLOR_TEXT_DIM))
	var high := _bare_spin(count, float(pair[1]), 1, 50); high.name = "TargetMax"
	var write_count := func(_value): layout["target_count"] = [int(low.value), int(high.value)]; _modified()
	low.value_changed.connect(write_count); high.value_changed.connect(write_count)


func _build_rewards():
	container.add_child(InspectorStyle.create_sub_header("Rewards"))
	var rewards := _section("rewards")
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 8); container.add_child(row)
	row.add_child(InspectorStyle.lbl("XP", InspectorStyle.COLOR_TEXT_DIM)); _int_spin(row, rewards, "xp", 0, 1000000, 0)
	row.add_child(InspectorStyle.lbl("Gold", InspectorStyle.COLOR_TEXT_DIM)); _int_spin(row, rewards, "gold", 0, 1000000, 0)


# --- helpers ----------------------------------------------------------------

func _text_field(parent: Control, label: String, target: Dictionary, key: String) -> LineEdit:
	var row := VBoxContainer.new(); parent.add_child(row)
	row.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var field := LineEdit.new(); field.name = key.to_pascal_case(); field.text = str(target.get(key, "")); InspectorStyle.apply_input_style(field)
	field.text_changed.connect(func(text):
		if text.strip_edges() == "": target.erase(key)
		else: target[key] = text
		_modified())
	row.add_child(field)
	return field


## The value is set before the signal is connected: SpinBox emits
## value_changed on a programmatic set, and opening must not write.
func _int_spin(parent: Control, target: Dictionary, key: String, low: int, high: int, fallback: int) -> SpinBox:
	var spin := _bare_spin(parent, float(target.get(key, fallback)), low, high)
	spin.name = key.to_pascal_case()
	spin.value_changed.connect(func(value): target[key] = int(value); _modified())
	return spin


func _bare_spin(parent: Control, value: float, low: int, high: int) -> SpinBox:
	var spin := SpinBox.new(); spin.min_value = low; spin.max_value = high; spin.step = 1; spin.value = value
	spin.custom_minimum_size.x = 80; InspectorStyle.apply_input_style(spin); parent.add_child(spin)
	return spin


func _npc_picker(parent: Control, target: Dictionary, key: String, empty_label: String) -> OptionButton:
	var picker := OptionButton.new(); picker.name = key.to_pascal_case(); picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	QuestGenerationSection._fill_picker(picker, _npc_ids(), _npc_labels(), str(target.get(key, "")), empty_label)
	InspectorStyle.apply_button_style(picker)
	picker.item_selected.connect(func(index):
		var value := str(picker.get_item_metadata(index))
		if value == "": target.erase(key)
		else: target[key] = value
		_modified())
	parent.add_child(picker)
	return picker


func _list(parent: Control, label: String, button_text: String) -> VBoxContainer:
	var header := HBoxContainer.new(); parent.add_child(header)
	header.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = button_text; InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS); header.add_child(add)
	var rows := VBoxContainer.new(); rows.add_theme_constant_override("separation", 4); rows.set_meta("add_button", add); parent.add_child(rows)
	return rows


## Rebuilds one id-list's rows from `target[key]`; removing the last entry
## removes the key, so an emptied list does not reach the file as `[]`.
func _refresh_id_list(rows: VBoxContainer, target: Dictionary, key: String, ids: Array, empty_label: String):
	for child in rows.get_children(): rows.remove_child(child); child.queue_free()
	var values: Array = target.get(key, []) if target.get(key) is Array else []
	for index in range(values.size()):
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6); rows.add_child(row)
		var picker := OptionButton.new(); picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		QuestGenerationSection._fill_picker(picker, ids, _npc_labels() if key == "possible_target_template_ids" else {}, str(values[index]), empty_label)
		InspectorStyle.apply_button_style(picker)
		var slot := index
		picker.item_selected.connect(func(picked):
			values[slot] = str(picker.get_item_metadata(picked)); _modified())
		row.add_child(picker)
		var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
		remove.pressed.connect(func():
			values.remove_at(slot)
			if values.is_empty(): target.erase(key)
			_refresh_id_list(rows, target, key, ids, empty_label); _modified())
		row.add_child(remove)


func _npc_ids() -> Array: return database_mgr.get_npc_ids() if database_mgr != null else []


func _npc_labels() -> Dictionary:
	var labels := {}
	for npc_id in _npc_ids():
		if database_mgr.npcs.get(npc_id) is Dictionary: labels[npc_id] = "%s — %s" % [str(database_mgr.npcs[npc_id].get("name", npc_id)), npc_id]
	return labels


func _region_ids() -> Array:
	var ids: Array = []
	var dir_path := DataRoot.content_dir("regions")
	for file_name in DirAccess.get_files_at(dir_path):
		if not file_name.ends_with(".json"): continue
		var region = JSON.parse_string(FileAccess.get_file_as_string(dir_path.path_join(file_name)))
		if region is Dictionary and not (region.get("themes") is Dictionary):
			ids.append(str(region.get("region_id", file_name.get_basename())))
	ids.sort()
	return ids


func _section(key: String) -> Dictionary:
	if cur_data.get(key) is Dictionary: return cur_data[key]
	var detached := {}
	_detached[key] = detached
	return detached


func _modified():
	for key in _detached:
		if not _detached[key].is_empty(): cur_data[key] = _detached[key]
	if cur_data.get("objective") is Dictionary and not cur_data["objective"].has("type"):
		cur_data["objective"]["type"] = "clear_region"
	database_modified.emit()
