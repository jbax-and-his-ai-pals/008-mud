# scripts/generators/LayoutOptimizer.gd
class_name LayoutOptimizer
extends RefCounted

const SNAP_GRID = Vector2(32, 32)
# One cell is the normal, comfortable center-to-center distance for room cards.
# It is deliberately independent of graph size: a long route should look long
# because it has more moves, not because the arranger enlarged every move.
const ROOM_SPACING = Vector2(256, 192) # Both values are exact SNAP_GRID multiples.
const MAX_DIRECTIONAL_SEARCH = 16

# A room graph communicates spatial intent in its exit names.  Keep the most
# literal intent first; a cellar's ``in``/``out`` is useful, but should not
# consume the only clean east/west or north/south space around a room.
const CARDINAL_DIRECTIONS = ["north", "south", "east", "west"]
const SECONDARY_DIRECTIONS = [
	"northeast", "northwest", "southeast", "southwest",
	"up", "down", "climb", "dive",
]
const IN_OUT_DIRECTIONS = ["in", "out"]

static func optimize_layout(rooms: Dictionary) -> Dictionary:
	# The old first-visit BFS was compact, but whichever edge happened to be
	# visited first fixed a room's position.  That routinely put an east exit on
	# a diagonal or a north exit off its source column.  This pass works in grid
	# cells: cardinal exits retain their row/column, while increasing distance
	# absorbs collisions without losing the visual direction.
	var start_id = _find_layout_root(rooms)
	if start_id == "":
		return {}
	if not can_preserve_cardinal_alignment(rooms):
		return _safe_legacy_optimize_layout(rooms)

	var cells := {}
	var occupied := {}
	var visual_offsets := {}
	var queue: Array = []
	var island_index := 0

	for root_id in _layout_roots(rooms, start_id):
		if cells.has(root_id):
			continue
		var root_cell := Vector2i(0, island_index * (MAX_DIRECTIONAL_SEARCH + 4))
		if occupied.has(_cell_key(root_cell)):
			# This should only occur for an unusually dense disconnected graph.  It
			# is safer to keep the old deterministic layout than to return overlaps.
			return _safe_legacy_optimize_layout(rooms)
		cells[root_id] = root_cell
		occupied[_cell_key(root_cell)] = true
		queue.append(root_id)

		while not queue.is_empty():
			var current_id: String = queue.pop_front()
			var current_room = rooms.get(current_id, {})
			if not current_room is Dictionary:
				continue
			var exits = current_room.get("exits", {})
			if not exits is Dictionary:
				continue
			for direction in _ordered_exit_directions(exits):
				var target_id = str(exits[direction])
				# Other-region links render as proxies in the local graph.
				if ":" in target_id or cells.has(target_id) or not rooms.has(target_id):
					continue
				if not rooms[target_id] is Dictionary:
					continue
				var layout_hint = current_room.get("_editor_exit_layout", {}).get(direction, {})
				if not layout_hint is Dictionary:
					layout_hint = {}
				var placement = _find_directional_cell(cells[current_id], direction, occupied, layout_hint)
				if placement.is_empty():
					# A bounded search is deliberate: falling back is preferable to
					# spreading a malformed/dense graph across an unusable canvas.
					return _safe_legacy_optimize_layout(rooms)
				var target_cell: Vector2i = placement["cell"]
				cells[target_id] = target_cell
				visual_offsets[target_id] = placement.get("visual_offset", Vector2.ZERO)
				occupied[_cell_key(target_cell)] = true
				queue.append(target_id)
			# One-way/system exits still express useful map adjacency. Traverse an
			# incoming local exit in reverse when needed, using its inverse direction
			# to place the otherwise-unreachable source near this room.
			for incoming in _incoming_local_exits(rooms, current_id):
				var incoming_id: String = incoming["source"]
				if cells.has(incoming_id):
					continue
				var reverse_direction := str(Constants.INV_DIR_MAP.get(incoming["direction"], ""))
				if reverse_direction == "":
					continue
				var incoming_placement = _find_directional_cell(cells[current_id], reverse_direction, occupied)
				if incoming_placement.is_empty():
					return _safe_legacy_optimize_layout(rooms)
				var incoming_cell: Vector2i = incoming_placement["cell"]
				cells[incoming_id] = incoming_cell
				visual_offsets[incoming_id] = incoming_placement.get("visual_offset", Vector2.ZERO)
				occupied[_cell_key(incoming_cell)] = true
				queue.append(incoming_id)
		island_index += 1

	# Every valid room should have been visited from one of the roots.  This
	# catches malformed entries without returning an incomplete rearrangement.
	for room_id in rooms:
		if rooms[room_id] is Dictionary and not cells.has(room_id):
			return _safe_legacy_optimize_layout(rooms)
	if not _normalize_cardinal_axes(rooms, cells):
		# A map can make mutually impossible claims (for example, A is north of B
		# while B is east of A).  Do not silently overlap those rooms.
		return _safe_legacy_optimize_layout(rooms)

	var result := {}
	for room_id in cells:
		# A room that participates in a cardinal street/corridor must stay on the
		# main grid so its own connections continue to render straight. The half
		# step is reserved for terminal/ambiguous inner rooms.
		var visual_offset: Vector2 = Vector2.ZERO if _has_local_cardinal_connection(rooms, room_id) else visual_offsets.get(room_id, Vector2.ZERO)
		var visual_cell: Vector2 = Vector2(cells[room_id]) + visual_offset
		result[room_id] = (visual_cell * ROOM_SPACING).snapped(SNAP_GRID)
	return result

