# tests/room_passages_authoring_smoke.gd
#
# `properties.exit_requirements`, `hidden_exits` and `env_interactions` were
# read-only property notes; RoomPassagesPanel now edits them. fantasy_frontier's
# jail cell (a pickable lock with no key) and obsidian_trial's hall_of_gates (a
# hidden exit) are the real rooms; the edited region is finally run through the
# engine's own validator, since a bad value here fails open rather than loud.
#
#   godot --headless --path mud-world-editor --script tests/room_passages_authoring_smoke.gd

extends SceneTree

const PANEL = preload("res://scripts/ui/inspectors/panels/RoomPassagesPanel.gd")

var failures := 0
var fixture := ""
# Panels are RefCounted; the room inspector keeps its own, so the test must too.
var panels: Array = []


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/room-passages-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "room passages smoke"
	var database := DatabaseManager.new()

	print("\n[opening real rooms changes nothing]")
	var town_path := fixture.path_join("data/regions/town.json")
	var town: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(town_path))
	var cell: Dictionary = town["rooms"]["jail_cell"]
	var cell_before := JSON.stringify(cell)
	var holder := _panel(cell, database)
	_assert(JSON.stringify(cell) == cell_before, "the jail cell is unchanged by opening")
	_assert(holder.find_child("Requirement_up", true, false) != null, "its lock on 'up' is shown")
	var gates_region: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(fixture.path_join("data/regions/obsidian_trial.json")))
	var gates: Dictionary = gates_region["rooms"]["hall_of_gates"]
	var gates_before := JSON.stringify(gates)
	holder = _panel(gates, database)
	_assert(JSON.stringify(gates) == gates_before, "hall_of_gates is unchanged by opening")
	_assert(holder.find_child("Hidden_north", true, false) != null, "its hidden exit is shown")

	print("\n[editing a room]")
	var square: Dictionary = town["rooms"]["town_square"]
	holder = _panel(square, database)
	_button(holder, "+ Requirement").pressed.emit()
	var requirements: Dictionary = square["properties"]["exit_requirements"]
	var direction: String = requirements.keys()[0]
	_assert(square["exits"].has(direction), "a new requirement guards one of the room's real exits (%s)" % direction)
	var row: Node = holder.find_child("Requirement_" + direction, true, false)
	var type_picker: OptionButton = row.find_child("Type", true, false)
	type_picker.select(1); type_picker.item_selected.emit(1)
	_assert(requirements[direction]["type"] == "skill" and not requirements[direction].has("pick_difficulty"), "switching to a skill check drops the lock's fields")
	row = holder.find_child("Requirement_" + direction, true, false)
	_edit(row.find_child("SkillName", true, false), "athletics")
	(row.find_child("Difficulty", true, false) as SpinBox).value = 25
	_assert(requirements[direction]["skill_name"] == "athletics" and requirements[direction]["difficulty"] == 25, "the skill and difficulty were written")

	_button(holder, "+ Reaction").pressed.emit()
	var reactions: Dictionary = square["properties"]["env_interactions"]
	var damage_type: String = reactions.keys()[0]
	_assert(database.combat_vocabulary.damage_types.has(damage_type), "a new reaction uses a declared damage type (%s)" % damage_type)
	_assert(reactions[damage_type]["direction"] == direction, "and clears the room's own requirement")

	_button(holder, "+ Hidden Exit").pressed.emit()
	var hidden_row: Node = holder.find_child("Hidden_secret", true, false)
	_edit(hidden_row.find_child("Destination", true, false), "north_gate_road")
	_assert(square["properties"]["hidden_exits"] == {"secret": "north_gate_road"}, "the hidden exit was written")

	print("\n[a condition requirement]")
	row = holder.find_child("Requirement_" + direction, true, false)
	type_picker = row.find_child("Type", true, false)
	type_picker.select(2); type_picker.item_selected.emit(2)
	_assert(requirements[direction]["type"] == "condition" and requirements[direction].has("condition") and not requirements[direction].has("skill_name"),
		"switching to a condition drops the skill's fields and starts a condition to fill in: %s" % str(requirements[direction]))
	row = holder.find_child("Requirement_" + direction, true, false)
	var kind_picker: OptionButton = row.find_child("ConditionPicker", true, false)
	_assert(kind_picker != null, "the condition has the shared kind picker")
	var flag_index := -1
	var clear_index := -1
	for index in range(kind_picker.item_count):
		if kind_picker.get_item_text(index) == "flag": flag_index = index
		if kind_picker.get_item_text(index) == "room_clear": clear_index = index
	_assert(flag_index >= 0, "and offers the engine's kinds")
	_assert(clear_index >= 0, "including room_clear, for a kill-all room")
	kind_picker.select(flag_index); kind_picker.item_selected.emit(flag_index)
	row = holder.find_child("Requirement_" + direction, true, false)
	_edit(row.find_child("ConditionValue", true, false), "gate_open")
	_assert(requirements[direction]["condition"] == {"kind": "flag", "flag": "gate_open"}, "a flag gate was written: %s" % str(requirements[direction]))
	_edit(row.find_child("FailureMessage", true, false), "The gate is shut.")
	_assert(requirements[direction]["failure_message"] == "The gate is shut.", "with its message")

	print("\n[spending a key]")
	var consume_box: LineEdit = row.find_child("ConsumeItems", true, false)
	_assert(consume_box != null, "a condition gate has a box for what it spends")
	_edit(consume_box, "item_small_key, item_lantern")
	_assert(requirements[direction]["consume"] == ["item_small_key", "item_lantern"], "items are listed: %s" % str(requirements[direction].get("consume")))
	_edit(consume_box, "")
	_assert(not requirements[direction].has("consume"), "and emptying it removes the key")
	requirements[direction] = {"type": "locked", "key_id": "item_small_key"}
	holder = _panel(square, database)
	row = holder.find_child("Requirement_" + direction, true, false)
	var used_up: CheckBox = row.find_child("Consume", true, false)
	_assert(used_up != null, "a key lock has a used-up box")
	used_up.button_pressed = true
	_assert(requirements[direction].get("consume") == true, "ticking it writes consume: true")
	used_up.button_pressed = false
	_assert(not requirements[direction].has("consume"), "and unticking erases it, so a default stays unwritten")
	requirements[direction] = {"type": "condition", "condition": {"kind": "flag", "flag": "gate_open"}, "failure_message": "The gate is shut."}

	print("\n[removing]")
	_button(holder.find_child("Hidden_secret", true, false), "×").pressed.emit()
	_assert(not square["properties"].has("hidden_exits"), "removing the last hidden exit removes the key")

	print("\n[the engine accepts the result]")
	var result := SaveIO.write_json(town_path, town)
	_assert(result.get("ok", false), "the edited region was written")
	var output: Array = []
	var python := repo.path_join(".venv/Scripts/python.exe")
	if not FileAccess.file_exists(python): python = repo.path_join(".venv/bin/python")
	var code := OS.execute(python, [repo.path_join("toolkit/content_set_validator.py"), fixture], output, true)
	_assert(code == 0, "the engine's validator accepts the edited set")
	if code != 0: print("\n".join(output).right(1500))

	if failures > 0: push_error("room passages authoring failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _panel(room: Dictionary, database: DatabaseManager) -> Node:
	var holder := VBoxContainer.new(); root.add_child(holder)
	var panel = PANEL.new(); panels.append(panel)
	panel.build(holder, room, database)
	return holder


func _button(node: Node, text: String) -> Button:
	if node is Button and str(node.text) == text: return node
	for child in node.get_children():
		var found := _button(child, text)
		if found != null: return found
	return null


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _edit(field: LineEdit, value: String):
	field.text = value; field.text_changed.emit(value)


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
