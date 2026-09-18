# scripts/data/DatabaseManager.gd
class_name DatabaseManager
extends RefCounted

# Content paths come from the shared content set (DataRoot), not from a mirror.
# Editor-only libraries live under `<set>/editor/`, which the game server never
# reads. See docs/roadmap/editor-content-source.md.
static func npc_dir() -> String: return DataRoot.content_dir("npcs")
static func item_dir() -> String: return DataRoot.content_dir("items")
static func magic_dir() -> String: return DataRoot.content_dir("magic")
static func quest_dir() -> String: return DataRoot.content_dir("quests")
static func template_dir() -> String: return DataRoot.editor_file("templates") + "/"
static func campaign_dir() -> String: return DataRoot.content_dir("campaigns")
static func collections_file() -> String: return DataRoot.content_file("collections.json")
static func discoveries_file() -> String: return DataRoot.content_file("discoveries.json")
static func magic_groups_file() -> String: return DataRoot.editor_file("magic_groups.json")
# Branching campaign graphs (CampaignDefinition/CampaignNode) -- distinct
# from the simple linear quest-chain list in quests/campaigns.json, which
# quest_dir() already picks up since it lives inside quests/.
#
# collections.json and discoveries.json are single content-root files rather
# than directories: the editor loads them so it knows about real content-set
# data, and `magic_groups.json` is editor-only, so it lives under `editor/`.

# Data stores
var npcs: Dictionary = {}
var items: Dictionary = {}
var magic: Dictionary = {}
var quests: Dictionary = {}
var templates: Dictionary = {}
var campaigns: Dictionary = {}
var collections: Dictionary = {}
var discoveries: Dictionary = {}
var magic_groups: Dictionary = {}
var magic_groups_dirty := false

# Dirty State Tracking { "type": { "id": true } }
var dirty_flags: Dictionary = {
	"npc": {}, "item": {}, "magic": {}, "quest": {}, "template": {}
}

func _init():
	_ensure_dir(npc_dir())
	_ensure_dir(item_dir())
	_ensure_dir(magic_dir())
	_ensure_dir(quest_dir())
	_ensure_dir(template_dir())
	_ensure_dir(campaign_dir())
	load_all()

func _ensure_dir(path):
	if not DirAccess.dir_exists_absolute(path): DirAccess.make_dir_recursive_absolute(path)

func load_all():
	npcs.clear(); items.clear(); magic.clear(); quests.clear(); templates.clear()
	campaigns.clear(); collections.clear(); discoveries.clear(); magic_groups.clear(); magic_groups_dirty = false
	mark_clean()
	_load_recursive(npc_dir(), "", npcs)
	_load_recursive(item_dir(), "", items)
	_load_recursive(magic_dir(), "", magic)
	_load_recursive(quest_dir(), "", quests)
	# Quest stage graph positions live in `editor/quest_layout.json`, not in the
	# quests the game reads; merge them so every call site still sees them.
	quests = EditorLayout.merge_quests(quests)
	_load_recursive(template_dir(), "", templates)
	_load_campaigns()
	if FileAccess.file_exists(collections_file()): _load_file(collections_file(), "collections.json", collections)
	if FileAccess.file_exists(discoveries_file()): _load_file(discoveries_file(), "discoveries.json", discoveries)
	_load_magic_groups()

func _load_magic_groups():
	if not FileAccess.file_exists(magic_groups_file()):
		magic_groups = _default_magic_groups()
		return
	var json := JSON.new()
	if json.parse(FileAccess.get_file_as_string(magic_groups_file())) == OK:
		magic_groups = json.get_data().get("groups", {})
	if magic_groups.is_empty(): magic_groups = _default_magic_groups()

func _default_magic_groups() -> Dictionary:
	return {
		"restoration": {"name": "Restoration"}, "curses": {"name": "Curses"},
		"elemental": {"name": "Elemental"}, "evocation": {"name": "Evocation"},
		"conjuration": {"name": "Conjuration"}, "utility": {"name": "Utility"},
		"general": {"name": "General"}
	}

# Each file under campaign_dir() is one whole CampaignDefinition (campaign_id,
# name, start_node_id, nodes{...}) -- not a library of several entries the
# way an items/npcs file is. _load_file's single-vs-library heuristic keys
# off a "type" field these files don't have, and would otherwise misread the
# campaign's own "nodes" dictionary as if it were a second top-level entry.
# Load each file as exactly one campaign, keyed by its own campaign_id.
func _load_campaigns():
	var dir = DirAccess.open(campaign_dir())
	if not dir: return
	dir.list_dir_begin()
	var file_name = dir.get_next()
	while file_name != "":
		if not dir.current_is_dir() and file_name.ends_with(".json"):
			var f = FileAccess.open(campaign_dir().path_join(file_name), FileAccess.READ)
			if f:
				var json = JSON.new()
				if json.parse(f.get_as_text()) == OK:
					var data = json.get_data()
					if typeof(data) == TYPE_DICTIONARY and not data.is_empty():
						var id = data.get("campaign_id", file_name.replace(".json", ""))
						data["_filename"] = file_name
						campaigns[id] = data
				else:
					print("Error parsing JSON in %s: %s" % [file_name, json.get_error_message()])
		file_name = dir.get_next()

func _load_recursive(root_dir: String, current_subdir: String, target_dict: Dictionary):
	var full_current_path = root_dir.path_join(current_subdir)
	var dir = DirAccess.open(full_current_path)
	if dir:
		dir.list_dir_begin()
		var file_name = dir.get_next()
		while file_name != "":
			if dir.current_is_dir():
				if file_name != "." and file_name != "..":
					_load_recursive(root_dir, current_subdir.path_join(file_name), target_dict)
			elif file_name.ends_with(".json"):
				_load_file(full_current_path.path_join(file_name), current_subdir.path_join(file_name), target_dict)
			file_name = dir.get_next()

