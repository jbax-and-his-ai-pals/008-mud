# scripts/generators/DistrictLayout.gd
class_name DistrictLayout
extends RefCounted

# RegionScene draws 80x80 room cards.  Reserving a small gutter gives a drag
# preview the same no-overlap rule as the editor, without treating the empty
# area inside a diagonal or branching district as occupied.
const ROOM_CARD_SIZE := Vector2(200, 100)
const ROOM_CLEARANCE := Vector2(224, 128)

# Content spans several eras of grid convention (the current auto-arranger's
# 256x192 spacing, an older plain 256x256 grid, a still-older 350x250
# fallback, plus hand-dragged rooms that fit no grid at all). Rather than
# assume any one spacing, "adjacent" is derived per lookup: the nearest room
# in each 45-degree octant around a point, capped at a radius comfortably
# above the largest single-step diagonal in any of those conventions (362)
# but below their smallest double-step cardinal (512), so a real neighbor is
# never missed and a room two steps away is never mistaken for one.
const PINCH_NEIGHBOR_RADIUS := 420.0
const OCTANT_COUNT := 8

static func preview_attachment(rooms: Dictionary, district_room_ids: Array, anchor_room_id: String, target_room_id: String, direction: String, two_way: bool = true) -> Dictionary:
	# This is intentionally pure: callers can render `positions` as a ghost and
	# show `errors` before moving rooms or changing exits.
	var errors: Array = []
	var warnings: Array = []
	var district := _valid_district_ids(rooms, district_room_ids)
	var normalized := direction.to_lower()
	if district.is_empty():
		errors.append("Choose at least one valid room for the district.")
	if not district.has(anchor_room_id):
		errors.append("The attachment room must belong to the selected district.")
	if not rooms.has(target_room_id):
		errors.append("Choose an existing target room.")
	if target_room_id == anchor_room_id or district.has(target_room_id):
		errors.append("Attach the district to a room outside that district.")
	if not Constants.DIR_VECTORS.has(normalized) or normalized in ["in", "out"]:
		errors.append("Choose a compass, diagonal, or vertical attachment direction.")
	if not errors.is_empty():
		return _preview_result(false, errors, warnings)

	var components := _district_component_count(rooms, district)
	if components > 1:
		errors.append("The selected district has %d disconnected pieces; attach each piece separately or connect it first." % components)

	var target_exits: Dictionary = rooms[target_room_id].get("exits", {})
	if target_exits.has(normalized) and str(target_exits[normalized]) != anchor_room_id:
		errors.append("%s already uses its %s exit." % [target_room_id, normalized])
	var inverse: String = str(Constants.INV_DIR_MAP.get(normalized, ""))
	var anchor_exits: Dictionary = rooms[anchor_room_id].get("exits", {})
	if two_way and inverse != "" and anchor_exits.has(inverse) and str(anchor_exits[inverse]) != target_room_id:
		errors.append("%s already uses its %s return exit." % [anchor_room_id, inverse])
	if two_way and inverse == "":
		warnings.append("%s has no defined reciprocal direction; this attachment will be one-way unless you choose one manually." % normalized)

	var external_links := _external_links(rooms, district)
	for link in external_links:
		if link.source != anchor_room_id or link.target != target_room_id:
			warnings.append("Existing external link %s --%s--> %s remains attached." % [link.source, link.direction, link.target])

	var positions := _room_positions(rooms, district)
	var target_pos := _room_position(rooms[target_room_id])
	var anchor_pos: Vector2 = positions[anchor_room_id]
	var direction_vector: Vector2 = Constants.DIR_VECTORS[normalized]
	var desired_anchor := target_pos + direction_vector * LayoutOptimizer.ROOM_SPACING
	var offset := desired_anchor - anchor_pos
	var preview_positions := {}
	for room_id in district:
		preview_positions[room_id] = positions[room_id] + offset

	var collisions := _find_collisions(rooms, district, preview_positions)
	if not collisions.is_empty():
		errors.append("Placement overlaps room(s): " + ", ".join(collisions) + ".")

	var result = _preview_result(errors.is_empty(), errors, warnings)
	result["positions"] = preview_positions
	result["offset"] = offset
	result["connection_plan"] = {
		"source": target_room_id,
		"direction": normalized,
		"target": anchor_room_id,
		"two_way": two_way,
		"inverse_direction": inverse,
	}
	return result

