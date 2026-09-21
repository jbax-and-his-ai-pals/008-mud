# tests/nested_property_survival_smoke.gd
#
# Track G item 3: a property whose value is an object or an array must survive a
# trip through the inspector. Run with:
#
#   godot --headless --path mud-world-editor --script tests/nested_property_survival_smoke.gd
#
# The defect this exists for
# -------------------------
# Every inspector property row was a `LineEdit` holding `str(val)`. For a scalar
# that is faithful. For a Dictionary it is GDScript's debug form -- not JSON, not
# parseable -- and the submit handler wrote that string back over the object. So
# opening a room and editing *any* row in the panel could destroy a nested value
# the engine reads:
#
#   * `properties.hidden_exits` on obsidian_trial's hall_of_gates: a real
#     traversable link read by effects.py and interactive.py
#   * `properties.weather_hazard_multipliers` on three rooms: an object the
#     content validator requires to be an object
#   * `properties.exit_requirements` on town:jail_cell and depot:holding_room
#
# Three panels carried the shape -- RoomPropertiesPanel, RegionInspector,
# MultiRoomInspector -- and only RegionInspector had the guard, which is why the
# rule now lives in one place (`PropertyTagRow`) instead of in each panel.
#
# Every case here writes to a throwaway content set under `tmp/`.

extends SceneTree

var failure_count := 0
var content_set_root: String = ""
var data_root: String = ""

const NESTED_HIDDEN := {"north": "inner_sanctum"}
const NESTED_WEATHER := {"sandstorm": 0.5, "rain": 1.25}
const NESTED_REQUIREMENTS := ["item_brass_key", "flag:met_the_warden"]


