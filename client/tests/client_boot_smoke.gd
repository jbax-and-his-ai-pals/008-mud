extends "res://tests/lib/live_test.gd"
## The client opens, shows the world, and is ready to type into.


func run() -> void:
	if not await boot():
		return
	var room_text := ""
	check("the room pane shows the room you are in", await until(func():
		room_text = scene.room_label.get_parsed_text()
		return room_text.contains("Exits") and not room_text.contains("Waiting for the room"), 15.0), room_text)
	check("the world panel shows the time", await until(func(): return _all_text(scene.docks.panels["world"]).contains("Day"), 10.0))
	check("the surroundings panel lists the exits", await until(func(): return _all_text(scene.docks.panels["surroundings"]).contains("Exits"), 10.0))
	check("the pack panel lists what you carry", await until(func(): return _all_text(scene.docks.panels["pack"]).contains("Slots"), 10.0))
	check("the abilities panel names the set's ability", await until(func(): return _all_text(scene.docks.panels["spells"]).contains("Gloom Wave"), 10.0))
	check("the command box has the focus without a click", await until(func(): return scene.command_input.has_focus(), 5.0), "focus is on %s" % str(root.gui_get_focus_owner()))

	var said := await say("look")
	check("a command typed in the box is answered in the log", said.length() > 0)
	scene.command_input.grab_focus()
	scene.command_input.text = "status"
	scene.command_input.text_submitted.emit("status")
	await wait(0.5)
	check("sending a command leaves the box empty and still focused", scene.command_input.text == "" and scene.command_input.has_focus(),
		"text='%s' focused=%s" % [scene.command_input.text, scene.command_input.has_focus()])
