# scripts/ui/inspectors/sub_inspectors/TitleInspector.gd
#
# Title authoring: `titles.json`, the earned-identity system that replaced
# classes. A title is granted the moment its `condition` (and every entry in
# `requirements`) holds, and revoked the moment one stops -- see
# `engine/core/titles.py`.
#
# It shares its condition vocabulary with dialogue choice conditions
# (`engine/conditions.py`, the same evaluator), so this reuses
# `DialogueSchema`'s condition kinds/fields/notes rather than repeating them --
# a kind the dialogue editor knows is a kind this editor knows.
#
# `conferred_by` names a guild-like construct from the file's own `_guilds`
# registry, which several titles can share; editing a guild's place here edits
# it for every title conferred by that guild, which is what the shared
# registry means.

class_name TitleInspector
extends RefCounted

signal database_modified

const NEW_GUILD_SENTINEL := "+ New guild…"
const NO_GUILD_SENTINEL := "(none)"

var container: VBoxContainer
var cur_data: Dictionary
var cur_id: String
var database_mgr: DatabaseManager
var requirements_box: VBoxContainer
var new_guild_row: HBoxContainer
var place_field: LineEdit


func _init(c: VBoxContainer, db_mgr: DatabaseManager):
	container = c
	database_mgr = db_mgr


func build(id: String, data: Dictionary):
	cur_data = data
	cur_id = id
	container.add_child(InspectorStyle.create_section_header("TITLE: %s" % id.to_upper(), Color(0.95, 0.8, 0.4)))

	_build_identity()
	_build_conferred_by()
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Condition (all of these must hold)"))
	_condition_editor(container, cur_data, "condition", func(): _rebuild())
	_build_requirements()
	_build_extras()


func _rebuild():
	for child in container.get_children(): child.queue_free()
	# The id is not editable here, the same limitation the quest, recipe and
	# dialogue sub-inspectors share.
	build(cur_id, cur_data)


func _build_identity():
	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)

	vbox.add_child(InspectorStyle.lbl("Name (what the player sees):", InspectorStyle.COLOR_TEXT_DIM))
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


func _build_conferred_by():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Conferred by"))
	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)

	var conferred = cur_data.get("conferred_by")
	var current_guild_id := ""
	if conferred is Dictionary:
		current_guild_id = str(conferred.get("guild_id", ""))

	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
	var picker := OptionButton.new()
	var ids := database_mgr.guild_ids()
	var options: Array = [NO_GUILD_SENTINEL] + ids + [NEW_GUILD_SENTINEL]
	for option in options:
		picker.add_item(option if option in [NO_GUILD_SENTINEL, NEW_GUILD_SENTINEL] else "%s (%s)" % [database_mgr.guild_name(option), option])
	var selected_index := options.find(current_guild_id) if current_guild_id != "" else 0
	picker.select(selected_index if selected_index >= 0 else 0)
	InspectorStyle.apply_button_style(picker)
	picker.item_selected.connect(func(index):
		var chosen := str(options[index])
		if chosen == NEW_GUILD_SENTINEL:
			new_guild_row.visible = true
			return
		new_guild_row.visible = false
		if chosen == NO_GUILD_SENTINEL:
			cur_data.erase("conferred_by")
		else:
			cur_data["conferred_by"] = {"name": database_mgr.guild_name(chosen), "guild_id": chosen}
		database_modified.emit()
		_rebuild()
	)
	row.add_child(picker)
	vbox.add_child(row)

	if current_guild_id != "" and database_mgr.guilds.has(current_guild_id):
		var place_row := HBoxContainer.new(); place_row.add_theme_constant_override("separation", 6)
		place_row.add_child(InspectorStyle.lbl("Place (region:room, shared by the guild)", InspectorStyle.COLOR_TEXT_DIM))
		place_field = LineEdit.new()
		place_field.text = str(database_mgr.guilds[current_guild_id].get("place", ""))
		place_field.placeholder_text = "region_id:room_id"
		place_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_input_style(place_field)
		place_field.text_changed.connect(func(text):
			database_mgr.set_guild_place(current_guild_id, str(text).strip_edges())
			database_modified.emit()
		)
		place_row.add_child(place_field)
		vbox.add_child(place_row)

	new_guild_row = HBoxContainer.new(); new_guild_row.add_theme_constant_override("separation", 6)
	new_guild_row.visible = false
	var id_field := LineEdit.new(); id_field.placeholder_text = "guild id"
	id_field.custom_minimum_size.x = 120
	InspectorStyle.apply_input_style(id_field)
	new_guild_row.add_child(id_field)
	var name_field := LineEdit.new(); name_field.placeholder_text = "guild name, e.g. The Order of the Dawn"
	name_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(name_field)
	new_guild_row.add_child(name_field)
	var create := Button.new(); create.text = "Add"
	InspectorStyle.apply_button_style(create, Color(0.2, 0.3, 0.4))
	create.pressed.connect(func():
		var new_id := str(id_field.text).strip_edges()
		var new_name := str(name_field.text).strip_edges()
		if new_id == "" or new_name == "" or database_mgr.guilds.has(new_id): return
		database_mgr.add_guild(new_id, new_name)
		cur_data["conferred_by"] = {"name": new_name, "guild_id": new_id}
		database_modified.emit()
		_rebuild()
	)
	new_guild_row.add_child(create)
	vbox.add_child(new_guild_row)


