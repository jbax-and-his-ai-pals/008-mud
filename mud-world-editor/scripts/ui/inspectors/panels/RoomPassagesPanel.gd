# scripts/ui/inspectors/panels/RoomPassagesPanel.gd
#
# A room's passage rules, which were visible only as read-only property notes:
# `properties.exit_requirements` (World.move_player: a skill check or a lock on
# one exit), `properties.hidden_exits` (links a lever or spell reveals) and
# `properties.env_interactions` (Room.apply_elemental_interaction: what a spell's
# damage type does to the room for a while). Validated by
# `content_set.py::_validate_room_passage_properties`; both of the first and last
# fail open, so the pickers offer only this room's real exits and requirements.
# Entries are edited in place, so keys this panel does not show survive.

class_name RoomPassagesPanel
extends RefCounted

signal data_modified

const REQUIREMENT_TYPES := ["locked", "skill"]
const REQUIREMENT_KEYS := {
	"locked": ["type", "key_id", "pick_difficulty", "failure_message"],
	"skill": ["type", "skill_name", "difficulty", "failure_message"],
}
const REACTION_TYPES := ["clear_exit_req", "suppress_hazard"]
const REACTION_KEYS := {
	"clear_exit_req": ["type", "direction", "duration", "message"],
	"suppress_hazard": ["type", "duration", "message"],
}

var room: Dictionary
var database_mgr: DatabaseManager
var requirement_rows: VBoxContainer
var hidden_rows: VBoxContainer
var reaction_rows: VBoxContainer


func build(parent: VBoxContainer, room_data: Dictionary, db_mgr: DatabaseManager) -> void:
	room = room_data
	database_mgr = db_mgr
	parent.add_child(InspectorStyle.create_section_header("PASSAGES & LOCKS", InspectorStyle.COLOR_ACCENT))
	var card := InspectorStyle.create_card()
	var box: VBoxContainer = card.get_child(0).get_child(0)
	box.add_theme_constant_override("separation", 7)
	parent.add_child(card)
	requirement_rows = _list(box, "Exit requirements", "+ Requirement", _add_requirement,
		"A lock or a skill check on one of this room's exits.")
	box.add_child(HSeparator.new())
	hidden_rows = _list(box, "Hidden exits", "+ Hidden Exit", _add_hidden_exit,
		"Exits that stay closed until a linked lever or effect opens them. Destination: a room id, or region:room.")
	box.add_child(HSeparator.new())
	reaction_rows = _list(box, "Elemental reactions", "+ Reaction", _add_reaction,
		"What a spell of a damage type does to this room for a while: clear an exit requirement, or suppress its hazard.")
	_refresh()


func _refresh() -> void:
	for rows in [requirement_rows, hidden_rows, reaction_rows]:
		for child in rows.get_children(): rows.remove_child(child); child.queue_free()
	var requirements := _section("exit_requirements")
	for direction in requirements:
		if requirements[direction] is Dictionary: requirement_rows.add_child(_requirement_row(str(direction), requirements[direction]))
	var hidden := _section("hidden_exits")
	for direction in hidden: hidden_rows.add_child(_hidden_row(str(direction)))
	var reactions := _section("env_interactions")
	for damage_type in reactions:
		if reactions[damage_type] is Dictionary: reaction_rows.add_child(_reaction_row(str(damage_type), reactions[damage_type]))


# --- exit requirements ------------------------------------------------------

func _requirement_row(direction: String, requirement: Dictionary) -> Control:
	var box := VBoxContainer.new(); box.name = "Requirement_" + direction
	var head := HBoxContainer.new(); head.add_theme_constant_override("separation", 6); box.add_child(head)
	var direction_picker := _choice(_directions(), direction, "Direction")
	direction_picker.item_selected.connect(func(index): _rename_key("exit_requirements", direction, str(direction_picker.get_item_metadata(index))))
	head.add_child(direction_picker)
	var kind := str(requirement.get("type", "locked"))
	var type_picker := _choice(REQUIREMENT_TYPES, kind, "Type")
	type_picker.item_selected.connect(func(index): _retype(requirement, str(type_picker.get_item_metadata(index)), REQUIREMENT_KEYS))
	head.add_child(type_picker)
	if kind == "skill":
		head.add_child(_text(requirement, "skill_name", "skill"))
		head.add_child(InspectorStyle.lbl("difficulty", InspectorStyle.COLOR_TEXT_DIM))
		head.add_child(_spin(requirement, "difficulty", 10, 0, 1000))
	else:
		var key := OptionButton.new(); key.name = "KeyId"; key.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var ids: Array = database_mgr.get_item_ids() if database_mgr != null else []
		var current = requirement.get("key_id")
		QuestGenerationSection._fill_picker(key, ids, {}, str(current) if current is String else "", "No key (pick only)")
		InspectorStyle.apply_button_style(key)
		key.item_selected.connect(func(index):
			var value := str(key.get_item_metadata(index))
			requirement["key_id"] = value if value != "" else null
			data_modified.emit())
		head.add_child(key)
		head.add_child(InspectorStyle.lbl("pick", InspectorStyle.COLOR_TEXT_DIM))
		var pick := _spin(requirement, "pick_difficulty", 999, 0, 999)
		pick.tooltip_text = "Over 100 cannot be picked."
		head.add_child(pick)
	head.add_child(_remove("exit_requirements", direction))
	var message := _text(requirement, "failure_message", "message when refused (optional)")
	box.add_child(message)
	return box


