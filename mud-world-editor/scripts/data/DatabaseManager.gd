# scripts/data/DatabaseManager.gd
class_name DatabaseManager
extends RefCounted

const SaveIO = preload("res://scripts/data/SaveIO.gd")

# The content set's contracts, loaded once and shared: the item inspector lists
# families and roll tables from it, and the contract browser shows the whole
# vocabulary. One instance, so the editor and the engine are reading the same
# declarations rather than two caches that can disagree.
var catalog: ContractCatalog = ContractCatalog.new()

# Item-directory files the engine reads as something other than item templates.
# `definition_loader` skips exactly these two when it builds `item_templates`
# (sets.json feeds SetManager, affixes.json feeds the affix generator), and the
# editor used to load them into the Items cache anyway -- so `prefixes` and
# `suffixes` appeared in the library as if they were items, and saving any item
# rewrote affixes.json from that cache, deleting its two string-valued
# top-level keys (`generated_effect_name_pattern`,
# `generated_description_suffix`) that the engine reads.
const READ_ONLY_ITEM_FILES := ["sets.json", "affixes.json"]

# Content paths come from the shared content set (DataRoot), not from a mirror.
# Editor-only libraries live under `<set>/editor/`, which the game server never
# reads. See docs/roadmap/editor-content-source.md.
static func npc_dir() -> String: return DataRoot.content_dir("npcs")
static func item_dir() -> String: return DataRoot.content_dir("items")
static func magic_dir() -> String: return DataRoot.content_dir("magic")
# Where this content set's abilities live. The engine prefers `abilities/` and
# falls back to `magic/` (spell_registry.load_spells_from_json), so the editor
# asks the same question in the same order -- a set whose abilities are device
# charges rather than spells keeps its own directory name, and before this it was
# invisible: `orbital_salvage/data/abilities/overcharge.json` had no surface at
# all. The cache is still called `magic`; the ability *editor* keeps its name for
# now, and the vocabulary pass is recorded in the evaluation doc.
static func abilities_dir() -> String:
	var abilities := DataRoot.content_dir("abilities")
	if DirAccess.dir_exists_absolute(abilities):
		return abilities
	return magic_dir()

static func quest_dir() -> String: return DataRoot.content_dir("quests")
# Recipes: one directory, several files, each a library of recipes keyed by id.
static func recipe_dir() -> String: return DataRoot.content_dir("crafting")
# Dialogue: one *graph* per file, not a library of entries -- `nodes` inside a
# graph is the graph's own structure, and `_load_file`'s single-vs-library
# heuristic would read it as a second entry. Loaded and saved by hand, like
# campaigns.
static func dialogue_dir() -> String: return DataRoot.content_dir("dialogue")
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
var recipes: Dictionary = {}
var dialogues: Dictionary = {}
# Filename → graph id, so a deleted graph can take its file with it.
var dialogue_files: Dictionary = {}
var templates: Dictionary = {}
var campaigns: Dictionary = {}
var collections: Dictionary = {}
var discoveries: Dictionary = {}
var magic_groups: Dictionary = {}
var magic_groups_dirty := false

# Dirty State Tracking { "type": { "id": true } }
var dirty_flags: Dictionary = {
	"npc": {}, "item": {}, "magic": {}, "quest": {}, "template": {}, "recipe": {}, "dialogue": {}
}

# Top-level keys of a content file that are not entries: a `_comment`, a pattern
# string, anything the editor does not model. Recorded at load and re-emitted on
# save, so a file never loses data merely because the editor rewrote it.
var file_extras: Dictionary = {}
# Every content file the editor loaded, keyed by the directory it belongs to, so
# a file whose last entry is deleted is rewritten empty instead of being left
# alone with the stale entry still in it. Keyed by directory because a relative
# filename is not unique across categories: "library.json" under items and
# under magic are different files, and an unscoped set wrote every category's
# filenames into every other category's directory.
var known_files: Dictionary = {}

func _init():
	# Directories are created when a file is actually written (see the save
	# path), not here: creating `magic/` -- or `quests/`, or `campaigns/` -- in a
	# content set that has none is the editor writing vocabulary the world does
	# not speak, and it did that merely by being pointed at a content set.
	load_all()

func _ensure_dir(path):
	if not DirAccess.dir_exists_absolute(path): DirAccess.make_dir_recursive_absolute(path)

func load_all():
	npcs.clear(); items.clear(); magic.clear(); quests.clear(); templates.clear(); recipes.clear(); dialogues.clear()
	campaigns.clear(); collections.clear(); discoveries.clear(); magic_groups.clear(); magic_groups_dirty = false
	file_extras.clear(); known_files.clear()
	mark_clean()
	# Contracts first: an item inspector offers families and roll tables from here,
	# and a content set without contracts is legal (the engine falls back to its own
	# neutral defaults), so an empty catalog must stay loadable.
	catalog = ContractCatalog.new()
	catalog.load_contracts()
	_load_recursive(npc_dir(), "", npcs)
	_load_recursive(item_dir(), "", items, READ_ONLY_ITEM_FILES)
	_load_recursive(abilities_dir(), "", magic)
	_load_recursive(quest_dir(), "", quests)
	_load_recursive(recipe_dir(), "", recipes)
	_load_dialogue_graphs()
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