static func infer_exit_layout_metadata(rooms: Dictionary, positions: Dictionary) -> Dictionary:
	# Exit labels remain the gameplay contract. This editor-only sidecar records
	# the visual decision made for labels that carry no compass meaning (including
	# in/out), so a later auto-arrange starts from an inspectable, stable choice
	# instead of treating the connection as invisible or guessing anew in the UI.
	var metadata := {}
	for source_id in _sorted_valid_room_ids(rooms):
		var exits = rooms[source_id].get("exits", {})
		if not exits is Dictionary or not positions.has(source_id):
			continue
		for exit_name in exits:
			var normalized := str(exit_name).to_lower()
			if normalized in CARDINAL_DIRECTIONS or normalized in SECONDARY_DIRECTIONS:
				continue
			var target_id := str(exits[exit_name])
			if not positions.has(target_id):
				continue # Cross-region links are laid out by the world-map arranger.
			if not metadata.has(source_id):
				metadata[source_id] = {}
			var delta: Vector2 = positions[target_id] - positions[source_id]
			metadata[source_id][str(exit_name)] = {
				"target": target_id,
				"visual_direction": _visual_direction_from_delta(delta),
				"placement": "stacked" if _is_half_step(delta) else "adjacent",
				"inferred": true,
			}
	return metadata

static func _visual_direction_from_delta(delta: Vector2) -> String:
	var horizontal := "east" if delta.x >= 0 else "west"
	var vertical := "south" if delta.y >= 0 else "north"
	if is_zero_approx(delta.x):
		return vertical
	if is_zero_approx(delta.y):
		return horizontal
	if abs(delta.x) > abs(delta.y) * 1.5:
		return horizontal
	if abs(delta.y) > abs(delta.x) * 1.5:
		return vertical
	return vertical + horizontal

static func _is_half_step(delta: Vector2) -> bool:
	return is_equal_approx(abs(delta.x), ROOM_SPACING.x / 2.0) and is_equal_approx(abs(delta.y), ROOM_SPACING.y / 2.0)

static func _has_local_cardinal_connection(rooms: Dictionary, room_id: String) -> bool:
	for other_id in rooms:
		var room = rooms[other_id]
		if not room is Dictionary:
			continue
		var exits = room.get("exits", {})
		if not exits is Dictionary:
			continue
		for direction in CARDINAL_DIRECTIONS:
			if exits.has(direction) and str(exits[direction]) == room_id:
				return true
	return false

