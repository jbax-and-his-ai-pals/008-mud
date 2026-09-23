# tests/presentation_editing_smoke.gd
#
# The presentation file's `theme_pack` is now sent to the client in `hello`;
# PresentationDialog (from the Manifest editor) picks it from this repository's
# client packs and saves through ConfigurationSave. fantasy_frontier's real file
# is the fixture.
#
#   godot --headless --path mud-world-editor --script tests/presentation_editing_smoke.gd

extends SceneTree

var failures := 0


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var fixture := repo.path_join("tmp/presentation-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	var path := PresentationDialog.presentation_path()
	var before: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))

	_assert(PresentationDialog.client_theme_ids().has("fantasy_classic"), "the client's packs are offered (%s)" % str(PresentationDialog.client_theme_ids()))
	var dialog := PresentationDialog.new(); root.add_child(dialog); dialog.setup(); dialog.open_active()
	_assert(QuestGenerationSection._picked(dialog.theme_pack) == "fantasy_classic", "the declared pack is selected")
	_assert(_same(dialog.compose(), before), "opening composes the file unchanged")
	_assert(dialog.get_ok_button().disabled, "Save starts disabled")

	_pick(dialog.theme_pack, "scifi_frontier")
	_assert(not dialog.get_ok_button().disabled, "choosing another pack enables Save")
	(dialog.flag_checks["reduced_motion_supported"] as CheckBox).button_pressed = false
	dialog.confirmed.emit()
	var after: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	_assert(after["theme_pack"] == "scifi_frontier", "the new pack was saved")
	_assert(after["accessibility"]["reduced_motion_supported"] == false, "the flag was saved")
	_assert(after["display_name"] == before["display_name"] and after["accessibility"]["alt_text_required"] == true, "untouched fields survive")
	_assert(not dialog.visible, "a successful save closes the dialog")

	dialog.open_active()
	_assert(not dialog._form_changed(), "reopen is clean")
	_pick(dialog.theme_pack, "")
	_assert(not dialog.compose().has("theme_pack"), "choosing the client default removes the key")

	dialog._allow_close = true; dialog.hide(); dialog.queue_free()
	if failures > 0: push_error("presentation editing failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _pick(picker: OptionButton, value: String):
	for index in range(picker.item_count):
		if str(picker.get_item_metadata(index)) == value:
			picker.select(index); picker.item_selected.emit(index); return
	_assert(false, "picker offers '%s'" % value)


func _same(a, b) -> bool:
	return JSON.stringify(SaveIO._normalize_numbers(a)) == JSON.stringify(SaveIO._normalize_numbers(b))


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
