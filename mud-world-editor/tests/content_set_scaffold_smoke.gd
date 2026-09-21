# tests/content_set_scaffold_smoke.gd
#
# Track G item 6: creating a content set from inside the editor.
#
#   godot --headless --path mud-world-editor --script tests/content_set_scaffold_smoke.gd \
#       -- --python <path to python>
#
# Why this exists
# ---------------
# `DataRoot.available_content_sets()` finds a set by testing for
# `content_set.manifest.json` and nothing in the editor had ever written one, so
# the documented way to make a new set was to hand-write the manifest and guess at
# the rest -- which is what the editor's own tests did
# (`contract_authoring_smoke.gd:212`). A scaffold is only worth having if what it
# writes is a set the engine *loads*, so this check does not stop at "the files are
# there": it asks the engine, and then opens the result in the real editor and saves
# it, comparing every byte.
#
# The three claims:
#
# 1. **What it copies is what the source had.** Byte-for-byte, file for file. A
#    copy that quietly reformats its source is how a new set starts out different
#    from the one it was copied from.
# 2. **What it writes is a loadable set.** `EngineValidator.run` -- the same
#    toolkit the Validate button uses, so the editor and CI agree -- says ok.
# 3. **Opening and saving changes nothing.** The editor is pointed at the new set
#    through the real `Main.tscn`, saves everything, and no file is dropped,
#    invented or altered.
#
# The failures it refuses are asserted too: a taken id, an unknown id shape, a
# missing source, and a source that is not a content set.

extends SceneTree

const SaveIO = preload("res://scripts/data/SaveIO.gd")

var failure_count := 0
var repo_root: String = ""
var python_exe: String = ""
var scratch: String = ""
var source_set: String = ""
var target_root: String = ""
var create_result: Dictionary = {}
var checks_run := false
var main: Node2D = null
# `user://editor_settings.json` is the real editor's settings file, not scratch
# state: switching content set writes it, so whatever was there goes back.
var settings_path: String = ""
var previous_settings: String = ""
var previous_settings_existed := false


func _initialize() -> void:
	repo_root = ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	python_exe = _python_from_args()
	if python_exe == "":
		python_exe = _probe_python()

	settings_path = ProjectSettings.globalize_path("user://editor_settings.json")
	previous_settings_existed = FileAccess.file_exists(settings_path)
	if previous_settings_existed:
		previous_settings = FileAccess.get_file_as_string(settings_path)

	# Simplified, because `DataRoot` simplifies every path it resolves and a
	# comparison of `.../mud-world-editor/../tmp/x` against `.../tmp/x` fails on
	# text while both name the same directory.
	scratch = ProjectSettings.globalize_path("res://").path_join("../tmp/content_set_scaffold").simplify_path()
	_remove_recursive(scratch)
	target_root = scratch.path_join("sets")
	DirAccess.make_dir_recursive_absolute(target_root)
	source_set = scratch.path_join("source_set")
	_build_source_set()

	create_result = ContentSetScaffold.create("new_world", "New World", source_set, target_root)
	_assert(create_result.get("ok", false),
		"a set is created from the fixture: %s" % str(create_result.get("errors", [])))

	# point the real editor at it, exactly as the create dialog does by emitting
	# the switch after a successful create
	DataRoot._resolved = str(create_result.get("path", ""))
	DataRoot._source = "scaffold smoke test"
	main = load("res://scenes/Main.tscn").instantiate()
	root.add_child(main)


