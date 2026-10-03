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

	scene.network_lifecycle._send_command_to_server("reply 1")
	await until(func(): return scene.typewriter.is_revealing(), 8.0)
	scene.typewriter.finish()
	scene.typewriter.enabled = false
	var before := log.get_total_character_count()
	scene.typewriter.append("[pace=20]a long and slow passage that would take a while to reveal[/pace]")
	check("with the switch off, paced text is shown at once", not scene.typewriter.is_revealing() and log.visible_characters == -1)
	check("and is in the log", log.get_total_character_count() > before)
