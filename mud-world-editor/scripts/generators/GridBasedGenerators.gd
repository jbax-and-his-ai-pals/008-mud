# scripts/generators/GridBasedGenerators.gd
class_name GridBasedGenerators
extends RefCounted

static func generate_grid(p: Dictionary):
	var rows = int(p.get("rows", 10)); var cols = int(p.get("cols", 10)); var r_density = p.get("room_density", 0.5); var c_density = p.get("conn_density", 0.5)
	var rooms = {}; var grid_map = {} 
	for y in range(cols):
		for x in range(rows):
			if randf() < r_density:
				var pos = Vector2i(x, y); _add_grid_room(rooms, grid_map, pos, "Area")
	_connect_grid_neighbors(rooms, grid_map, c_density)
	return RegionGenerator.keep_largest_island(rooms)

static func generate_maze(p: Dictionary):
	var rows = int(p.get("rows", 10)); var cols = int(p.get("cols", 10)); var loop_chance = p.get("conn_density", 0.0)
	var rooms = {}; var visited = {}; var stack = []; var room_map = {}
	
	var get_or_create = func(pos: Vector2i):
		if not room_map.has(pos):
			var id = "maze_%d_%d" % [pos.x, pos.y]; rooms[id] = RegionGenerator.make_room("Maze", Vector2(pos) * RegionGenerator.CELL_SIZE); room_map[pos] = id
		return room_map[pos]
	
	var start_pos = Vector2i(randi_range(0, rows-1), randi_range(0, cols-1))
	stack.append(start_pos); visited[start_pos] = true; get_or_create.call(start_pos)
	
	# Include diagonals in maze traversal
	var dirs = [
		Vector2i(0, -1), Vector2i(0, 1), Vector2i(1, 0), Vector2i(-1, 0),
		Vector2i(1, 1), Vector2i(1, -1), Vector2i(-1, 1), Vector2i(-1, -1)
	]
	
	while not stack.is_empty():
		var curr = stack.back(); var neighbors = []
		for d in dirs:
			var n = curr + d
			if n.x >= 0 and n.x < rows and n.y >= 0 and n.y < cols and not visited.has(n): neighbors.append(d)
			
		if neighbors.is_empty(): stack.pop_back()
		else:
			var dir = neighbors[randi() % neighbors.size()]
			var next = curr + dir; visited[next] = true; stack.append(next)
			_link_rooms(rooms, get_or_create.call(curr), get_or_create.call(next), Vector2(dir))
	
	if loop_chance > 0.0:
		for pos in room_map:
			var id = room_map[pos]
			# Try linking to any adjacent neighbor not already linked
			for d in dirs:
				var n = pos + d
				if room_map.has(n) and not rooms[id].exits.has(RegionGenerator.get_dir_from_vec(Vector2(d))):
					if randf() < loop_chance: _link_rooms(rooms, id, room_map[n], Vector2(d))
	return rooms

static func generate_cavern(p: Dictionary):
	var w = int(p.get("rows", 20)); var h = int(p.get("cols", 20)); var fill_prob = p.get("room_density", 0.45) 
	var grid = []; for x in range(w): grid.append([]); for y in range(h): grid[x].append(randf() < fill_prob)
	for s in range(4): 
		var new_grid = grid.duplicate(true)
		for x in range(1, w-1):
			for y in range(1, h-1):
				var neighbors = 0
				for i in range(-1, 2):
					for j in range(-1, 2):
						if i == 0 and j == 0: continue
						if grid[x+i][y+j]: neighbors += 1
				if grid[x][y]: new_grid[x][y] = (neighbors >= 4)
				else: new_grid[x][y] = (neighbors >= 5)
		grid = new_grid
	var rooms = {}; var grid_map = {}
	for x in range(w):
		for y in range(h):
			if grid[x][y]: _add_grid_room(rooms, grid_map, Vector2i(x,y), "Cavern")
	_connect_grid_neighbors(rooms, grid_map, p.get("conn_density", 0.8))
	return RegionGenerator.keep_largest_island(rooms)