# Each file under dialogue_dir() is one whole conversation graph (`id`, `root`,
# `nodes{...}`), for the same reason campaigns are: `nodes` is the graph's own
# structure, not a library of entries, and the generic heuristic would read it as
# one. The graph id is the file's `id`, falling back to the filename stem, which
# is what the engine does (`content_set._validate_dialogue_content`).
func _load_dialogue_graphs():
	dialogues.clear()
	dialogue_files.clear()
	var dir = DirAccess.open(dialogue_dir())
	if not dir:
		return
	dir.list_dir_begin()
	var file_name = dir.get_next()
	while file_name != "":
		if not dir.current_is_dir() and file_name.ends_with(".json"):
			var path := dialogue_dir().path_join(file_name)
			var json := JSON.new()
			if json.parse(FileAccess.get_file_as_string(path)) == OK:
				var data = json.get_data()
				if typeof(data) == TYPE_DICTIONARY and not data.is_empty():
					# `str(x or y)` is a bool in GDScript, not a fallback: it
					# produced the graph id "true" for every file. The engine
					# falls back to the filename stem when `id` is absent.
					var authored_id := DialogueSchema.value_of(data.get("id", ""))
					var graph_id := authored_id if authored_id != "" else file_name.replace(".json", "")
					data["_filename"] = file_name
					dialogues[graph_id] = data
					dialogue_files[file_name] = graph_id
		file_name = dir.get_next()


# One graph per file, written back to the file it came from. `_save_category`
# cannot do this: it groups entries into `{id: entry}` documents, which for a
# dialogue graph would nest the graph one level deeper than the engine reads it.
func _save_dialogue_graphs(errors: Array) -> void:
	if dialogues.is_empty() and dialogue_files.is_empty():
		return
	_ensure_dir(dialogue_dir())
	for file_name in dialogue_files:
		# A graph deleted in the editor takes its file with it; otherwise the
		# entry would be back on the next load.
		if not dialogues.has(dialogue_files[file_name]):
			var stale := dialogue_dir().path_join(file_name)
			if FileAccess.file_exists(stale):
				DirAccess.remove_absolute(stale)
			continue

	for graph_id in dialogues:
		var data: Dictionary = dialogues[graph_id]
		if not (data is Dictionary):
			continue
		var file_name := str(data.get("_filename", "%s.json" % graph_id))
		var payload: Dictionary = data.duplicate(true)
		payload.erase("_filename")
		payload = EditorLayout.strip_entry(payload)
		var result: Dictionary = SaveIO.write_json(dialogue_dir().path_join(file_name), payload)
		if not result.get("ok", false):
			errors.append(result.get("error", "Could not save dialogue graph %s." % graph_id))


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

func _load_recursive(root_dir: String, current_subdir: String, target_dict: Dictionary,
		skip_filenames: Array = []):
	var full_current_path = root_dir.path_join(current_subdir)
	var dir = DirAccess.open(full_current_path)
	if dir:
		dir.list_dir_begin()
		var file_name = dir.get_next()
		while file_name != "":
			if dir.current_is_dir():
				if file_name != "." and file_name != "..":
					_load_recursive(root_dir, current_subdir.path_join(file_name), target_dict, skip_filenames)
			elif file_name.ends_with(".json"):
				if skip_filenames.has(file_name):
					# The engine reads these as something other than templates;
					# the editor keeps its hands off them entirely rather than
					# loading them into a cache it would later write back.
					pass
				else:
					_load_file(full_current_path.path_join(file_name),
						current_subdir.path_join(file_name), target_dict, root_dir)
			file_name = dir.get_next()

func _load_file(full_path: String, relative_path: String, target_dict: Dictionary, root_dir: String = ""):
	var f = FileAccess.open(full_path, FileAccess.READ)
	if f:
		var json = JSON.new()
		var parse_err = json.parse(f.get_as_text())
		if parse_err == OK:
			var data = json.get_data()
			if typeof(data) == TYPE_DICTIONARY:
				if data.is_empty(): return
				if root_dir != "":
					if not known_files.has(root_dir): known_files[root_dir] = {}
					known_files[root_dir][relative_path] = true

				# Anything at the top level that is not an entry is remembered and
				# written back on save. Without this, a `_comment` (or any scalar
				# metadata) in an items/npcs/magic/quests file is deleted the first
				# time the editor saves that category.
				var extras := {}
				for key in data:
					if typeof(data[key]) != TYPE_DICTIONARY:
						extras[key] = data[key]
				if not extras.is_empty():
					file_extras[relative_path] = extras

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

