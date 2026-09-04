# scripts/generators/StructureGenerators.gd
class_name StructureGenerators
extends RefCounted

# --- HOUSE ALGORITHM ---
static func generate_house(p: Dictionary):
	var count = int(p.get("rows", 10))
	var complexity = int(p.get("cols", 2))
	var loops = p.get("conn_density", 0.2)
	
	var rooms = {}; var grid_map = {}
	var center_pos = Vector2i(0,0)
	var center_id = RegionGenerator.add_grid_room(rooms, grid_map, center_pos, "Entry Hall")
	
	var queue = [center_id]
	var current_count = 1
	var neighbor_offsets = [Vector2i(1,0), Vector2i(-1,0), Vector2i(0,1), Vector2i(0,-1), Vector2i(1,1), Vector2i(1,-1), Vector2i(-1,1), Vector2i(-1,-1)]
	
	while not queue.is_empty() and current_count < count:
		var curr_id = queue.pop_front()
		var curr_pos = Vector2i( (Vector2(rooms[curr_id]._editor_pos[0], rooms[curr_id]._editor_pos[1]) / RegionGenerator.CELL_SIZE).round() )
		
		var dirs = neighbor_offsets.duplicate()
		dirs.shuffle()
		
		var extensions = randi_range(1, complexity)
		for i in range(extensions):
			if dirs.is_empty() or current_count >= count: break
			var d = dirs.pop_back()
			var next_pos = curr_pos + d
			
			if not grid_map.has(next_pos):
				var type = "Room"
				if randf() < 0.3: type = "Hallway"
				elif randf() < 0.5: type = "Bedroom"
				
				var next_id = RegionGenerator.add_grid_room(rooms, grid_map, next_pos, type)
				RegionGenerator.link_rooms(rooms, curr_id, next_id, Vector2(d))
				queue.append(next_id)
				current_count += 1
			elif randf() < loops:
				RegionGenerator.link_rooms(rooms, curr_id, grid_map[next_pos], Vector2(d))
				
	return rooms

# --- TOWN ALGORITHM ---
static func generate_town(p: Dictionary):
	var road_len = int(p.get("rows", 20))
	var branches = int(p.get("cols", 5))
	var b_density = p.get("room_density", 0.7)
	var alley_prob = p.get("conn_density", 0.3)
	
	var rooms = {}; var grid_map = {}
	var road_nodes = []
	
	var cursor = Vector2i(0,0)
	var dir = Vector2i(1,0)
	var last_id = RegionGenerator.add_grid_room(rooms, grid_map, cursor, "Town Gate")
	road_nodes.append(cursor)
	
	for i in range(road_len):
		if randf() < 0.3:
			var options = [Vector2i(1,0), Vector2i(1,1), Vector2i(1,-1)]
			dir = options.pick_random()
		
		cursor += dir
		if not grid_map.has(cursor):
			var new_id = RegionGenerator.add_grid_room(rooms, grid_map, cursor, "Main St.")
			var vec = Vector2(cursor - Vector2i((Vector2(rooms[last_id]._editor_pos[0], rooms[last_id]._editor_pos[1]) / RegionGenerator.CELL_SIZE).round()))
			RegionGenerator.link_rooms(rooms, last_id, new_id, vec)
			last_id = new_id
			road_nodes.append(cursor)
		else:
			last_id = grid_map[cursor]

	for b in range(branches):
		var start_pos = road_nodes.pick_random()
		var branch_dir = Vector2i(0,1) if randf() < 0.5 else Vector2i(0,-1)
		if randf() < 0.3: branch_dir = Vector2i(1,1) if randf() < 0.5 else Vector2i(-1,1)
		
		var b_cursor = start_pos
		var b_last = grid_map[start_pos]
		
		for k in range(randi_range(3, 8)):
			b_cursor += branch_dir
			if not grid_map.has(b_cursor):
				var b_id = RegionGenerator.add_grid_room(rooms, grid_map, b_cursor, "Side St.")
				var vec = Vector2(b_cursor - Vector2i((Vector2(rooms[b_last]._editor_pos[0], rooms[b_last]._editor_pos[1]) / RegionGenerator.CELL_SIZE).round()))
				RegionGenerator.link_rooms(rooms, b_last, b_id, vec)
				b_last = b_id
				road_nodes.append(b_cursor)
			else:
				b_last = grid_map[b_cursor]

	var neighbors = [Vector2i(1,0), Vector2i(-1,0), Vector2i(0,1), Vector2i(0,-1), Vector2i(1,1), Vector2i(1,-1), Vector2i(-1,1), Vector2i(-1,-1)]
	
	for r_pos in road_nodes:
		for n in neighbors:
			if not grid_map.has(r_pos + n):
				if randf() < b_density:
					var house_id = RegionGenerator.add_grid_room(rooms, grid_map, r_pos + n, "House")
					RegionGenerator.link_rooms(rooms, grid_map[r_pos], house_id, Vector2(n))
			elif alley_prob > 0 and randf() < alley_prob:
				var neighbor_id = grid_map[r_pos + n]
				var r_id = grid_map[r_pos]
				var dir_str = RegionGenerator.get_dir_from_vec(Vector2(n))
				if not rooms[r_id].exits.has(dir_str):
					RegionGenerator.link_rooms(rooms, r_id, neighbor_id, Vector2(n))

	return RegionGenerator.keep_largest_island(rooms)

