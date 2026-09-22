# scripts/data/RegionManager.gd
class_name RegionManager
extends RefCounted

const SaveIO = preload("res://scripts/data/SaveIO.gd")
# Preloaded rather than reached through the project's class cache: a headless
# check must not depend on the editor having scanned a new script first.
const ReferencePatch = preload("res://scripts/data/ReferencePatch.gd")

# Regions come from the shared content set, not from a mirror of it. The path is
# resolved at load/save time rather than frozen in a constant, because the
# editor's data root is agreed once at startup (DataRoot) and may be overridden
# on the command line.
static func regions_dir() -> String:
	return DataRoot.content_dir("regions")

var data: Dictionary = {}
var current_filename: String = ""

# Why the last load failed, for the UI to show. Empty after a successful load.
var load_error: String = ""
# Whether `data` came from a successful read of `current_filename`.
var loaded_ok: bool = false
# Files `_patch_external_references` could not rewrite during the last rename.
var patch_errors: Array = []

# --- DIRTY STATE TRACKING ---
var is_region_dirty: bool = false
var dirty_room_ids: Dictionary = {} 

func load_region(filename: String) -> bool:
	is_region_dirty = false
	dirty_room_ids.clear()
	load_error = ""

	if filename == "":
		# An explicit "no region": nothing was on disk to load, and nothing may
		# be saved over it. current_filename stays empty so save_region refuses.
		current_filename = ""
		loaded_ok = false
		data = {"region_id": "", "rooms": {}}
		return false

	var full_path = regions_dir().path_join(filename)
	if not FileAccess.file_exists(full_path):
		# Keep whatever is loaded. The old behaviour reset `data` to an empty
		# region while keeping the *real* filename, so one bad read plus any
		# later Save wrote the blank region over the file.
		load_error = "Region file not found: %s" % full_path
		push_error(load_error)
		return false

	var file = FileAccess.open(full_path, FileAccess.READ)
	if file == null:
		load_error = "Could not read %s (%s)" % [full_path, error_string(FileAccess.get_open_error())]
		push_error(load_error)
		return false

	var json = JSON.new()
	var err = json.parse(file.get_as_text())
	file.close()
	if err != OK:
		load_error = "%s is not valid JSON: %s" % [filename, json.get_error_message()]
		push_error(load_error)
		return false

	var parsed = json.get_data()
	if typeof(parsed) != TYPE_DICTIONARY:
		load_error = "%s must contain an object" % filename
		push_error(load_error)
		return false

	# A region-*generation* template (`{"themes": {...}}`), not a static room
	# graph -- the engine itself treats these as a different kind of file
	# (server/engine/server/content_set.py checks `themes` before treating
	# anything under regions/ as a room-shaped region) and never asks them for
	# `rooms`/`region_id`. Loading one here would fabricate both on the next
	# save and overwrite the real generator data with an empty region.
	if parsed.get("themes") is Dictionary:
		load_error = "%s is a region-generation template (has a top-level 'themes' key), not a static region -- the editor cannot open it" % filename
		push_error(load_error)
		return false

	current_filename = filename
	loaded_ok = true
	data = parsed
	if not data.has("rooms"): data["rooms"] = {}
	if not data.has("region_id"): data["region_id"] = filename.replace(".json", "")
	# Positions live beside the content, not inside it; merging them here
	# means every call site below keeps working unchanged.
	data = EditorLayout.merge_region(str(data.get("region_id", "")), data)
	_backfill_missing_editor_positions()
	return true

# Whether the data on screen came from a successful read of `current_filename`.
# Saving is refused when it did not, because "what is on screen" would then be a
# blank region rather than the author's work.
# Back to "nothing loaded". Used when the editor switches content set: the loaded
# region, its filename and its error belong to the world that was open.
func reset() -> void:
	data = {}
	current_filename = ""
	loaded_ok = false
	load_error = ""
	patch_errors.clear()
	is_region_dirty = false
	dirty_room_ids.clear()

func can_save() -> bool:
	return current_filename != "" and loaded_ok

# --- repairing references in region files --------------------------------------
#
# A rename reaches references that live here too: a spawner weight, a locked
# door's key, a jail's release destination. The region the editor has open is
# patched in memory, so the author's unsaved edits survive and the normal save
# path writes it. Any other region file is read, patched and written with the
# same stripper and verified writer a normal save uses -- and a file that cannot
# be parsed is never rewritten, because that is how a repair becomes a
# truncation. (Same rule as `_patch_external_references`, which does this for
# exits one room rename at a time.)
func patch_reference(file_name: String, path: String, old_id: String, new_id: String) -> Dictionary:
	var target := file_name.get_file()
	if target == current_filename and loaded_ok:
		var in_memory := ReferencePatch.rename(data, path, old_id, new_id)
		if in_memory.get("ok", false):
			is_region_dirty = true
		return in_memory

	var full := regions_dir().path_join(target)
	if not FileAccess.file_exists(full):
		return {"ok": false, "error": "%s is not in this content set" % target}
	var raw := FileAccess.get_file_as_string(full)
	var json := JSON.new()
	if json.parse(raw) != OK:
		return {"ok": false, "error": "%s could not be parsed, so nothing was changed" % target}
	var payload = json.get_data()
	if not payload is Dictionary:
		return {"ok": false, "error": "%s is not a region object" % target}
	var patched := ReferencePatch.rename(payload, path, old_id, new_id)
	if not patched.get("ok", false):
		return patched
	var written := SaveIO.write_json(full, EditorLayout.strip_region(payload))
	if not written.get("ok", false):
		return {"ok": false, "error": str(written.get("error", "could not write %s" % target))}
	return patched

