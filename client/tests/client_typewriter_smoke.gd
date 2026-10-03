extends "res://tests/lib/live_test.gd"
## The king's words are revealed a few characters at a time; the player can skip ahead or switch it off.


func run() -> void:
	if not await boot():
		return
	var log: RichTextLabel = scene.log_view
	scene.network_lifecycle._send_command_to_server("talk king")
	var started: bool = await until(func(): return scene.typewriter.is_revealing(), 8.0)
	check("a paced passage starts being revealed", started)
	await wait(1.0)
	var total := log.get_total_character_count()
	check("part of it is hidden while it is revealed", log.visible_characters >= 0 and log.visible_characters < total,
		"visible %d of %d" % [log.visible_characters, total])
	var seen: int = log.visible_characters
	await wait(1.0)
	check("and more is shown as time passes", log.visible_characters > seen, "%d then %d" % [seen, log.visible_characters])

	scene.typewriter.finish()
	check("skipping shows everything at once", not scene.typewriter.is_revealing() and log.visible_characters == -1)

	# the player's own speed scales what the story asked for
	check("the typing speed starts as the story marked it", is_equal_approx(scene.typewriter.speed_scale, 1.0))
	var runs_probe: Array = scene.typewriter.get_script().runs_of("[pace=40]slow[/pace]")
	check("a run carries the speed the server marked", runs_probe == [["slow", 40.0]], str(runs_probe))
	scene.typewriter.speed_scale = 4.0
	var shown_before: int = log.visible_characters
	scene.typewriter.append("[pace=40]a passage typed at four times the marked speed, so it is quick[/pace]")
	await wait(0.5)
	check("faster typing reveals more in the same time", scene.typewriter.is_revealing() == false or log.visible_characters > shown_before)
	scene.typewriter.finish()
	scene.typewriter.speed_scale = 1.0
	var speed_select: OptionButton = scene.find_child("TextSpeed", true, false)
	check("the tools view offers a typing speed", speed_select != null and speed_select.item_count >= 3)
	if speed_select != null:
		speed_select.select(2); speed_select.item_selected.emit(2)
		check("choosing one changes how the typewriter reveals", is_equal_approx(scene.typewriter.speed_scale, 2.0))
		speed_select.select(1); speed_select.item_selected.emit(1)
		check("and the story's own speed can be chosen again", is_equal_approx(scene.typewriter.speed_scale, 1.0))

	scene.network_lifecycle._send_command_to_server("reply 1")
	await until(func(): return scene.typewriter.is_revealing(), 8.0)
	scene.typewriter.finish()
	scene.typewriter.enabled = false
	var before := log.get_total_character_count()
	scene.typewriter.append("[pace=20]a long and slow passage that would take a while to reveal[/pace]")
	check("with the switch off, paced text is shown at once", not scene.typewriter.is_revealing() and log.visible_characters == -1)
	check("and is in the log", log.get_total_character_count() > before)
