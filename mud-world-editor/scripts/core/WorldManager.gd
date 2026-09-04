# scripts/core/WorldManager.gd
class_name WorldManager
extends RefCounted

const REGIONS_DIR = "res://data/regions/"
const WORLD_LAYOUT_FILE = "res://data/world_layout.json"

var world_node_positions: Dictionary = {}

func _init():
	load_world_layout()

func load_world_layout():
	world_node_positions.clear()
	if FileAccess.file_exists(WORLD_LAYOUT_FILE):
		var f = FileAccess.open(WORLD_LAYOUT_FILE, FileAccess.READ)
		var json = JSON.new()
		if json.parse(f.get_as_text()) == OK:
			var d = json.get_data()
			if d.has("positions"): world_node_positions = d.positions

func save_world_layout():
	var d = { "positions": world_node_positions }
	var f = FileAccess.open(WORLD_LAYOUT_FILE, FileAccess.WRITE)
	if f: f.store_string(JSON.stringify(d, "\t"))

func update_world_node_pos(region_id: String, pos: Vector2):
	world_node_positions[region_id] = [pos.x, pos.y]

func get_global_hierarchy() -> Dictionary:
	var hierarchy = {}
	var files = _scan_regions_recursive(REGIONS_DIR, "")
	
	for fname in files:
		var f = FileAccess.open(REGIONS_DIR.path_join(fname), FileAccess.READ)
		if f:
			var json = JSON.new()
			if json.parse(f.get_as_text()) == OK:
				var d = json.get_data()
				# Use explicit region_id if present, otherwise filename without ext
				var rid = d.get("region_id", fname.get_file().replace(".json", ""))
				var room_list = {}
				var rooms = d.get("rooms", {})
				for r_id in rooms:
					room_list[r_id] = rooms[r_id].get("name", "Unnamed")
				hierarchy[rid] = {"filename": fname, "rooms": room_list}
	return hierarchy

func get_all_world_data() -> Dictionary:
	var world_data = {}
	var files = _scan_regions_recursive(REGIONS_DIR, "")
	
	for fname in files:
		var f = FileAccess.open(REGIONS_DIR.path_join(fname), FileAccess.READ)
		if f:
			var json = JSON.new()
			if json.parse(f.get_as_text()) == OK:
				var d = json.get_data()
				var rid = d.get("region_id", fname.get_file().replace(".json", ""))
				world_data[rid] = d
	return world_data

func _scan_regions_recursive(root_dir: String, current_subdir: String) -> Array:
	var files = []
	var full_path = root_dir.path_join(current_subdir)
	var dir = DirAccess.open(full_path)
	if dir:
		dir.list_dir_begin()
		var name = dir.get_next()
		while name != "":
			if dir.current_is_dir():
				if name != "." and name != "..":
					files.append_array(_scan_regions_recursive(root_dir, current_subdir.path_join(name)))
			elif name.ends_with(".json"):
				files.append(current_subdir.path_join(name))
			name = dir.get_next()
	return files

func validate_world_links() -> Array:
	var errors = []
	var full_world = get_all_world_data()
	
	for region_id in full_world:
		var rooms = full_world[region_id].get("rooms", {})
		for room_id in rooms:
			var exits = rooms[room_id].get("exits", {})
			for dir in exits:
				var target = exits[dir]
				if ":" in target:
					var parts = target.split(":")
					var target_rid = parts[0]
					var target_room = parts[1]
					if not full_world.has(target_rid):
						errors.append("[%s] %s -> %s: Unknown Region '%s'" % [region_id, room_id, dir, target_rid])
					elif not full_world[target_rid]["rooms"].has(target_room):
						errors.append("[%s] %s -> %s: Unknown Room '%s' in %s" % [region_id, room_id, dir, target_room, target_rid])
				else:
					if not rooms.has(target):
						errors.append("[%s] %s -> %s: Unknown Room '%s'" % [region_id, room_id, dir, target])
					else:
						# One-way check
						var t_exits = rooms[target].get("exits", {})
						var found_back = false
						for t_dir in t_exits:
							if t_exits[t_dir] == room_id: found_back = true
						if not found_back:
							errors.append("[%s] %s -> %s: One-way link (Target '%s' does not link back)" % [region_id, room_id, dir, target])
	return errors
