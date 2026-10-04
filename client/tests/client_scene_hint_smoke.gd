extends "res://tests/lib/live_test.gd"
## While a scene plays the command line is muted and says so, and it goes back to normal when the scene ends.


func _scene(active: bool) -> void:
	scene._on_line_received(JSON.stringify({"type": "scene", "session_id": "", "payload": {"active": active, "hint": "A scene is playing. You can act again when it ends."}}))


func run() -> void:
	if not await boot("Tester"):
		return
	var input: LineEdit = scene.command_input
	var usual := input.placeholder_text
	check("the command line starts with its usual hint, fully visible", usual != "" and input.modulate.a == 1.0, usual)

	_scene(true)
	check("a scene mutes the command line", input.modulate.a < 1.0, str(input.modulate))
	check("and the hint says why", input.placeholder_text.begins_with("A scene is playing"), input.placeholder_text)
	check("but it is not disabled: reading still works", input.editable)

	_scene(true)
	check("a repeated message does not lose the original hint", input.placeholder_text.begins_with("A scene is playing"))

	_scene(false)
	check("when the scene ends the hint comes back", input.placeholder_text == usual, input.placeholder_text)
	check("and the line is fully visible again", input.modulate.a == 1.0, str(input.modulate))