func _load_file(full_path: String, relative_path: String, target_dict: Dictionary):
	var f = FileAccess.open(full_path, FileAccess.READ)
	if f:
		var json = JSON.new()
		var parse_err = json.parse(f.get_as_text())
		if parse_err == OK:
			var data = json.get_data()
			if typeof(data) == TYPE_DICTIONARY:
				if data.is_empty(): return

				var is_likely_single = data.has("name") and data.has("type") and typeof(data.get("name")) == TYPE_STRING
				
				var dict_value_count = 0
				var total_keys = 0
				for k in data:
					total_keys += 1
					if typeof(data[k]) == TYPE_DICTIONARY:
						dict_value_count += 1
				
				var is_likely_library = dict_value_count > 0
				
				if is_likely_single and not (is_likely_library and total_keys > 5 and not data.has("id")):
					var id = data.get("id", relative_path.get_file().replace(".json", ""))
					target_dict[id] = data
					target_dict[id]["_filename"] = relative_path
				elif is_likely_library:
					for id in data:
						if typeof(data[id]) == TYPE_DICTIONARY:
							target_dict[id] = data[id]
							target_dict[id]["_filename"] = relative_path
				else:
					print("Warning: Could not determine format of %s. Loading contents as items." % relative_path)
					for id in data:
						if typeof(data[id]) == TYPE_DICTIONARY:
							target_dict[id] = data[id]
							target_dict[id]["_filename"] = relative_path
		else:
			print("Error parsing JSON in %s: %s" % [relative_path, json.get_error_message()])

func save_all():
	# Lift editor layout out to `editor/` before anything is written, so the
	# files the game reads never carry `_editor_*` keys.
	EditorLayout.split_quests(quests)
	_save_category(npcs, npc_dir())
	_save_category(items, item_dir())
	_save_category(magic, magic_dir())
	_save_category(quests, quest_dir())
	_save_category(templates, template_dir())
	_save_magic_groups()
	mark_clean()

func _save_magic_groups():
	var file := FileAccess.open(magic_groups_file(), FileAccess.WRITE)
	if file: file.store_string(JSON.stringify({"groups": magic_groups}, "\t"))
	magic_groups_dirty = false

func mark_magic_groups_dirty():
	magic_groups_dirty = true

func _save_category(cache: Dictionary, root_dir: String):
	var files_content = {}
	for id in cache:
		var data = cache[id]
		var fname = data.get("_filename", "custom.json")
		if not files_content.has(fname): files_content[fname] = {}
		var save_copy = data.duplicate(true)
		save_copy.erase("_filename")
		# Belt and braces with the split above: nothing `_editor_*` reaches the
		# game's content, at any nesting depth, whatever wrote it.
		save_copy = EditorLayout.strip_entry(save_copy)
		files_content[fname][id] = save_copy
	
	for fname in files_content:
		var full_path = root_dir.path_join(fname)
		var base_dir = full_path.get_base_dir()
		if not DirAccess.dir_exists_absolute(base_dir): DirAccess.make_dir_recursive_absolute(base_dir)
		var f = FileAccess.open(full_path, FileAccess.WRITE)
		if f: f.store_string(JSON.stringify(files_content[fname], "\t"))

func add_npc(id: String, data: Dictionary): _add_entry(id, data, npcs); mark_dirty("npc", id)
func add_item(id: String, data: Dictionary): _add_entry(id, data, items); mark_dirty("item", id)
func add_magic(id: String, data: Dictionary): _add_entry(id, data, magic); mark_dirty("magic", id)
func add_quest(id: String, data: Dictionary): _add_entry(id, data, quests); mark_dirty("quest", id)
func save_template(id: String, data: Dictionary): _add_entry(id, data, templates); mark_dirty("template", id)

func rename_entry(type: String, old_id: String, new_id: String) -> bool:
	var target_dict
	match type:
		"npc": target_dict = npcs
		"item": target_dict = items
		"magic": target_dict = magic
		"quest": target_dict = quests
		"template": target_dict = templates
	
	if not target_dict.has(old_id) or target_dict.has(new_id): return false
	
	var data = target_dict[old_id]
	target_dict[new_id] = data
	target_dict.erase(old_id)
	
	# Transfer dirty state
	if dirty_flags[type].has(old_id):
		dirty_flags[type].erase(old_id)
	
	mark_dirty(type, new_id)
	return true

func _add_entry(id: String, data: Dictionary, cache: Dictionary):
	if not data.has("_filename"): data["_filename"] = "custom.json" 
	cache[id] = data

func delete_entry(type: String, id: String):
	var target_dict
	match type:
		"npc": target_dict = npcs
		"item": target_dict = items
		"magic": target_dict = magic
		"quest": target_dict = quests
		"template": target_dict = templates
	if target_dict.has(id):
		target_dict.erase(id)
		# Saving rewrites the category files; retain a dirty marker even though
		# the deleted entry itself can no longer appear in the browser.
		mark_dirty(type, id)

func mark_dirty(type: String, id: String):
	if dirty_flags.has(type): dirty_flags[type][id] = true

func mark_clean():
	for t in dirty_flags: dirty_flags[t].clear()

func get_ids(type: String) -> Array:
	var d
	match type:
		"npc": d = npcs
		"item": d = items
		"magic": d = magic
		"quest": d = quests
		"template": d = templates
	var k = d.keys()
	k.sort()
	return k

func get_npc_ids() -> Array: return get_ids("npc")
func get_item_ids() -> Array: return get_ids("item")
func get_template_ids() -> Array: return get_ids("template")
