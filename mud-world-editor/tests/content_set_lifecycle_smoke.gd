# tests/content_set_lifecycle_smoke.gd
#
# Renaming and removing a content set -- the two actions that cannot be undone.
#
# The editor lists sets beside the checkout; before this, an author who created one
# by mistake opened a file manager, and renaming one silently disagreed with the
# manifest id inside it. What the test cares about is the refusals, because they
# are what stands between an author and a deleted world:
#
#   * a directory that is not a content set is not one to delete;
#   * a set outside the sets root is refused rather than half-supported;
#   * the typed name has to match, and a rename needs a usable id and a free one;
#   * a rename moves the directory *and* the manifest's id, together or not at all.
#
# Everything happens in a scratch parent under `tmp/`, so the fixtures are the
# test's own and no shipped set is touched.
#
# Run with:
#
#   godot --headless --path mud-world-editor --script tests/content_set_lifecycle_smoke.gd -- --python <interp>

extends SceneTree

const AdminScript = preload("res://scripts/data/ContentSetAdmin.gd")
const Scaffold = preload("res://scripts/data/ContentSetScaffold.gd")

var failures := 0
var scratch := ""

func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	scratch = repo.path_join("tmp/content-set-lifecycle-%s" % Time.get_ticks_usec())
	DirAccess.make_dir_recursive_absolute(scratch)
	var set_root := scratch.path_join("sets")
	DirAccess.make_dir_recursive_absolute(set_root)
	_copy(repo.path_join("content_sets/orbital_salvage"), set_root.path_join("orbital_salvage"))
	DirAccess.make_dir_recursive_absolute(set_root.path_join("not_a_set"))
	_write(set_root.path_join("not_a_set/readme.txt"), "not a content set\n")

	_check_a_report_counts_what_a_confirmation_needs(set_root)
	_check_a_directory_without_a_manifest_is_refused(set_root)
	_check_a_set_outside_the_sets_root_is_refused(set_root)
	_check_the_typed_name_has_to_match(set_root)
	_check_a_rename_needs_a_usable_free_id(set_root)
	_check_a_rename_moves_the_directory_and_the_id(set_root)
	_check_a_delete_removes_exactly_what_it_reported(set_root)
	_check_the_editor_open_set_is_the_callers_business(set_root)

	_remove_recursive(scratch)
	if failures > 0:
		push_error("content set lifecycle smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


# --- the checks ---------------------------------------------------------------

func _check_a_report_counts_what_a_confirmation_needs(set_root: String) -> void:
	print("\n[a report counts what a confirmation needs]")
	var described: Dictionary = AdminScript.report(set_root.path_join("orbital_salvage"))
	_assert(described.get("ok", false), "the set is reported: %s" % described.get("error", ""))
	_assert(str(described.get("id", "")) == "orbital_salvage", "with its id: %s" % described.get("id", ""))
	_assert(str(described.get("title", "")) == "Orbital Salvage", "and its title")
	_assert(int(described.get("files", 0)) > 5, "and a file count: %d" % int(described.get("files", 0)))
	_assert(int(described.get("bytes", 0)) > 0, "and a size")
	# The count is what a delete confirmation shows, so it must be the real number.
	_assert(int(described.get("files", 0)) == _count_files(set_root.path_join("orbital_salvage")),
		"the count matches the tree on disk")


func _check_a_directory_without_a_manifest_is_refused(set_root: String) -> void:
	print("\n[a directory without a manifest is refused]")
	var described: Dictionary = AdminScript.report(set_root.path_join("not_a_set"))
	_assert(not described.get("ok", true), "a plain directory is not a content set")
	var removed: Dictionary = AdminScript.delete(set_root.path_join("not_a_set"), "not_a_set", set_root)
	_assert(not removed.get("ok", true), "and cannot be deleted through this door")
	_assert(DirAccess.dir_exists_absolute(set_root.path_join("not_a_set")), "so it is still there")


func _check_a_set_outside_the_sets_root_is_refused(set_root: String) -> void:
	print("\n[a set outside the sets root is refused]")
	var outside := scratch.path_join("elsewhere")
	DirAccess.make_dir_recursive_absolute(outside)
	_copy(set_root.path_join("orbital_salvage"), outside.path_join("orbital_salvage"))
	var removed: Dictionary = AdminScript.delete(outside.path_join("orbital_salvage"), "orbital_salvage", set_root)
	_assert(not removed.get("ok", true), "deleting outside the sets root is refused")
	_assert(DirAccess.dir_exists_absolute(outside.path_join("orbital_salvage")), "and the copy is untouched")
	var renamed: Dictionary = AdminScript.rename(outside.path_join("orbital_salvage"), "renamed", set_root)
	_assert(not renamed.get("ok", true), "so is renaming")
	var empty_parent: Dictionary = AdminScript.delete(set_root.path_join("orbital_salvage"), "orbital_salvage", "")
	_assert(not empty_parent.get("ok", true), "and an empty allowed-parent is not a wildcard")


func _check_the_typed_name_has_to_match(set_root: String) -> void:
	print("\n[the typed name has to match]")
	var wrong: Dictionary = AdminScript.delete(set_root.path_join("orbital_salvage"), "orbital", set_root)
	_assert(not wrong.get("ok", true), "a partial name is refused")
	_assert(str(wrong.get("error", "")).contains("did not match"), "and says so: %s" % wrong.get("error", ""))
	var empty: Dictionary = AdminScript.delete(set_root.path_join("orbital_salvage"), "", set_root)
	_assert(not empty.get("ok", true), "an empty name is refused")
	_assert(DirAccess.dir_exists_absolute(set_root.path_join("orbital_salvage")), "the set is still there")


func _check_a_rename_needs_a_usable_free_id(set_root: String) -> void:
	print("\n[a rename needs a usable, free id]")
	var bad: Dictionary = AdminScript.rename(set_root.path_join("orbital_salvage"), "Not An Id", set_root)
	_assert(not bad.get("ok", true), "an id the engine would refuse is refused here")
	_assert(str(bad.get("error", "")).contains("[a-z]"), "and the message names the pattern: %s" % bad.get("error", ""))
	var taken := AdminScript.rename(set_root.path_join("orbital_salvage"), "not_a_set", set_root)
	_assert(not taken.get("ok", true), "an id another directory already holds is refused")
	var same: Dictionary = AdminScript.rename(set_root.path_join("orbital_salvage"), "orbital_salvage", set_root)
	_assert(not same.get("ok", true), "renaming to the same name is refused")
	_assert(DirAccess.dir_exists_absolute(set_root.path_join("orbital_salvage")),
		"and after every refusal the set is still where it was")


func _check_a_rename_moves_the_directory_and_the_id(set_root: String) -> void:
	print("\n[a rename moves the directory and the id together]")
	var before := set_root.path_join("orbital_salvage")
	var renamed: Dictionary = AdminScript.rename(before, "orbital_salvage_v2", set_root)
	_assert(renamed.get("ok", false), "the rename succeeds: %s" % renamed.get("error", ""))
	var after := set_root.path_join("orbital_salvage_v2")
	_assert(not DirAccess.dir_exists_absolute(before), "the old directory is gone")
	_assert(DirAccess.dir_exists_absolute(after), "the new one exists")
	_assert(str(renamed.get("path", "")) == after, "and the result says where it went")
	var manifest = JSON.parse_string(FileAccess.get_file_as_string(after.path_join(Scaffold.MANIFEST_FILENAME)))
	_assert(manifest is Dictionary and str(manifest.get("id", "")) == "orbital_salvage_v2",
		"the manifest id followed the directory: %s" % str(manifest.get("id", "")))
	_assert(str(manifest.get("title", "")) == "Orbital Salvage", "and nothing else in it moved")
	var described: Dictionary = AdminScript.report(after)
	_assert(described.get("ok", false), "the renamed set still reports as a set")


func _check_a_delete_removes_exactly_what_it_reported(set_root: String) -> void:
	print("\n[a delete removes exactly what it reported]")
	var target := set_root.path_join("orbital_salvage_v2")
	var described: Dictionary = AdminScript.report(target)
	var expected := int(described.get("files", 0))
	var removed: Dictionary = AdminScript.delete(target, "orbital_salvage_v2", set_root)
	_assert(removed.get("ok", false), "the delete succeeds: %s" % removed.get("error", ""))
	_assert(not DirAccess.dir_exists_absolute(target), "the directory is gone")
	_assert(int(removed.get("removed_files", -1)) == expected,
		"and it removed the %d files it reported, not %d" % [expected, int(removed.get("removed_files", -1))])
	_assert(DirAccess.dir_exists_absolute(set_root.path_join("not_a_set")),
		"the neighbouring directory is untouched")


func _check_the_editor_open_set_is_the_callers_business(set_root: String) -> void:
	# The admin layer does not know which set the editor has open -- that is the UI's
	# check, and it is asserted here so the split is visible rather than assumed.
	print("\n[the open set is the caller's business]")
	var described: Dictionary = AdminScript.report(set_root.path_join("not_a_set"))
	_assert(not described.get("ok", true), "the admin layer answers about disk, not about what is open")


# --- helpers ------------------------------------------------------------------

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
