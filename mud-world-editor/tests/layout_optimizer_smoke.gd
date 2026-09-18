extends SceneTree

var failure_count := 0

func _init() -> void:
	var rooms := {
		"start": {"properties": {"is_start_node": true}, "exits": {"east": "east_1", "north": "north_1", "in": "cellar", "portal": "archive"}},
		"east_1": {"exits": {"east": "east_2"}},
		"east_2": {"exits": {}},
		"north_1": {"exits": {"north": "north_2"}},
		"north_2": {"exits": {}},
		"cellar": {"exits": {}},
		"archive": {"exits": {}},
		"one_way_cell": {"exits": {"up": "north_2"}},
	}
	var positions = LayoutOptimizer.optimize_layout(rooms)
	_assert(positions.size() == rooms.size(), "every room receives a position")
	_assert(positions["start"].y == positions["east_1"].y, "east exit remains horizontally aligned")
	_assert(positions["east_1"].y == positions["east_2"].y, "east chain remains horizontally aligned")
	_assert(positions["start"].x == positions["north_1"].x, "north exit remains vertically aligned")
	_assert(positions["north_1"].x == positions["north_2"].x, "north chain remains vertically aligned")
	_assert(positions["east_1"].x - positions["start"].x == LayoutOptimizer.ROOM_SPACING.x, "east exit uses one layout unit")
	_assert(positions["east_2"].x - positions["east_1"].x == LayoutOptimizer.ROOM_SPACING.x, "east chain uses one layout unit")
	_assert(positions["north_1"].y - positions["start"].y == -LayoutOptimizer.ROOM_SPACING.y, "north exit uses one layout unit")
	_assert(positions["north_2"].y - positions["north_1"].y == -LayoutOptimizer.ROOM_SPACING.y, "north chain uses one layout unit")
	_assert(positions["one_way_cell"].x < positions["north_2"].x and positions["one_way_cell"].y > positions["north_2"].y, "one-way up exit is reverse-traversed using its down direction")
	_assert(positions["cellar"] - positions["start"] == ROOM_HALF_STEP, "in exit stacks half a cell down and right")
	_assert(positions["archive"] != positions["start"], "unmapped exit receives a visible placement")
	_assert_unique_positions(positions, "synthetic layout")
	var metadata = LayoutOptimizer.infer_exit_layout_metadata(rooms, positions)
	_assert(metadata["start"]["in"]["visual_direction"] == "southeast", "in exit persists its visual direction")
	_assert(metadata["start"]["in"]["placement"] == "stacked", "in exit persists its stacked placement")
	_assert(metadata["start"].has("portal"), "unmapped exit receives inferred layout metadata")
	_assert_all_region_cardinal_alignment()
	_assert_district_layout()
	quit(1 if failure_count > 0 else 0)

func _assert_district_layout() -> void:
	var district_rooms := {
		"d1_a": {"_editor_pos": [0, 0], "exits": {"east": "d1_b"}},
		"d1_b": {"_editor_pos": [256, 0], "exits": {"west": "d1_a", "east": "d2_a"}},
		"d2_a": {"_editor_pos": [512, 0], "exits": {"west": "d1_b"}},
		"d2_b": {"_editor_pos": [512, 192], "exits": {}},
	}
	var districts := {
		"d1": {"members": ["d1_a", "d1_b"]},
		"d2": {"members": ["d2_a", "d2_b"]},
	}
	var district_positions = LayoutOptimizer.optimize_district_layout(district_rooms, districts)
	_assert(district_positions.has("d1") and district_positions.has("d2"), "every district receives a new center")
	_assert(district_positions.get("d1") != district_positions.get("d2"), "connected districts don't collapse onto the same center")

	var empty_positions = LayoutOptimizer.optimize_district_layout({}, {"solo": {"members": []}})
	_assert(empty_positions.has("solo"), "a district with no live member rooms still gets a fallback position")

func _assert(condition: bool, message: String) -> void:
	if not condition:
		failure_count += 1
		push_error("LayoutOptimizer smoke test failed: " + message)

const ROOM_HALF_STEP = LayoutOptimizer.ROOM_SPACING / 2.0

func _assert_unique_positions(positions: Dictionary, label: String) -> void:
	var occupied := {}
	for room_id in positions:
		var position: Vector2 = positions[room_id]
		var key := "%d:%d" % [roundi(position.x), roundi(position.y)]
		_assert(not occupied.has(key), "%s has no overlapping rooms (%s)" % [label, room_id])
		occupied[key] = room_id

func _assert_all_region_cardinal_alignment() -> void:
	var directory := DirAccess.open("res://data/regions")
	_assert(directory != null, "editor region directory opens")
	if directory == null:
		return
	directory.list_dir_begin()
	var filename := directory.get_next()
	while filename != "":
		if not directory.current_is_dir() and filename.ends_with(".json"):
			_assert_real_region_cardinal_alignment("res://data/regions/" + filename)
		filename = directory.get_next()
	directory.list_dir_end()

func _assert_real_region_cardinal_alignment(path: String) -> void:
	var data = JSON.parse_string(FileAccess.get_file_as_string(path))
	_assert(data is Dictionary, "real region parses: " + path)
	if not data is Dictionary:
		return
	var rooms: Dictionary = data.get("rooms", {})
	var positions = LayoutOptimizer.optimize_layout(rooms)
	_assert(positions.size() == rooms.size(), "every room receives a position: " + path)
	_assert_unique_positions(positions, path)
	if not LayoutOptimizer.can_preserve_cardinal_alignment(rooms):
		return # Contradictory directional cycles intentionally use legacy layout.
	for room_id in rooms:
		var exits: Dictionary = rooms[room_id].get("exits", {})
		for direction in exits:
			var target_id := str(exits[direction])
			if not rooms.has(target_id):
				continue
			var normalized := str(direction).to_lower()
			if normalized in ["east", "west"]:
				_assert(positions[room_id].y == positions[target_id].y, "%s keeps %s/%s horizontal" % [path, room_id, target_id])
			elif normalized in ["north", "south"]:
				_assert(positions[room_id].x == positions[target_id].x, "%s keeps %s/%s vertical" % [path, room_id, target_id])
