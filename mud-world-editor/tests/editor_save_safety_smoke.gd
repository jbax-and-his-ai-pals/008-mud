# tests/editor_save_safety_smoke.gd
#
# Batch A of docs/roadmap/world-editor-evaluation.md: the editor must not be able
# to lose an author's work silently. Run with:
#
#   godot --headless --path mud-world-editor --script tests/editor_save_safety_smoke.gd
#
# Every case here writes to a throwaway content set under `tmp/` and points
# `DataRoot` at it, so no shipped content file is touched. Each case is the
# behaviour a defect used to have:
#
#   * a failed write reported as a successful one (SaveIO)
#   * a failed read replacing the loaded region with a blank one
#   * a content file losing keys the editor does not model
#   * an item save truncating a file the engine reads as something else
#   * the last entry of a file being deleted but the file keeping it
#   * a cross-region rename never repairing the other regions
#   * `_proxy_positions` leaking into content
#   * undo history surviving a region change
#   * deleting a content-library entry with no way back

extends SceneTree

const SaveIO = preload("res://scripts/data/SaveIO.gd")

var failure_count := 0
var content_set_root: String = ""
var data_root: String = ""


func _init() -> void:
	content_set_root = ProjectSettings.globalize_path("res://").path_join("../tmp/editor_save_safety/content_set")
	data_root = content_set_root.path_join("data")
	_rebuild_fixture()
	# The editor resolves its content root once; point that resolution at the
	# scratch set before anything in here asks for it.
	DataRoot._resolved = content_set_root
	DataRoot._source = "test fixture"

	print("scratch content set: ", DataRoot.describe())

	_check_verified_write()
	_check_failed_read_keeps_the_region()
	_check_unmodelled_keys_survive()
	_check_read_only_item_files_are_untouched()
	_check_abilities_directory()
	_check_deleting_the_last_entry_sticks()
	_check_delete_and_restore()
	_check_cross_region_rename_repairs_other_files()
	_check_editor_keys_never_reach_content()
	_check_history_clears_on_load()

	if failure_count > 0:
		push_error("editor save safety failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- cases -------------------------------------------------------------------

func _check_verified_write() -> void:
	print("\n[verified write]")
	var manager := RegionManager.new()
	_assert(manager.load_region("good.json"), "the fixture region loads")
	manager.data.rooms["one"]["name"] = "Renamed One"
	manager.mark_room_dirty("one")

	var result := manager.save_region()
	_assert(result.get("ok", false), "a writable region saves: %s" % result.get("error", ""))
	_assert(not manager.load_error.is_empty() == false, "no load error after a good load")

	var text := FileAccess.get_file_as_string(data_root.path_join("regions/good.json"))
	_assert(text.contains("Renamed One"), "the edit reached the file")
	_assert(not text.contains("\t"), "content is written with spaces, not tabs")
	_assert(text.contains("\n    \""), "content is written 4-space indented")
	# `JSON.stringify` sorts keys unless told not to, which alphabetises every
	# object in the file. The fixture authors `region_id` first; sorted output
	# would put `name` first.
	_assert(text.begins_with("{\n    \"region_id\""), "key order is preserved, not alphabetised")

	# A write that cannot happen must say so. Point the manager at a path whose
	# parent is a file, which no platform lets us create.
	var blocked := RegionManager.new()
	blocked.current_filename = "blocked/good.json"
	blocked.loaded_ok = true
	blocked.data = {"region_id": "blocked", "rooms": {}}
	var blocked_result := blocked.save_region()
	_assert(not blocked_result.get("ok", true), "an unwritable path is reported as a failure")
	_assert(not str(blocked_result.get("error", "")).is_empty(), "the failure names a reason")

	var direct := SaveIO.write_json(ProjectSettings.globalize_path("res://").path_join("../tmp/editor_save_safety/nope/x.json"), {})
	_assert(not direct.get("ok", true), "SaveIO reports a bad path rather than assuming success")


func _check_failed_read_keeps_the_region() -> void:
	print("\n[failed read]")
	var manager := RegionManager.new()
	_assert(manager.load_region("good.json"), "the good region loads first")
	var rooms_before: int = manager.data.rooms.size()

	_assert(not manager.load_region("broken.json"), "a malformed region fails to load")
	_assert(not manager.load_error.is_empty(), "and says why: %s" % manager.load_error)
	_assert(manager.current_filename == "good.json",
		"the loaded region is still the good one (not the broken filename)")
	_assert(manager.data.rooms.size() == rooms_before,
		"the loaded data is untouched, so a later Save cannot write a blank region over a real one")
	_assert(manager.save_region().get("ok", false), "and that region can still be saved")

	var fresh := RegionManager.new()
	_assert(not fresh.load_region("broken.json"), "a first load of a malformed region fails")
	_assert(not fresh.can_save(), "and refuses to save, because nothing valid is loaded")
	var refused := fresh.save_region()
	_assert(not refused.get("ok", true), "the refusal is explicit: %s" % refused.get("error", ""))

	var missing := RegionManager.new()
	_assert(not missing.load_region("no_such_region.json"), "a missing region fails to load")
	_assert(missing.current_filename == "", "and leaves no filename to save over")


func _check_unmodelled_keys_survive() -> void:
	print("\n[unmodelled keys]")
	var database := DatabaseManager.new()
	database.load_all()
	_assert(database.items.has("item_probe"), "the fixture item loads")
	_assert(not database.items.has("prefixes"), "read-only files are not loaded as items")

	database.items["item_probe"]["value"] = 99
	database.mark_dirty("item", "item_probe")
	var saved := database.save_all()
	_assert(saved.get("ok", false), "the database saves: %s" % str(saved.get("errors", [])))

	var payload = JSON.parse_string(FileAccess.get_file_as_string(data_root.path_join("items/library.json")))
	_assert(typeof(payload) == TYPE_DICTIONARY, "the items file is still valid JSON")
	_assert(payload.get("_comment", "") == "kept", "a top-level comment the editor does not model survives")
	_assert(int(payload.get("item_probe", {}).get("value", 0)) == 99, "the editor's own edit landed")


func _check_read_only_item_files_are_untouched() -> void:
	print("\n[read-only item files]")
	var affixes_path := data_root.path_join("items/affixes.json")
	var before := FileAccess.get_file_as_string(affixes_path)

	var database := DatabaseManager.new()
	database.load_all()
	database.items["item_probe"]["value"] = 12
	database.mark_dirty("item", "item_probe")
	database.save_all()

	var after := FileAccess.get_file_as_string(affixes_path)
	_assert(before == after, "affixes.json is byte-identical after an item save")
	_assert(after.contains("generated_effect_name_pattern"),
		"its string-valued top-level keys are still there")


func _check_abilities_directory() -> void:
	print("\n[ability definitions]")
	# The engine prefers `abilities/` over `magic/`; the editor used to look only
	# at `magic/`, so a set whose abilities are not spells was invisible.
	_assert(DatabaseManager.abilities_dir() == data_root.path_join("abilities"),
		"a set with abilities/ is read from there: " + DatabaseManager.abilities_dir())

	var database := DatabaseManager.new()
	database.load_all()
	_assert(database.magic.has("overcharge"), "its ability definitions are loaded")
	database.magic["overcharge"]["cooldown"] = 9.0
	database.mark_dirty("magic", "overcharge")
	var saved := database.save_all()
	_assert(saved.get("ok", false), "and can be edited and saved: %s" % str(saved.get("errors", [])))
	var payload = JSON.parse_string(FileAccess.get_file_as_string(data_root.path_join("abilities/overcharge.json")))
	_assert(typeof(payload) == TYPE_DICTIONARY and payload.has("overcharge"), "the file still holds the ability")
	_assert(float(payload["overcharge"].get("cooldown", 0.0)) == 9.0, "with the edit")
	_assert(not DirAccess.dir_exists_absolute(data_root.path_join("magic")),
		"and no magic/ directory was invented beside it")

	# A set that names the directory `magic/` keeps working.
	var legacy_root := ProjectSettings.globalize_path("res://").path_join("../tmp/editor_save_safety/legacy_set")
	_remove_recursive(legacy_root)
	DirAccess.make_dir_recursive_absolute(legacy_root.path_join("data/magic"))
	_write(legacy_root.path_join("data/magic/spells.json"), {
		"magic_missile": {"name": "Magic Missile", "mana_cost": 5},
	})
	var previous := DataRoot._resolved
	DataRoot._resolved = legacy_root
	_assert(DatabaseManager.abilities_dir() == legacy_root.path_join("data/magic"),
		"a set with only magic/ falls back to it")
	var legacy := DatabaseManager.new()
	legacy.load_all()
	_assert(legacy.magic.has("magic_missile"), "and its definitions load")
	DataRoot._resolved = previous


func _check_deleting_the_last_entry_sticks() -> void:
	print("\n[deleting the last entry]")
	database_delete_probe()

	var reloaded := DatabaseManager.new()
	reloaded.load_all()
	_assert(not reloaded.npcs.has("lone_npc"),
		"an entry deleted from a single-entry file does not come back on reload")


func database_delete_probe() -> void:
	var database := DatabaseManager.new()
	database.load_all()
	_assert(database.npcs.has("lone_npc"), "the single-entry file loads")
	database.delete_entry("npc", "lone_npc")
	var saved := database.save_all()
	_assert(saved.get("ok", false), "the deletion saves: %s" % str(saved.get("errors", [])))


func _check_delete_and_restore() -> void:
	print("\n[delete and restore]")
	var database := DatabaseManager.new()
	database.load_all()
	var original := database.entry("item", "item_probe")
	_assert(not original.is_empty(), "the entry is readable before deletion")

	var removal := database.delete_entry("item", "item_probe")
	_assert(not removal.is_empty(), "deletion returns what it removed, so undo has something to restore")
	_assert(not database.has_entry("item", "item_probe"), "and the entry is gone")

	database.restore_entry("item", "item_probe", removal["removed"])
	_assert(database.has_entry("item", "item_probe"), "restore puts it back")
	_assert(int(database.entry("item", "item_probe").get("value", 0)) == int(original.get("value", 0)),
		"with its data intact")


func _check_cross_region_rename_repairs_other_files() -> void:
	print("\n[cross-region rename]")
	var manager := RegionManager.new()
	_assert(manager.load_region("region_a.json"), "region A loads")
	_assert(manager.patch_errors.is_empty(), "no repair errors before the rename")

	manager.rename_room("one", "one_renamed")
	_assert(manager.patch_errors.is_empty(), "the repair reported no errors: %s" % str(manager.patch_errors))

	var other := FileAccess.get_file_as_string(data_root.path_join("regions/region_b.json"))
	_assert(not other.contains("region_a:one\""), "region B no longer points at the old room id")
	_assert(other.contains("region_a:one_renamed"), "region B points at the new one")

	var payload = JSON.parse_string(other)
	var exit_target: String = str(payload.get("rooms", {}).get("hall", {}).get("exits", {}).get("west", ""))
	_assert(exit_target == "region_a:one_renamed", "and the exit is the repaired one (%s)" % exit_target)


func _check_editor_keys_never_reach_content() -> void:
	print("\n[editor keys]")
	var manager := RegionManager.new()
	manager.load_region("region_a.json")
	manager.data["_proxy_positions"] = {"region_b:hall": [10, 20]}
	manager.data.rooms["one"]["_editor_pos"] = [1, 2]
	manager.data.rooms["one"]["_editor_exit_layout"] = {"north": "straight"}
	manager.mark_room_dirty("one")
	_assert(manager.save_region().get("ok", false), "the region saves")

	var text := FileAccess.get_file_as_string(data_root.path_join("regions/region_a.json"))
	_assert(not text.contains("_editor_"), "no `_editor_*` key reaches content")
	_assert(not text.contains("_proxy_positions"),
		"and neither does `_proxy_positions`, which the prefix rule alone let through")


func _check_history_clears_on_load() -> void:
	print("\n[undo history]")
	var processor := CommandProcessor.new()
	var touched := {"count": 0}
	processor.commit(func(): touched["count"] += 1, func(): touched["count"] -= 1, "probe")
	_assert(processor.undo_stack.size() == 1, "the command is on the stack")
	processor.clear_history()
	_assert(processor.undo_stack.is_empty() and processor.redo_stack.is_empty(), "history clears")
	processor.undo()
	_assert(touched["count"] == 1, "and undo after a clear changes nothing")


# --- fixture -----------------------------------------------------------------

func _rebuild_fixture() -> void:
	var scratch := ProjectSettings.globalize_path("res://").path_join("../tmp/editor_save_safety")
	_remove_recursive(scratch)
	DirAccess.make_dir_recursive_absolute(data_root.path_join("regions"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("items"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("npcs"))

	_write(data_root.path_join("regions/good.json"), {
		"region_id": "good", "name": "Good Region",
		"rooms": {
			"one": {"name": "One", "exits": {"east": "two"}},
			"two": {"name": "Two", "exits": {"west": "one"}},
		},
	})
	# Cross-region exits, for the rename repair: region B points into region A.
	_write(data_root.path_join("regions/region_a.json"), {
		"region_id": "region_a", "name": "Region A",
		"rooms": {"one": {"name": "One", "exits": {}}},
	})
	_write(data_root.path_join("regions/region_b.json"), {
		"region_id": "region_b", "name": "Region B",
		"rooms": {"hall": {"name": "Hall", "exits": {"west": "region_a:one"}}},
	})
	FileAccess.open(data_root.path_join("regions/broken.json"), FileAccess.WRITE) \
		.store_string("{ this is not json")

	_write(data_root.path_join("items/library.json"), {
		"_comment": "kept",
		"item_probe": {"name": "probe", "type": "Item", "value": 10, "weight": 0.1},
	})
	# The shape the engine reads as affix data, not as items.
	_write(data_root.path_join("items/affixes.json"), {
		"generated_effect_name_pattern": "Enchantment of {item_name}",
		"generated_description_suffix": " It hums with magical energy.",
		"prefixes": {"Sharp": {"allowed_types": ["Weapon"], "level_min": 1}},
	})
	_write(data_root.path_join("npcs/one.json"), {
		"lone_npc": {"name": "Lone", "health": 10, "friendly": true},
	})
	# Ability definitions, in the directory the engine prefers.
	_write(data_root.path_join("abilities/overcharge.json"), {
		"overcharge": {"name": "Overcharge", "mana_cost": 6, "cooldown": 6.0, "target_type": "enemy"},
	})
	_write(content_set_root.path_join("rules/ruleset.json"), {"ruleset_id": "fixture", "world": {"regions": {}}})


func _write(path: String, payload: Dictionary) -> void:
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	SaveIO.write_json(path, payload)


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		var child := path.path_join(name)
		if dir.current_is_dir():
			_remove_recursive(child)
		else:
			DirAccess.remove_absolute(child)
		name = dir.get_next()
	dir.list_dir_end()
	DirAccess.remove_absolute(path)


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		push_error("FAIL: " + message)