func _init() -> void:
	content_set_root = ProjectSettings.globalize_path("res://").path_join("../tmp/nested_property/content_set")
	data_root = content_set_root.path_join("data")
	_rebuild_fixture()
	DataRoot._resolved = content_set_root
	DataRoot._source = "test fixture"
	print("scratch content set: ", DataRoot.describe())

	_check_the_rule_itself()
	_check_the_room_panel_leaves_nested_values_alone()
	_check_the_room_panel_still_edits_scalars()
	_check_integers_stay_integers()
	_check_multi_room_panel_leaves_nested_values_alone()
	_check_item_panel_leaves_nested_values_alone()

	if failure_count > 0:
		push_error("nested property survival failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- the rule -----------------------------------------------------------------

func _check_the_rule_itself() -> void:
	print("\n[the shared rule]")
	_assert(PropertyTagRow.is_inline_editable(1), "an int is editable inline")
	_assert(PropertyTagRow.is_inline_editable(1.5), "a float is editable inline")
	_assert(PropertyTagRow.is_inline_editable("damp earth"), "a string is editable inline")
	_assert(PropertyTagRow.is_inline_editable(true), "a bool is editable inline")
	_assert(not PropertyTagRow.is_inline_editable(NESTED_HIDDEN), "an object is not")
	_assert(not PropertyTagRow.is_inline_editable(NESTED_REQUIREMENTS), "an array is not")

	var props := {"dark": true, "hidden_exits": NESTED_HIDDEN, "level_min": 2}
	_assert(PropertyTagRow.editable_keys(props) == ["dark", "level_min"],
		"editable_keys returns the scalars in order: %s" % str(PropertyTagRow.editable_keys(props)))
	_assert(PropertyTagRow.nested_keys(props) == ["hidden_exits"], "and only the structured ones")


# --- the room panel -----------------------------------------------------------

func _check_the_room_panel_leaves_nested_values_alone() -> void:
	print("\n[a room whose properties are structured]")
	var rooms := _load_rooms()
	var props: Dictionary = rooms["hall_of_gates"]["properties"]

	_assert(props.has("hidden_exits"), "the fixture room starts with hidden_exits")
	var before := JSON.stringify(props["hidden_exits"])

	# Build the real panel over the real dictionary, exactly as the inspector does.
	var holder := VBoxContainer.new()
	root.add_child(holder)
	var panel := RoomPropertiesPanel.new()
	panel.build(holder, props)

	# The panel must not have offered an editable row for the object...
	var nested_editors := _count_editable_fields(holder, "hidden_exits")
	_assert(nested_editors == 0,
		"no editable field is built for a structured property (found %d)" % nested_editors)

	# ...and the value must be untouched after the panel has been through it, and
	# after a save and reload, which is where the damage used to become permanent.
	_assert(JSON.stringify(props["hidden_exits"]) == before, "hidden_exits is unchanged in memory")
	_save_rooms(rooms)
	var after := JSON.stringify(_load_rooms()["hall_of_gates"]["properties"]["hidden_exits"])
	_assert(after == before, "and unchanged on disk after a save (%s vs %s)" % [after, before])

	# The other structured shapes, for the same reason.
	var weather: Dictionary = _load_rooms()["salt_flat"]["properties"]
	_assert(JSON.stringify(weather["weather_hazard_multipliers"]) == JSON.stringify(NESTED_WEATHER),
		"a weather multiplier object survives")
	var requirements: Dictionary = _load_rooms()["jail_cell"]["properties"]
	_assert(JSON.stringify(requirements["exit_requirements"]) == JSON.stringify(NESTED_REQUIREMENTS),
		"an exit requirement array survives")
	holder.queue_free()


func _check_the_room_panel_still_edits_scalars() -> void:
	print("\n[a scalar in the same room]")
	var rooms := _load_rooms()
	var props: Dictionary = rooms["hall_of_gates"]["properties"]
	_assert(props.has("dark"), "the fixture room has a scalar property")

	var holder := VBoxContainer.new()
	root.add_child(holder)
	var panel := RoomPropertiesPanel.new()
	panel.build(holder, props)

	# Drive the scalar the way a submit does, then confirm both the edit and the
	# survival of the nested value beside it.
	props["dark"] = false
	_save_rooms(rooms)
	var reloaded: Dictionary = _load_rooms()["hall_of_gates"]["properties"]
	_assert(reloaded["dark"] == false, "the scalar edit landed")
	_assert(JSON.stringify(reloaded["hidden_exits"]) == JSON.stringify(NESTED_HIDDEN),
		"and the structured property beside it is still an object, not a string")
	holder.queue_free()


func _check_integers_stay_integers() -> void:
	print("\n[an integer property]")
	# The number gate exists because this project has already lost a build to a
	# writer that emitted every integer as a float. The row builder must not
	# reintroduce it: submitting "3" into an int field keeps an int.
	var holder := VBoxContainer.new()
	root.add_child(holder)
	var props := {"level_min": 2}
	var panel := RoomPropertiesPanel.new()
	panel.build(holder, props)

	var edit := _first_editable_field(holder)
	_assert(edit != null, "the integer property has an editable field")
	if edit != null:
		edit.text = "7"
		edit.text_submitted.emit("7")
		_assert(typeof(props["level_min"]) == TYPE_INT,
			"an int field stays an int after an edit (got %s)" % type_string(typeof(props["level_min"])))
		_assert(int(props["level_min"]) == 7, "and takes the new value")
	holder.queue_free()


func _check_multi_room_panel_leaves_nested_values_alone() -> void:
	print("\n[two rooms selected at once]")
	# The third panel with this shape: a multi-room edit writes one value into every
	# selected room, so a stringified object would be copied into all of them.
	#
	# Asserted on the panel's own analysis function rather than by building the
	# panel: `build()` needs an ActionHandler wired to a live main controller, and
	# the decision being tested -- which keys may be edited inline -- is exactly
	# what that function returns.
	var rooms := _load_rooms()
	var shared := {
		"dark": true,
		"hidden_exits": NESTED_HIDDEN,
	}
	rooms["multi_a"] = {"name": "Multi A", "properties": shared.duplicate(true), "exits": {}}
	rooms["multi_b"] = {"name": "Multi B", "properties": shared.duplicate(true), "exits": {}}
	_save_rooms(rooms)

	var holder := VBoxContainer.new()
	root.add_child(holder)
	var region_mgr := RegionManager.new()
	region_mgr.data = {"rooms": _load_rooms()}
	var inspector := MultiRoomInspector.new(holder, region_mgr, null)
	inspector.selected_ids = ["multi_a", "multi_b"]
	var analysis := inspector._analyze_selected()

	_assert(analysis["editable"] == ["dark"],
		"only the scalar is editable across both rooms: %s" % str(analysis["editable"]))
	_assert(analysis["nested"] == ["hidden_exits"],
		"the object is classified as nested: %s" % str(analysis["nested"]))
	_assert(int(analysis["counts"].get("hidden_exits", 0)) == 2,
		"and it is still counted, so the panel can report it exists on both")

	var after := _load_rooms()
	for room_id in ["multi_a", "multi_b"]:
		_assert(JSON.stringify(after[room_id]["properties"]["hidden_exits"]) == JSON.stringify(NESTED_HIDDEN),
			"%s kept its object" % room_id)
	holder.queue_free()


func _check_item_panel_leaves_nested_values_alone() -> void:
	print("\n[an item whose properties are structured]")
	# The item inspector used to be the last panel with its own LineEdit loop.
	# `resistances` has no special item widget, so it proves the generic fallback
	# preserves arbitrary engine-facing structured data rather than stringifying it.
	var item := {
		"id": "probe_relic", "name": "Probe Relic", "description": "For testing.",
		"type": "Item",
		"properties": {
			"resistances": {"fire": 0.25, "frost": 0.5},
			"substitute_resource_ids": ["item_scrap", "item_ore"],
			"level_min": 2,
		},
	}
	var before_resistances := JSON.stringify(item["properties"]["resistances"])
	var before_substitutes := JSON.stringify(item["properties"]["substitute_resource_ids"])
	var holder := VBoxContainer.new()
	root.add_child(holder)
	var inspector := ItemInspector.new()
	inspector.build(holder, item)

	_assert(JSON.stringify(item["properties"]["resistances"]) == before_resistances,
		"item resistance object is unchanged after building the inspector")
	_assert(JSON.stringify(item["properties"]["substitute_resource_ids"]) == before_substitutes,
		"item substitute array is unchanged after building the inspector")
	_assert(_count_editable_fields(holder, "resistances") == 0,
		"the item inspector does not offer an editable structured resistance row")
	_assert(_count_editable_fields(holder, "substitute_resource_ids") == 0,
		"the item inspector does not offer an editable structured array row")
	holder.queue_free()


# --- helpers ------------------------------------------------------------------

func _load_rooms() -> Dictionary:
	var payload = JSON.parse_string(FileAccess.get_file_as_string(data_root.path_join("regions/probe.json")))
	_assert(typeof(payload) == TYPE_DICTIONARY, "the fixture region is valid JSON")
	return payload.get("rooms", {})


func _save_rooms(rooms: Dictionary) -> void:
	var payload = JSON.parse_string(FileAccess.get_file_as_string(data_root.path_join("regions/probe.json")))
	payload["rooms"] = rooms
	var file := FileAccess.open(data_root.path_join("regions/probe.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(payload, "  "))
	file.close()


## How many editable text fields the built panel made whose row is `key`.
func _count_editable_fields(node: Node, key: String) -> int:
	var found := 0
	for edit in _editable_fields(node):
		if _row_label_text(edit).begins_with(key + ":"):
			found += 1
	return found


func _first_editable_field(node: Node) -> LineEdit:
	var fields := _editable_fields(node)
	return fields[0] if not fields.is_empty() else null


func _editable_fields(node: Node) -> Array:
	var out: Array = []
	if node is LineEdit and node.editable:
		out.append(node)
	for child in node.get_children():
		out.append_array(_editable_fields(child))
	return out


## The label text of the row a field sits in, so a field can be attributed to a key.
func _row_label_text(edit: LineEdit) -> String:
	var parent := edit.get_parent()
	if parent == null:
		return ""
	for sibling in parent.get_children():
		if sibling is Label:
			return str(sibling.text)
	return ""


func _rebuild_fixture() -> void:
	var scratch := ProjectSettings.globalize_path("res://").path_join("../tmp/nested_property")
	_remove_recursive(scratch)
	DirAccess.make_dir_recursive_absolute(data_root.path_join("regions"))

	var file := FileAccess.open(data_root.path_join("regions/probe.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify({
		"region_id": "probe",
		"name": "Probe",
		"rooms": {
			"hall_of_gates": {
				"name": "Hall of Gates",
				"exits": {"south": "entry"},
				"properties": {"dark": true, "hidden_exits": NESTED_HIDDEN},
			},
			"entry": {"name": "Entry", "exits": {"north": "hall_of_gates"}, "properties": {}},
			"salt_flat": {
				"name": "Salt Flat",
				"exits": {},
				"properties": {"weather_hazard_multipliers": NESTED_WEATHER},
			},
			"jail_cell": {
				"name": "Jail Cell",
				"exits": {},
				"properties": {"exit_requirements": NESTED_REQUIREMENTS},
			},
		},
	}, "  "))
	file.close()


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		var full := path.path_join(name)
		if dir.current_is_dir():
			_remove_recursive(full)
		else:
			DirAccess.remove_absolute(full)
		name = dir.get_next()
	dir.list_dir_end()


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		printerr("  FAIL ", message)