static func _normalize_cardinal_axes(rooms: Dictionary, cells: Dictionary) -> bool:
	# East/west edges constrain only Y; north/south edges constrain only X.
	# Normalising the two independent components after the roomy first pass keeps
	# multi-route maps aligned without forcing every connected room onto a single
	# line or discarding the collision spacing chosen above.
	var horizontal_components = _axis_components(rooms, ["east", "west"])
	var vertical_components = _axis_components(rooms, ["north", "south"])
	var ids = _sorted_valid_room_ids(rooms)
	var component_y := {}
	var component_x := {}

	for room_id in ids:
		var cell: Vector2i = cells[room_id]
		var horizontal = horizontal_components[room_id]
		var vertical = vertical_components[room_id]
		if not component_y.has(horizontal):
			component_y[horizontal] = cell.y
		if not component_x.has(vertical):
			component_x[vertical] = cell.x
	# Keep the compact coordinates selected by the directional walk. The former
	# lane pass reassigned every independent component to index * 2, causing
	# large maps to expand even when all direct exits were one cell apart.
	if not _resolve_component_collisions(ids, horizontal_components, vertical_components, component_y, component_x):
		return false

	var occupied := {}
	for room_id in ids:
		var cell: Vector2i = cells[room_id]
		cell.y = component_y[horizontal_components[room_id]]
		cell.x = component_x[vertical_components[room_id]]
		var key = _cell_key(cell)
		if occupied.has(key):
			# If two rooms share both components, their directional constraints are
			# contradictory.  Independent components were already given distinct
			# lanes above, so no amount of additional spacing can repair this case.
			return false
		occupied[key] = true
		cells[room_id] = cell
	return true

static func _resolve_component_collisions(ids: Array, horizontal_components: Dictionary, vertical_components: Dictionary, component_y: Dictionary, component_x: Dictionary) -> bool:
	# Only move a component when it would make two rooms share a cell.  Changing a
	# whole horizontal/vertical component preserves the cardinal row/column rules,
	# and probing +1/-1 first keeps the exception as close as possible.
	for attempt in range(ids.size() * 2):
		var occupied := {}
		var collision_room := ""
		for room_id in ids:
			var cell = Vector2i(component_x[vertical_components[room_id]], component_y[horizontal_components[room_id]])
			var key = _cell_key(cell)
			if occupied.has(key):
				collision_room = room_id
				break
			occupied[key] = room_id
		if collision_room == "":
			return true

		var horizontal = horizontal_components[collision_room]
		if _move_horizontal_component_to_nearest_free_lane(ids, collision_room, horizontal_components, vertical_components, component_y, component_x):
			continue
		var vertical = vertical_components[collision_room]
		if _move_vertical_component_to_nearest_free_lane(ids, collision_room, horizontal_components, vertical_components, component_y, component_x):
			continue
		return false
	return false

static func _move_horizontal_component_to_nearest_free_lane(ids: Array, room_id: String, horizontal_components: Dictionary, vertical_components: Dictionary, component_y: Dictionary, component_x: Dictionary) -> bool:
	var component = horizontal_components[room_id]
	var original = int(component_y[component])
	for distance in range(1, MAX_DIRECTIONAL_SEARCH + 1):
		for candidate in [original + distance, original - distance]:
			if _horizontal_component_fits(ids, component, candidate, horizontal_components, vertical_components, component_y, component_x):
				component_y[component] = candidate
				return true
	return false

