# tests/room_environment_authoring_smoke.gd
# A room can now author atmosphere and a declared hazard without falling back to
# opaque property tags.  This smoke pins both the shape and the no-write-on-open
# rule for a room that has no environment data yet.

extends SceneTree

const SaveIO = preload("res://scripts/data/SaveIO.gd")
const PANEL = preload("res://scripts/ui/inspectors/panels/RoomEnvironmentPanel.gd")

var failures := 0
var content_root := ""


func _init() -> void:
	content_root = ProjectSettings.globalize_path("res://").path_join("../tmp/room_environment/content_set")
	_build_fixture()
	DataRoot._resolved = content_root
	DataRoot._source = "room environment smoke"
	var database := DatabaseManager.new()
	var room := {"properties": {}}
	var holder := VBoxContainer.new()
	var panel := PANEL.new()
	panel.build(holder, room, database)
	_assert(not room.has("env_properties"), "opening the panel does not invent environment data")
	_check_atmosphere(holder, room)
	_check_time_descriptions(holder, room)
	_check_hazard(holder, room)
	if failures > 0: push_error("room environment authoring smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _check_atmosphere(holder: Node, room: Dictionary) -> void:
	print("\n[atmosphere]")
	var dark: CheckBox = _first_named(holder, "EnvironmentDark")
	_assert(dark != null, "the panel presents room darkness as a controlled value")
	if dark != null: dark.toggled.emit(true)
	_assert(room.get("env_properties", {}).get("dark") == true, "atmosphere writes to env_properties, not generic room tags")
	var temperature: OptionButton = _first_named(holder, "EnvironmentTemperature")
	_assert(temperature != null, "the panel exposes the room temperature vocabulary")
	if temperature != null: temperature.item_selected.emit(2) # hot
	_assert(room.get("env_properties", {}).get("temperature") == "hot", "temperature uses the engine's authored value")


func _check_hazard(holder: Node, room: Dictionary) -> void:
	print("\n[hazards]")
	var picker: OptionButton = _first_named(holder, "HazardPicker")
	_assert(picker != null and picker.item_count == 2, "the picker lists hazards declared by this content set")
	if picker != null: picker.item_selected.emit(1)
	_assert(room.get("properties", {}).get("hazard_type") == "hull_frost", "selecting a hazard writes its declared id")
	var damage: SpinBox = _first_named(holder, "HazardDamage")
	_assert(damage != null and damage.editable, "hazard overrides enable only after a hazard is selected")
	if damage != null: damage.value_changed.emit(4.0)
	_assert(room.get("properties", {}).get("hazard_damage") == 4.0, "room damage is written as an optional per-room override")
	var add_weather: Button = _button_named(holder, "+ Weather")
	_assert(add_weather != null and not add_weather.disabled, "weather multipliers are available for a selected hazard")
	if add_weather != null: add_weather.pressed.emit()
	_assert(room.get("properties", {}).get("weather_hazard_multipliers", {}).get("weather") == 1.0, "a weather multiplier uses the validated object shape")
	if picker != null: picker.item_selected.emit(0)
	_assert(not room.get("properties", {}).has("hazard_type") and not room.get("properties", {}).has("weather_hazard_multipliers"), "clearing a hazard clears its dependent overrides")


func _check_time_descriptions(holder: Node, room: Dictionary) -> void:
	print("\n[time descriptions]")
	var day: TextEdit = _first_named(holder, "TimeDescriptionDay")
	_assert(day != null, "the panel exposes the engine's day-period description fields")
	if day != null: day.text_changed.emit()
	# Assign through the control to cover its actual change handler.
	if day != null:
		day.text = "The market wakes early."
		day.text_changed.emit()
	_assert(room.get("time_descriptions", {}).get("day") == "The market wakes early.", "a day description stays separate from generic room properties")


func _first_named(node: Node, wanted: String):
	if node.name == wanted: return node
	for child in node.get_children():
		var found = _first_named(child, wanted)
		if found != null: return found
	return null


func _button_named(node: Node, label: String):
	if node is Button and node.text == label: return node
	for child in node.get_children():
		var found = _button_named(child, label)
		if found != null: return found
	return null


func _build_fixture() -> void:
	_remove_recursive(content_root)
	var data := content_root.path_join("data")
	for directory in ["items", "npcs", "regions", "combat"]: DirAccess.make_dir_recursive_absolute(data.path_join(directory))
	DirAccess.make_dir_recursive_absolute(content_root.path_join("rules")); DirAccess.make_dir_recursive_absolute(content_root.path_join("presentation"))
	SaveIO.write_json(content_root.path_join("content_set.manifest.json"), {
		"id": "environment_fixture", "title": "Environment Fixture", "version": "0.1.0", "manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
		"paths": {"content_root": "data", "ruleset": "rules/ruleset.json", "presentation": "presentation/default.json"},
		"start": {"scenario_id": "fixture", "region_id": "fixture", "room_id": "start"}, "capabilities": ["combat"],
	})
	SaveIO.write_json(content_root.path_join("rules/ruleset.json"), {})
	SaveIO.write_json(content_root.path_join("presentation/default.json"), {})
	SaveIO.write_json(data.path_join("regions/fixture.json"), {"region_id": "fixture", "rooms": {"start": {"name": "Start"}}})
	SaveIO.write_json(data.path_join("combat/elements.json"), {
		"valid_damage_types": ["frost"], "hazards": {"hull_frost": {"channel": "frost", "flavor": "The hull freezes.", "damage": 2, "tick_interval": 5}},
	})


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null: return
	dir.list_dir_begin(); var name := dir.get_next()
	while name != "":
		var child := path.path_join(name)
		if dir.current_is_dir(): _remove_recursive(child)
		else: DirAccess.remove_absolute(child)
		name = dir.get_next()
	dir.list_dir_end(); DirAccess.remove_absolute(path)


func _assert(condition: bool, message: String) -> void:
	if condition: print("  ok   ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)