static func generate_sector(p: Dictionary):
	var w = int(p.get("rows", 20)); var h = int(p.get("cols", 20)); var min_size = lerp(8, 3, p.get("room_density", 0.5))
	var rooms = {}; var grid_map = {}; var rects = [Rect2i(0, 0, w, h)]; var final_sectors = []
	while not rects.is_empty():
		var r = rects.pop_front()
		if r.size.x <= min_size or r.size.y <= min_size or randf() < 0.1: final_sectors.append(r); continue
		var split_horz = r.size.x > r.size.y; if r.size.x == r.size.y: split_horz = (randf() > 0.5)
		if split_horz:
			var split = randi_range(int(r.size.x * 0.4), int(r.size.x * 0.6))
			rects.append(Rect2i(r.position.x, r.position.y, split, r.size.y))
			rects.append(Rect2i(r.position.x + split, r.position.y, r.size.x - split, r.size.y))
		else:
			var split = randi_range(int(r.size.y * 0.4), int(r.size.y * 0.6))
			rects.append(Rect2i(r.position.x, r.position.y, r.size.x, split))
			rects.append(Rect2i(r.position.x, r.position.y + split, r.size.x, r.size.y - split))
	
	# Create Rooms
	for i in range(final_sectors.size()):
		var r = final_sectors[i].grow(-1)
		for x in range(r.position.x, r.end.x):
			for y in range(r.position.y, r.end.y):
				var pos = Vector2i(x, y)
				_add_grid_room(rooms, grid_map, pos, "Sector %d" % i)
				
				# Intra-sector connections (Card + Diag)
				var stitch_dirs = [Vector2i(-1,0), Vector2i(0,-1), Vector2i(-1,-1), Vector2i(1,-1)]
				for d in stitch_dirs:
					if grid_map.has(pos + d): _link_rooms(rooms, grid_map[pos], grid_map[pos+d], Vector2(d))

	# Connect Sectors (Path Walking)
	for i in range(len(final_sectors) - 1):
		var p1 = final_sectors[i].get_center(); var p2 = final_sectors[i+1].get_center()
		var cursor = Vector2i(p1)
		var end_pos = Vector2i(p2)
		
		while cursor != end_pos:
			# Diagonal Walk
			var dx = sign(end_pos.x - cursor.x)
			var dy = sign(end_pos.y - cursor.y)
			cursor += Vector2i(dx, dy)
			
			if not grid_map.has(cursor): _add_grid_room(rooms, grid_map, cursor, "Hallway")
			_connect_grid_neighbors(rooms, {cursor: grid_map[cursor]}, 1.0) # Local density
			
	return RegionGenerator.keep_largest_island(rooms)
	
static func generate_target(p: Dictionary):
	var ring_count = int(p.get("rows", 3)); var spacing = int(p.get("cols", 2)); var bridge_prob = p.get("conn_density", 0.5)
	if spacing < 1: spacing = 1
	var rooms = {}; var grid_map = {}
	var prev_ring_nodes = []
	
	# Center
	prev_ring_nodes.append(_add_grid_room(rooms, grid_map, Vector2i(0,0), "Bullseye"))
	
	for r in range(1, ring_count + 1):
		var current_ring_nodes = []
		var radius = r * (spacing + 1)
		
		# Build Perimeter
		for i in range(-radius, radius + 1):
			var pts = [Vector2i(i, -radius), Vector2i(i, radius), Vector2i(-radius, i), Vector2i(radius, i)]
			for pos in pts:
				if not grid_map.has(pos):
					current_ring_nodes.append(_add_grid_room(rooms, grid_map, pos, "Ring %d" % r))

		# Link Ring Internally (Including Diagonals)
		for id in current_ring_nodes:
			var pos = Vector2i( (Vector2(rooms[id]._editor_pos[0], rooms[id]._editor_pos[1]) / RegionGenerator.CELL_SIZE).round() )
			var neighbors = [
				Vector2i(1,0), Vector2i(-1,0), Vector2i(0,1), Vector2i(0,-1),
				Vector2i(1,1), Vector2i(1,-1), Vector2i(-1,1), Vector2i(-1,-1)
			]
			for n in neighbors:
				if grid_map.has(pos+n):
					var nid = grid_map[pos+n]
					if rooms[nid].name.begins_with("Ring %d" % r):
						_link_rooms(rooms, id, nid, Vector2(n))

		# Bridges to previous ring (Diagonal Walking Path)
		var bridges_count = 1 + int(bridge_prob * 4)
		for _b in range(bridges_count):
			var start_id = prev_ring_nodes.pick_random()
			var end_id = current_ring_nodes.pick_random()
			var s_pos = Vector2i( (Vector2(rooms[start_id]._editor_pos[0], rooms[start_id]._editor_pos[1]) / RegionGenerator.CELL_SIZE).round() )
			var e_pos = Vector2i( (Vector2(rooms[end_id]._editor_pos[0], rooms[end_id]._editor_pos[1]) / RegionGenerator.CELL_SIZE).round() )
			
			var cursor = s_pos
			var last_id = start_id
			
			while cursor != e_pos:
				# Chebyshev step
				var dx = sign(e_pos.x - cursor.x)
				var dy = sign(e_pos.y - cursor.y)
				var move = Vector2i(dx, dy)
				
				cursor += move
				
				var next_id = _add_grid_room(rooms, grid_map, cursor, "Bridge")
				_link_rooms(rooms, last_id, next_id, Vector2(move))
				last_id = next_id
				
		prev_ring_nodes = current_ring_nodes
		
	return rooms

static func _add_grid_room(rooms, grid_map, pos, prefix): return RegionGenerator.add_grid_room(rooms, grid_map, pos, prefix)
static func _connect_grid_neighbors(rooms, grid_map, density): RegionGenerator.connect_grid_neighbors(rooms, grid_map, density)
static func _link_rooms(rooms, id_a, id_b, vec): RegionGenerator.link_rooms(rooms, id_a, id_b, vec)
