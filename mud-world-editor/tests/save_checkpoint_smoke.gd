# tests/save_checkpoint_smoke.gd
#
# A save that writes many files either lands whole or is put back.
#
# `save_all()` rewrites a dozen files one at a time. Each write is atomic on its
# own, which is why the editor felt safe, but a failure on the fourth leaves three
# new files beside an old rest -- a set the engine may refuse and an author cannot
# reason about. The checkpoint is what makes "the previous coherent set" a fact
# rather than a hope.
#
# What this checks is mostly the failure path, because that is the one nobody
# exercises by hand: a modified file comes back, a file the failed save *created*
# goes away, a file it deleted returns, a checkpoint of another set is refused,
# and only the newest few are kept.
#
# Run with:
#
#   godot --headless --path mud-world-editor --script tests/save_checkpoint_smoke.gd -- --python <interp>

extends SceneTree

const Checkpoint = preload("res://scripts/data/SaveCheckpoint.gd")

var failures := 0
var scratch := ""
var set_root := ""

func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	scratch = repo.path_join("tmp/save-checkpoint-%s" % Time.get_ticks_usec())
	DirAccess.make_dir_recursive_absolute(scratch)
	set_root = scratch.path_join("orbital_salvage")
	_copy(repo.path_join("content_sets/orbital_salvage"), set_root)

	_check_a_checkpoint_is_taken_before_the_write()
	_check_restore_puts_a_modified_file_back()
	_check_restore_removes_what_the_failed_save_created()
	_check_restore_brings_back_what_the_failed_save_deleted()
	_check_a_checkpoint_of_another_set_is_refused()
	_check_pruning_keeps_the_newest()
	_check_a_tree_with_no_data_is_not_checkpointable()

	_remove_recursive(scratch)
	if failures > 0:
		push_error("save checkpoint smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


# --- the checks ---------------------------------------------------------------

func _check_a_checkpoint_is_taken_before_the_write() -> void:
	print("\n[a checkpoint is taken before the write]")
	var result: Dictionary = Checkpoint.begin(set_root)
	_assert(result.get("ok", false), "the checkpoint is taken: %s" % result.get("error", ""))
	_assert(DirAccess.dir_exists_absolute(str(result.get("dir", ""))), "and its directory exists")
	_assert(int(result.get("files", 0)) == _count_files(set_root.path_join("data")),
		"it copied every file in data/: %d" % int(result.get("files", 0)))
	var summary: Dictionary = Checkpoint.summary(str(result.get("dir", "")))
	_assert(int(summary.get("files", 0)) == int(result.get("files", 0)),
		"and its index says the same")
	_assert(Checkpoint.latest(set_root) == str(result.get("dir", "")),
		"and it is the newest one")


func _check_restore_puts_a_modified_file_back() -> void:
	print("\n[restore puts a modified file back]")
	var target := set_root.path_join("data/items/components.json")
	var original := FileAccess.get_file_as_string(target)
	var checkpoint: Dictionary = Checkpoint.begin(set_root)
	# The failed save: one file written, then the failure.
	_write(target, original.replace("\"name\"", "\"renamed_by_a_failed_save\""))
	_assert(FileAccess.get_file_as_string(target) != original, "the live file really changed")
	var restored: Dictionary = Checkpoint.restore(str(checkpoint["dir"]), set_root)
	_assert(restored.get("ok", false), "the restore succeeds: %s" % restored.get("error", ""))
	_assert(FileAccess.get_file_as_string(target) == original, "and the file is byte-for-byte what it was")


func _check_restore_removes_what_the_failed_save_created() -> void:
	print("\n[restore removes what the failed save created]")
	var created := set_root.path_join("data/items/invented_by_a_failed_save.json")
	var checkpoint: Dictionary = Checkpoint.begin(set_root)
	_write(created, "{\"item_ghost\": {\"name\": \"Ghost\", \"type\": \"Item\"}}")
	_assert(FileAccess.file_exists(created), "the failed save created a file")
	Checkpoint.restore(str(checkpoint["dir"]), set_root)
	_assert(not FileAccess.file_exists(created),
		"and restoring removes it: a merge would have left it behind")


func _check_restore_brings_back_what_the_failed_save_deleted() -> void:
	print("\n[restore brings back what the failed save deleted]")
	var doomed := set_root.path_join("data/items/supplies.json")
	var original := FileAccess.get_file_as_string(doomed)
	var checkpoint: Dictionary = Checkpoint.begin(set_root)
	DirAccess.remove_absolute(doomed)
	_assert(not FileAccess.file_exists(doomed), "the failed save deleted a file")
	Checkpoint.restore(str(checkpoint["dir"]), set_root)
	_assert(FileAccess.get_file_as_string(doomed) == original, "and restoring brings it back whole")


func _check_a_checkpoint_of_another_set_is_refused() -> void:
	print("\n[a checkpoint of another set is refused]")
	var other := scratch.path_join("night_shift")
	_copy(set_root, other)
	var checkpoint: Dictionary = Checkpoint.begin(set_root)
	var wrong: Dictionary = Checkpoint.restore(str(checkpoint["dir"]), other)
	_assert(not wrong.get("ok", true), "a checkpoint is refused by a set it does not belong to")
	_assert(str(wrong.get("error", "")).contains("belongs to"), "and says why: %s" % wrong.get("error", ""))


func _check_pruning_keeps_the_newest() -> void:
	print("\n[pruning keeps the newest]")
	for index in range(3):
		Checkpoint.begin(set_root)
	var before := _checkpoint_names().size()
	_assert(before >= 4, "there are several checkpoints now: %d" % before)
	var removed: int = Checkpoint.prune(set_root, 2)
	_assert(removed == before - 2, "pruning removed all but two: %d" % removed)
	var kept := _checkpoint_names()
	_assert(kept.size() == 2, "two are kept: %s" % str(kept))
	kept.sort()
	_assert(kept[kept.size() - 1] == Checkpoint.latest(set_root).get_file(),
		"and the newest one survives")


func _check_a_tree_with_no_data_is_not_checkpointable() -> void:
	print("\n[a tree with no data is not checkpointable]")
	var empty := scratch.path_join("empty_set")
	DirAccess.make_dir_recursive_absolute(empty)
	var result: Dictionary = Checkpoint.begin(empty)
	_assert(not result.get("ok", true), "there is nothing to checkpoint")
	_assert(str(result.get("error", "")).contains("does not exist"), "and it says what is missing")


# --- helpers ------------------------------------------------------------------

func _checkpoint_names() -> Array:
	var names: Array = []
	var dir := DirAccess.open(set_root.path_join(Checkpoint.CHECKPOINT_DIR))
	if dir == null: return names
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != ".." and dir.current_is_dir(): names.append(name)
		name = dir.get_next()
	dir.list_dir_end()
	return names


func _count_files(path: String) -> int:
	var files := 0
	var dir := DirAccess.open(path)
	if dir == null: return 0
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			if dir.current_is_dir(): files += _count_files(path.path_join(name))
			else: files += 1
		name = dir.get_next()
	dir.list_dir_end()
	return files


func _write(path: String, text: String) -> void:
	var handle := FileAccess.open(path, FileAccess.WRITE)
	if handle != null: handle.store_string(text)


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
			if dir.current_is_dir():
				_copy(from.path_join(name), to.path_join(name))
			else:
				DirAccess.copy_absolute(from.path_join(name), to.path_join(name))
		name = dir.get_next()
	dir.list_dir_end()


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null: return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			if dir.current_is_dir():
				_remove_recursive(path.path_join(name))
			else:
				DirAccess.remove_absolute(path.path_join(name))
		name = dir.get_next()
	dir.list_dir_end()
	DirAccess.remove_absolute(path)