func _build_requirements():
	container.add_child(HSeparator.new())
	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.create_sub_header("Additional requirements (also all must hold)"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var add := Button.new(); add.text = "+ Requirement"
	InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var list: Array = cur_data.get("requirements", []) if cur_data.get("requirements") is Array else []
		list.append({})
		cur_data["requirements"] = list
		database_modified.emit()
		_refresh_requirements()
	)
	header.add_child(add)
	container.add_child(header)

	requirements_box = VBoxContainer.new()
	requirements_box.add_theme_constant_override("separation", 10)
	container.add_child(requirements_box)
	_refresh_requirements()


func _refresh_requirements():
	for child in requirements_box.get_children(): child.queue_free()
	var requirements: Array = cur_data.get("requirements", []) if cur_data.get("requirements") is Array else []
	if requirements.is_empty():
		requirements_box.add_child(InspectorStyle.lbl("None -- the condition above is the whole gate.", InspectorStyle.COLOR_TEXT_DIM))
		return
	for index in range(requirements.size()):
		if not (requirements[index] is Dictionary): continue
		var row_card := InspectorStyle.create_card()
		var row_vbox := row_card.get_child(0).get_child(0)
		requirements_box.add_child(row_card)

		var remove_row := HBoxContainer.new()
		var remove_spacer := Control.new(); remove_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		remove_row.add_child(remove_spacer)
		var remove := Button.new(); remove.text = "× remove"
		InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		var captured_index := index
		remove.pressed.connect(func():
			requirements.remove_at(captured_index)
			if requirements.is_empty(): cur_data.erase("requirements")
			database_modified.emit()
			_refresh_requirements()
		)
		remove_row.add_child(remove)
		row_vbox.add_child(remove_row)

		_condition_fields(row_vbox, requirements[index], func(chosen: String):
			if chosen == "": requirements[captured_index] = {}
			else: requirements[captured_index] = {"kind": chosen}
			database_modified.emit()
			_refresh_requirements()
		)


# A condition editor bound to `holder[key]` -- used for the single top-level
# `condition`. `on_kind_changed` lets a caller with a different storage shape
# (an array element, for `requirements`) reuse the same field rendering.
func _condition_editor(parent: VBoxContainer, holder: Dictionary, key: String, on_rebuild: Callable) -> void:
	# Dictionaries are reference types in GDScript, so mutating `condition` here
	# mutates `holder[key]` directly when it already exists -- nothing needs
	# writing back except when a kind is first chosen. A blank `{}` must never
	# reach `holder[key]`: the content validator reports any condition object
	# with no `kind` as an error, even an absent-by-convention empty one.
	var condition = holder.get(key)
	if not (condition is Dictionary): condition = {}
	_condition_fields(parent, condition, func(chosen: String):
		if chosen == "": holder.erase(key)
		else: holder[key] = {"kind": chosen}
		database_modified.emit()
		on_rebuild.call()
	)


