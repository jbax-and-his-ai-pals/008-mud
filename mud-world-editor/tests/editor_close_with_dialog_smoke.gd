# tests/editor_close_with_dialog_smoke.gd
#
# Closing the editor window while a dialog is open.
#
# With unsaved work, closing the window shows "Save and quit / Quit without
# saving / Keep editing" -- but only one exclusive dialog can be open, so with
# another one showing that prompt was refused ("the parent window already has
# another exclusive child") and the window simply would not close. Now open
# dialogs are put away first, keeping their unsaved form contents, and "Keep
# editing" brings them back as they were.
#
#   godot --headless --path mud-world-editor --script tests/editor_close_with_dialog_smoke.gd

extends SceneTree

var main: Node2D
var started := false
var failures := 0


func _initialize() -> void:
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var fixture := repo.path_join("tmp/close-with-dialog-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
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
	print("\n[closing the window with a dialog open and unsaved work]")
	ui.show_ruleset_editor()
	await process_frame
	var rules = ui.ruleset_editor
	var currency: LineEdit = rules.world_rules_section.controls["economy.currency_name"]
	currency.text = "crowns"; currency.text_changed.emit("crowns")
	_assert(rules.visible and main._has_unsaved_work(), "the Ruleset dialog is open with an unsaved edit")

	# What the OS close button delivers: the notification reaches the editor's
	# nodes, not its embedded dialogs.
	main.notification(Node.NOTIFICATION_WM_CLOSE_REQUEST)
	for _i in 3: await process_frame
	_assert(ui.quit_modal.visible, "the quit prompt is shown")
	_assert(not rules.visible, "the open dialog is put away so it can be")
	_assert(currency.text == "crowns" and ui.has_configuration_drafts(), "and its unsaved edit is kept, so Save and quit still saves it")

	print("\n[keep editing]")
	ui.quit_modal.hide(); ui.quit_modal.canceled.emit()
	for _i in 3: await process_frame
	_assert(rules.visible and currency.text == "crowns", "the dialog comes back as it was")
	_assert(not ui.quit_modal.visible, "and the quit prompt is gone")

	if failures > 0: push_error("editor close with dialog smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String) -> void:
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
