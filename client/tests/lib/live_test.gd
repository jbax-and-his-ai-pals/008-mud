extends SceneTree
## Shared scaffolding for the client's smoke checks (run by `run_client_checks.py`).
##
## A check extends this, overrides `run()` (it may `await`), and calls `check(label, condition)`.
## `boot()` opens the real main scene connected to the server the runner started (its port is in
## the CLIENT_TEST_PORT environment variable), creates a character and waits for the first panels.
## Lines print as `ok  ...` or `FAIL ...`; the exit code is 1 if anything failed or the check hung.

var scene: Node
var failures := 0
var checks := 0
const WATCHDOG_SECONDS := 100.0


func _initialize() -> void:
	create_timer(WATCHDOG_SECONDS).timeout.connect(func():
		print("FAIL the check did not finish within %d seconds" % int(WATCHDOG_SECONDS))
		quit(1))
	await run()
	finish()


func run() -> void:
	pass


func check(label: String, condition: bool, detail: String = "") -> void:
	checks += 1
	if condition:
		print("ok  %s" % label)
	else:
		failures += 1
		print("FAIL %s%s" % [label, ("  -- " + detail) if detail != "" else ""])


func finish() -> void:
	print("%d checks, %d failed" % [checks, failures])
	quit(1 if failures > 0 or checks == 0 else 0)


## Waits (a frame at a time) until `condition` holds; false when it did not within `seconds`.
func until(condition: Callable, seconds: float = 10.0) -> bool:
	var deadline := Time.get_ticks_msec() + int(seconds * 1000.0)
	while Time.get_ticks_msec() < deadline:
		if condition.call():
			return true
		await process_frame
	return bool(condition.call())


func wait(seconds: float) -> void:
	await create_timer(seconds).timeout


## Opens the game and makes a character; returns once the character panel has its name.
func boot(character: String = "Tester") -> bool:
	var port := int(OS.get_environment("CLIENT_TEST_PORT"))
	Engine.set_meta("launch_host", "127.0.0.1")
	Engine.set_meta("launch_port", port)
	Engine.set_meta("launch_mode", "offline")
	Engine.set_meta("launch_auto_connect", true)
	change_scene_to_file("res://scenes/main.tscn")
	if not await until(func(): return current_scene != null and current_scene.has_node("CharCreateOverlay"), 15.0):
		check("the main scene opened", false)
		return false
	scene = current_scene
	if not await until(func(): return scene.get("docks") != null and scene.get("network_lifecycle") != null, 15.0):
		check("the client set itself up", false)
		return false
	scene.get_node("CrashRecoveryOverlay").visible = false
	var base := "CharCreateOverlay/CenterContainer/Panel/VBox/"
	if not await until(func(): return scene.get_node(base + "ButtonRow/CreateButton").is_visible_in_tree(), 20.0):
		check("the character form appeared once connected", false)
		return false
	scene.get_node(base + "NameInput").text = character
	scene.get_node(base + "ButtonRow/CreateButton").pressed.emit()
	var named := await until(func(): return character in _all_text(scene.docks.panels["character"]), 20.0)
	check("a character was created and the character panel names it", named)
	return named


## The text of every label under `node`, joined.
func _all_text(node: Node) -> String:
	var text := ""
	if node is RichTextLabel:
		text += (node as RichTextLabel).get_parsed_text() + "\n"
	elif node is Label:
		text += (node as Label).text + "\n"
	for child in node.get_children():
		text += _all_text(child)
	return text


func log_text() -> String:
	return (scene.log_view as RichTextLabel).get_parsed_text()


## Sends a command as the player would and waits for the log to grow (the server answered).
func say(command: String, seconds: float = 6.0) -> String:
	var before := log_text().length()
	scene.network_lifecycle._send_command_to_server(command)
	await until(func(): return log_text().length() > before, seconds)
	return log_text().substr(before)
