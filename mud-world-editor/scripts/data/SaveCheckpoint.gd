# scripts/data/SaveCheckpoint.gd
#
# One coherent copy of a content set, taken before a save writes many files.
#
# `save_all()` rewrites a dozen files one at a time, and `RegionManager` writes the
# region beside them. Every individual write is atomic, but the *set* is not: a
# failure on the eighth file leaves seven new files next to an old rest, which is a
# state the engine may refuse and no author can reason about. This is the
# checkpoint half of batch 6B's "a failed multi-file apply recovers the previous
# coherent set".
#
# Scope is deliberate. It snapshots the one tree the library and the region saves
# write -- `data/`, 610 KB and 92 files for the reference set -- and not the whole
# repository. The configuration files (ruleset, contracts, elements, manifest) take
# their own single-file `.bak` after a staged engine verdict, so they are already
# recoverable one file at a time; this covers the tree that has no such guard.
#
# Restore replaces rather than merges: a file the failed save created has to go,
# and a file it truncated has to come back whole. That is also why a restore
# refuses a checkpoint belonging to another set.
class_name SaveCheckpoint
extends RefCounted

const SaveIO = preload("res://scripts/data/SaveIO.gd")

const CHECKPOINT_DIR := "editor/checkpoints"
const DATA_DIR := "data"
const INDEX_NAME := "checkpoint.json"
const KEEP := 3

## Snapshot `data/` before a save touches it. Returns `{ok, dir, files, error}`.
static func begin(set_root: String) -> Dictionary:
	var source := set_root.path_join(DATA_DIR)
	if not DirAccess.dir_exists_absolute(source):
		return {"ok": false, "dir": "", "files": 0,
			"error": "Nothing to checkpoint: %s does not exist." % source}
	var stamp := "%d-%03d" % [int(Time.get_unix_time_from_system()), Time.get_ticks_msec() % 1000]
	var target := set_root.path_join(CHECKPOINT_DIR).path_join(stamp)
	DirAccess.make_dir_recursive_absolute(target)
	var copied := _copy_tree(source, target.path_join(DATA_DIR))
	if copied < 0:
		return {"ok": false, "dir": "", "files": 0, "error": "Could not copy %s into a checkpoint." % source}
	var index := SaveIO.write_json(target.path_join(INDEX_NAME), {
		"set_root": set_root,
		"stamp": stamp,
		"files": copied,
		"note": "Taken before a save wrote data/. Restoring replaces data/ with this copy.",
	})
	if not index.get("ok", false):
		return {"ok": false, "dir": "", "files": 0,
			"error": str(index.get("error", "could not write the checkpoint index"))}
	return {"ok": true, "dir": target, "files": copied, "error": ""}

## Put the checkpointed tree back, replacing whatever is there now.
static func restore(checkpoint_dir: String, set_root: String) -> Dictionary:
	var index = JSON.parse_string(FileAccess.get_file_as_string(checkpoint_dir.path_join(INDEX_NAME)))
	if not (index is Dictionary):
		return {"ok": false, "restored": 0, "error": "%s has no readable checkpoint index." % checkpoint_dir}
	if str(index.get("set_root", "")) != set_root:
		return {"ok": false, "restored": 0,
			"error": "That checkpoint belongs to %s, not %s." % [str(index.get("set_root", "?")), set_root]}
	var snapshot := checkpoint_dir.path_join(DATA_DIR)
	if not DirAccess.dir_exists_absolute(snapshot):
		return {"ok": false, "restored": 0, "error": "The checkpoint has no %s tree." % DATA_DIR}
	var live := set_root.path_join(DATA_DIR)
	if DirAccess.dir_exists_absolute(live) and not _remove_tree(live):
		return {"ok": false, "restored": 0, "error": "Could not clear %s before restoring it." % live}
	var copied := _copy_tree(snapshot, live)
	if copied < 0:
		return {"ok": false, "restored": 0, "error": "Could not copy the checkpoint back into %s." % live}
	return {"ok": true, "restored": copied, "error": ""}

## Keep the newest `keep` checkpoints and remove the rest. Called after a save
## succeeds, so the checkpoints on disk are always the most recent coherent states.
static func prune(set_root: String, keep: int = KEEP) -> int:
	var root := set_root.path_join(CHECKPOINT_DIR)
	var names := _directories(root)
	names.sort()
	var removed := 0
	while names.size() > keep:
		var oldest: String = names.pop_front()
		if _remove_tree(root.path_join(oldest)):
			removed += 1
	return removed

## The newest checkpoint that still has an index, or "" when there is none.
static func latest(set_root: String) -> String:
	var root := set_root.path_join(CHECKPOINT_DIR)
	var names := _directories(root)
	names.sort()
	names.reverse()
	for name in names:
		var candidate := root.path_join(name)
		if FileAccess.file_exists(candidate.path_join(INDEX_NAME)):
			return candidate
	return ""

## What a checkpoint holds, for a message or a test: `{files, stamp}`.
static func summary(checkpoint_dir: String) -> Dictionary:
	var index = JSON.parse_string(FileAccess.get_file_as_string(checkpoint_dir.path_join(INDEX_NAME)))
	if not (index is Dictionary):
		return {}
	return {"files": int(index.get("files", 0)), "stamp": str(index.get("stamp", ""))}


# --- file helpers ---------------------------------------------------------------

## Copies a tree, returning the file count or -1. Directories are created as they
## are met, so an empty directory survives the round trip.
static func _copy_tree(from: String, to: String) -> int:
	DirAccess.make_dir_recursive_absolute(to)
	var dir := DirAccess.open(from)
	if dir == null:
		return -1
	var copied := 0
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			var source := from.path_join(name)
			var target := to.path_join(name)
			if dir.current_is_dir():
				var inner := _copy_tree(source, target)
				if inner < 0:
					dir.list_dir_end()
					return -1
				copied += inner
			else:
				if DirAccess.copy_absolute(source, target) != OK:
					dir.list_dir_end()
					return -1
				copied += 1
		name = dir.get_next()
	dir.list_dir_end()
	return copied

static func _remove_tree(path: String) -> bool:
	var dir := DirAccess.open(path)
	if dir == null:
		return false
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			var child := path.path_join(name)
			if dir.current_is_dir():
				if not _remove_tree(child):
					dir.list_dir_end()
					return false
			elif DirAccess.remove_absolute(child) != OK:
				dir.list_dir_end()
				return false
		name = dir.get_next()
	dir.list_dir_end()
	return DirAccess.remove_absolute(path) == OK

static func _directories(path: String) -> Array:
	var names: Array = []
	var dir := DirAccess.open(path)
	if dir == null:
		return names
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != ".." and dir.current_is_dir():
			names.append(name)
		name = dir.get_next()
	dir.list_dir_end()
	return names