static func _preview_result(valid: bool, errors: Array, warnings: Array) -> Dictionary:
	return {"valid": valid, "errors": errors, "warnings": warnings, "positions": {}, "offset": Vector2.ZERO, "connection_plan": {}}

static func _valid_district_ids(rooms: Dictionary, room_ids: Array) -> Array:
	var ids: Array = []
	for room_id in room_ids:
		var id := str(room_id)
		if rooms.has(id) and not ids.has(id):
			ids.append(id)
	ids.sort()
	return ids

static func _district_component_count(rooms: Dictionary, district: Array) -> int:
	var remaining := {}
	for room_id in district:
		remaining[room_id] = true
	var components := 0
	while not remaining.is_empty():
		components += 1
		var root = remaining.keys()[0]
		var queue: Array = [root]
		remaining.erase(root)
		while not queue.is_empty():
			var current = queue.pop_front()
			for neighbor in _local_neighbors(rooms, current, district):
				if remaining.has(neighbor):
					remaining.erase(neighbor)
					queue.append(neighbor)
	return components

static func _local_neighbors(rooms: Dictionary, room_id: String, district: Array) -> Array:
	var neighbors: Array = []
	var exits = rooms[room_id].get("exits", {})
	if exits is Dictionary:
		for direction in exits:
			var target := str(exits[direction])
			if district.has(target) and not neighbors.has(target):
				neighbors.append(target)
	for other_id in district:
		var other_exits = rooms[other_id].get("exits", {})
		if other_exits is Dictionary and other_exits.values().has(room_id) and not neighbors.has(other_id):
			neighbors.append(other_id)
	return neighbors

static func _external_links(rooms: Dictionary, district: Array) -> Array:
	var links: Array = []
	for room_id in district:
		var exits = rooms[room_id].get("exits", {})
		if not exits is Dictionary:
			continue
		for direction in exits:
			var target := str(exits[direction])
			if not district.has(target):
				links.append({"source": room_id, "direction": str(direction), "target": target})
	return links

static func _room_positions(rooms: Dictionary, room_ids: Array) -> Dictionary:
	var positions := {}
	for room_id in room_ids:
		positions[room_id] = _room_position(rooms[room_id])
	return positions

static func _room_position(room: Dictionary) -> Vector2:
	var raw = room.get("_editor_pos", [0, 0])
	if raw is Vector2:
		return raw
	if raw is Array and raw.size() >= 2:
		return Vector2(float(raw[0]), float(raw[1]))
	return Vector2.ZERO

static func _find_collisions(rooms: Dictionary, district: Array, preview_positions: Dictionary) -> Array:
	var collisions: Array = []
	for moved_id in preview_positions:
		var moved_pos: Vector2 = preview_positions[moved_id]
		for stationary_id in rooms:
			if district.has(stationary_id):
				continue
			var stationary = rooms[stationary_id]
			if not stationary is Dictionary:
				continue
			var stationary_pos := _room_position(stationary)
			if abs(moved_pos.x - stationary_pos.x) < ROOM_CLEARANCE.x and abs(moved_pos.y - stationary_pos.y) < ROOM_CLEARANCE.y:
				if not collisions.has(str(stationary_id)):
					collisions.append(str(stationary_id))
	collisions.sort()
	return collisions

# Validate the connection separately from footprint placement. The draft is
# allowed to float freely, but its eventual exits must be unused and its line
# must not cut through unrelated room cards.
static func validate_preview_connection(existing_rooms: Dictionary, preview_rooms: Dictionary, preview_positions: Dictionary, port_id: String, target_id: String, source_direction: String) -> Array:
	var errors: Array = []
	var target_direction := str(Constants.INV_DIR_MAP.get(source_direction, ""))
	if port_id == "" or target_id == "" or source_direction == "" or target_direction == "":
		return errors
	if not preview_rooms.has(port_id) or not preview_positions.has(port_id) or not existing_rooms.has(target_id):
		return ["Choose valid connection endpoints."]
	var port_exits: Dictionary = preview_rooms[port_id].get("exits", {})
	if port_exits.has(source_direction) and str(port_exits[source_direction]) != target_id:
		errors.append("District port already uses its %s exit." % source_direction)
	var target_exits: Dictionary = existing_rooms[target_id].get("exits", {})
	if target_exits.has(target_direction) and str(target_exits[target_direction]) != port_id:
		errors.append("Town destination already uses its %s exit." % target_direction)
	var source_pos: Vector2 = preview_positions[port_id]
	var target_pos: Vector2 = _room_position(existing_rooms[target_id])
	for room_id in existing_rooms:
		if str(room_id) == target_id: continue
		if _connection_hits_room(source_pos, target_pos, _room_position(existing_rooms[room_id])):
			errors.append("Connection crosses %s." % str(existing_rooms[room_id].get("name", room_id)))
	for room_id in preview_positions:
		if str(room_id) == port_id: continue
		if _connection_hits_room(source_pos, target_pos, preview_positions[room_id]):
			errors.append("Connection crosses district room %s." % str(preview_rooms.get(room_id, {}).get("name", room_id)))
	return errors

