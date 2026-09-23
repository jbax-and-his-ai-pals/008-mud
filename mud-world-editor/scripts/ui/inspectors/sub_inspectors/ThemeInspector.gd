# scripts/ui/inspectors/sub_inspectors/ThemeInspector.gd
#
# One region-generation theme from `regions/dynamic_themes.json`
# (`world/region_generator.py`): what a generated region is called, what its
# rooms are called and look like, and what spawns there. Validated by
# `content_set.py::_validate_dynamic_themes`. Region names and room
# descriptions may use `{Word}`/`{word}` for any shared word list below; room
# names and the description are shown as written. A list emptied here is
# removed rather than written as `[]`, because an empty list stops the region
# being generated. The word lists are shared by every theme.

class_name ThemeInspector
extends RefCounted

signal database_modified

const LISTS := [
	["name_templates", "Region names (one per line; word lists allowed)"],
	["room_names", "Room names (one per line; shown as written)"],
	["room_descriptions", "Room descriptions (one per line; word lists allowed)"],
]

var container: VBoxContainer
var database_mgr: DatabaseManager
var cur_id := ""
var cur_data: Dictionary
var monster_rows: VBoxContainer
var word_rows: VBoxContainer


func _init(c: VBoxContainer, db_mgr: DatabaseManager):
	container = c
	database_mgr = db_mgr


func build(id: String, data: Dictionary):
	cur_id = id
	cur_data = data
	container.add_child(InspectorStyle.create_section_header("REGION THEME: %s" % id.to_upper(), Color(0.45, 0.7, 0.45)))
	var hint := InspectorStyle.lbl("Used when a quest generates a region with this theme (a quest's procedural_regions, or the ruleset's default procedural theme).", InspectorStyle.COLOR_TEXT_DIM)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; container.add_child(hint)
	var desc_row := VBoxContainer.new(); container.add_child(desc_row)
	desc_row.add_child(InspectorStyle.lbl("Region description (shown as written)", InspectorStyle.COLOR_TEXT_DIM))
	var description := LineEdit.new(); description.name = "Description"; description.text = str(cur_data.get("description", ""))
	InspectorStyle.apply_input_style(description)
	description.text_changed.connect(func(text):
		if text.strip_edges() == "": cur_data.erase("description")
		else: cur_data["description"] = text
		database_modified.emit())
	desc_row.add_child(description)
	for spec in LISTS: _list_editor(spec[0], spec[1])
	_build_spawner()
	_build_word_lists()


func _list_editor(key: String, label: String) -> void:
	container.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var edit := TextEdit.new(); edit.name = key.to_pascal_case(); edit.custom_minimum_size.y = 90
	edit.text = "\n".join(cur_data.get(key, [])) if cur_data.get(key) is Array else ""
	InspectorStyle.apply_input_style(edit)
	edit.text_changed.connect(func():
		var values: Array = []
		for line in edit.text.split("\n"):
			if line.strip_edges() != "": values.append(line.strip_edges())
		if values.is_empty(): cur_data.erase(key)
		else: cur_data[key] = values
		database_modified.emit())
	container.add_child(edit)


func _build_spawner() -> void:
	container.add_child(InspectorStyle.create_sub_header("Spawns"))
	var header := HBoxContainer.new(); container.add_child(header)
	header.add_child(InspectorStyle.lbl("Creature weights", InspectorStyle.COLOR_TEXT_DIM))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = "+ Creature"; InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS)
	add.pressed.connect(_add_monster); header.add_child(add)
	monster_rows = VBoxContainer.new(); monster_rows.add_theme_constant_override("separation", 4); container.add_child(monster_rows)
	_refresh_monsters()
	var range_row := HBoxContainer.new(); range_row.add_theme_constant_override("separation", 8); container.add_child(range_row)
	range_row.add_child(InspectorStyle.lbl("Level from", InspectorStyle.COLOR_TEXT_DIM))
	var spawner: Dictionary = cur_data.get("spawner", {}) if cur_data.get("spawner") is Dictionary else {}
	var pair: Array = spawner.get("level_range", []) if spawner.get("level_range") is Array and spawner.get("level_range").size() == 2 else [1, 1]
	var low := _spin(range_row, float(pair[0]), "LevelMin")
	range_row.add_child(InspectorStyle.lbl("to", InspectorStyle.COLOR_TEXT_DIM))
	var high := _spin(range_row, float(pair[1]), "LevelMax")
	var write := func(_value):
		_spawner()["level_range"] = [int(low.value), int(max(low.value, high.value))]
		database_modified.emit()
	low.value_changed.connect(write); high.value_changed.connect(write)


func _refresh_monsters() -> void:
	for child in monster_rows.get_children(): monster_rows.remove_child(child); child.queue_free()
	var spawner = cur_data.get("spawner", {})
	var monsters: Dictionary = spawner.get("monster_types", {}) if spawner is Dictionary and spawner.get("monster_types") is Dictionary else {}
	for monster in monsters:
		var row := HBoxContainer.new(); row.name = "Monster_" + str(monster); row.add_theme_constant_override("separation", 6)
		var picker := OptionButton.new(); picker.name = "Npc"; picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		QuestGenerationSection._fill_picker(picker, database_mgr.get_npc_ids() if database_mgr != null else [], {}, str(monster), "Choose creature")
		InspectorStyle.apply_button_style(picker)
		var old_id := str(monster)
		picker.item_selected.connect(func(index): _rename_monster(old_id, str(picker.get_item_metadata(index))))
		row.add_child(picker)
		var weight := _spin(row, float(monsters[monster]), "Weight")
		weight.value_changed.connect(func(value): _spawner()["monster_types"][old_id] = int(value); database_modified.emit())
		var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
		remove.pressed.connect(func(): _remove_monster(old_id))
		row.add_child(remove)
		monster_rows.add_child(row)


