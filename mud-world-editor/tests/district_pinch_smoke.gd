extends SceneTree

const DistrictLayout = preload("res://scripts/generators/DistrictLayout.gd")

var failures := 0

func _init() -> void:
	# Mirrors the real town.json shape around "west_lane": one civic_core room
	# boxed on its south side by two different foreign districts (riverside,
	# residential), with only one of the two sides explained by an exit.
	var rooms := {
		"town_square": {"_editor_pos": [0, 0], "exits": {"west": "west_lane"}},
		"west_lane": {"_editor_pos": [-256, 0], "exits": {"east": "town_square", "southwest": "residential_street_east"}},
		"museum_exterior": {"_editor_pos": [-256, 192], "exits": {}},
		"residential_street_east": {"_editor_pos": [-512, 192], "exits": {"northeast": "west_lane"}},
	}
	var room_to_district := {
		"town_square": "civic_core",
		"west_lane": "civic_core",
		"museum_exterior": "riverside",
		"residential_street_east": "residential",
	}
	# west_lane itself is NOT flagged: its one unexplained foreign side
	# (south, to museum_exterior/riverside) is only a single foreign
	# district, and its other foreign-adjacent side (southwest, to
	# residential_street_east) is a real, authored exit -- an intentional
	# link, not a squeeze. museum_exterior is the room actually pinched: it
	# borders civic_core (north, via west_lane) and residential (west, via
	# residential_street_east) with no exit explaining either side.
	var pinches := DistrictLayout.find_multi_district_pinches(rooms, room_to_district)
	_assert(pinches.size() == 1, "exactly the sandwiched room is flagged, got %d" % pinches.size())
	if pinches.size() == 1:
		_assert(pinches[0].room_id == "museum_exterior", "the flagged room is museum_exterior, not west_lane")
		_assert(pinches[0].foreign_districts == ["civic_core", "residential"], "both foreign districts are named, sorted")

	# An ordinary shared border -- one foreign neighbor, one district -- must
	# stay silent. A district touching exactly one neighbor somewhere is the
	# normal case, not a bug.
	var bordering_rooms := {
		"a": {"_editor_pos": [0, 0], "exits": {}},
		"b": {"_editor_pos": [256, 0], "exits": {}},
	}
	var bordering_districts := {"a": "north_ward", "b": "south_ward"}
	var no_pinch := DistrictLayout.find_multi_district_pinches(bordering_rooms, bordering_districts)
	_assert(no_pinch.is_empty(), "a single foreign neighbor is not a pinch")

	# A hub room with real exits into both neighboring districts is a
	# deliberate junction, not a squeeze -- both sides are explained.
	var hub_rooms := {
		"hub": {"_editor_pos": [0, 0], "exits": {"east": "market", "south": "docks"}},
		"market": {"_editor_pos": [256, 0], "exits": {"west": "hub"}},
		"docks": {"_editor_pos": [0, 192], "exits": {"north": "hub"}},
	}
	var hub_districts := {"hub": "civic_core", "market": "market_row", "docks": "riverside"}
	var hub_pinch := DistrictLayout.find_multi_district_pinches(hub_rooms, hub_districts)
	_assert(hub_pinch.is_empty(), "a junction room explained by real exits on both sides is not a pinch")

	# Detection is octant-based, not tied to any exact grid spacing -- a
	# hand-dragged, off-grid room sandwiched between two foreign districts
	# must still be caught. This is the same shape as the museum_exterior
	# case above, just not snapped to any particular spacing.
	var offgrid_rooms := {
		"drifted": {"_editor_pos": [37, -41], "exits": {}},
		"foreign_one": {"_editor_pos": [37 - 250, -41 + 188], "exits": {}},
		"foreign_two": {"_editor_pos": [37 + 251, -41 - 190], "exits": {}},
	}
	var offgrid_districts := {"drifted": "civic_core", "foreign_one": "riverside", "foreign_two": "market_row"}
	var offgrid_pinch := DistrictLayout.find_multi_district_pinches(offgrid_rooms, offgrid_districts)
	_assert(offgrid_pinch.size() == 1 and offgrid_pinch[0].room_id == "drifted", "an off-grid sandwiched room is still caught")

	# But a room genuinely far from any foreign neighbor -- well beyond the
	# pinch radius -- must not be flagged just because it is technically the
	# nearest thing in some far-off octant.
	var distant_rooms := {
		"lonely": {"_editor_pos": [0, 0], "exits": {}},
		"far_one": {"_editor_pos": [2000, 0], "exits": {}},
		"far_two": {"_editor_pos": [0, 2000], "exits": {}},
	}
	var distant_districts := {"lonely": "civic_core", "far_one": "riverside", "far_two": "market_row"}
	var distant_pinch := DistrictLayout.find_multi_district_pinches(distant_rooms, distant_districts)
	_assert(distant_pinch.is_empty(), "distant rooms outside the pinch radius are not flagged")

	quit(1 if failures > 0 else 0)

func _assert(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error("District pinch smoke test failed: " + message)
