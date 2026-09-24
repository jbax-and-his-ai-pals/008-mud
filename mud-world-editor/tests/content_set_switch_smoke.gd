# tests/content_set_switch_smoke.gd
#
# Switching content set from inside the editor.
#
# Every manager reads its content at load time, so "switch worlds" is really
# "run the startup sequence again, minus the window" -- and the failure mode is
# subtle: whichever manager is not reloaded keeps serving the *previous* world's
# data while the title bar says otherwise. Run with:
#
#   godot --headless --path mud-world-editor --script tests/content_set_switch_smoke.gd
#
# It drives the real `Main.tscn` between two scratch content sets that differ in
# every way it can check: regions, item ids, families and ability directories.

extends SceneTree

const SaveIO = preload("res://scripts/data/SaveIO.gd")

var failure_count := 0
var repo_root: String = ""
var first_set: String = ""
var second_set: String = ""
var main: Node2D = null
var checks_run := false
# `user://editor_settings.json` is the real editor's settings file, not scratch
# state, so whatever was there before this test runs goes back afterwards.
var settings_path: String = ""
var previous_settings: String = ""
var previous_settings_existed := false


func _initialize() -> void:
	repo_root = ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	first_set = ProjectSettings.globalize_path("res://").path_join("../tmp/switch_smoke/alpha_frontier")
	second_set = ProjectSettings.globalize_path("res://").path_join("../tmp/switch_smoke/beta_frontier")
	_build_set(first_set, "alpha", "alpha_region", "item_alpha_part", "alpha_family", "alpha")
	_build_set(second_set, "beta", "beta_region", "item_beta_part", "beta_family", "beta")

	settings_path = ProjectSettings.globalize_path("user://editor_settings.json")
	previous_settings_existed = FileAccess.file_exists(settings_path)
	if previous_settings_existed:
		previous_settings = FileAccess.get_file_as_string(settings_path)

	DataRoot._resolved = first_set
	DataRoot._source = "test fixture"
	main = load("res://scenes/Main.tscn").instantiate()
	root.add_child(main)