# --- CITY ALGORITHM (Revamped) ---
static func generate_city(p: Dictionary):
	var scale = int(p.get("rows", 25)) # Area Scale
	var district_count = int(p.get("cols", 5)) # Number of districts
	var density = p.get("room_density", 0.8)
	var winding = p.get("conn_density", 0.3)
	
	var rooms = {}; var grid_map = {}
	var districts = [] # List of Rect2i
	
	# 1. Place Districts
	var attempts = 0
	while districts.size() < district_count and attempts < 100:
		attempts += 1
		var rx = randi_range(-scale/2, scale/2)
		var ry = randi_range(-scale/2, scale/2)
		var w = randi_range(4, 8)
		var h = randi_range(4, 8)
		var rect = Rect2i(rx, ry, w, h)
		
		var overlap = false
		for other in districts:
			if rect.intersects(other.grow(1)):
				overlap = true; break
		
		if not overlap: districts.append(rect)
			
	if districts.is_empty(): districts.append(Rect2i(-5, -5, 10, 10))
		
	# 2. Rasterize Districts
	for r in districts:
		for x in range(r.position.x, r.end.x):
			for y in range(r.position.y, r.end.y):
				var pos = Vector2i(x,y)
				if randf() < density:
					var type = "Building"
					if x == r.position.x or x == r.end.x - 1 or y == r.position.y or y == r.end.y - 1:
						if randf() < 0.5: type = "Street"
					RegionGenerator.add_grid_room(rooms, grid_map, pos, type)
		
		# Internally connect the district
		RegionGenerator.connect_grid_neighbors(rooms, grid_map, 1.0)

	# 3. Connect Districts with Paths
	for i in range(districts.size() - 1):
		var start_pos = Vector2i(districts[i].get_center())
		var end_pos = Vector2i(districts[i+1].get_center())
		var cursor = start_pos
		
		var steps = 0
		while cursor != end_pos and steps < 1000:
			steps += 1
			var dx = sign(end_pos.x - cursor.x)
			var dy = sign(end_pos.y - cursor.y)
			
			var move = Vector2i.ZERO
			if dx != 0 and dy != 0:
				if randf() < 0.5: move = Vector2i(dx, 0)
				else: move = Vector2i(0, dy)
			elif dx != 0: move = Vector2i(dx, 0)
			else: move = Vector2i(0, dy)
			
			if randf() < winding:
				var axes = [Vector2i(1,0), Vector2i(-1,0), Vector2i(0,1), Vector2i(0,-1)]
				move = axes.pick_random()
			
			cursor += move
			
			if not grid_map.has(cursor):
				var _r_id = RegionGenerator.add_grid_room(rooms, grid_map, cursor, "Road")
				_connect_to_neighbors(rooms, grid_map, cursor)
			else:
				# Ensure existing nodes connect to the path
				_connect_to_neighbors(rooms, grid_map, cursor)

	return RegionGenerator.keep_largest_island(rooms)