static func _connection_hits_room(from: Vector2, to: Vector2, room_pos: Vector2) -> bool:
	var rect := Rect2(room_pos - ROOM_CARD_SIZE * 0.5, ROOM_CARD_SIZE)
	if rect.has_point(from) or rect.has_point(to): return false
	var corners := [rect.position, Vector2(rect.end.x, rect.position.y), rect.end, Vector2(rect.position.x, rect.end.y)]
	for index in range(corners.size()):
		if Geometry2D.segment_intersects_segment(from, to, corners[index], corners[(index + 1) % corners.size()]) != null:
			return true
	return false

# Flags a room whose immediate visual neighbors are dominated by two or more
# *different* foreign districts on sides it has no exit to (in either
# direction). A single foreign neighbor is an ordinary shared border -- every
# district touches its neighbors somewhere. Two distinct ones with neither
# explained by a connection is the "sandwiched" shape a hand-authored or
# bulk-generated district can end up in, squeezing that room's own territory
# down to almost nothing between them.
static func find_multi_district_pinches(rooms: Dictionary, room_to_district: Dictionary) -> Array:
	var findings: Array = []
	var position_lookup: Dictionary = {}
	for room_id in rooms:
		if rooms[room_id] is Dictionary:
			position_lookup[str(room_id)] = _room_position(rooms[room_id])
	var sorted_ids := room_to_district.keys()
	sorted_ids.sort()
	for room_id in sorted_ids:
		if not rooms.has(room_id) or not position_lookup.has(room_id):
			continue
		var own_district = room_to_district[room_id]
		var pos: Vector2 = position_lookup[room_id]
		var exit_targets: Dictionary = {}
		for target in rooms[room_id].get("exits", {}).values():
			exit_targets[str(target)] = true
		var foreign_districts: Dictionary = {}
		for neighbor_id in _nearest_room_per_octant(room_id, pos, position_lookup):
			var neighbor_district = room_to_district.get(neighbor_id)
			if neighbor_district == null or neighbor_district == own_district:
				continue
			if exit_targets.has(neighbor_id):
				continue
			var neighbor_exits: Dictionary = rooms[neighbor_id].get("exits", {})
			if neighbor_exits.values().has(room_id):
				continue
			foreign_districts[neighbor_district] = true
		if foreign_districts.size() >= 2:
			var foreign_ids := foreign_districts.keys()
			foreign_ids.sort()
			findings.append({"room_id": room_id, "district_id": own_district, "foreign_districts": foreign_ids})
	return findings

# The single nearest other room in each 45-degree slice around `pos`, within
# PINCH_NEIGHBOR_RADIUS. At most eight results, one per octant; an empty
# octant (nothing that close in that direction) simply contributes nothing.
static func _nearest_room_per_octant(exclude_id: String, pos: Vector2, position_lookup: Dictionary) -> Array:
	var best_id: Array = []
	var best_dist: Array = []
	best_id.resize(OCTANT_COUNT)
	best_dist.resize(OCTANT_COUNT)
	for i in range(OCTANT_COUNT):
		best_id[i] = ""
		best_dist[i] = INF
	for room_id in position_lookup:
		if room_id == exclude_id:
			continue
		var delta: Vector2 = position_lookup[room_id] - pos
		var dist := delta.length()
		if dist <= 0.001 or dist > PINCH_NEIGHBOR_RADIUS:
			continue
		var octant := _octant_index(delta)
		if dist < best_dist[octant]:
			best_dist[octant] = dist
			best_id[octant] = room_id
	var result: Array = []
	for i in range(OCTANT_COUNT):
		if best_id[i] != "":
			result.append(best_id[i])
	return result

static func _octant_index(delta: Vector2) -> int:
	var octant := int(round(delta.angle() / (PI / 4.0)))
	return ((octant % OCTANT_COUNT) + OCTANT_COUNT) % OCTANT_COUNT
