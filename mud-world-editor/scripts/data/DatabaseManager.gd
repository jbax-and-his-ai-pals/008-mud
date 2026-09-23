# scripts/data/DatabaseManager.gd
class_name DatabaseManager
extends RefCounted

const SaveIO = preload("res://scripts/data/SaveIO.gd")
const COMBAT_VOCABULARY_CATALOG_SCRIPT = preload("res://scripts/data/CombatVocabularyCatalog.gd")

# The content set's contracts, loaded once and shared: the item inspector lists
# families and roll tables from it, and the contract browser shows the whole
# vocabulary. One instance, so the editor and the engine are reading the same
# declarations rather than two caches that can disagree.
var catalog: ContractCatalog = ContractCatalog.new()
var combat_vocabulary = COMBAT_VOCABULARY_CATALOG_SCRIPT.new()

# Item-directory files the engine reads as something other than item templates.
# `definition_loader` skips exactly these two when it builds `item_templates`
# (sets.json feeds SetManager, affixes.json feeds the affix generator). The editor
# used to load them into the Items cache, so `prefixes` and `suffixes` appeared in
# the library as if they were items, and saving any item rewrote affixes.json from
# that cache, deleting its string-valued top-level keys
# (`generated_effect_name_pattern`, `generated_description_suffix`).
#
# They stay excluded from the *items* cache, and are now loaded as what they are:
# `_load_affixes` and `_load_item_sets` read them into their own caches, keep their
# non-entry keys, and write them back whole. Excluding them was the workaround;
# this is the fix.
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
# Titles and their conferring guilds share one file (`engine/core/titles.py`):
# `_guilds` is a registry several titles reference by id, and the entries keyed
# without a leading underscore are the titles themselves.
static func titles_file() -> String: return DataRoot.content_file("titles.json")
static func backgrounds_file() -> String: return DataRoot.content_file("player/backgrounds.json")
# `__common_topics__` is a registry of topic ids always askable, the same
# not-an-entry-but-shares-the-file shape titles.json's `_guilds` is.
static func topics_file() -> String: return DataRoot.content_file("knowledge/topics.json")
# Region-generation themes (`world/region_generator.py`): `themes` holds one
# entry per theme and `placeholders` the word lists every theme shares.
static func themes_file() -> String: return DataRoot.content_dir("regions").path_join("dynamic_themes.json")
# Affixes and item sets live in the item directory but are their own contracts:
# `affix_data.py` reads `prefixes`/`suffixes`, `set_manager.py` reads the sets.
static func affixes_file() -> String: return DataRoot.content_file("items/affixes.json")
static func sets_file() -> String: return DataRoot.content_file("items/sets.json")
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
# Filename → campaign id, so a deleted campaign can take its file with it --
# the same reason `dialogue_files` exists.
var campaign_files: Dictionary = {}
var collections: Dictionary = {}
var discoveries: Dictionary = {}
var magic_groups: Dictionary = {}
var magic_groups_dirty := false
# ability id -> group id, the editor's own grouping. Kept here rather than in the
# ability entry because the engine's `Spell` takes keyword arguments and no
# `**kwargs`, so an unknown key like `magic_group` makes the whole abilities file
# fail to load (`spell.py`, `spell_registry.py`). An authored `magic_group` is
# migrated out of content on load and re-emitted into `editor/magic_groups.json`.
var magic_group_assignments: Dictionary = {}
var titles: Dictionary = {}
# guild_id -> {name, place}, the `_guilds` registry titles.json keeps alongside
# the titles themselves.
var guilds: Dictionary = {}
# Top-level keys of titles.json that are not `_guilds` and not a title (a
# `_comment`, for instance), kept and re-emitted on save.
var titles_extras: Dictionary = {}
# Whether titles.json existed at load, so deleting the last title still
# rewrites the file empty instead of leaving it alone with a stale entry.
var titles_file_known := false
# Same "did this file exist" tracking for the other two single-file
# categories: `_load_file` only registers a `known_files` entry when it is
# given a root directory, which collections.json/discoveries.json are not.
var collections_file_known := false
var discoveries_file_known := false
var backgrounds: Dictionary = {}
var topics: Dictionary = {}
# `__common_topics__`: topic ids askable of any NPC regardless of conversation
# history (`knowledge_manager.py`'s own docstring on the field).
var common_topics: Array = []
# Top-level keys of topics.json that are not `__common_topics__` and not a
# topic, kept and re-emitted on save -- the same reason `titles_extras` exists.
var topics_extras: Dictionary = {}
var topics_file_known := false
var themes: Dictionary = {}
var theme_placeholders: Dictionary = {}
# The file's other top-level keys, and the order all of them were written in.
var themes_extras: Dictionary = {}
var themes_key_order: Array = []
var themes_file_known := false
# Affixes and item sets: the two item-directory files that are contracts rather
# than templates. Kept in their own caches so an affix can never be edited as an
# item -- which is what corrupted `affixes.json` before -- while still being
# authorable, which it was not until now.
var affix_prefixes: Dictionary = {}
var affix_suffixes: Dictionary = {}
var item_sets: Dictionary = {}
# Non-entry top-level keys of those two files (`generated_effect_name_pattern`,
# `generated_description_suffix`, a `_comment`), kept verbatim and written back.
var affix_extras: Dictionary = {}
var sets_extras: Dictionary = {}
# Whether those two files existed at load. A set that has neither must not grow
# one merely because the editor was opened and saved.
var affixes_file_known := false
var sets_file_known := false# Top-level keys of backgrounds.json that are not a background (`_comment`,
# `_kit_rule`); `_default` is tracked separately since it is a meaningful id,
# not inert commentary.
var backgrounds_extras: Dictionary = {}
var backgrounds_default: String = ""
var backgrounds_file_known := false