# --- CASTLE ALGORITHM (Revamped) ---
static func generate_castle(p: Dictionary):
	var wall_size = int(p.get("rows", 20))
	var keep_size = int(p.get("cols", 6))
	var tower_freq = p.get("room_density", 0.3)
	var yard_density = p.get("conn_density", 0.3) # Buildings freq
	
	if keep_size >= wall_size: keep_size = wall_size - 4
	if keep_size < 2: keep_size = 2
	
	var rooms = {}; var grid_map = {}
	var center = Vector2i(wall_size/2, wall_size/2)
	
	# 1. Keep
	var keep_start = center - Vector2i(keep_size/2, keep_size/2)
	var keep_end = keep_start + Vector2i(keep_size, keep_size)
	var keep_rect = Rect2i(keep_start, Vector2i(keep_size, keep_size))
	
	for x in range(keep_start.x, keep_end.x):
		for y in range(keep_start.y, keep_end.y):
			var type = "Keep Hall"
			if x == keep_start.x or x == keep_end.x - 1 or y == keep_start.y or y == keep_end.y - 1:
				type = "Keep Wall"
			RegionGenerator.add_grid_room(rooms, grid_map, Vector2i(x,y), type)
			
	RegionGenerator.connect_grid_neighbors(rooms, grid_map, 1.0)
	
	# 2. Outer Wall
	for x in range(wall_size):
		for y in range(wall_size):
			if x == 0 or x == wall_size - 1 or y == 0 or y == wall_size - 1:
				var pos = Vector2i(x,y)
				var type = "Wall"
				if (x==0 or x==wall_size-1) and (y==0 or y==wall_size-1): type = "Tower"
				elif randf() < tower_freq: type = "Tower"
				RegionGenerator.add_grid_room(rooms, grid_map, pos, type)
				
	for i in range(wall_size):
		_safe_link(rooms, grid_map, Vector2i(i, 0), Vector2i(i+1, 0))
		_safe_link(rooms, grid_map, Vector2i(i, wall_size-1), Vector2i(i+1, wall_size-1))
		_safe_link(rooms, grid_map, Vector2i(0, i), Vector2i(0, i+1))
		_safe_link(rooms, grid_map, Vector2i(wall_size-1, i), Vector2i(wall_size-1, i+1))

	# 3. Gatehouse & Main Path
	var gate_x = wall_size / 2
	var gate_pos = Vector2i(gate_x, wall_size - 1)
	if grid_map.has(gate_pos):
		rooms[grid_map[gate_pos]].name = "Gatehouse"
		var cursor = gate_pos + Vector2i(0, -1)
		var keep_entry_y = keep_end.y
		
		while cursor.y >= keep_entry_y:
			var pid = RegionGenerator.add_grid_room(rooms, grid_map, cursor, "Courtyard Path")
			if grid_map.has(cursor + Vector2i(0,1)):
				RegionGenerator.link_rooms(rooms, grid_map[cursor + Vector2i(0,1)], pid, Vector2.UP)
			cursor.y -= 1
			
		if grid_map.has(cursor):
			RegionGenerator.link_rooms(rooms, grid_map[cursor + Vector2i(0,1)], grid_map[cursor], Vector2.UP)

	# 4. Outbuildings
	var num_buildings = int(yard_density * 10) + 1
	for b in range(num_buildings):
		var w = randi_range(2, 4); var h = randi_range(2, 4)
		var bx = randi_range(2, wall_size - 2 - w)
		var by = randi_range(2, wall_size - 2 - h)
		var b_rect = Rect2i(bx, by, w, h)
		
		# Avoid Keep and Main Path area
		if b_rect.intersects(keep_rect.grow(1)): continue
		if b_rect.has_point(Vector2i(gate_x, by)) or b_rect.has_point(Vector2i(gate_x, by+h)): continue
		
		for x in range(b_rect.position.x, b_rect.end.x):
			for y in range(b_rect.position.y, b_rect.end.y):
				var pos = Vector2i(x,y)
				if not grid_map.has(pos):
					RegionGenerator.add_grid_room(rooms, grid_map, pos, "Barracks" if randf()<0.5 else "Stable")
					_connect_to_neighbors(rooms, grid_map, pos)
		
		# Path to nearest wall/path
		var center_i = Vector2i(b_rect.get_center())
		var d_l = center_i.x; var d_r = wall_size-1-center_i.x; var d_t = center_i.y; var d_b = wall_size-1-center_i.y
		var m = min(d_l, d_r, d_t, d_b)
		var dir = Vector2i(-1,0) if m==d_l else (Vector2i(1,0) if m==d_r else (Vector2i(0,-1) if m==d_t else Vector2i(0,1)))
		
		var cursor = center_i
		while true:
			cursor += dir
			if cursor.x <= 0 or cursor.x >= wall_size-1 or cursor.y <= 0 or cursor.y >= wall_size-1: break
			
			if not grid_map.has(cursor):
				RegionGenerator.add_grid_room(rooms, grid_map, cursor, "Path")
				_connect_to_neighbors(rooms, grid_map, cursor)
			else:
				var hit_id = grid_map[cursor]
				if grid_map.has(cursor - dir):
					RegionGenerator.link_rooms(rooms, grid_map[cursor - dir], hit_id, Vector2(dir))
				break

	return RegionGenerator.keep_largest_island(rooms)

static func _connect_to_neighbors(rooms, grid_map, pos):
	var neighbors = [Vector2i(1,0), Vector2i(-1,0), Vector2i(0,1), Vector2i(0,-1)]
	var my_id = grid_map[pos]
	for n in neighbors:
		if grid_map.has(pos + n):
			RegionGenerator.link_rooms(rooms, my_id, grid_map[pos+n], Vector2(n))

static func _safe_link(rooms, grid, p1, p2):
	if grid.has(p1) and grid.has(p2):
		RegionGenerator.link_rooms(rooms, grid[p1], grid[p2], Vector2(p2-p1))