# Renders a condition kind picker plus that kind's fields, operating on the
# `condition` dictionary in place. `on_kind_changed(chosen_kind)` is called
# when the picker changes -- `""` means "no condition" -- because replacing a
# dictionary in an Array requires assigning back to the array, which this
# function has no reference to.
func _condition_fields(parent: VBoxContainer, condition: Dictionary, on_kind_changed: Callable) -> void:
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
	row.add_child(InspectorStyle.lbl("Kind", InspectorStyle.COLOR_TEXT_DIM))
	var picker := OptionButton.new()
	var kinds: Array = ["(none)"] + DialogueSchema.condition_kinds()
	var current_kind := str(condition.get("kind", ""))
	if current_kind != "" and not DialogueSchema.has_condition_kind(current_kind):
		kinds.append(current_kind)
	for kind in kinds: picker.add_item(str(kind))
	var index := kinds.find(current_kind) if current_kind != "" else 0
	picker.select(index if index >= 0 else 0)
	InspectorStyle.apply_button_style(picker)
	picker.item_selected.connect(func(selected):
		var chosen := str(kinds[selected])
		on_kind_changed.call("" if chosen == "(none)" else chosen)
	)
	row.add_child(picker)
	parent.add_child(row)

	if current_kind == "":
		return

	var note := Label.new()
	note.text = DialogueSchema.condition_note(current_kind)
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	note.add_theme_font_size_override("font_size", 11)
	note.modulate = Color(0.68, 0.7, 0.78)
	parent.add_child(note)

	var fields := DialogueSchema.condition_fields(current_kind)
	for field in fields:
		_condition_field_row(parent, condition, str(field), str(fields[field]))

	var extras: Array = []
	for key in condition:
		if str(key) != "kind" and not fields.has(str(key)):
			extras.append(key)
	if not extras.is_empty():
		_condition_extras_row(parent, condition, extras)


func _condition_field_row(parent: VBoxContainer, condition: Dictionary, key: String, kind: String):
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
	row.add_child(InspectorStyle.lbl("    " + key.replace("_", " "), InspectorStyle.COLOR_TEXT_DIM))
	var line := LineEdit.new()
	line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if kind == "int":
		line.text = str(int(condition.get(key, 0)))
	else:
		line.text = str(condition.get(key, ""))
	line.placeholder_text = kind
	InspectorStyle.apply_input_style(line)
	line.text_changed.connect(func(text):
		var trimmed: String = str(text).strip_edges()
		if trimmed == "":
			condition.erase(key)
		elif kind == "int" and trimmed.is_valid_int():
			condition[key] = int(trimmed)
		else:
			condition[key] = trimmed
		database_modified.emit()
	)
	row.add_child(line)
	match kind:
		"item_id": InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_item_ids())
		"npc_id": InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_npc_ids())
		"quest_id": InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_ids("quest"))
		"recipe_id": InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_recipe_ids())
	parent.add_child(row)


func _condition_extras_row(parent: VBoxContainer, condition: Dictionary, keys: Array):
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
	row.add_child(InspectorStyle.lbl("    other fields", InspectorStyle.COLOR_TEXT_DIM))
	var line := LineEdit.new()
	var subset := {}
	for key in keys: subset[key] = condition[key]
	line.text = JSON.stringify(subset)
	line.tooltip_text = "Fields this editor does not model for this condition kind."
	line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(line)
	line.text_changed.connect(func(text):
		var parsed = JSON.parse_string(str(text).strip_edges())
		if typeof(parsed) != TYPE_DICTIONARY:
			line.modulate = Color(1.0, 0.6, 0.6)
			return
		line.modulate = Color.WHITE
		for key in keys: condition.erase(key)
		for key in parsed: condition[key] = parsed[key]
		database_modified.emit()
	)
	row.add_child(line)
	parent.add_child(row)


func _build_extras():
	var known := ["name", "description", "conferred_by", "condition", "requirements"]
	var extras: Array = []
	for key in cur_data:
		if not known.has(str(key)):
			extras.append(key)
	extras.sort()
	if extras.is_empty(): return
	var note := Label.new()
	note.text = "Other title fields (kept as authored): %s" % ", ".join(extras)
	note.add_theme_font_size_override("font_size", 11)
	note.modulate = Color(0.7, 0.72, 0.6)
	container.add_child(note)