static func _horizontal_component_fits(ids: Array, component, candidate_y: int, horizontal_components: Dictionary, vertical_components: Dictionary, component_y: Dictionary, component_x: Dictionary) -> bool:
	var occupied := {}
	for other_id in ids:
		if horizontal_components[other_id] == component:
			continue
		var cell = Vector2i(component_x[vertical_components[other_id]], component_y[horizontal_components[other_id]])
		occupied[_cell_key(cell)] = true
	for member_id in ids:
		if horizontal_components[member_id] != component:
			continue
		var cell = Vector2i(component_x[vertical_components[member_id]], candidate_y)
		if occupied.has(_cell_key(cell)):
			return false
		occupied[_cell_key(cell)] = true
	return true

static func _move_vertical_component_to_nearest_free_lane(ids: Array, room_id: String, horizontal_components: Dictionary, vertical_components: Dictionary, component_y: Dictionary, component_x: Dictionary) -> bool:
	var component = vertical_components[room_id]
	var original = int(component_x[component])
	for distance in range(1, MAX_DIRECTIONAL_SEARCH + 1):
		for candidate in [original + distance, original - distance]:
			if _vertical_component_fits(ids, component, candidate, horizontal_components, vertical_components, component_y, component_x):
				component_x[component] = candidate
				return true
	return false

static func _vertical_component_fits(ids: Array, component, candidate_x: int, horizontal_components: Dictionary, vertical_components: Dictionary, component_y: Dictionary, component_x: Dictionary) -> bool:
	var occupied := {}
	for other_id in ids:
		if vertical_components[other_id] == component:
			continue
		var cell = Vector2i(component_x[vertical_components[other_id]], component_y[horizontal_components[other_id]])
		occupied[_cell_key(cell)] = true
	for member_id in ids:
		if vertical_components[member_id] != component:
			continue
		var cell = Vector2i(candidate_x, component_y[horizontal_components[member_id]])
		if occupied.has(_cell_key(cell)):
			return false
		occupied[_cell_key(cell)] = true
	return true

static func can_preserve_cardinal_alignment(rooms: Dictionary) -> bool:
	# A room's final cell is the intersection of one east/west row component and
	# one north/south column component.  If two rooms require the same pair, the
	# authored graph has made incompatible directional claims and needs fallback.
	var horizontal_components = _axis_components(rooms, ["east", "west"])
	var vertical_components = _axis_components(rooms, ["north", "south"])
	var intersections := {}
	for room_id in _sorted_valid_room_ids(rooms):
		var intersection = "%s|%s" % [horizontal_components[room_id], vertical_components[room_id]]
		if intersections.has(intersection):
			return false
		intersections[intersection] = true
	return true

static func _axis_components(rooms: Dictionary, directions: Array) -> Dictionary:
	var parent := {}
	var ids = _sorted_valid_room_ids(rooms)
	for room_id in ids:
		parent[room_id] = room_id
	for room_id in ids:
		var exits = rooms[room_id].get("exits", {})
		if not exits is Dictionary:
			continue
		for direction in directions:
			if not exits.has(direction):
				continue
			var target_id = str(exits[direction])
			if parent.has(target_id):
				_union_components(parent, room_id, target_id)
	var components := {}
	for room_id in ids:
		components[room_id] = _find_component(parent, room_id)
	return components

static func _sorted_valid_room_ids(rooms: Dictionary) -> Array:
	var ids: Array = []
	for room_id in rooms:
		if rooms[room_id] is Dictionary:
			ids.append(str(room_id))
	ids.sort()
	return ids

static func _find_component(parent: Dictionary, room_id: String) -> String:
	var root = room_id
	while parent[root] != root:
		root = parent[root]
	var cursor = room_id
	while parent[cursor] != cursor:
		var next = parent[cursor]
		parent[cursor] = root
		cursor = next
	return root

static func _union_components(parent: Dictionary, first: String, second: String) -> void:
	var first_root = _find_component(parent, first)
	var second_root = _find_component(parent, second)
	if first_root != second_root:
		parent[second_root] = first_root

static func _find_layout_root(rooms: Dictionary) -> String:
	for room_id in rooms:
		if rooms[room_id] is Dictionary and rooms[room_id].get("properties", {}).get("is_start_node", false):
			return str(room_id)
	for room_id in rooms:
		if rooms[room_id] is Dictionary:
			return str(room_id)
	return ""

