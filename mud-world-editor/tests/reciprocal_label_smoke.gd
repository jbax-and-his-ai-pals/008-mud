# tests/reciprocal_label_smoke.gd
#
# A two-way connection's map label must show each room's own exit direction
# physically next to that room, for any ordinary compass pair (north/south,
# up/down, northeast/southwest, ...).
#
# The bug this pins: `Constants.format_reciprocal_pair_label`'s "authored
# emitter" swap (meant to give a stable word order to a mismatched custom
# reciprocal like "opening"/"out", which has no natural geometric opposite)
# shifts the angle used for its flip decision by exactly PI. That reliably
# flips which side of the +-90-degree boundary the angle lands on for almost
# any angle -- except exactly AT that boundary (a perfectly vertical or
# horizontal connector), where both the original and the PI-shifted angle
# land on the same side of the strict `>`/`<` comparison. Since
# `GraphRenderer._draw_label_rotated` always rotates the drawn text by the
# *unswapped* angle, that one-value coincidence desyncs the label from the
# actual rotation -- reported live: two rooms connected due north/south had
# their direction words swapped only while exactly grid-aligned; nudging
# either room one grid unit off that exact alignment made the label correct
# again. Run with:
#
#   godot --headless --path mud-world-editor --script tests/reciprocal_label_smoke.gd

extends SceneTree

var failure_count := 0


func _init() -> void:
	_check_exact_vertical_alignment_matches_offset_alignment()
	_check_mismatched_pair_keeps_authored_order()

	if failure_count > 0:
		push_error("reciprocal label smoke failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# Hall of Names (names_hall) sits due north of Sealed Chapel (sealed_chapel)
# in content_sets/fantasy_frontier -- names_hall.exits.south leads to
# sealed_chapel, sealed_chapel.exits.north leads back. Both rooms share the
# same editor-authored X coordinate (-160), so this connector is *exactly*
# vertical: precisely the alignment that reproduced the bug live.
#
# The precise mechanism: `authored_source` naming the room that ISN'T
# first_id triggers a swap that shifts the angle by PI. For almost any angle
# that reliably flips which side of the +-90-degree boundary it lands on, so
# the label stays in sync with the actual drawn rotation -- but exactly AT
# that boundary (this connector), both the original and the shifted angle
# land on the same side of the strict comparison, and the swap silently stops
# doing anything to compensate for the word-order change it still makes. So
# the one property that must hold, especially right here at the boundary, is
# that a clean compass pair's label no longer depends on which room
# `authored_source` names at all.
func _check_exact_vertical_alignment_matches_offset_alignment() -> void:
	print("\n[exact vertical alignment]")
	var hall_pos := Vector2(-160, 178)      # names_hall's south anchor
	var chapel_pos := Vector2(-160, 334)    # sealed_chapel's north anchor -- same X

	var unset := Constants.format_reciprocal_pair_label(
		"names_hall", "sealed_chapel", "south", "north", hall_pos, chapel_pos, "")
	var source_is_first := Constants.format_reciprocal_pair_label(
		"names_hall", "sealed_chapel", "south", "north", hall_pos, chapel_pos, "names_hall")
	var source_is_second := Constants.format_reciprocal_pair_label(
		"names_hall", "sealed_chapel", "south", "north", hall_pos, chapel_pos, "sealed_chapel")

	_assert(source_is_first == unset,
		"authored_source naming the first room changes nothing: %s vs %s" % [source_is_first, unset])
	_assert(source_is_second == unset,
		"authored_source naming the SECOND room no longer changes a clean-inverse label at this exact boundary either: %s vs %s -- this is the live-reported bug" % [source_is_second, unset])


# A mismatched reciprocal (no clean geometric opposite) has nothing for
# geometry to get right or wrong, so the authored emitter's word order is
# preserved exactly as before this fix.
func _check_mismatched_pair_keeps_authored_order() -> void:
	print("\n[mismatched custom reciprocal]")
	var cave_pos := Vector2(400, 400)
	var tunnel_pos := Vector2(600, 400)

	var authored_cave := Constants.format_reciprocal_pair_label(
		"cave", "tunnel", "opening", "out", cave_pos, tunnel_pos, "cave")
	_assert(authored_cave == "Opening ↔ Out", "the cave's authored 'opening' leads: %s" % authored_cave)

	var authored_from_tunnel := Constants.format_reciprocal_pair_label(
		"tunnel", "cave", "out", "opening", tunnel_pos, cave_pos, "cave")
	_assert(authored_from_tunnel == "Opening ↔ Out",
		"the authored order survives being rendered from the other room: %s" % authored_from_tunnel)


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		push_error("FAIL: " + message)
