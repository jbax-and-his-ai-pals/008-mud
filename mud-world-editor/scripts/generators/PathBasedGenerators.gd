# scripts/generators/PathBasedGenerators.gd
class_name PathBasedGenerators
extends RefCounted

static func generate_highway(p: Dictionary):
	var length = int(p.get("rows", 20)); var rotation = int(p.get("cols", 0)); var town_freq = p.get("room_density", 0.3); var winding = p.get("conn_density", 0.5)
	var rooms = {}; var grid_map = {}
	var dir_vec = Vector2.RIGHT.rotated(deg_to_rad(rotation)); var cursor_float = Vector2.ZERO
	var all_neighbors = [Vector2i(-1,0), Vector2i(1,0), Vector2i(0,-1), Vector2i(0,1), Vector2i(-1,-1), Vector2i(1,1), Vector2i(-1,1), Vector2i(1,-1)]
	
	for i in range(length):
		var pos_i = Vector2i(cursor_float.round())
		_add_grid_room(rooms, grid_map, pos_i, "Highway")
		for n in all_neighbors:
			if grid_map.has(pos_i + n):
				_link_rooms(rooms, grid_map[pos_i], grid_map[pos_i + n], Vector2(n))

		if randf() < town_freq:
			for t in range(randi_range(3, 7)):
				var t_pos = pos_i + Vector2i(randi_range(-2, 2), randi_range(-2, 2))
				if not grid_map.has(t_pos):
					_add_grid_room(rooms, grid_map, t_pos, "Settlement")
					_connect_grid_neighbors(rooms, {t_pos: grid_map[t_pos]}, 1.0)
					
		cursor_float += dir_vec
		if randf() < winding:
			cursor_float += dir_vec.rotated(PI/2) * (randf() * 2.0 - 1.0)
			
	return RegionGenerator.keep_largest_island(rooms)

static func generate_river(p: Dictionary):
	var length = int(p.get("rows", 30))
	var width = int(p.get("cols", 5))
	
	# Mapped from engine.ui sliders
	var amplitude_factor = p.get("room_density", 0.3) # 0.0 to 1.0
	var freq_factor = p.get("conn_density", 0.2)      # 0.0 to 1.0
	
	# Amplitude scales with length, e.g., max amplitude is length/3
	var amplitude = amplitude_factor * (length / 3.0)
	
	# Frequency: Number of full cycles over the length.
	# Range: 0.2 cycles (gentle arc) to 3.0 cycles (serpentine)
	var num_cycles = lerp(0.2, 3.0, freq_factor)
	var k = (TAU * num_cycles) / length
	
	var rooms = {}; var grid_map = {}
	
	for x in range(length):
		# Sine Wave Center
		var y_center = amplitude * sin(x * k)
		var center_y_int = int(round(y_center))
		
		# Draw Width slice
		var half_width = width / 2
		for w in range(-half_width, half_width + 1):
			var pos = Vector2i(x, center_y_int + w)
			
			if not grid_map.has(pos):
				var type = "Water"
				if w == -half_width or w == half_width: type = "Bank"
				
				var id = _add_grid_room(rooms, grid_map, pos, type)
				
				# Connect to existing neighbors (8-way for fluid connectivity)
				var neighbors = [
					Vector2i(-1, 0), Vector2i(-1, -1), Vector2i(-1, 1), # Previous column
					Vector2i(0, -1), Vector2i(0, 1) # Vertical in slice
				]
				
				for n in neighbors:
					if grid_map.has(pos + n):
						_link_rooms(rooms, id, grid_map[pos+n], Vector2(n))

	return RegionGenerator.keep_largest_island(rooms)

static func generate_spiral(p: Dictionary):
	var length = int(p.get("rows", 50))
	var spacing = int(p.get("cols", 1))
	if spacing < 1: spacing = 1
	var shortcuts = p.get("conn_density", 0.0)
	
	var rooms = {}; var grid_map = {}
	var cursor = Vector2i(0,0)
	var last_id = _add_grid_room(rooms, grid_map, cursor, "Spiral Center")
	
	var dirs = [Vector2i(1,0), Vector2i(0,1), Vector2i(-1,0), Vector2i(0,-1)]
	var shortcut_dirs = [
		Vector2i(1,0), Vector2i(0,1), Vector2i(-1,0), Vector2i(0,-1),
		Vector2i(1,1), Vector2i(1,-1), Vector2i(-1,1), Vector2i(-1,-1)
	]
	
	var dir_idx = 0
	var steps_in_leg = 1
	var steps_taken = 0
	var leg_count = 0 
	var total_rooms = 1
	
	while total_rooms < length:
		var move = dirs[dir_idx]
		cursor += move
		
		if not grid_map.has(cursor):
			var new_id = _add_grid_room(rooms, grid_map, cursor, "Spiral")
			_link_rooms(rooms, new_id, last_id, -Vector2(move))
			
			if shortcuts > 0 and randf() < shortcuts:
				for d in shortcut_dirs:
					var neighbor_pos = cursor + d
					if grid_map.has(neighbor_pos):
						var neighbor_id = grid_map[neighbor_pos]
						if neighbor_id != last_id:
							_link_rooms(rooms, new_id, neighbor_id, Vector2(d))
			
			last_id = new_id
			total_rooms += 1
		else:
			last_id = grid_map[cursor]
		
		steps_taken += 1
		if steps_taken >= steps_in_leg:
			steps_taken = 0
			dir_idx = (dir_idx + 1) % 4
			leg_count += 1
			if leg_count % 2 == 0:
				steps_in_leg += spacing

	return rooms

static func _add_grid_room(rooms, grid_map, pos, prefix): return RegionGenerator.add_grid_room(rooms, grid_map, pos, prefix)
static func _connect_grid_neighbors(rooms, grid_map, density): RegionGenerator.connect_grid_neighbors(rooms, grid_map, density)
static func _link_rooms(rooms, id_a, id_b, vec): RegionGenerator.link_rooms(rooms, id_a, id_b, vec)