static func _layout_roots(rooms: Dictionary, start_id: String) -> Array:
	var roots: Array = [start_id]
	var remaining: Array = []
	for room_id in rooms:
		if str(room_id) != start_id and rooms[room_id] is Dictionary:
			remaining.append(str(room_id))
	remaining.sort()
	roots.append_array(remaining)
	return roots

static func _incoming_local_exits(rooms: Dictionary, target_id: String) -> Array:
	var incoming: Array = []
	for source_id in _sorted_valid_room_ids(rooms):
		var exits = rooms[source_id].get("exits", {})
		if not exits is Dictionary:
			continue
		for direction in exits:
			if str(exits[direction]) == target_id:
				incoming.append({"source": source_id, "direction": str(direction).to_lower()})
	incoming.sort_custom(func(a, b): return a["source"] < b["source"] or (a["source"] == b["source"] and a["direction"] < b["direction"]))
	return incoming

static func _ordered_exit_directions(exits: Dictionary) -> Array:
	var directions: Array = []
	for group in [CARDINAL_DIRECTIONS, SECONDARY_DIRECTIONS, IN_OUT_DIRECTIONS]:
		for direction in group:
			if exits.has(direction):
				directions.append(direction)
	var unknown: Array = []
	for direction in exits:
		var normalized := str(direction).to_lower()
		if not directions.has(normalized):
			unknown.append(normalized)
	unknown.sort()
	directions.append_array(unknown)
	return directions

static func _find_directional_cell(origin: Vector2i, direction: String, occupied: Dictionary, layout_hint: Dictionary = {}) -> Dictionary:
	var normalized := direction.to_lower()
	if normalized in IN_OUT_DIRECTIONS or not Constants.DIR_VECTORS.has(normalized):
		# If a prior run had to choose an adjacent fallback, preserve that visual
		# contract rather than repeatedly trying southeast and making the graph
		# shuffle as unrelated rooms are added.
		if layout_hint.get("placement", "") == "adjacent":
			var hinted_direction := str(layout_hint.get("visual_direction", ""))
			if Constants.DIR_VECTORS.has(hinted_direction):
				return _find_cell_along_direction(origin, hinted_direction, occupied)
		return _find_stacked_cell(origin, occupied)

	var vec: Vector2 = Constants.DIR_VECTORS.get(normalized, Vector2(1, 1))
	var step := Vector2i(int(sign(vec.x)), int(sign(vec.y)))
	if step == Vector2i.ZERO:
		step = Vector2i(1, 1)
	for distance in range(1, MAX_DIRECTIONAL_SEARCH + 1):
		var candidate: Vector2i = origin + step * distance
		if not occupied.has(_cell_key(candidate)):
			return {"cell": candidate}
	return {}

static func _find_cell_along_direction(origin: Vector2i, direction: String, occupied: Dictionary) -> Dictionary:
	var vec: Vector2 = Constants.DIR_VECTORS[direction]
	var step := Vector2i(int(sign(vec.x)), int(sign(vec.y)))
	if step == Vector2i.ZERO:
		step = Vector2i(1, 1)
	for distance in range(1, MAX_DIRECTIONAL_SEARCH + 1):
		var candidate := origin + step * distance
		if not occupied.has(_cell_key(candidate)):
			return {"cell": candidate}
	return {}

