# scripts/data/RegionManager.gd
class_name RegionManager
extends RefCounted

const REGIONS_DIR = "res://data/regions/"

var data: Dictionary = {}
var current_filename: String = ""

# --- DIRTY STATE TRACKING ---
var is_region_dirty: bool = false
var dirty_room_ids: Dictionary = {} 

func load_region(filename: String) -> bool:
	is_region_dirty = false
	dirty_room_ids.clear()

	current_filename = filename
	var full_path = REGIONS_DIR + filename
	if not FileAccess.file_exists(full_path):
		# Don't error on blank load
		if filename != "": push_error("Region file not found: " + full_path)
		return false
	
	var file = FileAccess.open(full_path, FileAccess.READ)
	if file:
		var json = JSON.new()
		var err = json.parse(file.get_as_text())
		if err == OK:
			data = json.get_data()
			if not data.has("rooms"): data["rooms"] = {}
			if not data.has("region_id"): data["region_id"] = filename.replace(".json", "")
			return true
		else:
			push_error("JSON Parse Error: " + json.get_error_message())
			
	data = {"region_id": filename.replace(".json",""), "rooms": {}}
	return false

func save_region():
	if current_filename == "": return
	var file = FileAccess.open(REGIONS_DIR + current_filename, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify(data, "\t"))

# --- MUTATION METHODS ---

func add_room_data(id: String, room_data: Dictionary):
	if not data.has("rooms"): data["rooms"] = {}
	data["rooms"][id] = room_data

func remove_room_data(id: String):
	if data.get("rooms", {}).has(id):
		data["rooms"].erase(id)

func set_room_pos(id: String, pos: Vector2):
	if data.get("rooms", {}).has(id):
		data["rooms"][id]["_editor_pos"] = [pos.x, pos.y]
	else:
		# Handle Proxy/External Nodes
		if not data.has("_proxy_positions"): data["_proxy_positions"] = {}
		data["_proxy_positions"][id] = [pos.x, pos.y]

func add_exit(src: String, dir: String, target: String):
	if data["rooms"].has(src):
		if not data["rooms"][src].has("exits"): data["rooms"][src]["exits"] = {}
		data["rooms"][src]["exits"][dir] = target

func remove_exit(src: String, dir: String):
	if data["rooms"].has(src) and data["rooms"][src].has("exits"):
		data["rooms"][src]["exits"].erase(dir)

# Renamed to avoid conflict with Object.get_incoming_connections()
func find_incoming_connections(target_id: String) -> Array:
	var links = []
	if not data.has("rooms"): return links
	for room_id in data.rooms:
		var r = data.rooms[room_id]
		if r.has("exits"):
			for dir in r.exits:
				if r.exits[dir] == target_id:
					links.append({"source": room_id, "dir": dir})
	return links

func rename_room(old_id: String, new_id: String) -> bool:
	if not data["rooms"].has(old_id) or data["rooms"].has(new_id): return false
	
	if dirty_room_ids.has(old_id):
		dirty_room_ids.erase(old_id)
		dirty_room_ids[new_id] = true

	var r = data["rooms"][old_id]
	data["rooms"][new_id] = r
	data["rooms"].erase(old_id)
	
	for rid in data["rooms"]:
		var exits = data["rooms"][rid].get("exits", {})
		for dir in exits:
			if exits[dir] == old_id: 
				exits[dir] = new_id
			elif ":" in exits[dir]:
				var parts = exits[dir].split(":")
				if parts[0] == data["region_id"] and parts[1] == old_id:
					exits[dir] = parts[0] + ":" + new_id

	is_region_dirty = true
	_patch_external_references(data["region_id"], old_id, new_id)
	return true

func _patch_external_references(target_region: String, old_room: String, new_room: String):
	var dir = DirAccess.open(REGIONS_DIR)
	if dir:
		dir.list_dir_begin()
		var fname = dir.get_next()
		while fname != "":
			if fname.ends_with(".json") and fname != current_filename:
				var content = FileAccess.get_file_as_string(REGIONS_DIR + fname)
				var search_str = target_region + ":" + old_room
				if content.contains(search_str):
					var f_read = FileAccess.open(REGIONS_DIR + fname, FileAccess.READ)
					var json = JSON.new()
					if json.parse(f_read.get_as_text()) == OK:
						var d = json.get_data()
						var dirty = false
						for rid in d.get("rooms", {}):
							var exits = d["rooms"][rid].get("exits", {})
							for dir_key in exits:
								if exits[dir_key] == search_str:
									exits[dir_key] = target_region + ":" + new_room
									dirty = true
						if dirty:
							var f_write = FileAccess.open(REGIONS_DIR + fname, FileAccess.WRITE)
							f_write.store_string(JSON.stringify(d, "\t"))
			fname = dir.get_next()

func mark_room_dirty(room_id: String):
	if room_id != "": dirty_room_ids[room_id] = true
	is_region_dirty = true

func mark_clean():
	is_region_dirty = false
	dirty_room_ids.clear()
