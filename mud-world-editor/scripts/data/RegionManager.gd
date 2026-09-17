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
			_backfill_missing_editor_positions()
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

# Content-set-authored rooms (content_sets/fantasy_frontier/data/regions/*)
# carry no "_editor_pos" -- it is purely editor layout metadata, never
# written by the game server. Most read sites default safely
# (data.get("_editor_pos", [0,0])), but several on the main interaction
# path (GraphController.update_specific_node, Main.gd's drag/select
# handlers) index it directly and would throw on a missing key. Backfilling
# it once here, right after load, is cheaper and safer than auditing every
# call site: from this point on every room in `data.rooms` is guaranteed to
# have one. Mirrors the same fallback QuestViewBuilder already does per
# quest stage ("if not s.has(_editor_pos): s._editor_pos = [i * 250, 0]").
const _BACKFILL_GRID_SPACING: float = 250.0
const _BACKFILL_GRID_COLUMNS: int = 12
const _BACKFILL_ORIGIN: Vector2 = Vector2(3000.0, -3000.0)

func _backfill_missing_editor_positions():
	var rooms: Dictionary = data.get("rooms", {})
	var unpositioned_ids: Array = []
	for room_id in rooms:
		var room = rooms[room_id]
		if room is Dictionary and not room.has("_editor_pos"):
			unpositioned_ids.append(room_id)
	unpositioned_ids.sort()
	for i in range(unpositioned_ids.size()):
		var col = i % _BACKFILL_GRID_COLUMNS
		var row = i / _BACKFILL_GRID_COLUMNS
		var pos = _BACKFILL_ORIGIN + Vector2(col, row) * _BACKFILL_GRID_SPACING
		rooms[unpositioned_ids[i]]["_editor_pos"] = [pos.x, pos.y]

# --- MUTATION METHODS ---

func add_room_data(id: String, room_data: Dictionary):
	if not data.has("rooms"): data["rooms"] = {}
	data["rooms"][id] = room_data

# District records deliberately live with the region, rather than being inferred
# from a room-name prefix.  That gives a generator a stable public contract
# (seed, ports, and member list) while leaving ordinary hand-authored rooms
# entirely unaffected.
func get_districts() -> Dictionary:
	if not data.has("properties") or not data["properties"] is Dictionary:
		data["properties"] = {}
	if not data["properties"].has("districts") or not data["properties"]["districts"] is Dictionary:
		data["properties"]["districts"] = {}
	return data["properties"]["districts"]

func set_district(district_id: String, district: Dictionary):
	get_districts()[district_id] = district.duplicate(true)

func remove_district(district_id: String):
	get_districts().erase(district_id)

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

func connection_label_key(first_id: String, second_id: String) -> String:
	var ids := [first_id, second_id]
	ids.sort()
	return str(ids[0]) + "|" + str(ids[1])

func set_connection_label_source(source_id: String, target_id: String, direction: String):
	if ":" in target_id: return
	if not data.has("_editor_connection_label_sources") or not data["_editor_connection_label_sources"] is Dictionary:
		data["_editor_connection_label_sources"] = {}
	data["_editor_connection_label_sources"][connection_label_key(source_id, target_id)] = {"source": source_id, "direction": direction}

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
