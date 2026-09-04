# scripts/generators/LayoutOptimizer.gd
class_name LayoutOptimizer
extends RefCounted

const SNAP_GRID = Vector2(32, 32)

static func optimize_layout(rooms: Dictionary) -> Dictionary:
	var result = {}
	var processed = {}
	var queue = []
	var spacing = Vector2(350, 250) 
	
	# Use constants for direction mapping
	var vectors = Constants.DIR_VECTORS

	var start_id = ""
	for id in rooms:
		if not rooms[id] is Dictionary: continue # Skip malformed data
		if rooms[id].get("properties", {}).get("is_start_node", false): start_id = id; break
	if start_id == "" and not rooms.is_empty(): start_id = rooms.keys()[0]
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