static func _find_stacked_cell(origin: Vector2i, occupied: Dictionary) -> Dictionary:
	# In/out and semantic exits such as "portal" are deliberately drawn as an
	# inner room: half a normal cell down and right of the parent.  Reserve the
	# next full cell as its logical anchor, so this visual offset can never put two
	# cards on top of each other. Additional ambiguous exits expand diagonally only
	# after the preferred stacked position is occupied.
	var fallback_slots = [Vector2i(1, 0), Vector2i(0, 1), Vector2i(-1, 0), Vector2i(0, -1), Vector2i(1, -1), Vector2i(-1, 1), Vector2i(-1, -1)]
	for distance in range(1, MAX_DIRECTIONAL_SEARCH + 1):
		var preferred := origin + Vector2i(distance, distance)
		if not occupied.has(_cell_key(preferred)):
			return {"cell": preferred, "visual_offset": Vector2(-0.5, -0.5)}
		# Dense maps can already use the southeast anchor. Fall back to the closest
		# available cell instead of abandoning the new layout entirely.
		for slot in fallback_slots:
			var candidate: Vector2i = origin + slot * distance
			if not occupied.has(_cell_key(candidate)):
				return {"cell": candidate}
	return {}

static func _cell_key(cell: Vector2i) -> String:
	return "%d:%d" % [cell.x, cell.y]

static func _safe_legacy_optimize_layout(rooms: Dictionary) -> Dictionary:
	# Contradictory authored directions still need a usable map. The historical
	# fallback may place two first-visited rooms on the same snapped coordinate,
	# so deconflict its result rather than returning overlapping cards.
	var result = _legacy_optimize_layout(rooms)
	var occupied := {}
	for room_id in _sorted_valid_room_ids(rooms):
		if not result.has(room_id):
			continue
		var position: Vector2 = result[room_id]
		while occupied.has(_position_key(position)):
			position += ROOM_SPACING
		result[room_id] = position
		occupied[_position_key(position)] = true
	return result

static func _position_key(position: Vector2) -> String:
	return "%d:%d" % [roundi(position.x), roundi(position.y)]

static func _legacy_optimize_layout(rooms: Dictionary) -> Dictionary:
	var result = {}
	var processed = {}
	var queue = []
	var spacing = Vector2(350, 250)
	
	# Use constants for direction mapping
	var vectors = Constants.DIR_VECTORS

	var start_id = _find_layout_root(rooms)
	if start_id == "": return {}

	var run_bfs = func(root_id, start_pos):
		if processed.has(root_id): return
		
		# Snap start position
		result[root_id] = start_pos.snapped(SNAP_GRID)
		processed[root_id] = true
		queue.append(root_id)
		
		while not queue.is_empty():
			var curr_id = queue.pop_front()
			var curr_pos = result[curr_id]
			var exits = rooms[curr_id].get("exits", {})
			
			for dir in exits:
				var target_id = exits[dir]
				if ":" in target_id or processed.has(target_id): continue
				if not rooms.has(target_id): continue
				
				# Get vector from constants, default to diagonal if unknown
				var vec = vectors.get(dir.to_lower(), Vector2(1, 1))
				
				# Calculate and Snap Target Position
				var raw_target_pos = curr_pos + (vec * spacing)
				result[target_id] = raw_target_pos.snapped(SNAP_GRID)
				
				processed[target_id] = true
				queue.append(target_id)

	run_bfs.call(start_id, Vector2.ZERO)
	
	# Handle disconnected islands
	var island_offset = Vector2(0, 600)
	for id in rooms:
		if not processed.has(id): 
			run_bfs.call(id, island_offset)
			island_offset.y += 600
			
	return result

