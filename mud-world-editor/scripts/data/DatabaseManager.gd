# scripts/data/DatabaseManager.gd
class_name DatabaseManager
extends RefCounted

const NPC_DIR = "res://data/npcs/"
const ITEM_DIR = "res://data/items/"
const MAGIC_DIR = "res://data/magic/"
const QUEST_DIR = "res://data/quests/"
const TEMPLATE_DIR = "res://data/templates/"

# Data stores
var npcs: Dictionary = {}
var items: Dictionary = {}
var magic: Dictionary = {}
var quests: Dictionary = {}
var templates: Dictionary = {}

# Dirty State Tracking { "type": { "id": true } }
var dirty_flags: Dictionary = {
	"npc": {}, "item": {}, "magic": {}, "quest": {}, "template": {}
}

func _init():
	_ensure_dir(NPC_DIR)
	_ensure_dir(ITEM_DIR)
	_ensure_dir(MAGIC_DIR)
	_ensure_dir(QUEST_DIR)
	_ensure_dir(TEMPLATE_DIR)
	load_all()

func _ensure_dir(path):
	if not DirAccess.dir_exists_absolute(path): DirAccess.make_dir_recursive_absolute(path)

func load_all():
	npcs.clear(); items.clear(); magic.clear(); quests.clear(); templates.clear()
	mark_clean()
	_load_recursive(NPC_DIR, "", npcs)
	_load_recursive(ITEM_DIR, "", items)
	_load_recursive(MAGIC_DIR, "", magic)
	_load_recursive(QUEST_DIR, "", quests)
	_load_recursive(TEMPLATE_DIR, "", templates)

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
	_save_category(npcs, NPC_DIR)
	_save_category(items, ITEM_DIR)
	_save_category(magic, MAGIC_DIR)
	_save_category(quests, QUEST_DIR)
	_save_category(templates, TEMPLATE_DIR)
	mark_clean()

func _save_category(cache: Dictionary, root_dir: String):
	var files_content = {}
	for id in cache:
		var data = cache[id]
		var fname = data.get("_filename", "custom.json")
		if not files_content.has(fname): files_content[fname] = {}
		var save_copy = data.duplicate(true)
		save_copy.erase("_filename")
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
	if target_dict.has(id): target_dict.erase(id)

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