## Non-mutating companion to `patch_reference`.  A reference refactor calls this
## for every region hit before changing any cache or file, so a malformed sibling
## region cannot produce a partly repaired rename.
func can_patch_reference(file_name: String, path: String, old_id: String, new_id: String) -> Dictionary:
	var target := file_name.get_file()
	if target == current_filename and loaded_ok:
		return ReferencePatch.rename(data.duplicate(true), path, old_id, new_id)
	var full := regions_dir().path_join(target)
	if not FileAccess.file_exists(full):
		return {"ok": false, "error": "%s is not in this content set" % target}
	var json := JSON.new()
	if json.parse(FileAccess.get_file_as_string(full)) != OK:
		return {"ok": false, "error": "%s could not be parsed, so nothing was changed" % target}
	var payload = json.get_data()
	if not payload is Dictionary:
		return {"ok": false, "error": "%s is not a region object" % target}
	return ReferencePatch.rename((payload as Dictionary).duplicate(true), path, old_id, new_id)
func save_region() -> Dictionary:
	if current_filename == "":
		return {"ok": false, "error": "No region is loaded, so there is nothing to save."}
	if not loaded_ok:
		return {"ok": false, "error": (
			"Refusing to save %s: it did not load from disk, so what is on screen is not "
			+ "what the file contains. Reload the region first."
		) % current_filename}
	var region_id := str(data.get("region_id", current_filename.replace(".json", "")))
	# Editor layout goes to the sidecar; the file the game reads stays clean.
	EditorLayout.split_region(region_id, data)
	var payload := EditorLayout.strip_region(data)
	var path := regions_dir().path_join(current_filename)
	if not DirAccess.dir_exists_absolute(regions_dir()):
		DirAccess.make_dir_recursive_absolute(regions_dir())
	return SaveIO.write_json(path, payload)

# Content-set-authored rooms (content_sets/fantasy_frontier/data/regions/*)
# carry no "_editor_pos" -- it is purely editor layout metadata, never
# written by the game server. Positions the editor already knows live in
# `editor/regions/<id>.editor.json` and are merged in by load_region above;
# this backfill covers a region the editor has never arranged, so that from
# this point on every room in `data.rooms` is guaranteed to have one. Several
# read sites on the main interaction path (GraphController.update_specific_node,
# Main.gd's drag/select handlers) index it directly and would throw on a missing
# key, which is cheaper to prevent here than to audit at every call site.
# Mirrors the same fallback QuestViewBuilder does per quest stage
# ("if not s.has(_editor_pos): s._editor_pos = [i * 250, 0]").
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
	# Every path here used to be built by concatenation (`regions_dir() + fname`),
	# and `DataRoot.content_dir` returns a `path_join` result with no trailing
	# separator -- so the path was `.../data/regionstown.json`, the read came back
	# empty, and the repair silently never ran. Renaming a room therefore left
	# `region:old_id` exits dangling in every other file.
	patch_errors.clear()
	var dir = DirAccess.open(regions_dir())
	if dir == null:
		patch_errors.append("Could not open %s to repair cross-region exits." % regions_dir())
		return
	dir.list_dir_begin()
	var fname = dir.get_next()
	while fname != "":
		if fname.ends_with(".json") and fname != current_filename:
			var path := regions_dir().path_join(fname)
			var content := FileAccess.get_file_as_string(path)
			var search_str = target_region + ":" + old_room
			if content.contains(search_str):
				var json = JSON.new()
				if json.parse(content) != OK:
					# Never rewrite a file we could not read: that is how a repair
					# turns into a truncation.
					patch_errors.append("%s could not be parsed, so its exits still point at '%s'."
						% [fname, old_room])
					fname = dir.get_next()
					continue
				var d = json.get_data()
				var dirty = false
				for rid in d.get("rooms", {}):
					var exits = d["rooms"][rid].get("exits", {})
					for dir_key in exits:
						if exits[dir_key] == search_str:
							exits[dir_key] = target_region + ":" + new_room
							dirty = true
				if dirty:
					# The same stripper and the same verified writer as a normal
					# save: this file the engine reads gets no editor keys and no
					# half-written state.
					var result: Dictionary = SaveIO.write_json(path, EditorLayout.strip_region(d))
					if not result.get("ok", false):
						patch_errors.append(result.get("error", "Could not update %s." % fname))
		fname = dir.get_next()

func mark_room_dirty(room_id: String):
	if room_id != "": dirty_room_ids[room_id] = true
	mark_region_dirty()

# Some edits live on the region or district metadata rather than a single
# room.  They still need to enable the shared Save Changes control.
func mark_region_dirty():
	is_region_dirty = true

func mark_clean():
	is_region_dirty = false
	dirty_room_ids.clear()
