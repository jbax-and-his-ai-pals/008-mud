extends "res://tests/lib/live_test.gd"
## A tester's row (Skip scene, a checkpoint picker and Go) appears only when the server says debug tools are on.


func _hello(debug_tools: Dictionary) -> void:
	scene._on_line_received(JSON.stringify({"type": "hello", "session_id": "", "payload": {"message": "connected", "debug_tools": debug_tools}}))


func _sent_line_count() -> int:
	return int(scene._network_telemetry.get("lines_sent", 0))


func run() -> void:
	if not await boot("Tester"):
		return
	check("a normal server shows no tester's row", scene.find_child("DebugTools", true, false) == null)

	_hello({"enabled": true, "checkpoints": [{"id": "king", "note": "in the throne room"}, {"id": "road", "note": "Kessa at your side"}]})
	var row := scene.find_child("DebugTools", true, false)
	check("a server with debug tools shows the row", row != null)
	var picker := scene.find_child("DebugCheckpoint", true, false) as OptionButton
	check("the picker lists the checkpoints by name", picker != null and picker.item_count == 2 and str(picker.get_item_metadata(0)) == "king" and str(picker.get_item_metadata(1)) == "road")
	check("with each note as its tooltip", picker != null and picker.get_item_tooltip(1) == "Kessa at your side")
	check("the row sits just above the command line", row != null and row.get_index() + 1 == scene.command_input.get_parent().get_index())

	var before := _sent_line_count()
	(scene.find_child("DebugSkipScene", true, false) as Button).pressed.emit()
	check("Skip scene sends a command", _sent_line_count() == before + 1)
	picker.select(1)
	(scene.find_child("DebugGo", true, false) as Button).pressed.emit()
	check("Go sends the chosen checkpoint", _sent_line_count() == before + 2)

	_hello({"enabled": true, "checkpoints": []})
	check("a set with no checkpoints has the skip button and a disabled Go", (scene.find_child("DebugGo", true, false) as Button).disabled and scene.find_child("DebugSkipScene", true, false) != null)
	_hello({"enabled": false})
	await process_frame
	check("and a hello that says debug is off takes the row away", scene.find_child("DebugTools", true, false) == null)
