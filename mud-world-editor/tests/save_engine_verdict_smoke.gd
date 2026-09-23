# tests/save_engine_verdict_smoke.gd
#
# Region and content-library saves are validated by the engine after they are
# written: `Main._save_everything` checkpoints the set, writes, runs the
# engine's content-set validator, and on refusal restores the checkpoint while
# the edits stay open and dirty. `editor_session_safety_smoke.gd` proves the
# failed-write half; this proves the refused-content half, through the real
# editor scene on a copy of fantasy_frontier, with the kind of value a form can
# now produce that fails open in the game rather than loudly.
#
#   godot --headless --path mud-world-editor --script tests/save_engine_verdict_smoke.gd

extends SceneTree

var failures := 0
var fixture := ""
var main: Node2D = null
var checks_run := false


func _initialize() -> void:
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/save-engine-verdict-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "test fixture"
	main = load("res://scenes/Main.tscn").instantiate()
	root.add_child(main)


func _process(_delta: float) -> bool:
	if checks_run: return true
	checks_run = true
	_check_a_refused_region_edit_is_put_back()
	_check_a_refused_library_edit_is_put_back()
	if failures > 0: push_error("save engine verdict failed (%d)" % failures)
	quit(1 if failures > 0 else 0)
	return true


func _check_a_refused_region_edit_is_put_back() -> void:
	print("\n[a region edit the engine refuses]")
	_assert(main.region_mgr.current_filename == "town.json", "the editor opened the start region")
	var path := fixture.path_join("data/regions/town.json")
	var before := FileAccess.get_file_as_string(path)
	var cell: Dictionary = main.region_mgr.data.rooms["jail_cell"]
	# "lock" is not a requirement type the engine enforces, so in play this
	# would leave the cell door open -- the kind of mistake that fails silently.
	cell["properties"]["exit_requirements"]["up"]["type"] = "lock"
	main.region_mgr.mark_room_dirty("jail_cell")

	_assert(not main._save_everything(), "the save reports failure")
	_assert(FileAccess.get_file_as_string(path) == before, "town.json is back to its bytes before the save")
	_assert(main.region_mgr.is_region_dirty, "the region is still dirty, so the edit can be fixed and saved")
	_assert(main.region_mgr.data.rooms["jail_cell"]["properties"]["exit_requirements"]["up"]["type"] == "lock", "and the edit is still on screen")
	_assert(main.ui_mgr.error_modal.visible, "the author is told")
	_assert("exit_requirements.up.type" in _error_text(), "and the message names the field: %s" % _error_text().left(300))
	main.ui_mgr.error_modal.hide()

	cell["properties"]["exit_requirements"]["up"]["type"] = "locked"
	cell["properties"]["exit_requirements"]["up"]["pick_difficulty"] = 40
	_assert(main._save_everything(), "once fixed, the same save succeeds")
	var saved: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	_assert(int(saved["rooms"]["jail_cell"]["properties"]["exit_requirements"]["up"]["pick_difficulty"]) == 40, "and the fixed edit is on disk")
	_assert(not main.region_mgr.is_region_dirty, "and only then is the region clean")


func _check_a_refused_library_edit_is_put_back() -> void:
	print("\n[a content-library edit the engine refuses]")
	var path := fixture.path_join("data/quests/instances.json")
	var before := FileAccess.get_file_as_string(path)
	var template: Dictionary = main.database_mgr.quests["instance_generic_infestation"]
	# Accepted by the board, never completed by the quest tracker.
	template["objective"]["type"] = "kill"
	main.database_mgr.mark_dirty("quest", "instance_generic_infestation")

	_assert(not main._save_everything(), "the save reports failure")
	_assert(FileAccess.get_file_as_string(path) == before, "instances.json is back to its bytes before the save")
	_assert(main.database_mgr.has_unsaved_changes(), "the library still has unsaved changes")
	_assert("clear_region" in _error_text(), "and the message says why")
	main.ui_mgr.error_modal.hide()

	template["objective"]["type"] = "clear_region"
	_assert(main._save_everything(), "once fixed, the same save succeeds")


func _error_text() -> String:
	var text := ""
	for node in _labels(main.ui_mgr.error_modal):
		text += str(node.dialog_text if node is AcceptDialog else node.text) + "\n"
	return text


func _labels(node: Node) -> Array:
	var out: Array = []
	if node is Label or node is RichTextLabel or node is AcceptDialog:
		out.append(node)
	for child in node.get_children(): out.append_array(_labels(child))
	return out


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