# Dirty State Tracking { "type": { "id": true } }
var dirty_flags: Dictionary = {
	"npc": {}, "item": {}, "magic": {}, "quest": {}, "template": {}, "recipe": {}, "dialogue": {}, "title": {},
	"collection": {}, "discovery": {}, "background": {}, "campaign": {}, "topic": {}, "theme": {},
	"affix_prefix": {}, "affix_suffix": {}, "item_set": {}
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

## Every stat any NPC in this content set carries, in first-seen order.
##
## The fallback vocabulary for a set that declares no stats: its own data rather
## than the engine's default names, which an author never agreed to. Called
## through `ContractCatalog.stat_vocabulary(carried_stats())`.
func carried_stats() -> Array:
	var out: Array = []
	for npc_id in npcs:
		var template = npcs[npc_id]
		if typeof(template) != TYPE_DICTIONARY:
			continue
		var carried = template.get("stats", {})
		if typeof(carried) != TYPE_DICTIONARY:
			continue
		for stat in carried:
			var text := str(stat).strip_edges()
			if text != "" and not out.has(text):
				out.append(text)
	return out

func load_all():
	npcs.clear(); items.clear(); magic.clear(); quests.clear(); templates.clear(); recipes.clear(); dialogues.clear()
	campaigns.clear(); campaign_files.clear(); collections.clear(); discoveries.clear(); magic_groups.clear(); magic_groups_dirty = false
	titles.clear(); guilds.clear(); titles_extras.clear(); titles_file_known = false
	topics.clear(); common_topics.clear(); topics_extras.clear(); topics_file_known = false
	themes.clear(); theme_placeholders.clear(); themes_extras.clear(); themes_key_order.clear(); themes_file_known = false
	collections_file_known = false; discoveries_file_known = false
	backgrounds.clear(); backgrounds_extras.clear(); backgrounds_default = ""; backgrounds_file_known = false
	file_extras.clear(); known_files.clear()
	mark_clean()
	# Contracts first: an item inspector offers families and roll tables from here,
	# and a content set without contracts is legal (the engine falls back to its own
	# neutral defaults), so an empty catalog must stay loadable.
	catalog = ContractCatalog.new()
	catalog.load_contracts()
	combat_vocabulary = COMBAT_VOCABULARY_CATALOG_SCRIPT.new()
	combat_vocabulary.load()
	_load_recursive(npc_dir(), "", npcs)
	_load_recursive(item_dir(), "", items, READ_ONLY_ITEM_FILES)
	_load_recursive(abilities_dir(), "", magic)
	_migrate_magic_groups()
	_load_recursive(quest_dir(), "", quests)
	_load_recursive(recipe_dir(), "", recipes)
	_load_dialogue_graphs()
	# Quest stage graph positions live in `editor/quest_layout.json`, not in the
	# quests the game reads; merge them so every call site still sees them.
	quests = EditorLayout.merge_quests(quests)
	_load_recursive(template_dir(), "", templates)
	_load_campaigns()
	collections_file_known = FileAccess.file_exists(collections_file())
	if collections_file_known: _load_file(collections_file(), "collections.json", collections)
	discoveries_file_known = FileAccess.file_exists(discoveries_file())
	if discoveries_file_known: _load_file(discoveries_file(), "discoveries.json", discoveries)
	_load_magic_groups()
	_load_titles()
	_load_topics()
	_load_themes()
	_load_backgrounds()
	_load_affixes()
	_load_item_sets()

# Titles are one file, not a directory of entries, and it carries a second
# registry (`_guilds`) alongside the titles themselves -- `_load_file`'s
# single-vs-library heuristic has no notion of that, so this is loaded by hand,
# the same reason dialogue graphs and campaigns are.
func _load_titles():
	titles_file_known = FileAccess.file_exists(titles_file())
	if not titles_file_known: return
	var json := JSON.new()
	if json.parse(FileAccess.get_file_as_string(titles_file())) != OK: return
	var data = json.get_data()
	if typeof(data) != TYPE_DICTIONARY: return
	for key in data:
		var id := str(key)
		if id == "_guilds":
			if data[key] is Dictionary: guilds = (data[key] as Dictionary).duplicate(true)
		elif id.begins_with("_"):
			titles_extras[id] = data[key]
		elif data[key] is Dictionary:
			titles[id] = (data[key] as Dictionary).duplicate(true)

func _save_titles(errors: Array) -> void:
	if not titles_file_known and titles.is_empty() and guilds.is_empty() and titles_extras.is_empty():
		return
	var payload := {}
	for key in titles_extras: payload[key] = titles_extras[key]
	if not guilds.is_empty(): payload["_guilds"] = guilds
	for id in titles: payload[id] = titles[id]
	var result: Dictionary = SaveIO.write_json(titles_file(), payload)
	if result.get("ok", false):
		titles_file_known = true
	else:
		errors.append(result.get("error", "Could not save titles."))

# `__common_topics__` alongside topic entries -- the same shape titles.json's
# `_guilds` is, for the same reason `_load_file`'s single-vs-library heuristic
# cannot be trusted with it (a topic has its own `responses` array, which the
# heuristic has no way to tell apart from a second entry).
func _load_topics():
	topics_file_known = FileAccess.file_exists(topics_file())
	if not topics_file_known: return
	var json := JSON.new()
	if json.parse(FileAccess.get_file_as_string(topics_file())) != OK: return
	var data = json.get_data()
	if typeof(data) != TYPE_DICTIONARY: return
	for key in data:
		var id := str(key)
		if id == "__common_topics__":
			if data[key] is Array: common_topics = (data[key] as Array).duplicate(true)
		elif id.begins_with("_"):
			topics_extras[id] = data[key]
		elif data[key] is Dictionary:
			topics[id] = (data[key] as Dictionary).duplicate(true)

func _save_topics(errors: Array) -> void:
	if not topics_file_known and topics.is_empty() and common_topics.is_empty() and topics_extras.is_empty():
		return
	var payload := {}
	for key in topics_extras: payload[key] = topics_extras[key]
	if not common_topics.is_empty(): payload["__common_topics__"] = common_topics
	for id in topics: payload[id] = topics[id]
	var result: Dictionary = SaveIO.write_json(topics_file(), payload)
	if result.get("ok", false):
		topics_file_known = true
	else:
		errors.append(result.get("error", "Could not save knowledge topics."))

func _load_themes():
	themes_file_known = FileAccess.file_exists(themes_file())
	if not themes_file_known: return
	var json := JSON.new()
	if json.parse(FileAccess.get_file_as_string(themes_file())) != OK: return
	var data = json.get_data()
	if typeof(data) != TYPE_DICTIONARY: return
	for key in data:
		var id := str(key)
		themes_key_order.append(id)
		if id == "themes" and data[key] is Dictionary:
			for theme_id in data[key]:
				if data[key][theme_id] is Dictionary: themes[str(theme_id)] = (data[key][theme_id] as Dictionary).duplicate(true)
		elif id == "placeholders" and data[key] is Dictionary:
			theme_placeholders = (data[key] as Dictionary).duplicate(true)
		else:
			themes_extras[id] = data[key]

func _save_themes(errors: Array) -> void:
	if not themes_file_known and themes.is_empty() and theme_placeholders.is_empty():
		return
	var payload := {}
	var order: Array = themes_key_order.duplicate()
	for key in ["themes", "placeholders"]:
		if not order.has(key): order.append(key)
	for key in order:
		match key:
			"themes": payload["themes"] = themes
			"placeholders": payload["placeholders"] = theme_placeholders
			_: if themes_extras.has(key): payload[key] = themes_extras[key]
	var result: Dictionary = SaveIO.write_json(themes_file(), payload)
	if result.get("ok", false):
		themes_file_known = true
	else:
		errors.append(result.get("error", "Could not save region themes."))

# A single-file, one-entry-per-key category (collections, discoveries): write
# its entries back over whatever non-entry keys the file already carried, and
# keep rewriting the file even once every entry is gone, the same reason
# `_save_category` rewrites a directory file whose last entry was deleted.
# Returns the "does this file exist now" flag the caller should keep.
func _save_single_file(cache: Dictionary, path: String, relative_key: String, file_known: bool, errors: Array) -> bool:
	if not file_known and cache.is_empty():
		return file_known
	var payload := {}
	if file_extras.has(relative_key):
		payload = (file_extras[relative_key] as Dictionary).duplicate(true)
	for id in cache: payload[id] = cache[id]
	var result: Dictionary = SaveIO.write_json(path, payload)
	if result.get("ok", false):
		return true
	errors.append(result.get("error", "Could not save %s." % relative_key))
	return file_known

# Backgrounds are one file with a special `_default` key (which background a
# new character gets when none is chosen), the same shape as titles' `_guilds`
# in that it is structured content, not inert commentary, so it is not folded
# into `backgrounds_extras`.
func _load_backgrounds():
	backgrounds_file_known = FileAccess.file_exists(backgrounds_file())
	if not backgrounds_file_known: return
	var json := JSON.new()
	if json.parse(FileAccess.get_file_as_string(backgrounds_file())) != OK: return
	var data = json.get_data()
	if typeof(data) != TYPE_DICTIONARY: return
	for key in data:
		var id := str(key)
		if id == "_default":
			backgrounds_default = str(data[key])
		elif id.begins_with("_"):
			backgrounds_extras[id] = data[key]
		elif data[key] is Dictionary:
			backgrounds[id] = (data[key] as Dictionary).duplicate(true)

func _save_backgrounds(errors: Array) -> void:
	if not backgrounds_file_known and backgrounds.is_empty() and backgrounds_extras.is_empty() and backgrounds_default == "":
		return
	var payload := {}
	for key in backgrounds_extras: payload[key] = backgrounds_extras[key]
	if backgrounds_default != "": payload["_default"] = backgrounds_default
	for id in backgrounds: payload[id] = backgrounds[id]
	var result: Dictionary = SaveIO.write_json(backgrounds_file(), payload)
	if result.get("ok", false):
		backgrounds_file_known = true
	else:
		errors.append(result.get("error", "Could not save backgrounds."))

func set_default_background(id: String) -> void:
	backgrounds_default = id
	mark_dirty("background", "_default")

func guild_ids() -> Array:
	var ids := guilds.keys()
	ids.sort()
	return ids

func guild_name(guild_id: String) -> String:
	return str(guilds.get(guild_id, {}).get("name", guild_id))

func add_guild(guild_id: String, guild_name_text: String, place: String = "") -> void:
	var entry := {"name": guild_name_text}
	if place != "": entry["place"] = place
	guilds[guild_id] = entry
	mark_dirty("title", "_guilds")

func set_guild_place(guild_id: String, place: String) -> void:
	if not guilds.has(guild_id): return
	if place == "": guilds[guild_id].erase("place")
	else: guilds[guild_id]["place"] = place
	mark_dirty("title", "_guilds")

func _load_magic_groups():
	if not FileAccess.file_exists(magic_groups_file()):
		magic_groups = _default_magic_groups()
		return
	var json := JSON.new()
	if json.parse(FileAccess.get_file_as_string(magic_groups_file())) == OK:
		var payload = json.get_data()
		magic_groups = payload.get("groups", {})
		magic_group_assignments = payload.get("assignments", {})
	if magic_groups.is_empty(): magic_groups = _default_magic_groups()

## The group an ability is filed under, from the editor's state.
func magic_group_of(ability_id: String) -> String:
	return str(magic_group_assignments.get(ability_id, "")).strip_edges()

func set_magic_group(ability_id: String, group_id: String) -> void:
	if ability_id == "":
		return
	if group_id == "": magic_group_assignments.erase(ability_id)
	else: magic_group_assignments[ability_id] = group_id
	mark_magic_groups_dirty()

## Move any authored `magic_group` out of the loaded abilities and into the
## editor's state. A set written before this existed keeps the grouping an author
## chose, and the key stops being written back into content the engine refuses.
func _migrate_magic_groups():
	for ability_id in magic:
		var entry = magic[ability_id]
		if typeof(entry) != TYPE_DICTIONARY or not entry.has("magic_group"):
			continue
		var group_id := str(entry["magic_group"]).strip_edges()
		if group_id != "" and not magic_group_assignments.has(ability_id):
			magic_group_assignments[ability_id] = group_id
		entry.erase("magic_group")
		mark_dirty("magic", str(ability_id))

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
	campaign_files.clear()
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
						campaign_files[file_name] = id
				else:
					print("Error parsing JSON in %s: %s" % [file_name, json.get_error_message()])
		file_name = dir.get_next()


# One campaign per file, written back to the file it came from -- the same
# reason `_save_dialogue_graphs` cannot use `_save_category`: a campaign's own
# `nodes` dictionary would nest one level deeper than the engine reads it if
# grouped into a `{id: entry}` document.
func _save_campaigns(errors: Array) -> void:
	if campaigns.is_empty() and campaign_files.is_empty():
		return
	_ensure_dir(campaign_dir())
	for file_name in campaign_files:
		# A campaign deleted in the editor takes its file with it; otherwise
		# the entry would be back on the next load.
		if not campaigns.has(campaign_files[file_name]):
			var stale := campaign_dir().path_join(file_name)
			if FileAccess.file_exists(stale):
				DirAccess.remove_absolute(stale)

	for campaign_id in campaigns:
		var data: Dictionary = campaigns[campaign_id]
		if not (data is Dictionary):
			continue
		var file_name := str(data.get("_filename", "%s.json" % campaign_id))
		var payload: Dictionary = data.duplicate(true)
		payload.erase("_filename")
		var result: Dictionary = SaveIO.write_json(campaign_dir().path_join(file_name), payload)
		if not result.get("ok", false):
			errors.append(result.get("error", "Could not save campaign %s." % campaign_id))
		else:
			campaign_files[file_name] = campaign_id

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
	_save_campaigns(errors)
	_save_category(templates, template_dir(), errors)
	_save_titles(errors)
	_save_topics(errors)
	_save_themes(errors)
	_save_backgrounds(errors)
	collections_file_known = _save_single_file(collections, collections_file(), "collections.json", collections_file_known, errors)
	discoveries_file_known = _save_single_file(discoveries, discoveries_file(), "discoveries.json", discoveries_file_known, errors)
	var groups := _save_magic_groups()
	if not groups.get("ok", false):
		errors.append(groups.get("error", "Could not save magic groups."))
	var affixes := _save_affixes()
	if not affixes.get("ok", false):
		errors.append(str(affixes.get("error", "Could not save affixes.")))
	var sets := _save_item_sets()
	if not sets.get("ok", false):
		errors.append(str(sets.get("error", "Could not save item sets.")))
	if errors.is_empty():
		mark_clean()
	return {"ok": errors.is_empty(), "errors": errors}

func _save_magic_groups() -> Dictionary:
	_ensure_dir(DataRoot.editor_dir())
	var result: Dictionary = SaveIO.write_json(magic_groups_file(), {
		"groups": magic_groups,
		"assignments": magic_group_assignments,
	})
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
		# The engine's `Spell` accepts no unknown keyword, so an editor-owned key
		# that reached an ability must not be written back.
		save_copy.erase("magic_group")
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
func add_affix_prefix(id: String, data: Dictionary): _add_entry(id, data, affix_prefixes); mark_dirty("affix_prefix", id)
func add_affix_suffix(id: String, data: Dictionary): _add_entry(id, data, affix_suffixes); mark_dirty("affix_suffix", id)
func add_item_set(id: String, data: Dictionary): _add_entry(id, data, item_sets); mark_dirty("item_set", id)

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
		"title": return titles
		"collection": return collections
		"discovery": return discoveries
		"background": return backgrounds
		"campaign": return campaigns
		"topic": return topics
		"theme": return themes
		"affix_prefix": return affix_prefixes
		"affix_suffix": return affix_suffixes
		"item_set": return item_sets
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

# --- affixes and item sets ------------------------------------------------------
#
# Both are libraries of entries keyed by id, with extra non-entry keys beside them.
# Loaded by hand rather than through `_load_recursive`, because that heuristic
# decides single-vs-library by counting dictionary values -- and `affixes.json` has
# exactly two (`prefixes`, `suffixes`) with string keys next to them, which is the
# shape it reads as "one entry". Guessing wrong here is what deleted those keys.

func _load_affixes() -> void:
	affix_prefixes.clear(); affix_suffixes.clear(); affix_extras.clear()
	affixes_file_known = FileAccess.file_exists(affixes_file())
	var payload = _read_object(affixes_file())
	if payload.is_empty(): return
	for section in ["prefixes", "suffixes"]:
		var library = payload.get(section, {})
		if not (library is Dictionary): continue
		var target := affix_prefixes if section == "prefixes" else affix_suffixes
		for id in library:
			if library[id] is Dictionary:
				var entry: Dictionary = (library[id] as Dictionary).duplicate(true)
				entry["_filename"] = "affixes.json"
				target[str(id)] = entry
	for key in payload:
		if key != "prefixes" and key != "suffixes":
			affix_extras[key] = payload[key]

func _load_item_sets() -> void:
	item_sets.clear(); sets_extras.clear()
	sets_file_known = FileAccess.file_exists(sets_file())
	var payload = _read_object(sets_file())
	if payload.is_empty(): return
	for id in payload:
		if payload[id] is Dictionary:
			var entry: Dictionary = (payload[id] as Dictionary).duplicate(true)
			entry["_filename"] = "sets.json"
			item_sets[str(id)] = entry
		else:
			sets_extras[id] = payload[id]

func _read_object(path: String) -> Dictionary:
	if not FileAccess.file_exists(path): return {}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Dictionary else {}

func _save_affixes() -> Dictionary:
	# A set that never had the file must not grow one: the editor does not write
	# vocabulary a world does not have (the same rule that keeps it from creating
	# `magic/`, `quests/` or `campaigns/` for sets that lack them).
	if not affixes_file_known and affix_prefixes.is_empty() and affix_suffixes.is_empty() and affix_extras.is_empty():
		return {"ok": true}
	var payload := {}
	payload["prefixes"] = _entries_without_internal(affix_prefixes)
	payload["suffixes"] = _entries_without_internal(affix_suffixes)
	# Written last so the string keys keep the position they had in the file.
	for key in affix_extras:
		payload[key] = affix_extras[key]
	_ensure_dir(affixes_file().get_base_dir())
	var result: Dictionary = SaveIO.write_json(affixes_file(), payload)
	if result.get("ok", false): affixes_file_known = true
	return result

func _save_item_sets() -> Dictionary:
	if not sets_file_known and item_sets.is_empty() and sets_extras.is_empty():
		return {"ok": true}
	var payload := _entries_without_internal(item_sets)
	for key in sets_extras:
		payload[key] = sets_extras[key]
	_ensure_dir(sets_file().get_base_dir())
	var result: Dictionary = SaveIO.write_json(sets_file(), payload)
	if result.get("ok", false): sets_file_known = true
	return result

func _entries_without_internal(cache: Dictionary) -> Dictionary:
	var out := {}
	for id in cache:
		var entry = cache[id]
		if not entry is Dictionary: continue
		var copy: Dictionary = (entry as Dictionary).duplicate(true)
		copy.erase("_filename")
		out[id] = EditorLayout.strip_entry(copy)
	return out


#
# `toolkit/reference_index.py` reports where an id is named: a file, a path inside
# it, and which entry that path starts from. Renaming an entry has to fix those,
# or the content keeps naming something that no longer exists.

const CACHE_TYPES := ["npc", "item", "magic", "quest", "recipe", "dialogue", "title",
	"collection", "discovery", "background", "campaign", "topic", "theme", "template"]

# Preloaded like the editor's other helpers: a fresh `class_name` is not in the
# project's class cache until the editor has scanned it, and a headless check must
# not depend on that having happened.
const Patch = preload("res://scripts/data/ReferencePatch.gd")

# The entry one indexed path belongs to: its first segment is an entry id, and the
# file says which category holds it. Matching on `_filename` rather than on a
# directory table keeps this honest when an id exists in two categories.
func entry_named_by(file: String, entry_id: String) -> Dictionary:
	for type in CACHE_TYPES:
		var cache := _cache_for(type)
		if not cache.has(entry_id):
			continue
		var candidate = cache[entry_id]
		if not candidate is Dictionary:
			continue
		var home := str(candidate.get("_filename", ""))
		if home == "" or home == file or file.ends_with("/" + home):
			return {"entry": candidate, "type": type}
	return {}

# Apply one indexed reference path. The path minus its entry id is what
# `ReferencePatch` walks.
func patch_reference(file: String, path: String, old_id: String, new_id: String) -> Dictionary:
	var parts: Array = Patch.parse_path(path)
	if parts.size() < 2:
		return {"ok": false, "error": "the index reported no path inside %s" % file}
	var owner := entry_named_by(file, str(parts[0]))
	if owner.is_empty():
		return {"ok": false, "error": "no %s entry named by %s is loaded" % [str(parts[0]), file]}
	var inner := ".".join(parts.slice(1))
	var result: Dictionary = Patch.rename(owner["entry"], inner, old_id, new_id)
	if result.get("ok", false):
		mark_dirty(str(owner["type"]), str(parts[0]))
		# The inner path is what the caller needs to undo the patch: in key mode the
		# id is part of the path, so it changes with the rename.
		result["path_after"] = "%s.%s" % [str(parts[0]), str(result.get("path_after", inner))]
	return result

## Ask whether an indexed reference can be repaired without touching the loaded
## library.  A rename used to learn that a later path was malformed only after it
## had already changed earlier entries.  The caller preflights every hit first,
## then either applies all of them or leaves the draft exactly as it was.
func can_patch_reference(file: String, path: String, old_id: String, new_id: String) -> Dictionary:
	var parts: Array = Patch.parse_path(path)
	if parts.size() < 2:
		return {"ok": false, "error": "the index reported no path inside %s" % file}
	var owner := entry_named_by(file, str(parts[0]))
	if owner.is_empty():
		return {"ok": false, "error": "no %s entry named by %s is loaded" % [str(parts[0]), file]}
	var copy: Dictionary = (owner["entry"] as Dictionary).duplicate(true)
	var inner := ".".join(parts.slice(1))
	return Patch.rename(copy, inner, old_id, new_id)

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

## The disk checkpoint was restored after a failed validation.  The in-memory
## entries still contain the author's edits, so every affected library section
## must become visibly dirty again rather than looking saved while disk disagrees.
func mark_all_dirty() -> void:
	for type in CACHE_TYPES:
		for id in _cache_for(type):
			mark_dirty(type, str(id))
	magic_groups_dirty = true

func get_ids(type: String) -> Array:
	var d = _cache_for(type)
	if d == null:
		return []
	var k = d.keys()
	k.sort()
	return k

func add_dialogue(id: String, data: Dictionary): _add_entry(id, data, dialogues); mark_dirty("dialogue", id)
func get_dialogue_ids() -> Array: return get_ids("dialogue")
# Not `_add_entry`: that defaults `_filename` to a shared "custom.json", which
# is wrong for a one-file-per-entry store -- two new campaigns would collide
# on the same file the way `_save_campaigns` writes them.
func add_campaign(id: String, data: Dictionary):
	if not data.has("_filename"): data["_filename"] = "%s.json" % id
	campaigns[id] = data
	mark_dirty("campaign", id)
func get_campaign_ids() -> Array: return get_ids("campaign")
func add_topic(id: String, data: Dictionary): topics[id] = data; mark_dirty("topic", id)
func add_theme(id: String, data: Dictionary): themes[id] = data; mark_dirty("theme", id)
func set_theme_placeholders(lists: Dictionary):
	theme_placeholders = lists.duplicate(true)
	mark_dirty("theme", "__placeholders__")
func get_topic_ids() -> Array: return get_ids("topic")

func set_common_topics(ids: Array):
	common_topics = ids.duplicate(true)
	mark_dirty("topic", "__common_topics__")
func add_recipe(id: String, data: Dictionary): _add_entry(id, data, recipes); mark_dirty("recipe", id)
func get_recipe_ids() -> Array: return get_ids("recipe")
# Titles are one file, not one-entry-per-directory-file, so they carry no
# `_filename` the way `_add_entry` assumes every other category needs.
func add_title(id: String, data: Dictionary): titles[id] = data; mark_dirty("title", id)
func get_title_ids() -> Array: return get_ids("title")
# Collections and discoveries are single-file categories too -- no `_filename`.
func add_collection(id: String, data: Dictionary): collections[id] = data; mark_dirty("collection", id)
func get_collection_ids() -> Array: return get_ids("collection")
func add_discovery(id: String, data: Dictionary): discoveries[id] = data; mark_dirty("discovery", id)
func get_discovery_ids() -> Array: return get_ids("discovery")
func add_background(id: String, data: Dictionary): backgrounds[id] = data; mark_dirty("background", id)
func get_background_ids() -> Array: return get_ids("background")
func get_npc_ids() -> Array: return get_ids("npc")
func get_item_ids() -> Array: return get_ids("item")
func get_template_ids() -> Array: return get_ids("template")
