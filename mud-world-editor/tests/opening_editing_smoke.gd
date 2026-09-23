extends SceneTree

const DialogScript = preload("res://scripts/ui/modals/OpeningEditorDialog.gd")
var failures := 0
var fixture := ""

func _init(): _run.call_deferred()

func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/opening-editing-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture; DataRoot._source = "opening smoke"
	var path := fixture.path_join("opening/arrival_in_town.json")
	var before := FileAccess.get_file_as_string(path)
	var dialog = DialogScript.new(); root.add_child(dialog); dialog.setup(); dialog.open_active()
	_assert(dialog.draft != null and dialog.get_ok_button().disabled, "opening dialog loads clean")
	dialog.heading.text = "Welcome, edited"; dialog._mark_dirty(); _assert(not dialog.get_ok_button().disabled, "editing opening prose enables Save")
	dialog._save()
	var written = JSON.parse_string(FileAccess.get_file_as_string(path))
	_assert(str(written.get("heading", "")) == "Welcome, edited", "the edited heading is saved")
	_assert(str(written.get("scenario_id", "")) == "arrival_in_town", "scenario identity is preserved")
	_assert(FileAccess.file_exists(path + ".bak") and FileAccess.get_file_as_string(path + ".bak") == before, "the opening keeps a recovery backup")
	dialog.open_active(); _assert(dialog.get_ok_button().disabled, "reopening a saved opening is clean")
	_remove_recursive(fixture)
	if failures > 0: push_error("opening editing smoke failed (%d)" % failures); quit(1)
	else: print("opening editing smoke passed"); quit(0)

func _copy(from: String, to: String):
	DirAccess.make_dir_recursive_absolute(to); var dir := DirAccess.open(from); if dir == null: return
	dir.list_dir_begin(); var name := dir.get_next()
	while name != "":
		if not name in [".", ".."]:
			if dir.current_is_dir(): _copy(from.path_join(name), to.path_join(name))
			else: DirAccess.copy_absolute(from.path_join(name), to.path_join(name))
		name = dir.get_next()
	dir.list_dir_end()

func _remove_recursive(path: String):
	var dir := DirAccess.open(path); if dir == null: return
	dir.list_dir_begin(); var name := dir.get_next()
	while name != "":
		if not name in [".", ".."]:
			var child := path.path_join(name)
			if dir.current_is_dir(): _remove_recursive(child)
			else: DirAccess.remove_absolute(child)
		name = dir.get_next()
	dir.list_dir_end(); DirAccess.remove_absolute(path)

func _assert(condition: bool, message: String):
	if condition: print("  ok: ", message)
	else: failures += 1; push_error("FAIL: " + message)
