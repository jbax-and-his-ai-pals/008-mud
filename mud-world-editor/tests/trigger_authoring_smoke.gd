# tests/trigger_authoring_smoke.gd
#
# Triggers (`data/triggers/*.json`) are authorable, and what the inspector writes is what
# the engine reads.
#
# A trigger is `{on, when, once, effects}`: something that happens when the player walks
# into a room. The library loads the folder like any other set of entries, the inspector
# edits one without writing on open, and the *engine's* validator has the last word.
#
#   godot --headless --path mud-world-editor --script tests/trigger_authoring_smoke.gd

extends SceneTree

const RowProbe = preload("res://tests/lib/RowProbe.gd")
const TriggerInspectorScript = preload("res://scripts/ui/inspectors/sub_inspectors/TriggerInspector.gd")
const RoomTriggersPanelScript = preload("res://scripts/ui/inspectors/panels/RoomTriggersPanel.gd")

var failures := 0
var fixture := ""
var repo := ""
var database: DatabaseManager


func _init() -> void:
	_run.call_deferred()


func _run() -> void:
	repo = ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/trigger-authoring-%s/zelda_slice" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/zelda_slice"), fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "trigger authoring smoke"
	database = DatabaseManager.new()

	print("\n[the library loads the folder]")
	_assert(database.triggers.has("wyrm_hall") and database.triggers.has("tower_gate_opens"), "both authored triggers are loaded by id: %s" % str(database.triggers.keys()))
	_assert(database.get_trigger_ids().has("wyrm_hall"), "and listed")
	_assert(database.dirty_flags.has("trigger"), "with their own dirty state")
	_assert(not database.triggers["wyrm_hall"].has("id"), "keyed by id, not carrying it")

	print("\n[opening one writes nothing]")
	var wyrm: Dictionary = database.triggers["wyrm_hall"]
	var before := JSON.stringify(wyrm)
	var holder := _open("wyrm_hall", wyrm)
	_assert(JSON.stringify(wyrm) == before, "the trigger is unchanged by opening")
	_assert(holder.find_child("TriggerRoom", true, false) != null, "it has a room picker")
	var room_picker := holder.find_child("TriggerRoom", true, false) as OptionButton
	_assert(room_picker.get_item_text(room_picker.selected) == "mossroot:boss_hall", "showing where it fires: %s" % room_picker.get_item_text(room_picker.selected))
	var once_picker := holder.find_child("TriggerOnce", true, false) as OptionButton
	_assert(once_picker.get_item_text(once_picker.selected) == "Once for each player", "and how often (an authored `player` shows as the default)")

	print("\n[editing]")
	var message := RowProbe.value_widget(holder, "message") as LineEdit
	_assert(message != null and message.text.begins_with("The air is hot"), "the effects are the shared rows")
	RowProbe.type_into(message, "The wyrm hears you.")
	_assert(wyrm["effects"]["message"] == "The wyrm hears you.", "editing a line writes it")

	var world_index := -1
	var every_index := -1
	var player_index := -1
	for index in range(once_picker.item_count):
		match str(once_picker.get_item_metadata(index)):
			"world": world_index = index
			"every": every_index = index
			"player": player_index = index
	once_picker.select(world_index); once_picker.item_selected.emit(world_index)
	_assert(wyrm.get("once") == "world", "once for the whole world is written")
	once_picker.select(every_index); once_picker.item_selected.emit(every_index)
	_assert(wyrm.has("once") and wyrm["once"] == false, "every time is written as false, not the string")
	once_picker.select(player_index); once_picker.item_selected.emit(player_index)
	_assert(not wyrm.has("once"), "and once for each player erases the key, the default the engine assumes")

	var refs := TriggerInspectorScript.room_refs()
	_assert(refs.has("mossroot:boss_hall") and refs.has("dread_tower:tower_gate"), "the room picker offers this set's rooms")
	var tower := room_picker.item_count
	for index in range(room_picker.item_count):
		if room_picker.get_item_text(index) == "dread_tower:tower_gate": tower = index
	room_picker.select(tower); room_picker.item_selected.emit(tower)
	_assert(wyrm["on"] == {"event": "on_enter", "region": "dread_tower", "room": "tower_gate"}, "choosing a room writes region and room together: %s" % str(wyrm["on"]))

	print("\n[the other events]")
	holder = _open("wyrm_hall", wyrm)
	var event_picker := holder.find_child("TriggerEvent", true, false) as OptionButton
	var events: Array = []
	for index in range(event_picker.item_count):
		events.append(str(event_picker.get_item_metadata(index)))
	_assert(events == ["on_enter", "npc_killed", "room_cleared", "item_taken", "health_below"], "the picker offers the engine's events: %s" % str(events))
	var kill_index := events.find("npc_killed")
	event_picker.select(kill_index); event_picker.item_selected.emit(kill_index)
	_assert(wyrm["on"]["event"] == "npc_killed" and wyrm["on"].has("npc") and wyrm["on"].has("region"),
		"a kill trigger gets a creature (and keeps the room as a narrowing): %s" % str(wyrm["on"]))
	holder = _open("wyrm_hall", wyrm)
	var npc_picker := holder.find_child("TriggerNpc", true, false) as OptionButton
	_assert(npc_picker != null, "and a creature picker")
	var wyrm_index := -1
	for index in range(npc_picker.item_count):
		if npc_picker.get_item_text(index) == "horned_wyrm": wyrm_index = index
	npc_picker.select(wyrm_index); npc_picker.item_selected.emit(wyrm_index)
	_assert(wyrm["on"]["npc"] == "horned_wyrm", "choosing one writes it")
	var kill_room := holder.find_child("TriggerRoom", true, false) as OptionButton
	_assert(kill_room.get_item_text(0) == "(anywhere)", "the room only narrows a kill")
	kill_room.select(0); kill_room.item_selected.emit(0)
	_assert(not wyrm["on"].has("region") and not wyrm["on"].has("room"), "and choosing 'anywhere' drops the pair together")
	holder = _open("wyrm_hall", wyrm)
	event_picker = holder.find_child("TriggerEvent", true, false) as OptionButton
	var clear_index := events.find("room_cleared")
	event_picker.select(clear_index); event_picker.item_selected.emit(clear_index)
	_assert(wyrm["on"]["event"] == "room_cleared" and not wyrm["on"].has("npc") and wyrm["on"].has("region") and wyrm["on"].has("room"),
		"a cleared-room trigger drops the creature and gets the room it needs: %s" % str(wyrm["on"]))
	holder = _open("wyrm_hall", wyrm)
	event_picker = holder.find_child("TriggerEvent", true, false) as OptionButton
	event_picker.select(0); event_picker.item_selected.emit(0)
	_assert(wyrm["on"]["event"] == "on_enter", "and back to entering")
	holder = _open("wyrm_hall", wyrm)
	event_picker = holder.find_child("TriggerEvent", true, false) as OptionButton
	var hurt_index := events.find("health_below")
	event_picker.select(hurt_index); event_picker.item_selected.emit(hurt_index)
	_assert(wyrm["on"]["event"] == "health_below" and wyrm["on"].get("who") == "player" and is_equal_approx(float(wyrm["on"].get("fraction", 0)), 0.25),
		"a health trigger starts as the player below a quarter: %s" % str(wyrm["on"]))
	holder = _open("wyrm_hall", wyrm)
	var fraction := holder.find_child("TriggerFraction", true, false) as SpinBox
	fraction.value = 0.5; fraction.value_changed.emit(0.5)
	_assert(is_equal_approx(float(wyrm["on"]["fraction"]), 0.5), "the line is a share of health, written as a number")
	var who := holder.find_child("TriggerWho", true, false) as OptionButton
	var wyrm_who := -1
	for index in range(who.item_count):
		if who.get_item_text(index) == "horned_wyrm": wyrm_who = index
	who.select(wyrm_who); who.item_selected.emit(wyrm_who)
	_assert(wyrm["on"]["who"] == "horned_wyrm", "and who is struck down can be a creature")
	holder = _open("wyrm_hall", wyrm)
	event_picker = holder.find_child("TriggerEvent", true, false) as OptionButton
	event_picker.select(0); event_picker.item_selected.emit(0)
	_assert(wyrm["on"]["event"] == "on_enter" and not wyrm["on"].has("who") and not wyrm["on"].has("fraction"), "and back to entering drops both")

	print("\n[a condition, through the shared rows]")
	holder = _open("wyrm_hall", wyrm)
	var kind_picker := holder.find_child("ConditionPicker", true, false) as OptionButton
	_assert(kind_picker != null and kind_picker.get_item_text(0) == "(always)", "the condition picker is there, worded for a trigger")
	var flag := -1
	for index in range(kind_picker.item_count):
		if kind_picker.get_item_text(index) == "flag": flag = index
	kind_picker.select(flag); kind_picker.item_selected.emit(flag)
	holder = _open("wyrm_hall", wyrm)
	RowProbe.type_into(holder.find_child("ConditionValue", true, false), "hermit_gone")
	_assert(wyrm["when"] == {"kind": "flag", "flag": "hermit_gone"}, "a flag condition is written: %s" % str(wyrm.get("when")))

	print("\n[a note and unknown keys]")
	RowProbe.type_into(holder.find_child("TriggerNote", true, false), "the wyrm wakes")
	_assert(wyrm.get("note") == "the wyrm wakes", "a note is written")
	wyrm["_editor_marker"] = "kept"
	_open("wyrm_hall", wyrm)
	_assert(wyrm.get("_editor_marker") == "kept", "a key the inspector does not model survives")
	wyrm.erase("_editor_marker")

	print("\n[a new trigger is valid before anything is typed]")
	var fresh: Dictionary = TriggerInspectorScript.data_defaults()
	_assert(fresh.has("on") and fresh["on"].has("region") and fresh["on"].has("room"), "it names a room this set has: %s" % str(fresh.get("on")))
	_assert(fresh["effects"] is Dictionary and not fresh["effects"].is_empty(), "and has an effect")
	database.add_trigger("new_trigger", fresh)

	print("\n[the room inspector lists what fires in a room]")
	var here := RoomTriggersPanelScript.triggers_in(database, "dread_tower", "tower_gate")
	_assert(here.has("tower_gate_opens") and not here.has("wyrm_slain"),
		"the triggers whose room is this one, and not others': %s" % str(here))
	var panel_holder := VBoxContainer.new(); root.add_child(panel_holder)
	RoomTriggersPanelScript.new().build(panel_holder, "dread_tower", "tower_gate", database)
	_assert(panel_holder.find_child("Trigger_tower_gate_opens", true, false) != null, "as rows")
	var empty_holder := VBoxContainer.new(); root.add_child(empty_holder)
	RoomTriggersPanelScript.new().build(empty_holder, "caves", "hermit_cave", database)
	_assert(empty_holder.find_child("Trigger_wyrm_hall", true, false) == null, "and not the rooms of others")

	print("\n[saving, and the engine's verdict]")
	var saved := database.save_all()
	_assert(saved.get("ok", false), "the edited library saves: %s" % str(saved.get("errors", [])))
	var reloaded := DatabaseManager.new()
	_assert(reloaded.triggers.has("new_trigger") and reloaded.triggers["wyrm_hall"].get("note") == "the wyrm wakes", "and reloads as it was written")
	_assert(not reloaded.triggers["wyrm_hall"].has("once"), "with the default still unwritten")
	var output: Array = []
	var python := repo.path_join(".venv/Scripts/python.exe")
	if not FileAccess.file_exists(python): python = repo.path_join(".venv/bin/python")
	var code := OS.execute(python, [repo.path_join("toolkit/content_set_validator.py"), fixture], output, true)
	_assert(code == 0, "the engine's validator accepts the edited set")
	if code != 0: print("\n".join(output).right(1800))

	if failures > 0: push_error("trigger authoring smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _open(id: String, data: Dictionary) -> VBoxContainer:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	var inspector = TriggerInspectorScript.new(holder, database)
	inspector.build(id, data)
	return holder


func _copy(source: String, destination: String) -> void:
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String) -> void:
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
