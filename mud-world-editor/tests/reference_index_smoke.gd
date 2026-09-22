# tests/reference_index_smoke.gd
#
# The editor's "what names this id?" answer, checked against real content.
#
# `Main._confirm_delete_db_entry` shows this text before an entry is deleted, and
# the point of it is that the author cannot see the referrers any other way: the
# library lists entries, not the files that name them. Two failure modes matter
# more than the feature working:
#
#   * the index disagrees with the gate about what a reference is, and the editor
#     says "nothing names this" for something a recipe depends on -- so this test
#     asserts a reference that is really in the content, in two different files;
#   * an empty answer reads as permission -- so this test asserts the sentence
#     always states its scope, and never claims an id is unused.
#
# Run with:
#
#   godot --headless --path mud-world-editor --script tests/reference_index_smoke.gd -- --python <interp>

extends SceneTree

const ReferenceIndexScript = preload("res://scripts/data/ReferenceIndex.gd")
const DatabaseManagerScript = preload("res://scripts/data/DatabaseManager.gd")
const RegionManagerScript = preload("res://scripts/data/RegionManager.gd")
const PatchScript = preload("res://scripts/data/ReferencePatch.gd")

var failures := 0
var fixture := ""


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/reference-index-%s" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/orbital_salvage"), fixture)
	var data_root := fixture.path_join("data")

	_check_the_index_runs(data_root)
	_check_a_real_reference_is_found(data_root)
	_check_the_confirmation_text_names_where(data_root)
	_check_an_empty_answer_states_its_scope(data_root)
	_check_types_the_index_does_not_read(data_root)
	_check_a_missing_root_fails_loudly()
	_check_clear_forgets_the_set(data_root)
	_check_a_path_is_walked_the_way_the_index_spells_it()
	_check_preflight_never_mutates_a_reference()
	_check_a_rename_repairs_the_entries_that_name_it(data_root)
	_check_a_region_reference_is_repaired_too()

	_remove_recursive(fixture)
	if failures > 0:
		push_error("reference index smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


# --- the checks ---------------------------------------------------------------

func _check_the_index_runs(data_root: String) -> void:
	print("\n[index runs]")
	var index = ReferenceIndexScript.new()
	var result: Dictionary = index.load_for(data_root)
	_assert(result.get("ok", false), "the index ran: %s" % result.get("error", ""))
	_assert(index.loaded(), "the index reports itself loaded")
	_assert(index.error() == "", "no error is reported")
	var payload: Dictionary = index.payload()
	_assert(payload.get("families") is Dictionary, "the payload carries families")
	_assert(payload.get("coverage") is Dictionary, "the payload carries its coverage")
	var indexed: Array = payload.get("coverage", {}).get("indexed", [])
	_assert(indexed.has("items") and indexed.has("npcs"), "items and npcs are indexed: %s" % str(indexed))
	_assert(not Array(payload.get("coverage", {}).get("not_indexed", [])).is_empty(),
		"the payload says what it does not index")


func _check_a_real_reference_is_found(data_root: String) -> void:
	# Grounded in the content rather than in the index: read the recipe, take the
	# item it produces, then ask the index who names it.
	print("\n[a real reference is found]")
	var fabrication := _read_json(fixture.path_join("data/crafting/fabrication.json"))
	var produced := ""
	for recipe_id in fabrication:
		if recipe_id.begins_with("_"): continue
		produced = str(fabrication[recipe_id].get("result_item_id", ""))
	_assert(produced != "", "the fixture recipe produces an item")

	var index = ReferenceIndexScript.new()
	index.load_for(data_root)
	var hits: Array = index.referrers_of(produced, "items")
	var files: Array = []
	for hit in hits: files.append(hit["file"])
	_assert(files.has("crafting/fabrication.json"),
		"the recipe that produces %s is listed as naming it: %s" % [produced, str(files)])
	_assert(files.has("npcs/crew.json"),
		"the crew member who carries %s is listed too: %s" % [produced, str(files)])
	_assert(hits.size() >= 2, "both referrers are returned, not just the first")


func _check_the_confirmation_text_names_where(data_root: String) -> void:
	print("\n[the text names where]")
	var index = ReferenceIndexScript.new()
	index.load_for(data_root)
	var text: String = index.describe("item_patch_kit", "item")
	_assert(text.contains("crafting/fabrication.json"), "the dialog names the file: %s" % text)
	_assert(text.contains("result_item_id"), "and the path inside it: %s" % text)
	_assert(text.contains("Indexed:"), "and what the index covers: %s" % text)


func _check_an_empty_answer_states_its_scope(data_root: String) -> void:
	# The failure this prevents: an author deletes something, reads "nothing names
	# this", and believes it. The index covers six families out of many bindings.
	print("\n[an empty answer states its scope]")
	var index = ReferenceIndexScript.new()
	index.load_for(data_root)
	var text: String = index.describe("an_id_nothing_names_at_all", "item")
	_assert(text.contains("Nothing in the indexed families names this"),
		"an empty answer says which families were searched: %s" % text)
	_assert(text.contains("Not indexed"), "and lists what was not searched: %s" % text)
	for forbidden in ["unused", "safe to delete", "no references"]:
		_assert(not text.to_lower().contains(forbidden),
			"the text never claims '%s': %s" % [forbidden, text])


func _check_types_the_index_does_not_read(data_root: String) -> void:
	print("\n[types the index does not read]")
	var index = ReferenceIndexScript.new()
	index.load_for(data_root)
	_assert(index.family_for_type("item") == "items", "an item maps to the items family")
	_assert(index.family_for_type("npc") == "npcs", "an NPC maps to the npcs family")
	_assert(index.family_for_type("quest") == "", "a quest has no indexed family yet")
	var text: String = index.describe("quest_anything", "quest")
	_assert(text.contains("does not read quest entries yet"),
		"an unindexed type says so rather than answering: %s" % text)


func _check_a_missing_root_fails_loudly() -> void:
	print("\n[a missing root fails loudly]")
	var index = ReferenceIndexScript.new()
	var result: Dictionary = index.load_for(fixture.path_join("data/does-not-exist"))
	_assert(not result.get("ok", true), "a root that is not there does not report success")
	_assert(not index.loaded(), "and does not leave the index looking loaded")
	var text: String = index.describe("item_patch_kit", "item")
	_assert(text.contains("unavailable"), "and the dialog says the check did not run: %s" % text)


func _check_clear_forgets_the_set(data_root: String) -> void:
	print("\n[clear forgets the set]")
	var index = ReferenceIndexScript.new()
	index.load_for(data_root)
	_assert(index.loaded(), "loaded before clearing")
	index.clear()
	_assert(not index.loaded(), "not loaded after clearing")
	_assert(index.referrers_of("item_patch_kit", "items").is_empty(), "and remembers nothing")


# --- applying a rename --------------------------------------------------------

func _check_a_path_is_walked_the_way_the_index_spells_it() -> void:
	# The pure half: what a reference path means and what it edits. Two shapes
	# occur, and getting the wrong one would silently rewrite the wrong thing.
	print("\n[a path is walked the way the index spells it]")
	var entry := {
		"properties": {"work_location": "town:forge"},
		"loot_table": {"item_sword": {"chance": 1.0}, "item_key": {"chance": 0.5}},
		"stages": [{"objective": {"recipient_template_id": "blacksmith"}}],
	}
	var value_mode: Dictionary = PatchScript.rename(entry, "properties.work_location", "town:forge", "town:smithy")
	_assert(value_mode.get("ok", false), "a value reference is replaced: %s" % value_mode.get("error", ""))
	_assert(entry["properties"]["work_location"] == "town:smithy", "and the value really changed")

	var key_mode: Dictionary = PatchScript.rename(entry, "loot_table.item_sword", "item_sword", "item_blade")
	_assert(key_mode.get("ok", false), "a keyed reference is renamed: %s" % key_mode.get("error", ""))
	_assert(entry["loot_table"].has("item_blade"), "the new key exists")
	_assert(not entry["loot_table"].has("item_sword"), "the old key is gone")
	_assert(key_mode.get("path_after", "") == "loot_table.item_blade",
		"the path after a key rename names the new id (undo needs it): %s" % key_mode.get("path_after", ""))
	_assert(entry["loot_table"].keys()[0] == "item_blade",
		"the renamed key keeps its position, so a save does not reorder the file")

	var nested: Dictionary = PatchScript.rename(entry, "stages.0.objective.recipient_template_id", "blacksmith", "smith")
	_assert(nested.get("ok", false), "an array index in a path resolves: %s" % nested.get("error", ""))
	_assert(entry["stages"][0]["objective"]["recipient_template_id"] == "smith", "and edits the value there")

	var wrong: Dictionary = PatchScript.rename(entry, "properties.work_location", "town:forge", "town:elsewhere")
	_assert(not wrong.get("ok", true), "an id the path does not hold is refused")
	_assert(str(wrong.get("error", "")).contains("town:smithy"),
		"and the refusal says what is really there: %s" % wrong.get("error", ""))

	var missing: Dictionary = PatchScript.rename(entry, "properties.nothing_here", "a", "b")
	_assert(not missing.get("ok", true), "a path that does not exist is refused, not created")

	var collision: Dictionary = PatchScript.rename(entry, "loot_table.item_blade", "item_blade", "item_key")
	_assert(not collision.get("ok", true), "renaming onto an existing key is refused rather than overwriting")


func _check_preflight_never_mutates_a_reference() -> void:
	# The rename dialog must know every path can be repaired before it alters the
	# first one.  These probes run the same walkers on copies and prove neither
	# cache nor file changes merely because an author opened the review.
	print("\n[reference preflight is non-mutating]")
	DataRoot._resolved = fixture
	DataRoot._source = "reference preflight smoke"
	var db = DatabaseManagerScript.new()
	db.load_all()
	var recipe_before: Dictionary = db.entry("recipe", "fabricate_patch_kit").duplicate(true)
	var check: Dictionary = db.can_patch_reference(
		"crafting/fabrication.json", "fabricate_patch_kit.result_item_id", "item_patch_kit", "item_patch_kit_preview")
	_assert(check.get("ok", false), "a valid library reference preflights: %s" % check.get("error", ""))
	_assert(db.entry("recipe", "fabricate_patch_kit") == recipe_before,
		"library preflight leaves the loaded entry byte-for-byte equivalent")
	_assert(not db.has_unsaved_changes(), "library preflight does not mark anything dirty")

	var region_path := fixture.path_join("data/regions/station.json")
	var region_before := FileAccess.get_file_as_string(region_path)
	var regions = RegionManagerScript.new()
	var missing: Dictionary = regions.can_patch_reference(
		"regions/station.json", "spawner.npc_types.no_such_npc", "no_such_npc", "replacement")
	_assert(not missing.get("ok", true), "a path that is not present is refused during preflight")
	_assert(FileAccess.get_file_as_string(region_path) == region_before,
		"failed region preflight leaves the file untouched")
	_assert(not regions.is_region_dirty, "and does not mark a region dirty")

	db.mark_all_dirty()
	_assert(db.has_unsaved_changes(), "a restored checkpoint can make all loaded library entries dirty again")


func _check_a_rename_repairs_the_entries_that_name_it(data_root: String) -> void:
	# The integration half: the paths the index reports, applied to the caches the
	# editor holds. Grounded in the fixture's own content, like the lookup above.
	print("\n[a rename repairs the entries that name it]")
	DataRoot._resolved = fixture
	DataRoot._source = "reference index smoke"
	var db = DatabaseManagerScript.new()
	db.load_all()

	var produced := ""
	var fabrication := _read_json(fixture.path_join("data/crafting/fabrication.json"))
	for recipe_id in fabrication:
		if recipe_id.begins_with("_"): continue
		produced = str(fabrication[recipe_id].get("result_item_id", ""))
	_assert(produced != "" and not db.entry("recipe", "fabricate_patch_kit").is_empty(),
		"the recipe is loaded from the fixture")

	var recipe_patch: Dictionary = db.patch_reference(
		"crafting/fabrication.json", "fabricate_patch_kit.result_item_id", produced, produced + "_v2")
	_assert(recipe_patch.get("ok", false), "the recipe's result is repointed: %s" % recipe_patch.get("error", ""))
	_assert(db.entry("recipe", "fabricate_patch_kit")["result_item_id"] == produced + "_v2",
		"and the loaded recipe now names the new id")

	var npc := {}
	for npc_id in db.get_npc_ids():
		var candidate: Dictionary = db.entry("npc", npc_id)
		var properties = candidate.get("properties")
		var wares: Array = properties.get("sells_items", []) if properties is Dictionary else []
		if not wares.is_empty() and str(wares[0].get("item_id", "")) == produced:
			npc = {"id": npc_id, "file": str(candidate.get("_filename", ""))}
			break
	_assert(not npc.is_empty(), "the fixture has an NPC selling the produced item")
	if not npc.is_empty():
		var npc_patch: Dictionary = db.patch_reference(
			"npcs/%s" % npc["file"], "%s.properties.sells_items[0].item_id" % npc["id"], produced, produced + "_v2")
		_assert(npc_patch.get("ok", false), "the vendor line is repointed: %s" % npc_patch.get("error", ""))
		var wares = db.entry("npc", npc["id"])["properties"]["sells_items"]
		_assert(str(wares[0]["item_id"]) == produced + "_v2", "and the loaded vendor line agrees")

	var unknown: Dictionary = db.patch_reference("npcs/crew.json", "nobody.properties.sells_items[0].item_id", produced, "x")
	_assert(not unknown.get("ok", true), "a path naming an entry that is not loaded is refused")
	_assert(str(unknown.get("error", "")).contains("nobody"), "and the refusal names it: %s" % unknown.get("error", ""))


func _check_a_region_reference_is_repaired_too() -> void:
	# A region names NPCs through its spawner table, and that is a reference a
	# rename has to reach: a spawner whose weights name a template that no longer
	# exists spawns nothing, quietly. The fixture has no spawner, so one is planted.
	print("\n[a region reference is repaired too]")
	var region_file := "station.json"
	var region_path := fixture.path_join("data/regions").path_join(region_file)
	var payload := _read_json(region_path)
	_assert(not payload.is_empty(), "the fixture has a region file to plant a spawner in")
	var npc_id := ""
	var crew := _read_json(fixture.path_join("data/npcs/crew.json"))
	for candidate in crew:
		if not str(candidate).begins_with("_"):
			npc_id = str(candidate)
			break
	_assert(npc_id != "", "the fixture declares an NPC to name")
	payload["spawner"] = {"level_range": [1, 2], "npc_types": {npc_id: 1}}
	_write_json(region_path, payload)

	var index = ReferenceIndexScript.new()
	index.load_for(fixture.path_join("data"))
	var hits: Array = index.referrers_of(npc_id, "npcs")
	var planted := {}
	for hit in hits:
		if str(hit["file"]) == "regions/" + region_file:
			planted = hit
	_assert(not planted.is_empty(), "the index reports the spawner weight as naming the NPC")
	_assert(str(planted.get("path", "")) == "spawner.npc_types.%s" % npc_id,
		"and its path is where the file really keeps it: %s" % planted.get("path", ""))

	# The file branch: no region is open in this manager, so this goes to disk.
	var regions = RegionManagerScript.new()
	var on_disk: Dictionary = regions.patch_reference(
		"regions/" + region_file, str(planted["path"]), npc_id, npc_id + "_v2")
	_assert(on_disk.get("ok", false), "the spawner weight is renamed on disk: %s" % on_disk.get("error", ""))
	var reread := _read_json(region_path)
	var spawner = reread.get("spawner")
	var weights: Dictionary = spawner.get("npc_types", {}) if spawner is Dictionary else {}
	_assert(weights.has(npc_id + "_v2"), "the file now carries the new key")
	_assert(not weights.has(npc_id), "and not the old one")
	_assert(weights.keys()[0] == npc_id + "_v2", "in the position the old key held")

	# The in-memory branch: a region the editor has open is edited, not re-read,
	# so unsaved work in it survives and the normal save path writes it.
	var open_regions = RegionManagerScript.new()
	_assert(open_regions.load_region(region_file), "the region loads for editing")
	var before_open: Dictionary = open_regions.data["spawner"]["npc_types"].duplicate()
	var in_memory: Dictionary = open_regions.patch_reference(
		"regions/" + region_file, "spawner.npc_types.%s_v2" % npc_id, npc_id + "_v2", npc_id + "_v3")
	_assert(in_memory.get("ok", false), "an open region is patched in memory: %s" % in_memory.get("error", ""))
	_assert(open_regions.is_region_dirty, "and is marked dirty so a save writes it")
	_assert(open_regions.data["spawner"]["npc_types"].has(npc_id + "_v3"),
		"the loaded region carries the new key")
	_assert(before_open.has(npc_id + "_v2"), "and held the previous one before the patch")

	# A file that cannot be parsed is left alone: a repair that truncates a file is
	# worse than a reference that still needs a hand.
	var broken := fixture.path_join("data/regions").path_join("broken.json")
	var handle := FileAccess.open(broken, FileAccess.WRITE)
	handle.store_string("{ this is not json")
	handle = null
	var refused: Dictionary = regions.patch_reference("regions/broken.json", "spawner.npc_types.x", "x", "y")
	_assert(not refused.get("ok", true), "an unparseable region file is refused")
	_assert(str(refused.get("error", "")).contains("could not be parsed"),
		"and says why: %s" % refused.get("error", ""))
	_assert(FileAccess.get_file_as_string(broken).contains("this is not json"),
		"the file is left exactly as it was")

	var missing: Dictionary = regions.patch_reference("regions/nope.json", "a.b", "a", "b")
	_assert(not missing.get("ok", true), "a region file that is not in the set is refused")


# --- helpers ------------------------------------------------------------------

func _read_json(path: String) -> Dictionary:
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Dictionary else {}


func _write_json(path: String, payload: Dictionary) -> void:
	var handle := FileAccess.open(path, FileAccess.WRITE)
	if handle == null:
		push_error("could not write %s" % path)
		return
	handle.store_string(JSON.stringify(payload, "  "))


func _assert(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("  ok: " + message)


func _copy(from: String, to: String) -> void:
	DirAccess.make_dir_recursive_absolute(to)
	var dir := DirAccess.open(from)
	if dir == null:
		push_error("could not open %s" % from)
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			var source := from.path_join(name)
			var target := to.path_join(name)
			if dir.current_is_dir():
				_copy(source, target)
			else:
				DirAccess.copy_absolute(source, target)
		name = dir.get_next()
	dir.list_dir_end()


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null: return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			var child := path.path_join(name)
			if dir.current_is_dir():
				_remove_recursive(child)
			else:
				DirAccess.remove_absolute(child)
		name = dir.get_next()
	dir.list_dir_end()
	DirAccess.remove_absolute(path)
