# tests/editor_session_safety_smoke.gd
#
# The Batch A guarantees, driven through the real editor scene rather than
# through the managers alone. Run with:
#
#   godot --headless --path mud-world-editor --script tests/editor_session_safety_smoke.gd
#
# `editor_save_safety_smoke.gd` covers the writers; this covers the session:
# the prompt that stands between a region click and an hour of work, the save
# that must not report success when it failed, the undo history that must not
# outlive the region it was recorded against, and the delete that must be asked
# about and be reversible.
#
# It instantiates `scenes/Main.tscn` against a scratch content set under `tmp/`,
# so no shipped content file is read for anything but its schema.

extends SceneTree

const SaveIO = preload("res://scripts/data/SaveIO.gd")

var failure_count := 0
var content_set_root: String = ""
var data_root: String = ""
var main: Node2D = null
var checks_run := false


func _initialize() -> void:
	content_set_root = ProjectSettings.globalize_path("res://").path_join("../tmp/editor_session_safety/content_set")
	data_root = content_set_root.path_join("data")
	_rebuild_fixture()
	DataRoot._resolved = content_set_root
	DataRoot._source = "test fixture"

	main = load("res://scenes/Main.tscn").instantiate()
	root.add_child(main)


# The scene's `_ready` runs on the first frame after it enters the tree, so the
# checks wait for one tick rather than running during initialization.
func _process(_delta: float) -> bool:
	if checks_run:
		return true
	checks_run = true

	_check_startup()
	_check_dirty_navigation()
	_check_failed_save_stays_dirty()
	_check_delete_is_confirmed_and_undoable()
	_check_quit_is_asked_about()

	if failure_count > 0:
		push_error("editor session safety failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)
	return true


# --- cases -------------------------------------------------------------------

func _check_startup() -> void:
	print("\n[startup]")
	_assert(main.region_mgr.current_filename == "town.json",
		"the scene opens the content set's start region (%s)" % main.region_mgr.current_filename)
	_assert(not main._has_unsaved_work(), "a freshly loaded region is not dirty")
	_assert(not main.ui_mgr.confirm_modal.visible, "no dialog is up at startup")


func _check_dirty_navigation() -> void:
	print("\n[leaving a dirty region]")
	main.region_mgr.data.rooms["square"]["name"] = "Edited"
	main.region_mgr.mark_room_dirty("square")
	_assert(main._has_unsaved_work(), "an edit marks the region dirty")

	# A command is on the stack, so the history-clearing half can be observed.
	main.cmd_proc.commit(func(): pass, func(): pass, "probe")
	_assert(main.cmd_proc.undo_stack.size() == 1, "an undoable action is on the stack")

	main._load_region("other.json")
	_assert(main.region_mgr.current_filename == "town.json",
		"a region click does NOT discard the edits: the loaded region is unchanged")
	_assert(main.ui_mgr.confirm_modal.visible, "and the author is asked first")

	# Confirming is the author's decision; the action runs then.
	main.ui_mgr._on_confirmed()
	_assert(main.region_mgr.current_filename == "other.json", "confirming loads the other region")
	_assert(not main.region_mgr.is_region_dirty, "the newly loaded region is clean")
	_assert(main.cmd_proc.undo_stack.is_empty(), "undo history does not cross a region change")

	# And the discarding path is opt-in: cancelling keeps the edits.
	main.region_mgr.data.rooms["hall"]["name"] = "Edited Hall"
	main.region_mgr.mark_room_dirty("hall")
	main._load_region("town.json")
	main.ui_mgr._confirm_action = Callable()
	main.ui_mgr.confirm_modal.hide()
	_assert(main.region_mgr.current_filename == "other.json", "cancelling leaves the region alone")
	_assert(main.region_mgr.data.rooms["hall"]["name"] == "Edited Hall", "and the edit survives")


func _check_failed_save_stays_dirty() -> void:
	print("\n[a save that cannot happen]")
	# The parent directory is a file, so no platform will let the write succeed.
	main.region_mgr.current_filename = "blocked/other.json"
	main.region_mgr.mark_room_dirty("hall")

	var saved: bool = main._save_everything()
	_assert(not saved, "a failed save reports failure")
	_assert(main.region_mgr.is_region_dirty, "and the region stays dirty, so Save can be retried")
	_assert(main.ui_mgr.error_modal.visible, "and the author is told, rather than the console")
	main.ui_mgr.error_modal.hide()

	# Put it back so the later cases have a saveable region.
	main.region_mgr.current_filename = "other.json"
	_assert(main._save_everything(), "a writable region saves through the same path")
	_assert(not main.region_mgr.is_region_dirty, "and only then is the work marked clean")


func _check_delete_is_confirmed_and_undoable() -> void:
	print("\n[deleting a content-library entry]")
	_assert(main.database_mgr.has_entry("item", "item_probe"), "the fixture item is loaded")

	main._confirm_delete_db_entry("item", "item_probe")
	_assert(main.ui_mgr.confirm_modal.visible, "deleting asks first")
	_assert(main.database_mgr.has_entry("item", "item_probe"), "and nothing is deleted until confirmed")

	main.ui_mgr._on_confirmed()
	_assert(not main.database_mgr.has_entry("item", "item_probe"), "confirming deletes it")

	main.cmd_proc.undo()
	_assert(main.database_mgr.has_entry("item", "item_probe"), "undo puts it back")
	_assert(int(main.database_mgr.entry("item", "item_probe").get("value", 0)) == 10,
		"with its data intact")


func _check_quit_is_asked_about() -> void:
	print("\n[quitting]")
	main.region_mgr.mark_room_dirty("hall")
	_assert(main._has_unsaved_work(), "there is unsaved work")
	main._request_quit()
	_assert(main.ui_mgr.quit_modal.visible, "quitting asks, rather than closing and losing it")
	main.ui_mgr.quit_modal.hide()

	main.region_mgr.mark_clean()
	main.database_mgr.mark_clean()
	_assert(not main._has_unsaved_work(), "with nothing outstanding there is nothing to ask about")


# --- fixture -----------------------------------------------------------------

func _rebuild_fixture() -> void:
	var scratch := ProjectSettings.globalize_path("res://").path_join("../tmp/editor_session_safety")
	_remove_recursive(scratch)
	DirAccess.make_dir_recursive_absolute(data_root.path_join("regions"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("items"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("npcs"))

	_write(data_root.path_join("regions/town.json"), {
		"region_id": "town", "name": "Town",
		"rooms": {
			"square": {"name": "Square", "exits": {"north": "market"}},
			"market": {"name": "Market", "exits": {"south": "square"}},
		},
	})
	_write(data_root.path_join("regions/other.json"), {
		"region_id": "other", "name": "Other",
		"rooms": {"hall": {"name": "Hall", "exits": {}}},
	})
	_write(data_root.path_join("items/library.json"), {
		"_comment": "kept",
		"item_probe": {"name": "probe", "type": "Item", "value": 10, "weight": 0.1},
	})
	_write(data_root.path_join("npcs/one.json"), {
		"lone_npc": {"name": "Lone", "health": 10, "friendly": true},
	})
	# A file where the blocked write will be attempted from.
	_write(data_root.path_join("regions/placeholder.json"), {"region_id": "placeholder", "rooms": {}})


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
