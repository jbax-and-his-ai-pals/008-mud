# tests/engine_validation_smoke.gd
#
# The editor's "Validate Content" path: `toolkit/editor_validate.py` is run as a
# subprocess and its JSON is parsed into what the modal shows. Run with:
#
#   godot --headless --path mud-world-editor --script tests/engine_validation_smoke.gd
#
# `run_editor_checks.py` also passes the interpreter it is running under, as
# `-- --python <path>`, so the check uses the same Python the rest of the build
# uses instead of guessing. Without it the usual candidates are probed, and if
# none exists the suite reports that rather than failing: no Python is a setup
# problem, not a content problem.
#
# What this must prove is the seam, not the validators themselves (the Python
# suite covers those): the subprocess runs, the JSON survives the engine's import
# logging, paths come back relative to the content set, a broken content set is
# reported as broken, and a missing toolchain is reported as missing.

extends SceneTree

const SaveIO = preload("res://scripts/data/SaveIO.gd")

var failure_count := 0
var repo_root: String = ""
var python_exe: String = ""
var scratch_root: String = ""


func _init() -> void:
	repo_root = ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	scratch_root = ProjectSettings.globalize_path("res://").path_join("../tmp/engine_validation/content_set")
	python_exe = _python_from_args()
	if python_exe == "":
		python_exe = _probe_python()
	_lock_data_root()

	if python_exe == "":
		print("\n[engine validation]")
		print("  skip  no Python interpreter found; set --python <path> or install one")
		print("        (validators: %s)" % repo_root.path_join("toolkit/editor_validate.py"))
		quit(0)
		return

	print("interpreter: %s" % python_exe)
	_check_clean_content_set()
	_check_broken_content_set()
	_check_missing_toolchain()

	if failure_count > 0:
		push_error("engine validation smoke failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- cases -------------------------------------------------------------------

func _check_clean_content_set() -> void:
	print("\n[the sci-fi proving set]")
	var result := EngineValidator.run(repo_root.path_join("content_sets/orbital_salvage"), repo_root, python_exe)
	_assert(result.get("ran", false), "the validator runs: %s" % result.get("error", ""))
	_assert(result.get("ok", false), "and passes this content set")
	_assert(not result.get("ran_checks", []).is_empty(), "it reports which checks ran (%s)" % str(result.get("ran_checks", [])))
	_assert(result.get("ran_checks", []).has("playability"),
		"it boots and exercises the open set, not only its files")
	_assert(result.get("not_run", {}).has("playability_other_sets"),
		"and names the release-only cross-set playability check")
	# `ok` means "no errors"; warnings are reported and tolerated, exactly as the
	# content gate tolerates them. This used to assert an empty issue list, which
	# held only while the editor ran a subset of the gate's checks -- adding the
	# skill audit surfaced a real, accurate warning about `crafting` being named
	# without a declared level, and the assertion had to stop calling that a
	# failure. The severity filter is the honest claim.
	var errors: Array = []
	for issue in result.get("issues", []):
		if str(issue.get("severity", "")) == "error":
			errors.append(issue)
	_assert(errors.is_empty(), "with no errors: %s" % str(errors))


func _check_broken_content_set() -> void:
	print("\n[a content set that will not load]")
	_build_broken_fixture()

	var result := EngineValidator.run(scratch_root, repo_root, python_exe)
	_assert(result.get("ran", false), "the validator still runs")
	_assert(not result.get("ok", true), "and reports the content set as broken")

	var issues: Array = result.get("issues", [])
	_assert(not issues.is_empty(), "with at least one issue")
	var named: Array = []
	for issue in issues:
		if str(issue.get("path", "")).contains("broken.json"):
			named.append(issue)
	_assert(not named.is_empty(), "naming the file that is wrong: %s" % str(issues))
	var paths_are_relative := true
	for issue in issues:
		var path := str(issue.get("path", ""))
		if path != "" and (path.begins_with("/") or path.contains(":")):
			paths_are_relative = false
	_assert(paths_are_relative, "paths are relative to the content set, not this machine's")


func _check_missing_toolchain() -> void:
	print("\n[no interpreter]")
	var result := EngineValidator.run(repo_root.path_join("content_sets/orbital_salvage"), repo_root, "")
	_assert(not result.get("ran", true), "a missing interpreter is a setup problem, not a pass")
	_assert(not str(result.get("error", "")).is_empty(), "and says so: %s" % result.get("error", ""))


# --- helpers -----------------------------------------------------------------

func _build_broken_fixture() -> void:
	_remove_recursive(scratch_root)
	# A complete-enough content set: manifest, ruleset, and one file that is not
	# valid JSON, so the engine's own loader reports it.
	DirAccess.make_dir_recursive_absolute(scratch_root.path_join("data/items"))
	DirAccess.make_dir_recursive_absolute(scratch_root.path_join("data/regions"))
	DirAccess.make_dir_recursive_absolute(scratch_root.path_join("rules"))
	SaveIO.write_json(scratch_root.path_join("content_set.manifest.json"), {
		"id": "validator_fixture", "title": "Validator Fixture", "version": "0.1.0",
		"manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
		"paths": {"content_root": "data", "ruleset": "rules/ruleset.json"},
		"start": {"region_id": "fixture", "room_id": "start"},
		"capabilities": ["inventory"],
	})
	SaveIO.write_json(scratch_root.path_join("rules/ruleset.json"), {})
	SaveIO.write_json(scratch_root.path_join("data/regions/fixture.json"), {
		"region_id": "fixture", "rooms": {"start": {"name": "Start", "exits": {}}},
	})
	var broken := FileAccess.open(scratch_root.path_join("data/items/broken.json"), FileAccess.WRITE)
	broken.store_string("{ this is not json")
	broken.close()


func _lock_data_root() -> void:
	# These checks pass their own paths, but a validator that resolves DataRoot
	# would otherwise read the real content set.
	DataRoot._resolved = repo_root.path_join("content_sets/fantasy_frontier")
	DataRoot._source = "test"


func _python_from_args() -> String:
	var args := OS.get_cmdline_user_args()
	for index in range(args.size()):
		if args[index] == "--python" and index + 1 < args.size():
			return args[index + 1]
	return ""


func _probe_python() -> String:
	var candidates := [
		repo_root.path_join(".venv/Scripts/python.exe"),
		repo_root.path_join(".venv/bin/python"),
		repo_root.path_join(".conda/python.exe"),
		"python",
	]
	for candidate in candidates:
		if candidate == "python" or FileAccess.file_exists(candidate):
			return candidate
	return ""


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
