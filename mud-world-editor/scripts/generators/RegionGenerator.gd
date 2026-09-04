# scripts/generators/RegionGenerator.gd
class_name RegionGenerator
extends RefCounted

const CELL_SIZE = Vector2(250, 250)

enum Algo { EMPTY, GRID, MAZE, HUB, CRESCENT, RING, CAVERN, SECTOR, HIGHWAY, SPIRAL, FRACTAL, RIVER, TARGET, HOUSE, TOWN, CITY, CASTLE }

const GRID_BASED = preload("res://scripts/generators/GridBasedGenerators.gd")
const PATH_BASED = preload("res://scripts/generators/PathBasedGenerators.gd")
const GRAPH_BASED = preload("res://scripts/generators/GraphBasedGenerators.gd")
const STRUCT_BASED = preload("res://scripts/generators/StructureGenerators.gd")

static func generate(algo: int, params: Dictionary) -> Dictionary:
	var rooms = {}
	match algo:
		Algo.EMPTY: rooms = {}
		Algo.GRID: rooms = GRID_BASED.generate_grid(params)
		Algo.MAZE: rooms = GRID_BASED.generate_maze(params)
		Algo.CAVERN: rooms = GRID_BASED.generate_cavern(params)
		Algo.SECTOR: rooms = GRID_BASED.generate_sector(params)
		Algo.TARGET: rooms = GRID_BASED.generate_target(params)
		Algo.HIGHWAY: rooms = PATH_BASED.generate_highway(params)
		Algo.RIVER: rooms = PATH_BASED.generate_river(params)
		Algo.SPIRAL: rooms = PATH_BASED.generate_spiral(params)
		Algo.HUB: rooms = GRAPH_BASED.generate_hub(params)
		Algo.CRESCENT: rooms = GRAPH_BASED.generate_crescent(params)
		Algo.RING: rooms = GRAPH_BASED.generate_ring(params)
		Algo.FRACTAL: rooms = GRAPH_BASED.generate_fractal(params)
		Algo.HOUSE: rooms = STRUCT_BASED.generate_house(params)
		Algo.TOWN: rooms = STRUCT_BASED.generate_town(params)
		Algo.CITY: rooms = STRUCT_BASED.generate_city(params)
		Algo.CASTLE: rooms = STRUCT_BASED.generate_castle(params)
	
	return _center_rooms(rooms)

# --- PUBLIC HELPERS ---

static func add_grid_room(rooms: Dictionary, grid_map: Dictionary, pos: Vector2i, prefix: String) -> String:
	if grid_map.has(pos): return grid_map[pos]
	var id = "room_%d_%d" % [pos.x, pos.y]
	rooms[id] = make_room("%s %d-%d" % [prefix, pos.x, pos.y], Vector2(pos) * CELL_SIZE)
	grid_map[pos] = id
	return id

static func connect_grid_neighbors(rooms: Dictionary, grid_map: Dictionary, density: float):
	var neighbors = [
		{ "off": Vector2i(1, 0), "d": false }, { "off": Vector2i(0, 1), "d": false },
		{ "off": Vector2i(1, 1), "d": true }, { "off": Vector2i(-1, 1), "d": true }
	]
	
	# If density is 1.0, we want guaranteed connection. 
	# lerp(0.3, 1.0, 1.0) is 1.0. randf() returns [0,1]. 
	# randf() < 1.0 fails if rand returns 1.0 (edge case), so use <=.
	var prob_card = lerp(0.3, 1.0, density)
	var prob_diag = lerp(0.0, 0.8, density)
	
	for pos in grid_map:
		for n in neighbors:
			if grid_map.has(pos + n.off):
				var chance = prob_diag if n.d else prob_card
				if randf() <= chance:
					link_rooms(rooms, grid_map[pos], grid_map[pos + n.off], Vector2(n.off))

static func link_rooms(rooms: Dictionary, id_a: String, id_b: String, vec_diff: Vector2):
	var d_str = get_dir_from_vec(vec_diff)
	var r_str = get_dir_from_vec(-vec_diff)
	if d_str != "" and r_str != "":
		rooms[id_a].exits[d_str] = id_b
		rooms[id_b].exits[r_str] = id_a

static func keep_largest_island(rooms: Dictionary) -> Dictionary:
	if rooms.is_empty(): return rooms
	var visited = {}; var islands = []
	for rid in rooms:
		if visited.has(rid): continue
		var island = []; var queue = [rid]; visited[rid] = true
		while not queue.is_empty():
			var curr = queue.pop_front(); island.append(curr)
			for dir in rooms[curr].exits:
				var neighbor = rooms[curr].exits[dir]
				if not ":" in neighbor and rooms.has(neighbor) and not visited.has(neighbor):
					visited[neighbor] = true; queue.append(neighbor)
		islands.append(island)
	if islands.is_empty(): return rooms
	islands.sort_custom(func(a, b): return a.size() > b.size())
	var final_rooms = {}; for id in islands[0]: final_rooms[id] = rooms[id]
	for id in final_rooms:
		var exits = final_rooms[id].exits.duplicate()
		for dir in exits:
			if not ":" in exits[dir] and not final_rooms.has(exits[dir]):
				final_rooms[id].exits.erase(dir)
	return final_rooms

static func make_room(name: String, pos: Vector2) -> Dictionary:
	return { "name": name, "description": "Generated.", "exits": {}, "properties": {}, "_editor_pos": [pos.x, pos.y] }

static func get_dir_from_vec(v: Vector2) -> String:
	var vn = v.normalized()
	var deg = rad_to_deg(vn.angle())
	if deg < 0: deg += 360
	if deg >= 337.5 or deg < 22.5: return Constants.DIR_E
	if deg >= 22.5 and deg < 67.5: return Constants.DIR_SE
	if deg >= 67.5 and deg < 112.5: return Constants.DIR_S
	if deg >= 112.5 and deg < 157.5: return Constants.DIR_SW
	if deg >= 157.5 and deg < 202.5: return Constants.DIR_W
	if deg >= 202.5 and deg < 247.5: return Constants.DIR_NW
	if deg >= 247.5 and deg < 292.5: return Constants.DIR_N
	if deg >= 292.5 and deg < 337.5: return Constants.DIR_NE
	return ""

static func _center_rooms(rooms: Dictionary) -> Dictionary:
	if rooms.is_empty(): return rooms
	var min_p = Vector2(INF, INF); var max_p = Vector2(-INF, -INF)
	for id in rooms:
		var p = Vector2(rooms[id]._editor_pos[0], rooms[id]._editor_pos[1])
		min_p.x = min(min_p.x, p.x); min_p.y = min(min_p.y, p.y)
		max_p.x = max(max_p.x, p.x); max_p.y = max(max_p.y, p.y)
	var center_offset = (min_p + max_p) / 2.0
	center_offset = center_offset.snapped(Vector2(CELL_SIZE.x / 2.0, CELL_SIZE.y / 2.0))
	for id in rooms:
		var p = Vector2(rooms[id]._editor_pos[0], rooms[id]._editor_pos[1]) - center_offset
		rooms[id]["_editor_pos"] = [p.x, p.y]
	return rooms
