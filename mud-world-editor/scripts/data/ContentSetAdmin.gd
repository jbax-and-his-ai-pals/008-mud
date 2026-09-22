# scripts/data/ContentSetAdmin.gd
#
# Removing and renaming a content set, which until now needed a file manager.
#
# Two rules shape this, and both are about not surprising an author:
#
#   * **Only inside the sets root.** The editor lists sets beside the checkout
#     (`ContentSetScaffold.sets_root()`), and it removes only what it lists. A set
#     opened from somewhere else is not supported yet, so deleting one is refused
#     rather than half-supported.
#   * **Nothing happens without the name typed.** A delete is the one action in
#     this editor that cannot be undone with Ctrl+Z, so the caller has to pass the
#     directory name back and it has to match.
#
# A rename moves the directory and rewrites the manifest's `id`, which is the
# identity saves are partitioned by: an existing save for the old id will refuse
# to load into the renamed set. The UI says so; the code does not pretend
# otherwise.
class_name ContentSetAdmin
extends RefCounted

const SaveIO = preload("res://scripts/data/SaveIO.gd")
const Scaffold = preload("res://scripts/data/ContentSetScaffold.gd")

## What a set contains, without changing anything: the counts a confirmation
## needs, and whether this is a set at all.
static func report(root: String) -> Dictionary:
	var manifest := root.path_join(Scaffold.MANIFEST_FILENAME)
	if not FileAccess.file_exists(manifest):
		return {"ok": false, "error": "%s has no %s, so it is not a content set." % [root, Scaffold.MANIFEST_FILENAME]}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(manifest))
	if not (parsed is Dictionary):
		return {"ok": false, "error": "The manifest at %s is not a JSON object." % manifest}
	var counted := _count(root)
	return {
		"ok": true,
		"error": "",
		"id": str(parsed.get("id", "")),
		"title": str(parsed.get("title", "")),
		"files": counted["files"],
		"directories": counted["directories"],
		"bytes": counted["bytes"],
	}

## Remove a set. `typed` must be the directory's own name.
static func delete(root: String, typed: String, allowed_parent: String) -> Dictionary:
	var described := report(root)
	if not described.get("ok", false):
		return described
	if not _is_inside(root, allowed_parent):
		return {"ok": false, "error": "%s is not inside %s, so the editor will not remove it." % [root, allowed_parent]}
	if str(typed) != root.get_file():
		return {"ok": false, "error": "The name did not match. Nothing was removed."}
	var removed := _remove_recursive(root)
	if not removed.get("ok", false):
		return removed
	return {"ok": true, "error": "", "removed_files": removed["files"], "path": root}

## Rename a set: the directory and the manifest's `id`, which must agree because
## the editor lists sets by directory and the engine reads them by id.
static func rename(root: String, new_id: String, allowed_parent: String) -> Dictionary:
	var described := report(root)
	if not described.get("ok", false):
		return described
	if not _is_inside(root, allowed_parent):
		return {"ok": false, "error": "%s is not inside %s, so the editor will not rename it." % [root, allowed_parent]}
	var wanted := str(new_id).strip_edges()
	var pattern := RegEx.new()
	# Anchored: `Scaffold.ID_PATTERN` is a bare character class, and an unanchored
	# search accepts "Not An Id" because it contains a lowercase letter. The engine
	# matches it whole (`fullmatch`), so this must too.
	pattern.compile("^%s$" % Scaffold.ID_PATTERN)
	if pattern.search(wanted) == null:
		return {"ok": false, "error": "'%s' is not a usable set id. Use %s." % [wanted, Scaffold.ID_PATTERN]}
	var target := root.get_base_dir().path_join(wanted)
	if target == root:
		return {"ok": false, "error": "That is already this set's name."}
	if DirAccess.dir_exists_absolute(target):
		return {"ok": false, "error": "%s already exists." % target}

	var error := DirAccess.rename_absolute(root, target)
	if error != OK:
		return {"ok": false, "error": "Could not rename the directory (error %d). Nothing was changed." % error}
	var manifest := target.path_join(Scaffold.MANIFEST_FILENAME)
	var payload = JSON.parse_string(FileAccess.get_file_as_string(manifest))
	if not (payload is Dictionary):
		# The directory moved but its manifest did not follow. Say exactly that
		# rather than reporting a clean rename.
		return {"ok": false, "error": "The directory is now %s, but its manifest could not be read to update the id." % target}
	payload["id"] = wanted
	var written := SaveIO.write_json(manifest, payload)
	if not written.get("ok", false):
		return {"ok": false, "error": "The directory is now %s, but writing its manifest failed: %s" % [target, str(written.get("error", ""))]}
	return {"ok": true, "error": "", "path": target, "previous_id": str(described.get("id", "")), "id": wanted}


static func _is_inside(root: String, parent: String) -> bool:
	if parent.strip_edges() == "":
		return false
	var resolved_root := ProjectSettings.globalize_path(root).simplify_path()
	var resolved_parent := ProjectSettings.globalize_path(parent).simplify_path().trim_suffix("/")
	return resolved_root.begins_with(resolved_parent + "/") and resolved_root != resolved_parent


static func _count(path: String) -> Dictionary:
	var files := 0
	var directories := 0
	var bytes := 0
	var dir := DirAccess.open(path)
	if dir == null:
		return {"files": 0, "directories": 0, "bytes": 0}
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			var child := path.path_join(name)
			if dir.current_is_dir():
				directories += 1
				var inner := _count(child)
				files += int(inner["files"]); directories += int(inner["directories"]); bytes += int(inner["bytes"])
			else:
				files += 1
				bytes += _size_of(child)
		name = dir.get_next()
	dir.list_dir_end()
	return {"files": files, "directories": directories, "bytes": bytes}


static func _size_of(path: String) -> int:
	var handle := FileAccess.open(path, FileAccess.READ)
	return 0 if handle == null else handle.get_length()


## Depth-first removal. Returns how many files went, so a confirmation can report
## what actually happened rather than what it expected to happen.
static func _remove_recursive(path: String) -> Dictionary:
	var files := 0
	var dir := DirAccess.open(path)
	if dir == null:
		return {"ok": false, "error": "Could not open %s to remove it." % path}
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			var child := path.path_join(name)
			if dir.current_is_dir():
				var inner := _remove_recursive(child)
				if not inner.get("ok", false):
					dir.list_dir_end()
					return inner
				files += int(inner["files"])
			else:
				var error := DirAccess.remove_absolute(child)
				if error != OK:
					dir.list_dir_end()
					return {"ok": false, "error": "Could not remove %s (error %d)." % [child, error]}
				files += 1
		name = dir.get_next()
	dir.list_dir_end()
	var closing := DirAccess.remove_absolute(path)
	if closing != OK:
		return {"ok": false, "error": "Removed the files but not %s (error %d)." % [path, closing]}
	return {"ok": true, "error": "", "files": files}