func _add_requirement() -> void:
	var requirements := _section("exit_requirements")
	var direction := _first_free(_directions(), requirements)
	if direction == "": return
	requirements[direction] = {"type": "locked", "key_id": null, "pick_difficulty": 30}
	_store("exit_requirements", requirements)


# --- hidden exits -----------------------------------------------------------

func _hidden_row(direction: String) -> Control:
	var row := HBoxContainer.new(); row.name = "Hidden_" + direction; row.add_theme_constant_override("separation", 6)
	var direction_field := LineEdit.new(); direction_field.name = "Direction"; direction_field.text = direction; direction_field.custom_minimum_size.x = 110
	InspectorStyle.apply_input_style(direction_field)
	direction_field.text_submitted.connect(func(value): _rename_key("hidden_exits", direction, value.strip_edges()))
	direction_field.focus_exited.connect(func(): _rename_key("hidden_exits", direction, direction_field.text.strip_edges()))
	row.add_child(direction_field)
	var hidden := _section("hidden_exits")
	var destination := LineEdit.new(); destination.name = "Destination"; destination.text = str(hidden.get(direction, ""))
	destination.placeholder_text = "room id or region:room"; destination.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(destination)
	destination.text_changed.connect(func(value): _section("hidden_exits")[direction] = value.strip_edges(); data_modified.emit())
	row.add_child(destination)
	row.add_child(_remove("hidden_exits", direction))
	return row


func _add_hidden_exit() -> void:
	var hidden := _section("hidden_exits")
	var direction := "secret"
	var suffix := 2
	while hidden.has(direction) or _visible_exits().has(direction): direction = "secret_%d" % suffix; suffix += 1
	hidden[direction] = ""
	_store("hidden_exits", hidden)


# --- elemental reactions ----------------------------------------------------

func _reaction_row(damage_type: String, reaction: Dictionary) -> Control:
	var row := HBoxContainer.new(); row.name = "Reaction_" + damage_type; row.add_theme_constant_override("separation", 6)
	var type_list := _damage_types()
	var damage := _choice(type_list, damage_type, "Damage")
	damage.item_selected.connect(func(index): _rename_key("env_interactions", damage_type, str(damage.get_item_metadata(index))))
	row.add_child(damage)
	var kind := str(reaction.get("type", "clear_exit_req"))
	var type_picker := _choice(REACTION_TYPES, kind, "Reaction")
	type_picker.item_selected.connect(func(index): _retype(reaction, str(type_picker.get_item_metadata(index)), REACTION_KEYS))
	row.add_child(type_picker)
	if kind == "clear_exit_req":
		var directions: Array = _section("exit_requirements").keys()
		var target := _choice(directions, str(reaction.get("direction", "")), "Requirement")
		target.item_selected.connect(func(index): reaction["direction"] = str(target.get_item_metadata(index)); data_modified.emit())
		row.add_child(target)
	row.add_child(InspectorStyle.lbl("for (s)", InspectorStyle.COLOR_TEXT_DIM))
	var duration := SpinBox.new(); duration.name = "Duration"; duration.min_value = 1; duration.max_value = 3600; duration.step = 1
	duration.value = float(reaction.get("duration", 10.0)); duration.custom_minimum_size.x = 70; InspectorStyle.apply_input_style(duration)
	duration.value_changed.connect(func(value): reaction["duration"] = int(value); data_modified.emit())
	row.add_child(duration)
	row.add_child(_text(reaction, "message", "message (optional)"))
	row.add_child(_remove("env_interactions", damage_type))
	return row


