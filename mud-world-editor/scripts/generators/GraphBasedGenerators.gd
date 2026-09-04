# scripts/generators/GraphBasedGenerators.gd
class_name GraphBasedGenerators
extends RefCounted

static func generate_hub(p: Dictionary):
	var tendril_len = int(p.get("rows", 10)); var branch_chance = p.get("room_density", 0.5); var c_density = p.get("conn_density", 0.5)
	var rooms = {}; var grid_map = {}
	var center_id = _add_grid_room(rooms, grid_map, Vector2i(0, 0), "The Hub")
	var start_nodes = []
	
	# 8-Way Neighbors for initial circle
	var neighbor_offsets = [
		Vector2i(0,-1), Vector2i(0,1), Vector2i(1,0), Vector2i(-1,0), 
		Vector2i(1,1), Vector2i(-1,1), Vector2i(1,-1), Vector2i(-1,-1)
	]
	
	for n in neighbor_offsets:
		var id = _add_grid_room(rooms, grid_map, n, "Inner Circle")
		_link_rooms(rooms, center_id, id, Vector2(n)); start_nodes.append(id)

	for start_id in start_nodes:
		var start_pos = Vector2i((Vector2(rooms[start_id]._editor_pos[0], rooms[start_id]._editor_pos[1]) / RegionGenerator.CELL_SIZE).round())
		var curr_pos = start_pos; var curr_id = start_id; var main_dir = start_pos
		for i in range(randi_range(tendril_len / 2, tendril_len)):
			var next_pos = curr_pos + main_dir
			if grid_map.has(next_pos): break
			var next_id = _add_grid_room(rooms, grid_map, next_pos, "Tendril")
			_link_rooms(rooms, curr_id, next_id, Vector2(main_dir))
			curr_pos = next_pos; curr_id = next_id
			if randf() < branch_chance:
				var spur_pos = curr_pos + neighbor_offsets.pick_random()
				if not grid_map.has(spur_pos):
					var spur_id = _add_grid_room(rooms, grid_map, spur_pos, "Spur")
					_link_rooms(rooms, curr_id, spur_id, Vector2(spur_pos - curr_pos))
	_connect_grid_neighbors(rooms, grid_map, c_density)
	return RegionGenerator.keep_largest_island(rooms)

static func generate_crescent(p: Dictionary):
	var size = int(p.get("rows", 15)); var rotation_deg = int(p.get("cols", 0)); var thickness = p.get("room_density", 0.5); var c_density = p.get("conn_density", 0.5)
	var rooms = {}; var grid_map = {}
	var radius_outer = size / 2.0; var radius_inner = radius_outer * (1.0 - thickness)
	var rot_rad = deg_to_rad(rotation_deg); var target_angle = Vector2.RIGHT.rotated(rot_rad).angle()
	for x in range(-size, size + 1):
		for y in range(-size, size + 1):
			var pos = Vector2(x, y); var dist = pos.length()
			if dist <= radius_outer and dist >= radius_inner:
				if abs(angle_difference(pos.angle(), target_angle)) < (PI * 0.6):
					_add_grid_room(rooms, grid_map, Vector2i(x, y), "Crescent")
	_connect_grid_neighbors(rooms, grid_map, c_density)
	return RegionGenerator.keep_largest_island(rooms)
	
static func generate_ring(p: Dictionary):
	var size = int(p.get("rows", 15)); var thickness = p.get("room_density", 0.5); var c_density = p.get("conn_density", 0.5)
	var rooms = {}; var grid_map = {}
	var radius_outer = size / 2.0; var radius_inner = radius_outer * (1.0 - thickness)
	for x in range(-size, size + 1):
		for y in range(-size, size + 1):
			var dist = Vector2(x, y).length()
			if dist <= radius_outer and dist >= radius_inner: _add_grid_room(rooms, grid_map, Vector2i(x, y), "Ring")
	_connect_grid_neighbors(rooms, grid_map, c_density)
	return RegionGenerator.keep_largest_island(rooms)

static func generate_fractal(p: Dictionary):
	var room_count = int(p.get("rows", 30)); var branches = int(p.get("cols", 2)); var cross_connect = p.get("conn_density", 0.1)
	var rooms = {}; var grid_map = {}; var q = []
	var root_id = _add_grid_room(rooms, grid_map, Vector2i.ZERO, "Root"); q.append(root_id)
	
	var created_count = 1
	while not q.is_empty() and created_count < room_count:
		var parent_id = q.pop_front()
		var parent_pos = Vector2i( (Vector2(rooms[parent_id]._editor_pos[0], rooms[parent_id]._editor_pos[1]) / RegionGenerator.CELL_SIZE).round() )
		
		for i in range(branches):
			if created_count >= room_count: break
			
			var angle = randf_range(0, TAU)
			var dist = randf_range(2.0, 5.0)
			var target_pos = parent_pos + Vector2i( (Vector2.RIGHT.rotated(angle) * dist).round() )
			
			# Chebyshev Walk (Diagonal enabled)
			var cursor = parent_pos
			var last_id = parent_id
			
			while cursor != target_pos:
				var dx = sign(target_pos.x - cursor.x)
				var dy = sign(target_pos.y - cursor.y)
				var move = Vector2i(dx, dy)
				
				cursor += move
				
				var next_id = _add_grid_room(rooms, grid_map, cursor, "Branch")
				_link_rooms(rooms, last_id, next_id, Vector2(move))
				last_id = next_id
				
			if not q.has(last_id):
				q.append(last_id)
				created_count += 1

	if cross_connect > 0:
		_connect_grid_neighbors(rooms, grid_map, cross_connect)
	return RegionGenerator.keep_largest_island(rooms)

static func _add_grid_room(rooms, grid_map, pos, prefix): return RegionGenerator.add_grid_room(rooms, grid_map, pos, prefix)
static func _connect_grid_neighbors(rooms, grid_map, density): RegionGenerator.connect_grid_neighbors(rooms, grid_map, density)
static func _link_rooms(rooms, id_a, id_b, vec): RegionGenerator.link_rooms(rooms, id_a, id_b, vec)
