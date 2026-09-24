# tests/room_item_placement_smoke.gd
#
# Room item placements are instance recipes.  This verifies the editor exposes
# a deliberate placement surface (rather than a JSON-only escape hatch) and
# that the fields it writes are the engine's `properties_override` contract.

extends SceneTree

const SaveIO = preload("res://scripts/data/SaveIO.gd")
const ROOM_CONTENT_PANEL = preload("res://scripts/ui/inspectors/panels/RoomContentPanel.gd")

var failures := 0
var content_root := ""


func _init() -> void:
	content_root = ProjectSettings.globalize_path("res://").path_join("../tmp/room_item_placement/content_set")
	_build_fixture()
	DataRoot._resolved = content_root
	DataRoot._source = "room placement smoke"
	var database := DatabaseManager.new()
	_check_add_row_is_unresolved_until_chosen(database)
	_check_resource_placement_overrides(database)
	_check_container_placement_overrides(database)
	_check_other_item_overrides(database)
	_check_npc_placement_overrides(database)
	if failures > 0:
		push_error("room item placement smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _check_add_row_is_unresolved_until_chosen(database: DatabaseManager) -> void:
	print("\n[new room item]")
	var room := {"items": []}
	var holder := _panel_for(room, database)
	for button in _buttons(holder):
		if button.text == "+ Add Item":
			button.pressed.emit()
	_assert(room.items.size() == 1 and room.items[0] == {"item_id": "", "quantity": 1},
		"a new room placement asks for a real template instead of guessing set-specific content")


func _check_resource_placement_overrides(database: DatabaseManager) -> void:
	print("\n[resource placement]")
	var placement := {"item_id": "item_node", "quantity": 2}
	var holder := _panel_for({"items": [placement]}, database)
	var names := _named(holder, "PlacementName")
	_assert(names.size() == 1, "a placement can override its displayed name")
	if not names.is_empty():
		names[0].text_changed.emit("Depleted north vein")
	_assert(placement.get("properties_override", {}).get("name") == "Depleted north vein",
		"the display name is stored on the placement, not the template")
	var charges := _named(holder, "PlacementCharges")
	_assert(charges.size() == 1, "resource placements expose their local charges")
	if not charges.is_empty():
		charges[0].value_changed.emit(1)
	_assert(placement.get("properties_override", {}).get("charges") == 1,
		"a room can place a partly depleted resource node")


func _check_container_placement_overrides(database: DatabaseManager) -> void:
	print("\n[container placement]")
	var placement := {"item_id": "item_chest"}
	var holder := _panel_for({"items": [placement]}, database)
	var state := _named(holder, "ContainerPlacementState")
	_assert(state.size() == 1, "container placements expose local open and locked state")
	if not state.is_empty():
		var boxes := _check_boxes(state[0])
		if boxes.size() >= 2:
			boxes[0].toggled.emit(true)
			boxes[1].toggled.emit(true)
	_assert(placement.get("properties_override", {}).get("is_open") == true and placement.get("properties_override", {}).get("locked") == true,
		"container state changes are captured as placement overrides")


func _check_other_item_overrides(database: DatabaseManager) -> void:
	print("
[other item overrides]")
	var placement := {"item_id": "item_ore", "properties_override": {"glint": false, "legacy_tag": [1, 2]}}
	var holder := _panel_for({"items": [placement]}, database)
	var glint := _named(holder, "ItemOverride_glint")
	_assert(glint.size() == 1 and _check_boxes(glint[0]).size() == 1 and not _check_boxes(glint[0])[0].button_pressed,
		"a boolean override the form does not cover is shown as a checkbox with its value")
	_assert(_named(holder, "ItemOverride_legacy_tag").size() == 1, "an array override is listed, not dropped")
	var picker: Array = _named(holder, "AddItemOverride")
	var offered: Array = []
	if not picker.is_empty():
		for index in range(1, picker[0].item_count): offered.append(str(picker[0].get_item_metadata(index)))
	_assert(offered == ["grade", "vein_note"], "only the template's other scalar properties can be added (got %s)" % str(offered))
	if not picker.is_empty():
		picker[0].select(1); picker[0].item_selected.emit(1)
	_assert(placement["properties_override"].get("grade") == 2, "adding one starts from the template's value")
	holder = _panel_for({"items": [placement]}, database)
	var grade := _named(holder, "ItemOverride_grade")
	if not grade.is_empty(): (grade[0].find_child("Value", true, false) as SpinBox).value_changed.emit(4.0)
	_assert(placement["properties_override"].get("grade") == 4 and placement["properties_override"]["grade"] is int, "a whole-number property stays a whole number")
	var legacy := _named(holder, "ItemOverride_legacy_tag")
	if not legacy.is_empty():
		for button in _buttons(legacy[0]):
			if button.text == "×": button.pressed.emit()
	_assert(not placement["properties_override"].has("legacy_tag") and placement["properties_override"].has("glint"), "an override can be removed, leaving the others")


func _check_npc_placement_overrides(database: DatabaseManager) -> void:
	print("\n[npc placement]")
	var placement := {"template_id": "npc_guide"}
	var holder := _panel_for({"initial_npcs": [placement]}, database)
	var names := _named(holder, "NPCPlacementName")
	_assert(names.size() == 1, "an NPC placement exposes a local display name")
	if not names.is_empty(): names[0].text_changed.emit("Wounded guide")
	_assert(placement.get("overrides", {}).get("name") == "Wounded guide",
		"the NPC name is stored on its placement, not the template")
	var behaviour := _named(holder, "NPCPlacementBehaviour")
	_assert(behaviour.size() == 1, "an NPC placement uses the engine behaviour vocabulary")
	if not behaviour.is_empty():
		behaviour[0].item_selected.emit(3) # aggressive
	_assert(placement.get("overrides", {}).get("behavior_type") == "aggressive",
		"the selected behaviour writes the runtime placement key")


func _panel_for(room: Dictionary, database: DatabaseManager) -> VBoxContainer:
	var holder := VBoxContainer.new()
	var panel := ROOM_CONTENT_PANEL.new()
	panel.build(holder, room, database)
	return holder


func _buttons(node: Node) -> Array:
	var found: Array = []
	if node is Button: found.append(node)
	for child in node.get_children(): found.append_array(_buttons(child))
	return found


func _check_boxes(node: Node) -> Array:
	var found: Array = []
	if node is CheckBox: found.append(node)
	for child in node.get_children(): found.append_array(_check_boxes(child))
	return found


func _named(node: Node, wanted: String) -> Array:
	var found: Array = []
	if node.name == wanted: found.append(node)
	for child in node.get_children(): found.append_array(_named(child, wanted))
	return found


func _build_fixture() -> void:
	_remove_recursive(content_root)
	var data_root := content_root.path_join("data")
	for directory in ["items", "npcs", "regions", "contracts"]:
		DirAccess.make_dir_recursive_absolute(data_root.path_join(directory))
	DirAccess.make_dir_recursive_absolute(content_root.path_join("rules"))
	DirAccess.make_dir_recursive_absolute(content_root.path_join("presentation"))
	SaveIO.write_json(content_root.path_join("content_set.manifest.json"), {
		"id": "room_item_fixture", "title": "Room Item Fixture", "version": "0.1.0", "manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
		"paths": {"content_root": "data", "ruleset": "rules/ruleset.json", "presentation": "presentation/default.json"},
		"start": {"scenario_id": "fixture", "region_id": "fixture", "room_id": "start"}, "capabilities": ["inventory"],
	})
	SaveIO.write_json(content_root.path_join("rules/ruleset.json"), {})
	SaveIO.write_json(content_root.path_join("presentation/default.json"), {})
	SaveIO.write_json(data_root.path_join("regions/fixture.json"), {"region_id": "fixture", "rooms": {"start": {"name": "Start"}}})
	SaveIO.write_json(data_root.path_join("items/items.json"), {
		"item_ore": {"name": "Ore", "type": "Item", "properties": {"glint": true, "grade": 2, "vein_note": "north", "assay": [1, 2]}},
		"item_node": {"name": "Ore vein", "type": "ResourceNode", "properties": {"resource_item_id": "item_ore", "charges": 3, "respawn_days": 2}},
		"item_chest": {"name": "Chest", "type": "Container", "properties": {"is_open": false, "locked": false}},
	})
	SaveIO.write_json(data_root.path_join("npcs/npcs.json"), {
		"npc_guide": {"name": "Guide", "description": "A guide.", "level": 1, "behavior_type": "stationary"},
	})


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null: return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		var child := path.path_join(name)
		if dir.current_is_dir(): _remove_recursive(child)
		else: DirAccess.remove_absolute(child)
		name = dir.get_next()
	dir.list_dir_end()
	DirAccess.remove_absolute(path)


func _assert(condition: bool, message: String) -> void:
	if condition: print("  ok   ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)
