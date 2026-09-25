# tests/dialog_fit_smoke.gd
#
# Every editor dialog opens at its content's size. An AcceptDialog grows to fit
# its content and never shrinks back, and a word-wrapped label measured before
# it has a width asks for one word per line: the content-set chooser opened
# 2,154 px tall, New content set 6,829, Edit Contracts 6,319, Combat Vocabulary
# 6,272 and Feature Profile 1,874 -- off the bottom of an 800 px window, buttons
# and all. DialogStyle.fit_to_screen now sizes each dialog to its content once
# layout settles (and on a real screen clamps it and centres it); Combat
# Vocabulary's body scrolls because its content is taller than a screen.
#
#   godot --headless --path mud-world-editor --script tests/dialog_fit_smoke.gd

extends SceneTree

var main: Node2D
var started := false
var failures := 0


func _initialize() -> void:
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
	var openers := {
		"Open a content set": func(): ui.show_content_set_chooser(),
		"New content set": func(): ui.show_create_content_set(),
		"Ruleset": func(): ui.show_ruleset_editor(),
		"Manifest": func(): ui.show_manifest_editor(),
		"Opening": func(): ui.show_opening_editor(),
		"Contracts": func(): ui.show_contracts(),
		"Edit Contracts": func(): ui.show_contract_editor(),
		"Combat Vocabulary": func(): ui.show_combat_vocabulary_editor(),
		"Feature Profile": func(): ui.show_feature_profile_editor(),
		"Ambient Fields": func(): ui.show_field_interactions_editor(),
	}
	print("\n[each dialog opens at its content's size]")
	for label in openers:
		openers[label].call()
		for _i in 4: await process_frame
		var shown: Window = null
		for dialog in ui.ui_layer.find_children("*", "AcceptDialog", true, false):
			if dialog.visible and (shown == null or dialog.size.y > shown.size.y): shown = dialog
		if shown == null:
			_assert(false, "%s opened" % label); continue
		var wanted := shown.get_contents_minimum_size()
		_assert(shown.size.y <= maxf(wanted.y, float(shown.min_size.y)) + 24.0 and shown.size.y <= 720,
			"%s is %d px tall (its content needs %d)" % [label, shown.size.y, int(wanted.y)])
		shown.hide()
		await process_frame
	if failures > 0: push_error("dialog fit smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _assert(condition: bool, message: String) -> void:
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
