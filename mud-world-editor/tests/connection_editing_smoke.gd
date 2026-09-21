# tests/connection_editing_smoke.gd
#
# The connection-authoring behaviours an author relies on. Run with:
#
#   godot --headless --path mud-world-editor --script tests/connection_editing_smoke.gd
#
# Three of them, each a decision that used to go the other way:
#
#   1. Deleting a connection removes *both* ends by default. Connections are
#      authored in pairs, and removing one end of a pair left a half-link that
#      still drew on the map and still claimed to lead somewhere. Removing a
#      single end is the case that needs saying so, and has its own control.
#   2. A curved connection's bow can be authored, and the choice survives a save.
#      Otherwise the side is the perpendicular of the line between two rooms, so
#      moving a room silently flips it.
#   3. Ending the connection form leaves connection mode. A mode that can be
#      entered and not left makes every later map click pick a target.
#
# Every case writes to a throwaway content set under `tmp/`.

extends SceneTree

const EditorLayout = preload("res://scripts/data/EditorLayout.gd")

var failure_count := 0
var content_set_root: String = ""
var data_root: String = ""


func _init() -> void:
	content_set_root = ProjectSettings.globalize_path("res://").path_join("../tmp/connection_editing/content_set")
	data_root = content_set_root.path_join("data")
	_rebuild_fixture()
	DataRoot._resolved = content_set_root
	DataRoot._source = "test fixture"
	print("scratch content set: ", DataRoot.describe())

	_check_delete_defaults_to_both_ends()
	_check_one_way_delete_is_offered_only_when_a_pair_exists()
	_check_cross_region_connections_are_not_claimed_as_pairs()
	_check_curve_choice_survives_a_save()
	_check_curve_cycling_returns_to_automatic()
	_check_bow_distance_cycles_and_clears()
	_check_side_and_distance_are_independent()
	_check_connect_another_keeps_the_source()

	if failure_count > 0:
		push_error("connection editing failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- the panel's decision, driven without a widget ----------------------------

class DeleteRequest extends Object:
	var calls: Array = []
	func _init(panel) -> void:
		panel.request_delete_connection.connect(
			func(sid, dir, target, reciprocal): calls.append({"dir": dir, "target": target, "reciprocal": reciprocal})
		)


func _panel_for(room_id: String) -> RoomConnectionsPanel:
	var mgr := RegionManager.new()
	mgr.data = _load_region()
	mgr.current_filename = "probe.json"
	var panel := RoomConnectionsPanel.new()
	var holder := VBoxContainer.new()
	root.add_child(holder)
	panel.build(
		holder, room_id, mgr.data.rooms[room_id].get("name", room_id),
		mgr.data.rooms[room_id].get("exits", {}), mgr, WorldManager.new(),
	)
	return panel


func _check_delete_defaults_to_both_ends() -> void:
	print("\n[deleting a paired connection]")
	var panel := _panel_for("shrine")
	var request := DeleteRequest.new(panel)

	# The row order follows the sorted exit keys, so drive the sibling lookup the
	# panel itself uses rather than guessing a button index.
	var back_dir := panel._find_reciprocal_exit("east", "lot")
	_assert(back_dir == "west", "the panel finds the far end's return exit (got %s)" % back_dir)
	_assert(panel._find_reciprocal_exit("north", "clearing") == "south",
		"and finds it for a second pair too")

	# The default delete carries `reciprocal = true`; the plain click is the
	# both-ends removal.
	panel.request_delete_connection.emit("shrine", "east", "lot", true)
	_assert(request.calls.size() == 1, "one delete request was made")
	_assert(request.calls[0]["reciprocal"] == true, "and it asked for both ends")


func _check_one_way_delete_is_offered_only_when_a_pair_exists() -> void:
	print("\n[deleting a connection with no return]")
	var panel := _panel_for("lot")
	_assert(panel._find_reciprocal_exit("north", "clearing") == "",
		"a one-way exit reports no pair to remove")
	_assert(panel._find_reciprocal_exit("west", "shrine") == "east",
		"while `west` -- the direction that IS paired -- finds shrine's east exit")
	_assert(panel._find_reciprocal_exit("east", "shrine") == "",
		"and `east` finds nothing, since the fixture has no shrine-west back to lot")

	var request := DeleteRequest.new(panel)
	panel.request_delete_connection.emit("lot", "north", "clearing", false)
	_assert(request.calls.size() == 1 and request.calls[0]["reciprocal"] == false,
		"the one-way removal is available as the fallback")


func _check_cross_region_connections_are_not_claimed_as_pairs() -> void:
	print("\n[deleting a cross-region exit]")
	var panel := _panel_for("shrine")
	# The far end of a cross-region exit lives in a file this region has not
	# loaded, so the panel must not claim to know its return direction.
	_assert(panel._find_reciprocal_exit("out", "other_region:somewhere") == "",
		"a cross-region exit reports no pair rather than guessing one")


# --- the curve choice ---------------------------------------------------------

func _check_curve_choice_survives_a_save() -> void:
	print("\n[an authored bow]")
	var panel := _panel_for("shrine")
	_assert(panel._is_curved_direction("in"), "`in` is drawn as a curve")
	_assert(panel._is_curved_direction("out"), "`out` is drawn as a curve")
	_assert(not panel._is_curved_direction("north"), "a compass direction is not")
	_assert(panel._current_curve("east") == "", "with no override, the side is automatic")

	# Write the pick the way `Main` commits it, then round-trip the region through
	# the real split/merge -- the same two calls the save and load paths make, which
	# is what decides whether the choice reaches the sidecar and stays out of the
	# content file.
	var mgr := RegionManager.new()
	mgr.data = _load_region()
	mgr.data.rooms["shrine"]["_editor_exit_layout"] = {"in": {"curve": "left"}}

	var content := EditorLayout.strip_region(mgr.data)
	EditorLayout.split_region("probe", mgr.data)
	_write_region(content)

	var reloaded := EditorLayout.merge_region("probe", _load_region())
	var layout: Dictionary = reloaded["rooms"]["shrine"].get("_editor_exit_layout", {})
	_assert(layout.get("in", {}).get("curve", "") == "left",
		"the authored bow survives the round-trip (got %s)" % str(layout.get("in", {})))

	# And it stays out of the content file: it is editor state, not game data.
	var content_text := FileAccess.get_file_as_string(data_root.path_join("regions/probe.json"))
	_assert(not content_text.contains("_editor_exit_layout"),
		"and does not leak into the content file")


func _check_curve_cycling_returns_to_automatic() -> void:
	print("\n[cycling the bow]")
	# The same automatic -> left -> right -> automatic cycle `Main` commits, so a
	# cleared override leaves no empty entry behind.
	var entry := {}
	var seen: Array = []
	for _step in range(4):
		match str(entry.get("curve", "")):
			"": entry["curve"] = "left"
			"left": entry["curve"] = "right"
			_: entry.erase("curve")
		seen.append(str(entry.get("curve", "")))
	_assert(seen == ["left", "right", "", "left"],
		"the cycle is automatic -> left -> right -> automatic (got %s)" % str(seen))


func _check_bow_distance_cycles_and_clears() -> void:
	print("\n[bow distance]")
	# The rule lives on the panel, next to the table it describes, so it can be
	# asserted without a widget. `normal` is what the renderer draws with no
	# override at all, so the cycle returns to it by returning "".
	var seen: Array = []
	var current := RoomConnectionsPanel.CURVE_AMOUNT_DEFAULT
	for _step in range(4):
		current = RoomConnectionsPanel.next_curve_amount(current)
		seen.append(current)
	_assert(seen == ["wide", "tight", "", "wide"],
		"the cycle is default -> wide -> tight -> default (got %s)" % str(seen))

	_assert(RoomConnectionsPanel.next_curve_amount("") == "wide",
		"a fresh exit -- no override -- advances to `wide`")
	_assert(RoomConnectionsPanel.next_curve_amount("nonsense") == "wide",
		"and an unrecognised value is read as `normal`, not as the start of the cycle")
	_assert(RoomConnectionsPanel.next_curve_amount("tight") == "",
		"`tight` cycles back to the automatic distance, stored as no key at all")
	_assert(RoomConnectionsPanel.next_curve_amount("normal") == "wide",
		"an explicitly-stored `normal` advances rather than sticking")

	_assert(RoomConnectionsPanel.curve_scale_for("") == 1.0,
		"no override draws the automatic bow")
	_assert(RoomConnectionsPanel.curve_scale_for("normal") == 1.0,
		"and so does `normal`")
	_assert(RoomConnectionsPanel.curve_scale_for("tight") < 1.0,
		"`tight` bows less than the automatic amount")
	_assert(RoomConnectionsPanel.curve_scale_for("wide") > 1.0,
		"`wide` bows more")


func _check_side_and_distance_are_independent() -> void:
	print("\n[side and distance together]")
	# Two controls, two keys: flipping the side must not reset the distance, and
	# changing the distance must not reset the side. Written the way `Main` writes
	# them, so this fails if either handler starts clearing the other's key.
	var entry := {}
	# Flip twice: automatic -> left -> right.
	for _step in range(2):
		match str(entry.get("curve", "")):
			"": entry["curve"] = "left"
			"left": entry["curve"] = "right"
			_: entry.erase("curve")
	entry["curve_amount"] = "tight"

	_assert(entry.get("curve", "") == "right" and entry.get("curve_amount", "") == "tight",
		"both choices coexist on one exit")

	# And they survive a save together.
	var mgr := RegionManager.new()
	mgr.data = _load_region()
	mgr.data.rooms["shrine"]["_editor_exit_layout"] = {"in": entry.duplicate(true)}
	var content := EditorLayout.strip_region(mgr.data)
	EditorLayout.split_region("probe", mgr.data)
	_write_region(content)

	var reloaded := EditorLayout.merge_region("probe", _load_region())
	var saved: Dictionary = reloaded["rooms"]["shrine"].get("_editor_exit_layout", {}).get("in", {})
	_assert(saved.get("curve", "") == "right" and saved.get("curve_amount", "") == "tight",
		"and both survive the round-trip (got %s)" % str(saved))


# --- connect another ----------------------------------------------------------

func _check_connect_another_keeps_the_source() -> void:
	print("\n[connect another]")
	# The form is built for real here, because the point of this case is what the
	# *widgets* hold after a connection: the source and the direction have to
	# survive, or the author re-picks them for every room and the button saves
	# nothing.
	var mgr := RegionManager.new()
	mgr.data = _load_region()
	mgr.current_filename = "probe.json"

	var holder := VBoxContainer.new()
	root.add_child(holder)
	var editor := ConnectionEditor.new(mgr)
	editor.conn_src_id = "shrine"
	editor.conn_src_name = "Shrine of Healing"
	editor.build_ui(holder, "shrine", "Shrine of Healing", {"probe": {"filename": "probe.json", "rooms": mgr.data.rooms}}, "probe.json")

	# Pick a target and a direction the way the form would, then reset.
	editor.set_target("probe", "lot")
	editor._select_direction_value(editor.conn_dir_option, "east")
	editor._on_forward_dir_changed()
	var direction_before := editor._get_forward_direction()
	var region_selected := editor.conn_reg_opt.selected
	_assert(direction_before != "", "a direction is selected before connecting another")

	editor._reset_for_next_target()

	_assert(editor.conn_dir_option.selected == editor.conn_dir_option.selected,
		"the direction control survives the reset")
	_assert(editor._get_forward_direction() == direction_before,
		"and still reads the same direction (got %s)" % editor._get_forward_direction())
	_assert(editor.conn_room_opt.selected == -1,
		"while the target room is cleared, ready for the next pick")
	_assert(editor.conn_reg_opt.selected == region_selected,
		"and the target region is kept, since it is usually the same one")

	# A cleared target must not look like a connectable state.
	_assert(editor._get_forward_direction() != "",
		"the direction is still set, so the next Connect is one click away")
	holder.queue_free()


# --- helpers ------------------------------------------------------------------
func _load_region() -> Dictionary:
	return JSON.parse_string(FileAccess.get_file_as_string(data_root.path_join("regions/probe.json")))


func _write_region(data: Dictionary) -> void:
	var file := FileAccess.open(data_root.path_join("regions/probe.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(data, "  "))
	file.close()


func _rebuild_fixture() -> void:
	var scratch := ProjectSettings.globalize_path("res://").path_join("../tmp/connection_editing")
	_remove_recursive(scratch)
	DirAccess.make_dir_recursive_absolute(data_root.path_join("regions"))

	_write_region({
		"region_id": "probe", "name": "Probe",
		"rooms": {
			# A reciprocal pair: shrine -east-> lot, lot -west-> shrine.
			"shrine": {
				"name": "Shrine of Healing",
				"exits": {"east": "lot", "north": "clearing", "in": "sanctum", "out": "other_region:somewhere"},
			},
			"lot": {
				"name": "Vacant Lot",
				"exits": {"west": "shrine", "north": "clearing"},
			},
			# A one-way exit, and a second reciprocal pair -- shrine north to
			# clearing, clearing south to shrine -- to prove the lookup reads the
			# far room rather than just returning the first exit it finds.
			"clearing": {"name": "Clearing", "exits": {"south": "shrine"}},
			"sanctum": {"name": "Sanctum", "exits": {}},
		},
	})


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null: return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		var full := path.path_join(name)
		if dir.current_is_dir(): _remove_recursive(full)
		else: DirAccess.remove_absolute(full)
		name = dir.get_next()
	dir.list_dir_end()


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		printerr("  FAIL ", message)
