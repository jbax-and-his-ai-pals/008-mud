# scripts/core/WorldManager.gd
class_name WorldManager
extends RefCounted

const DistrictLayout = preload("res://scripts/generators/DistrictLayout.gd")
const SaveIO = preload("res://scripts/data/SaveIO.gd")

# Regions come from the shared content set; the world layout is editor-only
# state beside it. Both are resolved at call time (see DataRoot).
static func regions_dir() -> String: return DataRoot.content_dir("regions")
static func world_layout_file() -> String: return DataRoot.editor_file("world_layout.json")

var world_node_positions: Dictionary = {}
var ignored_validation_warnings: Dictionary = {}

func _init():
	load_world_layout()

func load_world_layout():
	world_node_positions.clear()
	if FileAccess.file_exists(world_layout_file()):
		var f = FileAccess.open(world_layout_file(), FileAccess.READ)
		if f == null:
			push_error("Could not read %s (%s)" % [world_layout_file(), error_string(FileAccess.get_open_error())])
			return
		var json = JSON.new()
		if json.parse(f.get_as_text()) == OK:
			var d = json.get_data()
			if typeof(d) != TYPE_DICTIONARY:
				push_error("World layout %s must contain an object." % world_layout_file())
				return
			if d.has("positions"): world_node_positions = d.positions
			if d.has("ignored_validation_warnings") and d.ignored_validation_warnings is Array:
				for warning_id in d.ignored_validation_warnings: ignored_validation_warnings[str(warning_id)] = true
		else:
			push_error("Could not parse %s: %s" % [world_layout_file(), json.get_error_message()])

# Returns {"ok": bool, "error": String} like every other writer, so a failed
# save is something the caller can report rather than assume.
func save_world_layout() -> Dictionary:
	var d = { "positions": world_node_positions, "ignored_validation_warnings": ignored_validation_warnings.keys() }
	DataRoot.ensure_editor_dirs()
	return SaveIO.write_json(world_layout_file(), d)

func update_world_node_pos(region_id: String, pos: Vector2):
	world_node_positions[region_id] = [pos.x, pos.y]

func is_suppressible_warning(finding: String) -> bool:
	return "One-way link" in finding

func is_warning_ignored(finding: String) -> bool:
	return ignored_validation_warnings.has(finding)

func acknowledge_warning(finding: String):
	if not is_suppressible_warning(finding): return
	ignored_validation_warnings[finding] = true
	save_world_layout()

func reset_ignored_warnings():
	ignored_validation_warnings.clear()
	save_world_layout()

func get_global_hierarchy() -> Dictionary:
	var hierarchy = {}
	var files = _scan_regions_recursive(regions_dir(), "")
	
	for fname in files:
		var f = FileAccess.open(regions_dir().path_join(fname), FileAccess.READ)
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
				hierarchy[rid] = {"filename": fname, "rooms": room_list, "districts": d.get("properties", {}).get("districts", {})}
	return hierarchy

func get_all_world_data() -> Dictionary:
	var world_data = {}
	var files = _scan_regions_recursive(regions_dir(), "")
	
	for fname in files:
		var f = FileAccess.open(regions_dir().path_join(fname), FileAccess.READ)
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
	errors.append_array(validate_district_continuity(full_world))
	return errors

# Districts are spatial editing units, not merely tags. A valid district has
# exactly one membership for every listed room and can be walked internally
# without routing through another district. This catches the most confusing
# "non-euclidean" shape: disconnected islands that only appear related because
# their metadata shares a district id.
func validate_district_continuity(full_world: Dictionary) -> Array:
	var findings: Array = []
	for region_id in full_world:
		var region: Dictionary = full_world[region_id]
		var rooms: Dictionary = region.get("rooms", {})
		var districts: Dictionary = region.get("properties", {}).get("districts", {})
		var claimed := {}
		var room_to_district_id := {}
		for district_id in districts:
			var district: Dictionary = districts[district_id]
			var members: Array = district.get("members", district.get("rooms", []))
			var valid_members: Array = []
			for room_id_variant in members:
				var room_id := str(room_id_variant)
				if not rooms.has(room_id):
					findings.append("[%s] District '%s': member '%s' does not exist." % [region_id, district.get("name", district_id), room_id])
					continue
				if claimed.has(room_id):
					findings.append("[%s] District '%s': room '%s' is also in '%s'." % [region_id, district.get("name", district_id), room_id, claimed[room_id]])
					continue
				claimed[room_id] = district.get("name", district_id)
				room_to_district_id[room_id] = str(district_id)
				valid_members.append(room_id)
				var recorded_id := str(rooms[room_id].get("properties", {}).get("_district_id", ""))
				if recorded_id != str(district_id): findings.append("[%s] District '%s': room '%s' has _district_id '%s'." % [region_id, district.get("name", district_id), room_id, recorded_id])
			if valid_members.size() > 1 and not _district_members_are_connected(rooms, valid_members):
				findings.append("[%s] District '%s': members are disconnected; add an internal link or split the district." % [region_id, district.get("name", district_id)])
		for room_id in rooms:
			var stored_id := str(rooms[room_id].get("properties", {}).get("_district_id", ""))
			if stored_id != "" and not claimed.has(room_id): findings.append("[%s] Room '%s': _district_id '%s' has no district membership." % [region_id, room_id, stored_id])
		for pinch in DistrictLayout.find_multi_district_pinches(rooms, room_to_district_id):
			var own_name := str(districts.get(pinch.district_id, {}).get("name", pinch.district_id))
			var foreign_names: Array = []
			for foreign_id in pinch.foreign_districts:
				foreign_names.append(str(districts.get(foreign_id, {}).get("name", foreign_id)))
			findings.append("[%s] District '%s': room '%s' is pinched between %s with no connecting exit; the shared territory here will render cramped or ambiguous." % [region_id, own_name, pinch.room_id, ", ".join(foreign_names)])
	return findings

func _district_members_are_connected(rooms: Dictionary, members: Array) -> bool:
	var member_set := {}
	for room_id in members: member_set[room_id] = true
	var visited := {members[0]: true}
	var frontier: Array = [members[0]]
	while not frontier.is_empty():
		var room_id: String = frontier.pop_front()
		for target_variant in rooms[room_id].get("exits", {}).values():
			var target_id := str(target_variant)
			if member_set.has(target_id) and not visited.has(target_id):
				visited[target_id] = true
				frontier.append(target_id)
	return visited.size() == members.size()
