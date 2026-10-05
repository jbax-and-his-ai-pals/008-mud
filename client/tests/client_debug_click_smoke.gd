extends "res://tests/lib/live_test.gd"
## The game view's buttons work when clicked with a mouse, not only when their signal is emitted. The client hands
## focus back to the command line whenever a button in the game view takes it, and Godot cancels a click whose button
## loses focus mid-press, so a button that takes focus never fires `pressed`. (Send, the tester's Skip scene and Go.)


func _hello(debug_tools: Dictionary) -> void:
	scene._on_line_received(JSON.stringify({"type": "hello", "session_id": "", "payload": {"message": "connected", "debug_tools": debug_tools}}))


## A real click: the mouse moves over the control, then goes down and up on it, a frame apart.
func _click(control: Control) -> void:
	var at := control.get_global_rect().get_center()
	var motion := InputEventMouseMotion.new()
	motion.position = at
	motion.global_position = at
	Input.parse_input_event(motion)
	await process_frame
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = pressed
		event.position = at
		event.global_position = at
		event.button_mask = MOUSE_BUTTON_MASK_LEFT if pressed else 0
		Input.parse_input_event(event)
		await process_frame
		await process_frame   # the deferred "give focus back to the command line" has run by now


func _lines() -> int:
	return int(scene._network_telemetry.get("lines_sent", 0))


func run() -> void:
	if not await boot("Clicker"):
		return
	scene.get_node("OnboardingOverlay").visible = false   # the first-run welcome covers the whole window
	scene.get_window().size = Vector2i(1280, 800)   # a headless window starts at 64x64, which lays nothing out
	await process_frame
	await process_frame
	_hello({"enabled": true, "checkpoints": [{"id": "king", "note": ""}, {"id": "road", "note": ""}]})
	await process_frame
	await process_frame
	var skip := scene.find_child("DebugSkipScene", true, false) as Button
	var go := scene.find_child("DebugGo", true, false) as Button
	var picker := scene.find_child("DebugCheckpoint", true, false) as OptionButton

	scene.command_input.text = "look"
	var before := _lines()
	await _click(scene.send_button)
	check("clicking Send sends what is typed", _lines() == before + 1, "lines %d -> %d" % [before, _lines()])
	check("and the command line has the focus again", scene.command_input.has_focus() or scene.get_viewport().gui_get_focus_owner() == null or scene.get_viewport().gui_get_focus_owner() == scene.command_input)

	before = _lines()
	await _click(skip)
	check("clicking Skip scene sends a command", _lines() == before + 1, "lines %d -> %d" % [before, _lines()])
	picker.select(1)
	before = _lines()
	await _click(go)
	check("clicking Go sends the chosen checkpoint", _lines() == before + 1, "lines %d -> %d" % [before, _lines()])
