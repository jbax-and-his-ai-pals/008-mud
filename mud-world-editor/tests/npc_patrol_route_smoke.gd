# tests/npc_patrol_route_smoke.gd
#
# A placed NPC's patrol route (`initial_npcs[].overrides.patrol_points` and
# `patrol_index`) was preserved but not editable. RoomContentPanel now edits it:
# points picked from the region's rooms, reordered, a starting point, and a way
# back to the template's route. Its `properties_override` (behaviour tuning merged
# over the template's properties) is edited by the same card. Driven through the
# real editor scene on a copy of
# fantasy_frontier, so region saves go through the engine's verdict
# (content_set.py::_validate_patrol_routes, _npc_property_errors).
#
#   godot --headless --path mud-world-editor --script tests/npc_patrol_route_smoke.gd

extends SceneTree

var failures := 0
var fixture := ""
var main: Node2D = null
var checks_run := false
var panels: Array = []


func _initialize() -> void:
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/patrol-route-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "test fixture"
	main = load("res://scenes/Main.tscn").instantiate()
	root.add_child(main)


func _process(_delta: float) -> bool:
	# False keeps the loop running: `_run` awaits frames, and quits itself.
	if checks_run: return false
	checks_run = true
	_run.call_deferred()
	return false


func _run() -> void:
	var path := fixture.path_join("data/regions/town.json")
	_assert(main.region_mgr.current_filename == "town.json", "the editor opened the town")
	var square: Dictionary = main.region_mgr.data.rooms["town_square"]
	var guard: Dictionary = square["initial_npcs"][3]

	print("\n[a placement's own route]")
	var before := JSON.stringify(square)
	var holder := _panel(square)
	_assert(JSON.stringify(square) == before, "building the panel writes nothing")
	var card: Node = holder.find_child("NPCPlacement_3", true, false)
	_assert(_route_rooms(card) == ["town_square", "riverside_docks", "museum_exterior"], "the guard's route is shown point by point")
	_assert(holder.find_child("NPCPlacement_4", true, false).find_child("PatrolRoute", true, false) == null, "a stationary NPC shows no route")

	_press(card.find_child("PatrolPoint_2", true, false), "^")
	await process_frame
	card = holder.find_child("NPCPlacement_3", true, false)
	_assert(guard["overrides"]["patrol_points"] == ["town_square", "museum_exterior", "riverside_docks"], "points can be reordered")
	(card.find_child("AddPatrolPoint", true, false) as Button).pressed.emit()
	await process_frame
	card = holder.find_child("NPCPlacement_3", true, false)
	_pick(card.find_child("PatrolPoint_3", true, false).find_child("Room", true, false), "west_lane")
	_assert(guard["overrides"]["patrol_points"] == ["town_square", "museum_exterior", "riverside_docks", "west_lane"], "a point can be added and picked from the region's rooms")
	(card.find_child("PatrolStart", true, false) as SpinBox).value = 4
	_assert(guard["overrides"]["patrol_index"] == 3, "the starting point is written as patrol_index")
	_press(card.find_child("PatrolPoint_3", true, false), "×")
	await process_frame
	_assert(guard["overrides"]["patrol_points"].size() == 3 and not guard["overrides"].has("patrol_index"), "removing the point it started at clears the start (a start past the end raises)")

	main.region_mgr.mark_room_dirty("town_square")
	_assert(main._save_everything(), "the edited route saves: the engine can walk it")
	var saved: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	_assert(saved["rooms"]["town_square"]["initial_npcs"][3]["overrides"]["patrol_points"] == ["town_square", "museum_exterior", "riverside_docks"], "and it is on disk")

	print("\n[template route and behaviour]")
	holder = _panel(square)
	card = holder.find_child("NPCPlacement_3", true, false)
	(card.find_child("UseTemplateRoute", true, false) as Button).pressed.emit()
	await process_frame
	_assert(not guard.has("overrides"), "Use template route removes the placement's route (and the now-empty overrides)")
	card = holder.find_child("NPCPlacement_3", true, false)
	_assert("west_lane" in _text(card.find_child("PatrolRoute", true, false)), "and the template's route is shown instead")

	var captain: Dictionary = square["initial_npcs"][4]
	_pick(holder.find_child("NPCPlacement_4", true, false).find_child("NPCPlacementBehaviour", true, false), "patrol")
	await process_frame
	card = holder.find_child("NPCPlacement_4", true, false)
	_assert(card.find_child("PatrolRoute", true, false) != null and "stands still" in _text(card.find_child("PatrolRoute", true, false)), "switching to Patrol shows the route, and that the template has none")
	(card.find_child("SetPatrolRoute", true, false) as Button).pressed.emit()
	await process_frame
	_assert(captain["overrides"]["patrol_points"] == ["town_square"], "setting a route starts it at the NPC's own room")

	print("\n[placement behaviour tuning]")
	holder = _panel(square)
	var tuning: Node = holder.find_child("NPCPlacement_3", true, false).find_child("Tuning_aggression", true, false)
	_assert(not (tuning.find_child("Override", true, false) as CheckBox).button_pressed and not (tuning.find_child("Value", true, false) as SpinBox).editable, "an untouched value inherits the template (nothing written)")
	(tuning.find_child("Override", true, false) as CheckBox).button_pressed = true
	(tuning.find_child("Value", true, false) as SpinBox).value = 0.5
	_assert(is_equal_approx(float(guard["overrides"]["properties_override"]["aggression"]), 0.5), "ticking Override writes the value into properties_override")
	var respawn: Node = holder.find_child("NPCPlacement_3", true, false).find_child("Tuning_respawn_cooldown", true, false)
	(respawn.find_child("Override", true, false) as CheckBox).button_pressed = true
	(respawn.find_child("Value", true, false) as SpinBox).value = -1
	_assert(guard["overrides"]["properties_override"]["respawn_cooldown"] == -1 and guard["overrides"]["properties_override"]["respawn_cooldown"] is int, "whole-number values are written as integers (-1 = never respawns)")
	(respawn.find_child("Override", true, false) as CheckBox).button_pressed = false
	_assert(not guard["overrides"]["properties_override"].has("respawn_cooldown"), "unticking removes the override")
	guard["overrides"]["properties_override"]["vendor_note"] = "kept"
	holder = _panel(square)
	var other: Node = holder.find_child("NPCPlacement_3", true, false).find_child("OtherProperty_vendor_note", true, false)
	_assert(other != null, "a property override the form does not edit is listed")
	_press(other, "×")
	_assert(guard["overrides"]["properties_override"].keys() == ["aggression"], "and can be removed, leaving the rest")
	main.region_mgr.mark_room_dirty("town_square")
	_assert(main._save_everything(), "the tuned placement saves")
	guard["overrides"]["properties_override"]["aggression"] = 5
	main.region_mgr.mark_room_dirty("town_square")
	_assert(not main._save_everything() and "properties_override.aggression must be a number from 0 to 1" in _error_text(), "a value out of range in properties_override is refused, like the template's")
	main.ui_mgr.error_modal.hide()
	guard["overrides"]["properties_override"]["aggression"] = 0.5

	print("\n[what the engine refuses]")
	card = holder.find_child("NPCPlacement_4", true, false)
	_pick(card.find_child("NPCPlacementBehaviour", true, false), "stationary")
	await process_frame
	card = holder.find_child("NPCPlacement_4", true, false)
	_assert("route is ignored" in _text(card.find_child("PatrolRoute", true, false)), "a route on a non-patrol NPC stays visible, marked as ignored")
	var on_disk := FileAccess.get_file_as_string(path)
	main.region_mgr.mark_room_dirty("town_square")
	var accepted: bool = main._save_everything()
	_assert(not accepted and FileAccess.get_file_as_string(path) == on_disk, "the engine refuses that route and the region file is put back")
	_assert(main.ui_mgr.error_modal.visible and "walked only by a 'patrol' NPC" in _error_text(), "and the refusal says why")

	if failures > 0: push_error("npc patrol route failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _panel(room: Dictionary) -> Node:
	var holder := VBoxContainer.new(); root.add_child(holder)
	var panel := RoomContentPanel.new(); panels.append(panel)
	panel.build(holder, room, main.database_mgr, "town_square", main.region_mgr)
	return holder


func _route_rooms(card: Node) -> Array:
	var out: Array = []
	var index := 0
	while card.find_child("PatrolPoint_%d" % index, true, false) != null:
		var picker: OptionButton = card.find_child("PatrolPoint_%d" % index, true, false).find_child("Room", true, false)
		out.append(str(picker.get_item_metadata(picker.selected)))
		index += 1
	return out


func _pick(picker: OptionButton, value: String):
	for index in range(picker.item_count):
		if str(picker.get_item_metadata(index)) == value:
			picker.select(index); picker.item_selected.emit(index); return
	_assert(false, "picker offers '%s'" % value)


func _press(node: Node, text: String):
	for child in node.get_children():
		if child is Button and str(child.text) == text:
			child.pressed.emit(); return
	_assert(false, "button '%s' exists" % text)


func _text(node: Node) -> String:
	if node == null: return ""
	var out := ""
	if node is Label: out += str(node.text) + "\n"
	for child in node.get_children(): out += _text(child)
	return out


func _error_text() -> String:
	var text := ""
	for node in _labels(main.ui_mgr.error_modal):
		text += str(node.dialog_text if node is AcceptDialog else node.text) + "\n"
	return text


func _labels(node: Node) -> Array:
	var out: Array = []
	if node is Label or node is RichTextLabel or node is AcceptDialog: out.append(node)
	for child in node.get_children(): out.append_array(_labels(child))
	return out


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
