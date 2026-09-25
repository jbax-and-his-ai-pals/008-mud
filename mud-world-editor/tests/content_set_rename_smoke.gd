# tests/content_set_rename_smoke.gd
#
# Renaming a content set from the editor, including the one that is open.
#
# The chooser listed sets by folder name and refused to rename the open set
# ("Switch to another one before renaming it"), though a title -- the name
# people actually mean -- can always change safely. Now the chooser shows
# "Title   (id)", Rename edits title and id together, and renaming the open set
# is allowed: a title-only change is a manifest write, and an id change asks
# about unsaved work, moves the folder and reopens the set from its new place.
#
# Runs on a scratch copy of orbital_salvage under tmp/ (the sets root is pointed
# there), and leaves the editor's remembered-set setting as it found it.
#
#   godot --headless --path mud-world-editor --script tests/content_set_rename_smoke.gd

extends SceneTree

var failures := 0
var sets_dir := ""
var main: Node2D
var started := false
var settings_path := ""
var previous_settings := ""
var had_settings := false


func _initialize() -> void:
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	sets_dir = repo.path_join("tmp/rename-smoke-%s" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/orbital_salvage"), sets_dir.path_join("orbital_salvage"))
	_copy(repo.path_join("content_sets/night_shift"), sets_dir.path_join("night_shift"))
	ContentSetScaffold.sets_root_override = sets_dir
	settings_path = ProjectSettings.globalize_path("user://editor_settings.json")
	had_settings = FileAccess.file_exists(settings_path)
	if had_settings: previous_settings = FileAccess.get_file_as_string(settings_path)
	DataRoot._resolved = sets_dir.path_join("orbital_salvage")
	DataRoot._source = "test fixture"
	main = load("res://scenes/Main.tscn").instantiate()
	root.add_child(main)


func _process(_delta: float) -> bool:
	if started: return false
	started = true
	_run.call_deferred()
	return false


func _run() -> void:
	await process_frame
	var ui = main.ui_mgr
	var open_set := sets_dir.path_join("orbital_salvage")

	print("\n[the chooser shows titles]")
	var admin_title := str(ContentSetAdmin.identity(open_set).get("title", ""))
	_assert(admin_title != "", "the scratch set has a title (%s)" % admin_title)
	# The chooser lists sets beside the checkout plus registered ones; register
	# the scratch set the way "Add external content set..." does.
	DataRoot.register_content_set_root(open_set)
	var labels := _chooser_labels(ui)
	_assert(labels.has("Orbital Salvage   (orbital_salvage)"), "a shipped set is listed as \"Title   (id)\"")
	_assert(labels.any(func(l): return l.begins_with(admin_title + "   (orbital_salvage)") and l.ends_with("open now")), "the open set is listed by title, id and \"open now\": %s" % str(labels))

	print("\n[renaming another set, title and id together]")
	var other := sets_dir.path_join("night_shift")
	var moved: Dictionary = ContentSetAdmin.rename(other, "night_shift_b", sets_dir, "Night Shift B")
	_assert(moved.get("ok", false) and moved.get("moved", false), "a set that is not open moves: %s" % moved.get("error", ""))
	_assert(str(ContentSetAdmin.identity(sets_dir.path_join("night_shift_b")).get("title", "")) == "Night Shift B", "and takes its new title")
	var empty: Dictionary = ContentSetAdmin.rename(sets_dir.path_join("night_shift_b"), "night_shift_b", sets_dir, "  ")
	_assert(not empty.get("ok", true) and "title" in str(empty.get("error", "")), "an empty title is refused")

	print("\n[renaming the open set's title]")
	main._request_rename_open_content_set("orbital_salvage", "Orbital Salvage (renamed)")
	await process_frame
	_assert(DataRoot.root() == open_set, "a title-only change keeps the set where it is")
	_assert(str(ContentSetAdmin.identity(open_set).get("title", "")) == "Orbital Salvage (renamed)", "and writes the new title")

	print("\n[renaming the open set's id, with unsaved work]")
	main.region_mgr.mark_region_dirty()
	main._request_rename_open_content_set("orbital_renamed", "Orbital Salvage (renamed)")
	await process_frame
	_assert(ui.confirm_modal.visible, "the author is asked about unsaved work first")
	_assert(DirAccess.dir_exists_absolute(open_set), "and nothing has moved yet")
	ui.confirm_modal.custom_action.emit("extra")
	for _i in 3: await process_frame
	var renamed := sets_dir.path_join("orbital_renamed")
	_assert(not DirAccess.dir_exists_absolute(open_set) and DirAccess.dir_exists_absolute(renamed), "\"Rename without saving\" moves the folder")
	_assert(str(ContentSetAdmin.identity(renamed).get("id", "")) == "orbital_renamed", "and the manifest's id follows")
	_assert(DataRoot.root() == renamed, "the editor reopened the set from its new folder")
	_assert(not main.region_mgr.is_region_dirty, "with the unsaved edit left behind, as chosen")
	_assert(main.region_mgr.current_filename != "", "and a region loaded from it (%s)" % main.region_mgr.current_filename)
	var remembered := FileAccess.get_file_as_string(settings_path)
	_assert("orbital_renamed" in remembered, "the new location is what the next launch opens")

	_restore_settings()
	ContentSetScaffold.sets_root_override = ""
	if failures > 0: push_error("content set rename smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _chooser_labels(ui) -> Array:
	ui.show_content_set_chooser()
	var out: Array = []
	for i in ui.content_set_list.item_count: out.append(ui.content_set_list.get_item_text(i))
	ui.content_set_modal.hide()
	return out


func _restore_settings() -> void:
	if had_settings:
		var file := FileAccess.open(settings_path, FileAccess.WRITE)
		file.store_string(previous_settings); file.close()
	else:
		DirAccess.remove_absolute(settings_path)


func _copy(source: String, destination: String) -> void:
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String) -> void:
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
