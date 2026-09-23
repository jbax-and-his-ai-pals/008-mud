# tests/region_and_district_delete_smoke.gd
#
# Regions and districts had no delete control. A district delete is an
# undoable edit that keeps the rooms; a region delete removes a file, so it is
# refused where the answer is cheap (the start region, links from other
# regions, unsaved work) and otherwise runs under a checkpoint and the engine's
# verdict. Driven through the real editor scene on a copy of fantasy_frontier.
#
#   godot --headless --path mud-world-editor --script tests/region_and_district_delete_smoke.gd

extends SceneTree

var failures := 0
var fixture := ""
var main: Node2D = null
var checks_run := false


func _initialize() -> void:
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/region-delete-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	var regions := fixture.path_join("data/regions")
	# Two islands nothing links to by exit: one a quest board names, one nothing names.
	# Valid under fantasy_frontier's own region policy, and reachable without a
	# link from another region (which would make the delete refuse up front).
	SaveIO.write_json(regions.path_join("probe_board_isle.json"), _island("probe_board_isle", "dock"))
	SaveIO.write_json(regions.path_join("probe_empty_isle.json"), _island("probe_empty_isle", "shore"))
	var ruleset_path := fixture.path_join("rules/ruleset.json")
	var ruleset: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(ruleset_path))
	ruleset["quest_generation"]["quest_board_locations"].append("probe_board_isle:dock")
	SaveIO.write_json(ruleset_path, ruleset)
	DataRoot._resolved = fixture
	DataRoot._source = "test fixture"
	main = load("res://scenes/Main.tscn").instantiate()
	root.add_child(main)


func _process(_delta: float) -> bool:
	if checks_run: return true
	checks_run = true
	_check_district_delete()
	_check_region_delete_refusals()
	_check_engine_refusal_puts_the_file_back()
	_check_an_unreferenced_region_is_deleted()
	if failures > 0: push_error("region and district delete failed (%d)" % failures)
	quit(1 if failures > 0 else 0)
	return true


func _check_district_delete() -> void:
	print("\n[deleting a district]")
	_assert(main.region_mgr.current_filename == "town.json", "the editor opened the start region")
	var before := JSON.stringify(main.region_mgr.data)
	var members: Array = main.region_mgr.get_districts()["tavern_quarter"]["members"].duplicate()
	main.action_handler.delete_district("tavern_quarter")
	_assert(not main.region_mgr.get_districts().has("tavern_quarter"), "the district is gone")
	_assert(main.region_mgr.data.rooms.has(members[0]), "its rooms stay")
	var still_marked := members.filter(func(room_id): return str(main.region_mgr.data.rooms[room_id].get("properties", {}).get("_district_id", "")) == "tavern_quarter")
	_assert(still_marked.is_empty(), "and no room still names it")
	main.cmd_proc.undo()
	_assert(JSON.stringify(main.region_mgr.data) == before, "undo restores the region exactly, district order included")
	main.cmd_proc.redo()
	_assert(not main.region_mgr.get_districts().has("tavern_quarter"), "redo deletes it again")
	var saved_ok: bool = main._save_everything()
	if not saved_ok:
		print("  refusal: ", _error_text().left(600)); main.ui_mgr.error_modal.hide()
	_assert(saved_ok, "the edit saves: the engine accepts a region without that district")
	var saved: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(fixture.path_join("data/regions/town.json")))
	_assert(not saved["properties"]["districts"].has("tavern_quarter"), "and it is gone on disk")


func _check_region_delete_refusals() -> void:
	print("\n[refusals]")
	main._confirm_delete_region()
	_assert(main.ui_mgr.error_modal.visible and "start" in _error_text(), "the start region is refused")
	main.ui_mgr.error_modal.hide()

	main._load_region("farmland.json", true)
	_assert(main.region_mgr.current_filename == "farmland.json", "a linked region is open")
	main._confirm_delete_region()
	_assert(main.ui_mgr.error_modal.visible and "lead into 'farmland'" in _error_text(), "a region other regions link into is refused, with the links listed")
	main.ui_mgr.error_modal.hide()
	_assert(FileAccess.file_exists(fixture.path_join("data/regions/farmland.json")), "and nothing was deleted")

	main._load_region("probe_empty_isle.json", true)
	main.region_mgr.mark_room_dirty("shore")
	main._confirm_delete_region()
	_assert(main.ui_mgr.error_modal.visible and "Save or discard" in _error_text(), "unsaved work is refused first")
	main.ui_mgr.error_modal.hide()
	main.region_mgr.mark_clean()
	main.region_mgr.dirty_room_ids.clear()


func _check_engine_refusal_puts_the_file_back() -> void:
	print("\n[a region the engine still needs]")
	var path := fixture.path_join("data/regions/probe_board_isle.json")
	var before := FileAccess.get_file_as_string(path)
	main._load_region("probe_board_isle.json", true)
	main._confirm_delete_region()
	_assert(main.ui_mgr.confirm_modal.visible, "an unlinked region asks for confirmation")
	main.ui_mgr._on_confirmed()
	_assert(FileAccess.get_file_as_string(path) == before, "the quest board still names it, so the engine refuses and the file is put back byte for byte")
	_assert(main.ui_mgr.error_modal.visible and "probe_board_isle" in _error_text(), "and the refusal says why")
	main.ui_mgr.error_modal.hide()


func _check_an_unreferenced_region_is_deleted() -> void:
	print("\n[an unreferenced region]")
	var path := fixture.path_join("data/regions/probe_empty_isle.json")
	main._load_region("probe_empty_isle.json", true)
	main._confirm_delete_region()
	main.ui_mgr._on_confirmed()
	_assert(not FileAccess.file_exists(path), "the file is removed")
	_assert(main.region_mgr.current_filename == "town.json", "the editor moves to the start region")
	_assert(not main._has_unsaved_work(), "with nothing left unsaved")


func _island(region_id: String, room_id: String) -> Dictionary:
	return {
		"region_id": region_id, "name": region_id.capitalize(), "description": "An island for the test.",
		"properties": {"biome": "farmland", "region_type": "wilderness", "level_band": {"min": 1, "max": 3}},
		"rooms": {room_id: {"name": room_id.capitalize(), "description": "Sand.", "exits": {}, "properties": {"entered_by_system": "ferry"}}},
	}


func _error_text() -> String:
	var text := ""
	for node in _labels(main.ui_mgr.error_modal):
		text += str(node.dialog_text if node is AcceptDialog else node.text) + "\n"
	return text


func _labels(node: Node) -> Array:
	var out: Array = []
	if node is Label or node is RichTextLabel or node is AcceptDialog: out.append(node)
	for child in node.get_children(): out.append_array(_labels(child))
	return out


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String):
	if message == "": return
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