func _process(_delta: float) -> bool:
	if checks_run:
		return true
	checks_run = true

	_check_the_first_world_is_loaded()
	_check_switching_reloads_everything()
	_check_engine_rejection_restores_library_data()
	_check_save_and_switch_writes_both_kinds_of_work()
	_check_per_set_state_does_not_travel()
	_check_the_choice_is_remembered()
	_check_an_unknown_path_is_refused()
	_check_the_catalog_follows()
	_restore_settings()

	if failure_count > 0:
		push_error("content set switch smoke failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)
	return true


# --- the two paths that used to drop work ------------------------------------

# "Save and switch" is one button with two promises: save the region, and save the
# content library. It used to keep only the first. With a clean region it returned
# before `save_all()` ever ran, and in the world view it saved the layout and
# stopped -- so a library edit (an NPC's stats, an item's value) was reported as
# saved and then dropped by the next set's `load_all()`, which clears the dirty
# flags that were the only evidence it existed.

func _check_engine_rejection_restores_library_data() -> void:
	print("\n[engine refusal restores data]")
	main._switch_content_set(first_set)
	var original: Dictionary = main.database_mgr.entry("item", "item_alpha_part").duplicate(true)
	main.database_mgr.items["item_alpha_part"]["item_family"] = "family_that_does_not_exist"
	main.database_mgr.mark_dirty("item", "item_alpha_part")
	_assert(not main._save_everything(), "the engine rejects an invalid library edit")
	var on_disk = JSON.parse_string(FileAccess.get_file_as_string(first_set.path_join("data/items/library.json")))
	_assert(str(on_disk.get("item_alpha_part", {}).get("item_family", "")) == "alpha_family",
		"the checkpoint restored the previous library file")
	_assert(main.database_mgr.has_unsaved_changes(),
		"the visible invalid draft remains dirty for correction")
	_assert(main.ui_mgr.error_modal.visible, "the rejection is shown to the author")
	main.ui_mgr.error_modal.hide()

	# Repair the in-memory draft and prove the same path saves after validation.
	main.database_mgr.items["item_alpha_part"] = original
	main.database_mgr.mark_dirty("item", "item_alpha_part")
	_assert(main._save_everything(), "the corrected library edit saves")


func _check_save_and_switch_writes_both_kinds_of_work() -> void:
	print("\n[save and switch]")
	main._switch_content_set(first_set)
	_assert(DataRoot.root().get_file() == "alpha_frontier", "back on the first set")

	# 1. Library work only: the region is clean, which is the early-return case.
	main.database_mgr.items["item_alpha_part"]["value"] = 99
	main.database_mgr.mark_dirty("item", "item_alpha_part")
	_assert(not main.region_mgr.is_region_dirty, "the region itself is untouched")
	_assert(main._has_unsaved_work(), "but there is unsaved library work")

	main._request_switch_content_set(second_set)
	_assert(main.ui_mgr.confirm_modal.visible, "the author is asked")
	main.ui_mgr.confirm_modal.confirmed.emit()
	_assert(DataRoot.root().get_file() == "beta_frontier", "and the switch happened")

	var items_path := first_set.path_join("data/items/library.json")
	var written = JSON.parse_string(FileAccess.get_file_as_string(items_path))
	_assert(typeof(written) == TYPE_DICTIONARY and int(written.get("item_alpha_part", {}).get("value", 0)) == 99,
		"the library edit reached the file: value=%s" % str(written.get("item_alpha_part", {}).get("value")))

	# 2. Both kinds at once, so neither can be saved at the other's expense.
	main._switch_content_set(first_set)
	main.region_mgr.data.rooms["start"]["name"] = "Saved Alpha"
	main.region_mgr.mark_room_dirty("start")
	main.database_mgr.items["item_alpha_part"]["value"] = 123
	main.database_mgr.mark_dirty("item", "item_alpha_part")

	main._request_switch_content_set(second_set)
	main.ui_mgr.confirm_modal.confirmed.emit()

	var region_written = JSON.parse_string(FileAccess.get_file_as_string(
		first_set.path_join("data/regions/alpha_region.json")))
	written = JSON.parse_string(FileAccess.get_file_as_string(items_path))
	_assert(str(region_written.get("rooms", {}).get("start", {}).get("name", "")) == "Saved Alpha",
		"the region edit reached its file: %s" % str(region_written.get("rooms", {}).get("start", {}).get("name")))
	_assert(int(written.get("item_alpha_part", {}).get("value", 0)) == 123,
		"and so did the library edit, in the same press")


# State that is keyed by one world's ids must not survive into another: a tool
# armed with a stamp id draws it into the new set's rooms, a clipboard pastes an
# item that does not exist here, a search index answers with entries that are
# gone, and a library selection keeps an inspector writing into an orphaned
# dictionary.

func _check_per_set_state_does_not_travel() -> void:
	print("\n[state that belongs to one world]")
	main.ui_mgr.content_library.show_entry("item", "item_alpha_part")
	main.state.cur_tool_mode = EditorUIManager.ToolMode.STAMP
	main.state.cur_tool_data = {"stamp": "item_alpha_part"}
	main.editor_clipboard = ["item_alpha_part"]
	main.ui_mgr.search_data_cache["items"] = {"item_alpha_part": {}}
	main.world_mgr.ignored_validation_warnings["some alpha warning"] = true

	main._switch_content_set(second_set)

	_assert(main.state.cur_tool_mode == EditorUIManager.ToolMode.SELECT, "the tool is disarmed")
	_assert(main.state.cur_tool_data.is_empty(), "and holds none of the previous world's ids")
	_assert(main.editor_clipboard.is_empty(), "the clipboard is empty")
	_assert(main.ui_mgr.search_data_cache.is_empty(), "the search index is rebuilt, not carried")
	_assert(main.ui_mgr.content_library.selected_id == "", "no library entry stays selected")
	_assert(main.ui_mgr.content_library.current_editor == null, "and no inspector is bound to the old entry")
	_assert(main.world_mgr.ignored_validation_warnings.is_empty(),
		"an ignored warning from one world says nothing about another")


func _restore_settings() -> void:
	# Leave the machine as it was found: a test that changes which world the
	# editor opens next launch is a test that breaks the next launch. A previous
	# value pointing at scratch state (a `tmp/` path that this or an earlier run
	# wrote) is not something to restore -- it is the pollution itself.
	var restore := previous_settings_existed and not previous_settings.contains("tmp/")
	if restore:
		var file := FileAccess.open(settings_path, FileAccess.WRITE)
		if file:
			file.store_string(previous_settings)
			file.close()
		return
	if previous_settings_existed and not restore:
		print("  note: discarding a settings file that pointed at scratch state")
	DirAccess.remove_absolute(settings_path)


# --- cases -------------------------------------------------------------------

func _check_the_first_world_is_loaded() -> void:
	print("\n[the first world]")
	_assert(main.region_mgr.current_filename == "alpha_region.json",
		"the editor opened the first set's start region (%s)" % main.region_mgr.current_filename)
	_assert(main.database_mgr.items.has("item_alpha_part"), "and its items are loaded")
	_assert(main.database_mgr.catalog.family_ids() == ["alpha_family"],
		"and its families: %s" % str(main.database_mgr.catalog.family_ids()))


func _check_switching_reloads_everything() -> void:
	print("\n[switching]")
	# An unsaved edit, so the discard path is the one being exercised.
	main.region_mgr.data.rooms["start"]["name"] = "Edited Alpha"
	main.region_mgr.mark_room_dirty("start")
	_assert(main._has_unsaved_work(), "there is unsaved work before the switch")

	main._request_switch_content_set(second_set)
	_assert(DataRoot.root() == first_set, "switching does not happen without an answer")
	_assert(main.ui_mgr.confirm_modal.visible, "the author is asked first")

	# Take the "without saving" branch, which the prompt offers as a third button.
	main.ui_mgr.confirm_modal.custom_action.emit("extra")
	_assert(DataRoot.root().get_file() == "beta_frontier",
		"answering reloads the world (%s)" % DataRoot.root())

	_assert(main.region_mgr.current_filename == "beta_region.json",
		"onto the new set's start region (%s)" % main.region_mgr.current_filename)
	_assert(not main.region_mgr.is_region_dirty, "with no stale dirtiness carried over")
	_assert(main.region_mgr.data.rooms.has("start"), "and real rooms loaded")
	_assert(not main.region_mgr.data.rooms["start"].has("name") or main.region_mgr.data.rooms["start"]["name"] != "Edited Alpha",
		"not the previous world's edits")

	_assert(main.database_mgr.items.has("item_beta_part"), "the content library reloaded")
	_assert(not main.database_mgr.items.has("item_alpha_part"),
		"and no longer holds the previous world's items")
	_assert(main.database_mgr.recipes.has("beta_recipe"), "recipes reloaded too")
	_assert(not main.database_mgr.recipes.has("alpha_recipe"), "without leftovers")


func _check_the_choice_is_remembered() -> void:
	print("\n[remembering the choice]")
	var settings_path := "user://editor_settings.json"
	_assert(FileAccess.file_exists(settings_path), "the settings file was written")
	if not FileAccess.file_exists(settings_path):
		return
	var payload = JSON.parse_string(FileAccess.get_file_as_string(settings_path))
	_assert(typeof(payload) == TYPE_DICTIONARY, "and holds an object")
	_assert(str(payload.get("content_set_root", "")).get_file() == "beta_frontier",
		"naming the set that is now open: %s" % str(payload.get("content_set_root", "")))


func _check_an_unknown_path_is_refused() -> void:
	print("\n[a path that is not a content set]")
	var before := DataRoot.root()
	main._switch_content_set(first_set.path_join("no_such_set"))
	_assert(DataRoot.root() == before, "a missing directory leaves the open world alone")
	_assert(main.ui_mgr.error_modal.visible, "and says so")
	main.ui_mgr.error_modal.hide()

	# A directory that exists but is not a content set: no manifest. Accepting it
	# reloaded the editor into a world with no regions and no items, and nothing
	# in the window said the path had been wrong.
	var not_a_set := first_set.get_base_dir()
	_assert(DirAccess.dir_exists_absolute(not_a_set), "the fixture's parent directory exists")
	_assert(not FileAccess.file_exists(not_a_set.path_join("content_set.manifest.json")),
		"and is not itself a content set")
	main._switch_content_set(not_a_set)
	_assert(DataRoot.root() == before, "so it is refused too (%s)" % DataRoot.root().get_file())
	_assert(main.ui_mgr.error_modal.visible, "with the same message")
	main.ui_mgr.error_modal.hide()


func _check_the_catalog_follows() -> void:
	print("\n[the contract browser]")
	# The browser is built once with a catalog; a switch builds a new one, so the
	# editor has to re-point it or it would keep showing the previous world.
	_assert(main.database_mgr.catalog.family_ids() == ["beta_family"],
		"the manager holds the new world's contracts")
	main.ui_mgr.show_contracts()
	# The browser builds its list from the catalog it holds, so reading *its*
	# state is what proves it was re-pointed at the new world's contracts.
	var shown: Array = main.ui_mgr.contract_browser.sections
	var text := ""
	for section in shown:
		for entry in section["entries"]:
			text += str(entry["id"]) + " "
	_assert(text.contains("beta_family"), "and the browser shows them: %s" % text)
	_assert(not text.contains("alpha_family"), "not the previous world's")
	main.ui_mgr.contract_browser.hide()


# --- fixture -----------------------------------------------------------------

func _build_set(root_path: String, id: String, region: String, item_id: String,
		family_id: String, ability_id: String) -> void:
	_remove_recursive(root_path)
	var data_root := root_path.path_join("data")
	for directory in ["items", "npcs", "regions", "crafting", "contracts", "abilities"]:
		DirAccess.make_dir_recursive_absolute(data_root.path_join(directory))
	DirAccess.make_dir_recursive_absolute(root_path.path_join("rules"))
	DirAccess.make_dir_recursive_absolute(root_path.path_join("presentation"))

	SaveIO.write_json(root_path.path_join("content_set.manifest.json"), {
		"id": id, "title": id.capitalize(), "version": "0.1.0",
		"manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
		"paths": {
			"content_root": "data",
			"ruleset": "rules/ruleset.json",
			"presentation": "presentation/default.json",
		},
		"start": {"scenario_id": id, "region_id": region, "room_id": "start"},
		"capabilities": ["inventory", "crafting"],
	})
	SaveIO.write_json(root_path.path_join("presentation/default.json"), {
		"presentation_id": id, "display_name": id.capitalize(),
	})
	SaveIO.write_json(root_path.path_join("rules/ruleset.json"), {})
	SaveIO.write_json(data_root.path_join("regions/%s.json" % region), {
		"region_id": region, "name": id.capitalize(),
		"rooms": {"start": {"name": "%s start" % id.capitalize(), "exits": {}}},
	})
	SaveIO.write_json(data_root.path_join("items/library.json"), {
		item_id: {"name": "%s part" % id, "type": "Junk", "value": 5, "weight": 0.1,
			"item_family": family_id},
	})
	SaveIO.write_json(data_root.path_join("crafting/recipes.json"), {
		"%s_recipe" % id: {
			"name": "%s recipe" % id.capitalize(), "aliases": [], "description": "Makes a part.",
			"result_item_id": item_id, "result_quantity": 1, "station_required": null,
			"ingredients": [{"item_id": item_id, "quantity": 1}],
		},
	})
	SaveIO.write_json(data_root.path_join("contracts/world_contracts.json"), {
		"schema_version": 1, "label": "%s contracts" % id,
		"resources": [{"id": "health", "label": "Health", "kind": "vital"}],
		"item_families": [{
			"id": family_id, "label": family_id, "item_class": "Junk",
			"capabilities": ["vendor_trash"],
		}],
		"generation_profiles": [],
		"attack_profiles": [],
		"defense_profiles": [],
		"abilities": [],
		"effect_packets": [],
	})
	SaveIO.write_json(data_root.path_join("abilities/%s.json" % ability_id), {
		ability_id: {
			"name": ability_id.capitalize(), "description": "A test ability.",
			"mana_cost": 1, "target_type": "enemy",
			"effects": [{"type": "damage", "value": 1}],
		},
	})


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
