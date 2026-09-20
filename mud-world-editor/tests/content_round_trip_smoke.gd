# tests/content_round_trip_smoke.gd
#
# Load every shipped content set's data/ files through the real
# RegionManager/DatabaseManager, save them back through the real writer, and
# fail on any byte difference. This is the one structurally missing check in
# the editor's own test suite: every other authoring test builds a scratch
# fixture under tmp/, so nothing has ever exercised a load-then-save of the
# actual shipped content -- which is exactly the shape of the defect that
# already shipped once (a load/save round trip silently turning every
# authored integer into a float; see SaveIO.gd's _normalize_numbers). Run
# with:
#
#   godot --headless --path mud-world-editor --script tests/content_round_trip_smoke.gd
#
# Touches no real content: every set is copied under tmp/ first, and only
# the copy is ever loaded or saved.

extends SceneTree

const SaveIO = preload("res://scripts/data/SaveIO.gd")

var failure_count := 0
var repo_root: String = ""

const CONTENT_SETS := ["fantasy_frontier", "modern_capsule", "night_shift", "orbital_salvage"]


func _init() -> void:
	repo_root = ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()

	for set_id in CONTENT_SETS:
		_check_round_trip(set_id)

	_check_the_check_itself_catches_a_corrupted_file()

	if failure_count > 0:
		push_error("content round trip smoke failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- the real thing -----------------------------------------------------------

func _check_round_trip(set_id: String) -> void:
	print("\n[%s]" % set_id)
	var original_root := repo_root.path_join("content_sets").path_join(set_id)
	var scratch_root := repo_root.path_join("tmp/content_round_trip").path_join(set_id)
	_remove_recursive(scratch_root)
	_copy_recursive(original_root, scratch_root)

	DataRoot._resolved = scratch_root
	DataRoot._source = "content round trip test"

	var region_dir := scratch_root.path_join("data/regions")
	for file_name in _file_names_in(region_dir, ".json"):
		# A region-generation template ({"themes": {...}}) is not a static
		# region and the editor now refuses to load one (RegionManager.gd) --
		# matching the engine's own definition of what counts as a region
		# (server/engine/server/content_set.py checks the same key).
		var raw = JSON.parse_string(FileAccess.get_file_as_string(region_dir.path_join(file_name)))
		if raw is Dictionary and raw.get("themes") is Dictionary:
			continue
		var manager := RegionManager.new()
		if not manager.load_region(file_name):
			_assert(false, "%s: %s loads: %s" % [set_id, file_name, manager.load_error])
			continue
		var result: Dictionary = manager.save_region()
		_assert(result.get("ok", false), "%s: %s saves back cleanly: %s" % [set_id, file_name, result.get("error", "")])

	var database := DatabaseManager.new()
	var saved: Dictionary = database.save_all()
	_assert(saved.get("ok", false), "%s: the rest of the content saves back cleanly: %s" % [set_id, str(saved.get("errors", []))])

	_assert_data_dirs_match(set_id, original_root.path_join("data"), scratch_root.path_join("data"))

	DataRoot._resolved = ""
	DataRoot._source = ""


func _assert_data_dirs_match(set_id: String, original_dir: String, scratch_dir: String) -> void:
	var original_files := _json_files_recursive(original_dir, "")
	var scratch_files := _json_files_recursive(scratch_dir, "")

	var only_in_original: Array = []
	for rel_path in original_files:
		if not scratch_files.has(rel_path): only_in_original.append(rel_path)
	var only_in_scratch: Array = []
	for rel_path in scratch_files:
		if not original_files.has(rel_path): only_in_scratch.append(rel_path)
	_assert(only_in_original.is_empty(), "%s: no data file disappeared in the round trip: %s" % [set_id, str(only_in_original)])
	_assert(only_in_scratch.is_empty(), "%s: no data file was invented by the round trip: %s" % [set_id, str(only_in_scratch)])

	var changed: Array = []
	for rel_path in original_files:
		if not scratch_files.has(rel_path): continue
		var before := FileAccess.get_file_as_string(original_dir.path_join(rel_path))
		var after := FileAccess.get_file_as_string(scratch_dir.path_join(rel_path))
		if before != after:
			changed.append(rel_path)
			print("  DIFF: ", rel_path, "  ", _first_difference(before, after))
	_assert(changed.is_empty(), "%s: %d of %d data files changed after a load-and-save round trip: %s" % [set_id, changed.size(), original_files.size(), str(changed)])


# --- proving the check has teeth ----------------------------------------------

# The comparison logic above is the only thing standing between "the editor
# quietly rewrote shipped content" and a green run. Prove it actually fails on
# the exact defect shape it exists to catch: a JSON file where one integer
# became a float.
func _check_the_check_itself_catches_a_corrupted_file() -> void:
	print("\n[negative check]")
	var original_dir := repo_root.path_join("tmp/content_round_trip_negative/original")
	var corrupted_dir := repo_root.path_join("tmp/content_round_trip_negative/corrupted")
	_remove_recursive(original_dir.get_base_dir())
	DirAccess.make_dir_recursive_absolute(original_dir.path_join("items"))
	DirAccess.make_dir_recursive_absolute(corrupted_dir.path_join("items"))
	SaveIO.write_json(original_dir.path_join("items/library.json"), {
		"item_probe": {"name": "probe", "value": 10, "weight": 1},
	})
	# Written as raw text, deliberately bypassing SaveIO -- it would now
	# normalize a 10.0 float back to 10 on the way out (see SaveIO.gd's
	# _normalize_numbers), which is the fix, not something to route around.
	# This simulates the shape a pre-fix save actually produced on disk.
	var corrupted_file := FileAccess.open(corrupted_dir.path_join("items/library.json"), FileAccess.WRITE)
	corrupted_file.store_string(JSON.stringify({"item_probe": {"name": "probe", "value": 10.0, "weight": 1}}, "    ", false))
	corrupted_file.close()

	var original_files := _json_files_recursive(original_dir, "")
	var corrupted_files := _json_files_recursive(corrupted_dir, "")
	var changed: Array = []
	for rel_path in original_files:
		var before := FileAccess.get_file_as_string(original_dir.path_join(rel_path))
		var after := FileAccess.get_file_as_string(corrupted_dir.path_join(rel_path))
		if before != after:
			changed.append(rel_path)
	_assert(original_files == corrupted_files, "the fixture itself has matching file lists")
	_assert(not changed.is_empty(), "an int-to-float corruption is detected as a byte difference")


# --- helpers -------------------------------------------------------------------

func _file_names_in(dir_path: String, suffix: String) -> Array:
	var found: Array = []
	var dir := DirAccess.open(dir_path)
	if not dir:
		return found
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if not dir.current_is_dir() and name.ends_with(suffix):
			found.append(name)
		name = dir.get_next()
	dir.list_dir_end()
	return found


func _json_files_recursive(root_dir: String, relative: String) -> Dictionary:
	var found := {}
	var full := root_dir.path_join(relative) if relative != "" else root_dir
	var dir := DirAccess.open(full)
	if not dir:
		return found
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			var rel := relative.path_join(name) if relative != "" else name
			if dir.current_is_dir():
				for key in _json_files_recursive(root_dir, rel):
					found[key] = true
			elif name.ends_with(".json"):
				found[rel] = true
		name = dir.get_next()
	dir.list_dir_end()
	return found


func _first_difference(a: String, b: String) -> String:
	var shortest: int = min(a.length(), b.length())
	for i in range(shortest):
		if a[i] != b[i]:
			var start: int = max(0, i - 20)
			return "at char %d: ...%s... vs ...%s..." % [i, a.substr(start, 60), b.substr(start, 60)]
	return "one file is a prefix of the other (lengths %d vs %d)" % [a.length(), b.length()]


func _copy_recursive(from_dir: String, to_dir: String) -> void:
	DirAccess.make_dir_recursive_absolute(to_dir)
	var dir := DirAccess.open(from_dir)
	if not dir:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			var from_path := from_dir.path_join(name)
			var to_path := to_dir.path_join(name)
			if dir.current_is_dir():
				_copy_recursive(from_path, to_path)
			else:
				DirAccess.copy_absolute(from_path, to_path)
		name = dir.get_next()
	dir.list_dir_end()


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null:
		return
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


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		push_error("FAIL: " + message)