static func optimize_world_layout(all_data: Dictionary) -> Dictionary:
	var region_sizes = {}
	var region_centers = {} 
	var connections = {}
	var positions = {} 
	var placed_rects = [] 
	
	# --- 1. ANALYZE REGIONS ---
	for rid in all_data:
		var r_data = all_data[rid]
		var rooms = r_data.get("rooms", {})
		connections[rid] = []
		
		var min_p = Vector2(INF, INF)
		var max_p = Vector2(-INF, -INF)
		var has_rooms = false
		
		for room_id in rooms:
			var ep = rooms[room_id].get("_editor_pos", [0, 0])
			var p = Vector2(ep[0], ep[1])
			min_p.x = min(min_p.x, p.x)
			min_p.y = min(min_p.y, p.y)
			max_p.x = max(max_p.x, p.x)
			max_p.y = max(max_p.y, p.y)
			has_rooms = true
			
			var exits = rooms[room_id].get("exits", {})
			for dir in exits:
				var target = exits[dir]
				if ":" in target:
					var parts = target.split(":")
					var target_rid = parts[0]
					if target_rid != rid:
						connections[rid].append({
							"target": target_rid, 
							"dir": dir,
							"vec": _dir_to_vec(dir)
						})
		
		if has_rooms:
			var size = (max_p - min_p) + Vector2(250, 250)
			region_sizes[rid] = size
			region_centers[rid] = (min_p + max_p) / 2.0
		else:
			region_sizes[rid] = Vector2(500, 500)
			region_centers[rid] = Vector2(250, 250)

	# --- 2. PLACEMENT LOOP ---
	var nodes_to_process = all_data.keys()
	var island_start_x = 0.0 
	
	while not nodes_to_process.is_empty():
		var start_node = ""
		if "town" in nodes_to_process: start_node = "town"
		else: start_node = nodes_to_process[0]
			
		nodes_to_process.erase(start_node)
		
		var start_pos = Vector2(island_start_x, 0)
		positions[start_node] = start_pos.snapped(SNAP_GRID)
		
		var s_size = region_sizes[start_node]
		var s_rect_origin = start_pos + region_centers[start_node] - s_size/2.0
		var s_rect = Rect2(s_rect_origin, s_size)
		placed_rects.append(s_rect)
		
		var queue = [start_node]
		var processed_in_island = {start_node: true}
		
		while not queue.is_empty():
			var curr_id = queue.pop_front()
			var curr_pos = positions[curr_id]
			
			for conn in connections.get(curr_id, []):
				var neighbor = conn.target
				if positions.has(neighbor): continue
				if not region_sizes.has(neighbor): continue
				
				processed_in_island[neighbor] = true
				if neighbor in nodes_to_process: nodes_to_process.erase(neighbor)
				queue.append(neighbor)
				
				var dir_vec = conn.vec
				if dir_vec == Vector2.ZERO: dir_vec = Vector2(1, 0)
				
				var my_size = region_sizes[curr_id]
				var their_size = region_sizes[neighbor]
				
				var dist = (abs(dir_vec.x) * (my_size.x + their_size.x) + abs(dir_vec.y) * (my_size.y + their_size.y)) * 0.55
				dist = max(dist, 600.0)
				
				var placed = false
				var angle_attempts = [0, PI/6, -PI/6, PI/4, -PI/4, PI/2, -PI/2]
				
				for ang in angle_attempts:
					var rot_vec = dir_vec.rotated(ang)
					var test_pos = curr_pos + (rot_vec * dist)
					test_pos = test_pos.snapped(SNAP_GRID) # Snap calculated position
					
					var test_rect_origin = test_pos + region_centers[neighbor] - their_size/2.0
					var test_rect = Rect2(test_rect_origin, their_size)
					
					var overlap = false
					for r in placed_rects:
						if r.grow(-50).intersects(test_rect.grow(-50)):
							overlap = true
							break
					
					if not overlap:
						positions[neighbor] = test_pos
						placed_rects.append(test_rect)
						placed = true
						break
				
				if not placed:
					var fallback_pos = curr_pos + (dir_vec * (dist * 1.5))
					positions[neighbor] = fallback_pos.snapped(SNAP_GRID)
					var fallback_rect_origin = positions[neighbor] + region_centers[neighbor] - their_size/2.0
					var fallback_rect = Rect2(fallback_rect_origin, their_size)
					placed_rects.append(fallback_rect)

		var max_x = island_start_x
		for r in placed_rects:
			if r.end.x > max_x:
				max_x = r.end.x
		
		island_start_x = max_x + 800.0

	return positions

static func _dir_to_vec(d: String) -> Vector2:
	return Constants.DIR_VECTORS.get(d.to_lower(), Vector2(1,0))