func _add_reaction() -> void:
	var reactions := _section("env_interactions")
	var damage_type := _first_free(_damage_types(), reactions)
	if damage_type == "": return
	var requirements: Array = _section("exit_requirements").keys()
	if not requirements.is_empty():
		reactions[damage_type] = {"type": "clear_exit_req", "direction": requirements[0], "duration": 10}
	else:
		reactions[damage_type] = {"type": "suppress_hazard", "duration": 10}
	_store("env_interactions", reactions)


# --- shared -----------------------------------------------------------------

func _properties() -> Dictionary:
	if not (room.get("properties") is Dictionary): room["properties"] = {}
	return room["properties"]


func _section(key: String) -> Dictionary:
	var props = room.get("properties", {})
	var value = props.get(key, {}) if props is Dictionary else {}
	return value if value is Dictionary else {}


## Writes a section back, removing it once empty.
func _store(key: String, value: Dictionary) -> void:
	if value.is_empty(): _properties().erase(key)
	else: _properties()[key] = value
	data_modified.emit()
	_refresh()


func _rename_key(section_key: String, old: String, new: String) -> void:
	var section := _section(section_key)
	if new == "" or new == old or section.has(new):
		_refresh(); return
	var renamed := {}
	for key in section: renamed[new if key == old else key] = section[key]
	_store(section_key, renamed)


func _retype(entry: Dictionary, kind: String, keys: Dictionary) -> void:
	entry["type"] = kind
	for key in entry.keys():
		if not (key in keys[kind]): entry.erase(key)
	data_modified.emit()
	_refresh()


func _remove(section_key: String, key: String) -> Button:
	var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
	remove.pressed.connect(func():
		var section := _section(section_key); section.erase(key); _store(section_key, section))
	return remove


func _choice(options: Array, current: String, name: String) -> OptionButton:
	var picker := OptionButton.new(); picker.name = name
	var values := options.duplicate()
	if current != "" and not values.has(current): values.append(current)
	for value in values:
		var label := str(value) if options.has(value) else "Missing: %s" % value
		picker.add_item(label); picker.set_item_metadata(picker.item_count - 1, str(value))
		if str(value) == current: picker.select(picker.item_count - 1)
	InspectorStyle.apply_button_style(picker)
	return picker


func _text(entry: Dictionary, key: String, placeholder: String) -> LineEdit:
	var field := LineEdit.new(); field.name = key.to_pascal_case(); field.text = str(entry.get(key, "")); field.placeholder_text = placeholder
	field.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(field)
	field.text_changed.connect(func(value):
		if value.strip_edges() == "": entry.erase(key)
		else: entry[key] = value
		data_modified.emit())
	return field


## The value is set before the signal is connected: a SpinBox emits
## value_changed on a programmatic set, and building must not write.
func _spin(entry: Dictionary, key: String, fallback: int, low: int, high: int) -> SpinBox:
	var spin := SpinBox.new(); spin.name = key.to_pascal_case(); spin.min_value = low; spin.max_value = high; spin.step = 1
	spin.value = float(entry.get(key, fallback)); spin.custom_minimum_size.x = 70; InspectorStyle.apply_input_style(spin)
	spin.value_changed.connect(func(value): entry[key] = int(value); data_modified.emit())
	return spin


func _list(box: VBoxContainer, title: String, button_text: String, on_add: Callable, hint_text: String) -> VBoxContainer:
	var header := HBoxContainer.new(); box.add_child(header)
	header.add_child(InspectorStyle.create_sub_header(title))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = button_text; InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS); add.pressed.connect(on_add); header.add_child(add)
	var hint := InspectorStyle.lbl(hint_text, InspectorStyle.COLOR_TEXT_DIM); hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(hint)
	var rows := VBoxContainer.new(); rows.add_theme_constant_override("separation", 5); box.add_child(rows)
	return rows


func _visible_exits() -> Array:
	var exits = room.get("exits", {})
	return exits.keys() if exits is Dictionary else []


func _directions() -> Array:
	var out := _visible_exits().duplicate()
	for direction in _section("hidden_exits"):
		if not out.has(direction): out.append(direction)
	return out


func _damage_types() -> Array:
	if database_mgr != null and database_mgr.combat_vocabulary != null and not database_mgr.combat_vocabulary.damage_types.is_empty():
		return database_mgr.combat_vocabulary.damage_types.duplicate()
	return []


static func _first_free(options: Array, taken: Dictionary) -> String:
	for option in options:
		if not taken.has(option): return str(option)
	return ""
