# scripts/data/EditorLayout.gd
#
# Editor bookkeeping, kept out of the game's content files.
#
# `_editor_pos` (where a room sits on the graph) and `_editor_exit_layout` (how
# an exit is drawn) are how the editor remembers the shape of a region. They are
# not game data: `RegionManager` already documents that content-set-authored
# rooms carry no `_editor_pos` and that the server never writes one.
#
# So they live in `content_sets/<set>/editor/`, and the split happens here and
# nowhere else. The rest of the editor keeps reading and writing `_editor_*` on
# the in-memory dictionary exactly as before: `merge_region` puts them back after
# a load, `split_region` lifts them out before a save.

class_name EditorLayout
extends RefCounted

const POSITION_KEY := "_editor_pos"
const EXIT_LAYOUT_KEY := "_editor_exit_layout"

# --- regions ------------------------------------------------------------------

# Sidecar payload for one region:
#   { "region": { ...region-level editor keys... },
#     "rooms": { "<room_id>": { "_editor_pos": [x, y], "_editor_exit_layout": {...} } } }
static func merge_region(region_id: String, data: Dictionary) -> Dictionary:
	var payload := _read(DataRoot.region_editor_file(region_id))
	if payload.is_empty():
		return data

	var region_keys = payload.get("region", {})
	if typeof(region_keys) == TYPE_DICTIONARY:
		for key in region_keys:
			if not data.has(key):
				data[key] = region_keys[key]

	var rooms = payload.get("rooms", {})
	if typeof(rooms) == TYPE_DICTIONARY and data.has("rooms"):
		for room_id in rooms:
			if not data["rooms"].has(room_id):
				continue
			var saved = rooms[room_id]
			if typeof(saved) != TYPE_DICTIONARY:
				continue
			for key in saved:
				data["rooms"][room_id][key] = saved[key]
	return data

static func split_region(region_id: String, data: Dictionary) -> void:
	var payload := {
		"region": _editor_keys_of(data),
		"rooms": {},
	}
	if data.has("rooms") and typeof(data["rooms"]) == TYPE_DICTIONARY:
		for room_id in data["rooms"]:
			var room = data["rooms"][room_id]
			if typeof(room) != TYPE_DICTIONARY:
				continue
			var keys := _editor_keys_of(room)
			if not keys.is_empty():
				payload["rooms"][room_id] = keys

	if payload["region"].is_empty() and payload["rooms"].is_empty():
		_remove(DataRoot.region_editor_file(region_id))
		return
	_write(DataRoot.region_editor_file(region_id), payload)

# Region content without any editor keys in it -- what gets written to `data/`.
static func strip_region(data: Dictionary) -> Dictionary:
	var clean := data.duplicate(true)
	_erase_editor_keys(clean)
	if clean.has("rooms") and typeof(clean["rooms"]) == TYPE_DICTIONARY:
		for room_id in clean["rooms"]:
			var room = clean["rooms"][room_id]
			if typeof(room) == TYPE_DICTIONARY:
				_erase_editor_keys(room)
	return clean

# --- quests -------------------------------------------------------------------

# Quest stage positions, keyed by quest id then stage index:
#   { "<quest_id>": { "0": [x, y], "1": [x, y] } }
static func merge_quests(quests: Dictionary) -> Dictionary:
	for quest_id in quests:
		var quest = quests[quest_id]
		if typeof(quest) != TYPE_DICTIONARY:
			continue
		var saved := _read(DataRoot.editor_file("quest_layout.json"))
		var positions = saved.get(str(quest_id), {})
		if typeof(positions) != TYPE_DICTIONARY:
			continue
		var stages = quest.get("stages", [])
		if typeof(stages) != TYPE_ARRAY:
			continue
		for index in range(stages.size()):
			if typeof(stages[index]) != TYPE_DICTIONARY:
				continue
			var saved_pos = positions.get(str(index))
			if typeof(saved_pos) == TYPE_ARRAY and not stages[index].has(POSITION_KEY):
				stages[index][POSITION_KEY] = saved_pos
	return quests

static func split_quests(quests: Dictionary) -> void:
	var payload := {}
	for quest_id in quests:
		var quest = quests[quest_id]
		if typeof(quest) != TYPE_DICTIONARY:
			continue
		var stages = quest.get("stages", [])
		if typeof(stages) != TYPE_ARRAY:
			continue
		var positions := {}
		for index in range(stages.size()):
			if typeof(stages[index]) == TYPE_DICTIONARY and stages[index].has(POSITION_KEY):
				positions[str(index)] = stages[index][POSITION_KEY]
		if not positions.is_empty():
			payload[str(quest_id)] = positions
	if payload.is_empty():
		_remove(DataRoot.editor_file("quest_layout.json"))
		return
	_write(DataRoot.editor_file("quest_layout.json"), payload)

static func strip_quests(quests: Dictionary) -> Dictionary:
	var clean := quests.duplicate(true)
	for quest_id in clean:
		var quest = clean[quest_id]
		if typeof(quest) != TYPE_DICTIONARY:
			continue
		var stages = quest.get("stages", [])
		if typeof(stages) != TYPE_ARRAY:
			continue
		for stage in stages:
			if typeof(stage) == TYPE_DICTIONARY:
				_erase_editor_keys(stage)
	return clean

# --- helpers ------------------------------------------------------------------

static func is_editor_key(key: String) -> bool:
	return key.begins_with("_editor_")

# Recursively remove editor keys from any value, including inside arrays --
# quest stages are an array of dictionaries, so a shallow strip would miss them.
static func strip_entry(value: Variant) -> Variant:
	if typeof(value) == TYPE_DICTIONARY:
		var out := {}
		for key in value:
			if is_editor_key(str(key)):
				continue
			out[key] = strip_entry(value[key])
		return out
	if typeof(value) == TYPE_ARRAY:
		var list := []
		for item in value:
			list.append(strip_entry(item))
		return list
	return value

static func _editor_keys_of(source: Dictionary) -> Dictionary:
	var out := {}
	for key in source:
		if is_editor_key(str(key)):
			out[key] = source[key]
	return out

static func _erase_editor_keys(target: Dictionary) -> void:
	for key in target.keys():
		if is_editor_key(str(key)):
			target.erase(key)

static func _read(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var parsed := JSON.new()
	if parsed.parse(FileAccess.get_file_as_string(path)) != OK:
		push_warning("EditorLayout: could not read %s" % path)
		return {}
	var payload = parsed.get_data()
	return payload if typeof(payload) == TYPE_DICTIONARY else {}

static func _write(path: String, payload: Dictionary) -> void:
	DataRoot.ensure_editor_dirs()
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		push_error("EditorLayout: could not write %s" % path)
		return
	file.store_string(JSON.stringify(payload, "\t"))

static func _remove(path: String) -> void:
	if FileAccess.file_exists(path):
		DirAccess.remove_absolute(path)
