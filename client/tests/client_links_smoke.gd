extends "res://tests/lib/live_test.gd"
## Clicking a name in the text sends that command, apostrophes and all.


func run() -> void:
	if not await boot():
		return
	check("the pack lists the commander's seal as a link", await until(func(): return _all_text(scene.docks.panels["pack"]).contains("commander's seal"), 10.0))
	var before := log_text().length()
	scene._on_meta_clicked("cmd:" + "look commander's seal".replace("'", "%27"))
	var answered: bool = await until(func(): return log_text().length() > before, 6.0)
	var said := log_text().substr(before)
	check("clicking it sends the whole command and the game answers", answered and said.contains("look commander's seal"), said.left(200))
	check("and what comes back describes the seal", said.to_lower().contains("seal") and not said.contains("%27"), said.left(200))

	before = log_text().length()
	scene._on_meta_clicked("cmd:look king")
	await until(func(): return log_text().length() > before, 6.0)
	check("an ordinary link works the same way", log_text().substr(before).contains("look king"))