func _add_monster() -> void:
	var monsters: Dictionary = _spawner().get("monster_types", {}) if _spawner().get("monster_types") is Dictionary else {}
	for npc_id in (database_mgr.get_npc_ids() if database_mgr != null else []):
		if not monsters.has(npc_id) and not bool(database_mgr.npcs[npc_id].get("friendly", true)):
			monsters[npc_id] = 1
			_spawner()["monster_types"] = monsters
			database_modified.emit(); _refresh_monsters(); return


func _rename_monster(old_id: String, new_id: String) -> void:
	var monsters: Dictionary = _spawner().get("monster_types", {})
	if new_id == "" or new_id == old_id or monsters.has(new_id):
		_refresh_monsters(); return
	var renamed := {}
	for key in monsters: renamed[new_id if key == old_id else key] = monsters[key]
	_spawner()["monster_types"] = renamed
	database_modified.emit(); _refresh_monsters()


func _remove_monster(monster_id: String) -> void:
	var monsters: Dictionary = _spawner().get("monster_types", {})
	monsters.erase(monster_id)
	if monsters.is_empty(): _spawner().erase("monster_types")
	if _spawner().is_empty(): cur_data.erase("spawner")
	database_modified.emit(); _refresh_monsters()


func _spawner() -> Dictionary:
	if not (cur_data.get("spawner") is Dictionary): cur_data["spawner"] = {}
	return cur_data["spawner"]


## Shared by every theme: `{Name}` inserts a capitalised word, `{name}` a
## lower-case one.
func _build_word_lists() -> void:
	container.add_child(InspectorStyle.create_sub_header("Word lists (shared by every theme)"))
	var header := HBoxContainer.new(); container.add_child(header)
	header.add_child(InspectorStyle.lbl("{Name} inserts a capitalised word, {name} a lower-case one.", InspectorStyle.COLOR_TEXT_DIM))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = "+ Word List"; InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS)
	add.pressed.connect(func():
		var lists := database_mgr.theme_placeholders.duplicate(true)
		var name := "word"
		var suffix := 2
		while lists.has(name): name = "word%d" % suffix; suffix += 1
		lists[name] = ["example"]
		database_mgr.set_theme_placeholders(lists); database_modified.emit(); _refresh_words())
	header.add_child(add)
	word_rows = VBoxContainer.new(); word_rows.add_theme_constant_override("separation", 4); container.add_child(word_rows)
	_refresh_words()


func _refresh_words() -> void:
	for child in word_rows.get_children(): word_rows.remove_child(child); child.queue_free()
	for list_name in database_mgr.theme_placeholders:
		var name := str(list_name)
		var row := HBoxContainer.new(); row.name = "Words_" + name; row.add_theme_constant_override("separation", 6)
		var name_field := LineEdit.new(); name_field.name = "ListName"; name_field.text = name; name_field.custom_minimum_size.x = 110
		InspectorStyle.apply_input_style(name_field)
		name_field.text_submitted.connect(func(value): _rename_words(name, value.strip_edges().to_lower()))
		row.add_child(name_field)
		var words := LineEdit.new(); words.name = "Words"; words.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var current = database_mgr.theme_placeholders[list_name]
		words.text = ", ".join(current) if current is Array else ""
		InspectorStyle.apply_input_style(words)
		words.text_changed.connect(func(text):
			var lists := database_mgr.theme_placeholders.duplicate(true)
			lists[name] = WorldRulesSection._split(text)
			database_mgr.set_theme_placeholders(lists); database_modified.emit())
		row.add_child(words)
		var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
		remove.pressed.connect(func():
			var lists := database_mgr.theme_placeholders.duplicate(true)
			lists.erase(name)
			database_mgr.set_theme_placeholders(lists); database_modified.emit(); _refresh_words())
		row.add_child(remove)
		word_rows.add_child(row)


func _rename_words(old: String, new: String) -> void:
	var lists := database_mgr.theme_placeholders.duplicate(true)
	if new == "" or new == old or lists.has(new):
		_refresh_words(); return
	var renamed := {}
	for key in lists: renamed[new if key == old else key] = lists[key]
	database_mgr.set_theme_placeholders(renamed); database_modified.emit(); _refresh_words()


## The value is set before the caller connects value_changed: a SpinBox emits
## it on a programmatic set, and building must not write.
func _spin(parent: Control, value: float, node_name: String) -> SpinBox:
	var spin := SpinBox.new(); spin.name = node_name; spin.min_value = 1; spin.max_value = 1000; spin.step = 1; spin.value = value
	spin.custom_minimum_size.x = 70; InspectorStyle.apply_input_style(spin); parent.add_child(spin)
	return spin