# Save every category. Returns {"ok": bool, "errors": Array[String]}; the caller
# keeps the dirty state on failure and shows what went wrong.
func save_all() -> Dictionary:
	# Lift editor layout out to `editor/` before anything is written, so the
	# files the game reads never carry `_editor_*` keys.
	EditorLayout.split_quests(quests)
	var errors: Array = []
	_save_category(npcs, npc_dir(), errors)
	_save_category(items, item_dir(), errors)
	_save_category(magic, abilities_dir(), errors)
	_save_category(quests, quest_dir(), errors)
	_save_category(recipes, recipe_dir(), errors)
	_save_dialogue_graphs(errors)
	_save_category(templates, template_dir(), errors)
	var groups := _save_magic_groups()
	if not groups.get("ok", false):
		errors.append(groups.get("error", "Could not save magic groups."))
	if errors.is_empty():
		mark_clean()
	return {"ok": errors.is_empty(), "errors": errors}

func _save_magic_groups() -> Dictionary:
	_ensure_dir(DataRoot.editor_dir())
	var result: Dictionary = SaveIO.write_json(magic_groups_file(), {"groups": magic_groups})
	if result.get("ok", false):
		magic_groups_dirty = false
	return result

func mark_magic_groups_dirty():
	magic_groups_dirty = true

func _save_category(cache: Dictionary, root_dir: String, errors: Array):
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

	# A file the editor loaded is rewritten even when it has no entries left, so
	# deleting the last entry of a file actually deletes it instead of leaving
	# the file untouched for the entry to reappear on the next load. Only this
	# category's own files, keyed by the directory they were loaded from.
	var known: Dictionary = known_files.get(root_dir, {})
	for fname in known:
		if not files_content.has(fname):
			files_content[fname] = {}

	for fname in files_content:
		var full_path = root_dir.path_join(fname)
		_ensure_dir(full_path.get_base_dir())
		# Non-entry keys the editor does not model go back first, so a file it
		# rewrites is never a file it truncated.
		var payload := {}
		if file_extras.has(fname):
			payload = (file_extras[fname] as Dictionary).duplicate(true)
		for id in files_content[fname]:
			payload[id] = files_content[fname][id]
		var result: Dictionary = SaveIO.write_json(full_path, payload)
		if not result.get("ok", false):
			errors.append(result.get("error", "Could not save %s." % fname))

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

# The cache a type name refers to. An unknown type gets an empty dictionary
# rather than null, so every caller has one code path and no null checks.
func _cache_for(type: String) -> Dictionary:
	match type:
		"npc": return npcs
		"item": return items
		"magic": return magic
		"quest": return quests
		"template": return templates
		"recipe": return recipes
		"dialogue": return dialogues
	return {}

func has_entry(type: String, id: String) -> bool:
	return _cache_for(type).has(id)

func entry(type: String, id: String) -> Dictionary:
	var cache := _cache_for(type)
	if not cache.has(id):
		return {}
	return cache[id]

# Removes an entry and returns {"removed": <the entry as it was>} so the caller
# can put it back: deleting an item or an NPC is now undoable, which it was not.
func delete_entry(type: String, id: String) -> Dictionary:
	var cache := _cache_for(type)
	if not cache.has(id):
		return {}
	var removed: Dictionary = (cache[id] as Dictionary).duplicate(true)
	cache.erase(id)
	# Saving rewrites the category files; retain a dirty marker even though
	# the deleted entry itself can no longer appear in the browser.
	mark_dirty(type, id)
	return {"removed": removed}

func restore_entry(type: String, id: String, data: Dictionary) -> void:
	_cache_for(type)[id] = data.duplicate(true)
	mark_dirty(type, id)

func mark_dirty(type: String, id: String):
	if dirty_flags.has(type): dirty_flags[type][id] = true

# Whether anything at all is waiting to be written.
func has_unsaved_changes() -> bool:
	for type in dirty_flags:
		if not dirty_flags[type].is_empty():
			return true
	return magic_groups_dirty

func mark_clean():
	for t in dirty_flags: dirty_flags[t].clear()
	magic_groups_dirty = false

func get_ids(type: String) -> Array:
	var d = _cache_for(type)
	if d == null:
		return []
	var k = d.keys()
	k.sort()
	return k

func add_dialogue(id: String, data: Dictionary): _add_entry(id, data, dialogues); mark_dirty("dialogue", id)
func get_dialogue_ids() -> Array: return get_ids("dialogue")
func add_recipe(id: String, data: Dictionary): _add_entry(id, data, recipes); mark_dirty("recipe", id)
func get_recipe_ids() -> Array: return get_ids("recipe")
func get_npc_ids() -> Array: return get_ids("npc")
func get_item_ids() -> Array: return get_ids("item")
func get_template_ids() -> Array: return get_ids("template")