func _process(_delta: float) -> bool:
	if checks_run:
		return true
	checks_run = true

	_check_what_was_copied()
	_check_the_manifest()
	_check_the_starter_region()
	_check_the_engine_loads_it()
	_check_opening_and_saving_it_changes_nothing()
	_check_the_refusals()
	_check_what_it_says_is_still_owed()
	_check_the_default_rules_choice_validates()
	_check_the_dialog_creates_and_opens_one()
	_restore_settings()

	if failure_count > 0:
		push_error("content set scaffold smoke failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)
	return true


# --- the dialog, the way an author drives it ----------------------------------

## The last untested seam: the form. Everything above proves the scaffold writes a
## set the engine loads; this proves the dialog an author actually uses creates one
## and hands it to the switch.
##
## It is pointed at scratch state first. The dialog creates sets where sets live --
## beside the checkout -- and a check that exercised it as shipped would write a new
## content set into the repository and into every later content-check run.
func _check_the_dialog_creates_and_opens_one() -> void:
	print("\n[the dialog]")
	var dialog: CreateContentSetDialog = main.ui_mgr.create_content_set_dialog
	_assert(dialog != null, "the content-set chooser has a create dialog")
	if dialog == null:
		return
	dialog.set_target_root(scratch.path_join("dialog_sets"))
	main.ui_mgr.show_create_content_set()
	_assert(dialog.visible, "it opens")

	# The button is dead until the id is usable -- the commonest mistake cannot be
	# submitted at all.
	dialog.id_field.text = "Not An Id"
	dialog._validate()
	_assert(dialog.get_ok_button().disabled, "with an unusable id the button is disabled")
	_assert(dialog.status_label.text != "", "and the reason is shown: %s" % dialog.status_label.text)

	dialog.id_field.text = "from_dialog"
	dialog.title_field.text = "From Dialog"
	dialog._validate()
	_assert(not dialog.get_ok_button().disabled, "a usable id enables it")

	var chosen := _select_source(dialog.source_picker, "night_shift")
	_assert(chosen, "night_shift is offered as a source to copy from")
	if not chosen:
		return
	_assert(not dialog.copy_rules_check.button_pressed,
		"and the default is rules that declare nothing")

	dialog.confirmed.emit()
	_assert(dialog.ok_button_text == "Open it", "creating reports back instead of closing")
	_assert(dialog.status_label.text.contains("Created"), "the receipt names what happened: %s" % dialog.status_label.text)
	_assert(dialog.status_label.text.contains("night_shift"), "and where it came from")
	_assert(dialog.id_field.editable == false, "with the fields locked so the receipt cannot be edited")

	var target := scratch.path_join("dialog_sets").path_join("from_dialog")
	_assert(DirAccess.dir_exists_absolute(target), "the set is on disk at the scratch root")
	_assert(FileAccess.file_exists(target.path_join("content_set.manifest.json")), "with a manifest")

	# The second press is the one that opens it, through the same signal the
	# chooser uses.
	dialog.confirmed.emit()
	_assert(DataRoot.root() == target, "and the editor switched to it (%s)" % DataRoot.root())
	_assert(main.region_mgr.current_filename == "from_dialog.json",
		"loading its start region (%s)" % main.region_mgr.current_filename)


func _select_source(picker: OptionButton, set_name: String) -> bool:
	for index in range(picker.item_count):
		if str(picker.get_item_metadata(index)).get_file() == set_name:
			picker.select(index)
			picker.item_selected.emit(index)
			return true
	return false


## Leave the machine as it was found: a check that changes which world the editor
## opens next launch is a check that breaks the next launch. A previous value
## pointing at scratch state is the pollution itself rather than something to
## restore.
func _restore_settings() -> void:
	var restore := previous_settings_existed and not previous_settings.contains("tmp/")
	if restore:
		var file := FileAccess.open(settings_path, FileAccess.WRITE)
		if file != null:
			file.store_string(previous_settings)
			file.close()
		return
	if previous_settings_existed:
		print("  note: discarding a settings file that pointed at scratch state")
	DirAccess.remove_absolute(settings_path)


# --- what it wrote ------------------------------------------------------------

func _check_what_was_copied() -> void:
	print("\n[the copy]")
	var created := str(create_result.get("path", ""))
	# Everything the result says it copied is byte-identical to its source, checked
	# by path rather than by folder: the default mode copies `presentation/` and
	# `opening/` and writes its own `rules/`, and a folder-level comparison would
	# either miss the difference or call the placeholder a bad copy.
	var copied: Array = create_result.get("copied", [])
	_assert(not copied.is_empty(), "the result reports what it copied (%d files)" % copied.size())
	for path in copied:
		var relative := str(path).trim_prefix(created + "/")
		var original := source_set.path_join(relative)
		_assert(FileAccess.file_exists(original), "%s came from the source" % relative)
		_assert(FileAccess.get_file_as_string(original) == FileAccess.get_file_as_string(str(path)),
			"%s is byte-identical" % relative)

	# And the two folders that are always copied were copied whole.
	for folder in ["presentation", "opening"]:
		_assert(_relative_files(source_set.path_join(folder)) == _relative_files(created.path_join(folder)),
			"%s/ was copied whole" % folder)

	# `rules/` is copied only when asked, which is the whole of the rules choice.
	var copied_rules := false
	for path in copied:
		if str(path).contains("/rules/"):
			copied_rules = true
	_assert(not copied_rules, "the default mode did not copy the source's rules/")

	for directory in ContentSetScaffold.REQUIRED_DATA_DIRECTORIES:
		_assert(DirAccess.dir_exists_absolute(created.path_join("data").path_join(directory)),
			"the engine's required data directory `%s` exists" % directory)


func _check_the_manifest() -> void:
	print("\n[the manifest]")
	var created := str(create_result.get("path", ""))
	var manifest := _read_json(created.path_join(ContentSetScaffold.MANIFEST_FILENAME))
	_assert(not manifest.is_empty(), "the manifest is there and readable")

	for key in ContentSetScaffold.REQUIRED_STRINGS:
		_assert(typeof(manifest.get(key)) == TYPE_STRING and str(manifest[key]).strip_edges() != "",
			"the required string `%s` is written" % key)
	_assert(manifest.get("id") == "new_world", "with the id that was asked for")
	_assert(manifest.get("title") == "New World", "and the title")
	_assert(manifest.get("manifest_schema_version") == ContentSetScaffold.MANIFEST_SCHEMA_VERSION,
		"speaking the schema version the engine implements")

	var paths: Dictionary = manifest.get("paths", {})
	for key in ContentSetScaffold.REQUIRED_PATHS:
		_assert(paths.has(key), "paths.%s is declared" % key)
	_assert(paths.get("content_root") == "data", "the content root is `data`")

	var start: Dictionary = manifest.get("start", {})
	for key in ContentSetScaffold.REQUIRED_START_FIELDS:
		_assert(str(start.get(key, "")) != "", "start.%s is declared" % key)
	_assert(start.get("region_id") == "new_world", "starting in the region the scaffold wrote")

	# The source's capabilities are kept, and only ones the engine knows.
	var capabilities: Array = manifest.get("capabilities", [])
	_assert(capabilities == ["inventory", "crafting"],
		"the capabilities are the source's own: %s" % str(capabilities))
	for capability in capabilities:
		_assert(ContentSetScaffold.CAPABILITIES.has(str(capability)),
			"`%s` is a capability the engine has" % capability)

	# The opening is a real file the manifest points at, with the id `start` agrees
	# with: the engine refuses a pair that disagrees.
	if paths.has("opening"):
		var opening := _read_json(created.path_join(str(paths["opening"])))
		_assert(not opening.is_empty(), "paths.opening points at a file that is there")
		_assert(opening.get("scenario_id") == start.get("scenario_id"),
			"and its scenario_id matches start.scenario_id (%s)" % str(opening.get("scenario_id")))


func _check_the_starter_region() -> void:
	print("\n[the starter world]")
	var created := str(create_result.get("path", ""))
	var region := _read_json(created.path_join("data/regions/new_world.json"))
	_assert(not region.is_empty(), "the start region is written")
	_assert(region.get("region_id") == "new_world", "with the region id")
	var rooms: Dictionary = region.get("rooms", {})
	_assert(rooms.has("start"), "holding the start room")
	_assert(rooms.size() == 1, "one room and no more: the rest is the author's (%d)" % rooms.size())
	var room: Dictionary = rooms.get("start", {})
	_assert(typeof(room.get("exits")) == TYPE_DICTIONARY and room["exits"].is_empty(),
		"with no exits yet")

	# The fixture's ruleset declares no region policy, so nothing is required of the
	# region's properties. A set that requires them is checked against the real
	# content set below.
	_assert(not region.has("properties") or typeof(region.get("properties")) == TYPE_DICTIONARY,
		"properties are an object when present")


func _check_the_engine_loads_it() -> void:
	print("\n[the engine's verdict]")
	var created := str(create_result.get("path", ""))
	var result := EngineValidator.run(created, repo_root, python_exe)
	if not result.get("ran", false):
		print("  SKIP the validator could not run: %s" % str(result.get("error", "")))
		return
	var errors: Array = []
	for issue in result.get("issues", []):
		if str(issue.get("severity", "")) == "error":
			errors.append("%s: %s" % [str(issue.get("path", "")), str(issue.get("message", ""))])
	_assert(errors.is_empty(), "a scaffolded set loads: %s" % str(errors))
	_assert(result.get("ok", false), "the validator's own verdict is ok: %s" % str(result.get("counts", {})))


func _check_opening_and_saving_it_changes_nothing() -> void:
	print("\n[opening it in the editor]")
	var created := str(create_result.get("path", ""))
	var before := _snapshot(created)

	_assert(DataRoot.root() == created, "the editor is pointed at it (%s)" % DataRoot.root())
	_assert(main.region_mgr.current_filename == "new_world.json",
		"with its start region loaded (%s)" % main.region_mgr.current_filename)
	_assert(main.region_mgr.data.rooms.has("start"), "and its one room")

	var saved: bool = main._save_everything()
	_assert(saved, "the editor saves it")
	var after := _snapshot(created)

	var dropped: Array = []
	var invented: Array = []
	for path in before:
		if not after.has(path): dropped.append(path)
	for path in after:
		if not before.has(path): invented.append(path)
	_assert(dropped.is_empty(), "no file disappeared: %s" % str(dropped))
	_assert(invented.is_empty(), "no file was invented: %s" % str(invented))

	var changed: Array = []
	for path in before:
		if after.has(path) and before[path] != after[path]:
			changed.append(path)
	_assert(changed.is_empty(), "and no file changed: %s" % str(changed))


func _check_the_refusals() -> void:
	print("\n[what it refuses]")
	var before: Array = _relative_files(target_root)

	var taken := ContentSetScaffold.create("new_world", "Again", source_set, target_root)
	_assert(not taken.get("ok", false), "an id that is already taken is refused")

	var bad_id := ContentSetScaffold.create("New World", "Bad", source_set, target_root)
	_assert(not bad_id.get("ok", false), "an id with a space and capitals is refused")
	_assert(not bad_id.get("errors", []).is_empty(), "with a reason: %s" % str(bad_id.get("errors", [])))

	var missing := ContentSetScaffold.create("orphan", "Orphan", scratch.path_join("nowhere"), target_root)
	_assert(not missing.get("ok", false), "a source set that is not there is refused")

	var not_a_set := scratch.path_join("not_a_set")
	DirAccess.make_dir_recursive_absolute(not_a_set)
	var folderless := ContentSetScaffold.create("folderless", "Folderless", not_a_set, target_root)
	_assert(not folderless.get("ok", false), "a directory with no rules/ to copy is refused")

	_assert(_relative_files(target_root) == before,
		"no refused create left anything behind: %s" % str(_relative_files(target_root)))

	# The id rule itself, which the dialog disables its button on.
	_assert(ContentSetScaffold.id_problem("") != "", "an empty id is a problem")
	_assert(ContentSetScaffold.id_problem("ok_id") == "", "a plain id is not")
	_assert(ContentSetScaffold.id_problem("ok_id", target_root) == "", "and an unused one is fine to use")
	_assert(ContentSetScaffold.id_problem("new_world", target_root) != "", "a taken one is a problem")


func _check_what_it_says_is_still_owed() -> void:
	print("\n[what a copied ruleset leaves behind]")
	# The fixture's ruleset asks for nothing and names nothing, so a created set
	# owes nothing.
	_assert(Array(create_result.get("notes", [])).is_empty(),
		"a source with no region policy leaves no notes: %s" % str(create_result.get("notes", [])))

	# fantasy_frontier's ruleset requires every mapped hazard to appear in some room,
	# AND names ninety of its own items, quests and NPCs. A scaffold cannot invent
	# either, so it says what it knows and the engine says the rest.
	var fantasy := repo_root.path_join("content_sets").path_join("fantasy_frontier")
	if not DirAccess.dir_exists_absolute(fantasy):
		print("  SKIP fantasy_frontier is not beside this checkout")
		return
	var from_fantasy := ContentSetScaffold.create("hazard_notes", "Hazard Notes", fantasy, target_root, true)
	_assert(from_fantasy.get("ok", false),
		"a set copied from fantasy_frontier is created: %s" % str(from_fantasy.get("errors", [])))
	var notes: Array = from_fantasy.get("notes", [])
	_assert(notes.size() == 1, "with one note about what is left to do: %s" % str(notes))
	_assert(str(notes).contains("hazard"), "naming the requirement: %s" % str(notes))
	_assert(str(notes).contains("extreme_heat"),
		"and the hazards the set it came from defines, as a starting point: %s" % str(notes))

	# Required because the copied ruleset opts in: the starter region must carry the
	# classification and band that policy demands, or the set would not load at all.
	var region := _read_json(str(from_fantasy.get("path", "")).path_join("data/regions/hazard_notes.json"))
	var properties: Dictionary = region.get("properties", {})
	_assert(str(properties.get("biome", "")) != "", "the starter region is classified: %s" % str(properties))
	_assert(str(properties.get("region_type", "")) != "", "with a region type too")
	_assert(typeof(properties.get("level_band")) == TYPE_DICTIONARY, "and a level band")

	# The measurement that decided the default: a ruleset is a list of references
	# into the world it was written for. Every error the engine reports about this
	# set must be one of those references (or a directory the named capability
	# needs) -- never a structural problem with what the scaffold itself wrote.
	var verdict := EngineValidator.run(str(from_fantasy.get("path", "")), repo_root, python_exe)
	if not verdict.get("ran", false):
		print("  SKIP the validator could not run: %s" % str(verdict.get("error", "")))
		return
	var structural: Array = []
	var reference_errors := 0
	for issue in verdict.get("issues", []):
		if str(issue.get("severity", "")) != "error":
			continue
		var message := str(issue.get("message", ""))
		if message.contains("references missing") or message.contains("references a missing") \
		or message.contains("is not an item family") or message.contains("missing required data directory") \
		or message.contains("hazard") or message.contains("elements.json"):
			reference_errors += 1
		else:
			structural.append("%s: %s" % [str(issue.get("path", "")), message])
	_assert(structural.is_empty(),
		"every engine error is a reference into the world it was copied from, not a broken write: %s"
			% str(structural))
	_assert(reference_errors > 0, "and there are some, which is what the dialog warns about: %d" % reference_errors)
	_assert(not verdict.get("ok", false),
		"so the set is honestly not loadable yet, rather than passing on a technicality")


## The other half of the rules choice: with the placeholder ruleset the same source
## produces a set that validates, because nothing in it names a world it does not
## have. This is why `copy_rules` defaults off.
func _check_the_default_rules_choice_validates() -> void:
	print("\n[the default: rules that declare nothing]")
	var fantasy := repo_root.path_join("content_sets").path_join("fantasy_frontier")
	if not DirAccess.dir_exists_absolute(fantasy):
		print("  SKIP fantasy_frontier is not beside this checkout")
		return
	var created_id := "empty_rules_world"
	var result := ContentSetScaffold.create(created_id, "Empty Rules World", fantasy, target_root, false)
	_assert(result.get("ok", false), "a set is created: %s" % str(result.get("errors", [])))

	var copied: Array = result.get("copied", [])
	for path in copied:
		_assert(not str(path).contains("/rules/"),
			"the source's rules were not copied (%s)" % str(path))
	var ruleset := _read_json(str(result.get("path", "")).path_join("rules/ruleset.json"))
	_assert(ruleset.get("ruleset_id") == created_id, "the placeholder ruleset names the new set")
	_assert(ruleset.size() == 2, "and declares nothing else: %s" % str(ruleset.keys()))

	var verdict := EngineValidator.run(str(result.get("path", "")), repo_root, python_exe)
	if not verdict.get("ran", false):
		print("  SKIP the validator could not run: %s" % str(verdict.get("error", "")))
		return
	var errors: Array = []
	for issue in verdict.get("issues", []):
		if str(issue.get("severity", "")) == "error":
			errors.append("%s: %s" % [str(issue.get("path", "")), str(issue.get("message", ""))])
	_assert(errors.is_empty(), "and the engine accepts it: %s" % str(errors))
	_assert(verdict.get("ok", false), "which is the whole point of the default")

	# And the region this mode writes is unclassified, because the ruleset that
	# would demand classification is not there. Nothing requires what it need not.
	var region := _read_json(str(result.get("path", "")).path_join("data/regions/empty_rules_world.json"))
	var properties: Dictionary = region.get("properties", {})
	_assert(properties.is_empty(),
		"a ruleset that demands no classification gets a plain region: %s" % str(properties))


# --- fixtures and helpers -----------------------------------------------------

## A minimal but *valid* content set: the manifest, a ruleset, a presentation, an
## opening scenario, and one region. Built by hand rather than scaffolded, so the
## thing under test is not also the fixture.
func _build_source_set() -> void:
	var data_root := source_set.path_join("data")
	for directory in ["regions", "items", "npcs"]:
		DirAccess.make_dir_recursive_absolute(data_root.path_join(directory))
	for directory in ["rules", "presentation", "opening"]:
		DirAccess.make_dir_recursive_absolute(source_set.path_join(directory))

	SaveIO.write_json(source_set.path_join("content_set.manifest.json"), {
		"id": "source_set", "title": "Source Set", "version": "0.1.0",
		"manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
		"paths": {
			"content_root": "data",
			"ruleset": "rules/ruleset.json",
			"presentation": "presentation/default.json",
			"opening": "opening/arrival.json",
		},
		"start": {"scenario_id": "arrival", "region_id": "source_region", "room_id": "start"},
		"capabilities": ["inventory", "crafting"],
	})
	SaveIO.write_json(source_set.path_join("rules/ruleset.json"), {
		"ruleset_id": "source_set", "label": "Source Set rules",
	})
	SaveIO.write_json(source_set.path_join("presentation/default.json"), {
		"presentation_id": "source_set", "display_name": "Source Set",
	})
	SaveIO.write_json(source_set.path_join("opening/arrival.json"), {
		"scenario_id": "arrival", "heading": "Arrival",
		"intro": "A fixture opening. Its text belongs to the set it came from.",
	})
	SaveIO.write_json(data_root.path_join("regions/source_region.json"), {
		"region_id": "source_region", "name": "Source Region",
		"rooms": {"start": {"name": "Source Start", "exits": {}}},
	})


## Every file under `root`, relative to it, with its contents.
func _snapshot(root: String) -> Dictionary:
	var out := {}
	for relative in _relative_files(root):
		out[relative] = FileAccess.get_file_as_string(root.path_join(relative))
	return out


func _relative_files(root: String) -> Array:
	var out: Array = []
	_collect_files(root, "", out)
	out.sort()
	return out


func _collect_files(root: String, relative: String, out: Array) -> void:
	var directory := DirAccess.open(root)
	if directory == null:
		return
	directory.list_dir_begin()
	var name := directory.get_next()
	while name != "":
		if name.begins_with("."):
			name = directory.get_next()
			continue
		var child := relative.path_join(name) if relative != "" else name
		if directory.current_is_dir():
			_collect_files(root.path_join(name), child, out)
		else:
			out.append(child)
		name = directory.get_next()
	directory.list_dir_end()


func _read_json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var payload = JSON.parse_string(FileAccess.get_file_as_string(path))
	return payload if typeof(payload) == TYPE_DICTIONARY else {}


func _python_from_args() -> String:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--python="):
			return argument.trim_prefix("--python=")
	var args := OS.get_cmdline_user_args()
	for index in range(args.size() - 1):
		if args[index] == "--python":
			return args[index + 1]
	return ""


func _probe_python() -> String:
	for candidate in ["python3", "python", "py"]:
		var output: Array = []
		if OS.execute(candidate, ["--version"], output, true) == 0:
			return candidate
	return ""


func _remove_recursive(path: String) -> void:
	var directory := DirAccess.open(path)
	if directory == null:
		return
	directory.list_dir_begin()
	var name := directory.get_next()
	while name != "":
		var child := path.path_join(name)
		if directory.current_is_dir():
			_remove_recursive(child)
		else:
			DirAccess.remove_absolute(child)
		name = directory.get_next()
	directory.list_dir_end()
	# The directory itself goes too: this test asks whether an id is free by
	# whether its directory exists, so leaving an emptied tree behind makes the
	# second run fail on the first run's leftovers.
	DirAccess.remove_absolute(path)


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		printerr("  FAIL ", message)
