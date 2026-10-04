extends "res://tests/lib/live_test.gd"
## The panels around the story: laid out by default, draggable, collapsible, remembered per character.
## And the bars that drain while an attack or an ability cools down.

var docks


func _ids(column: Control) -> Array:
	var ids := []
	for child in column.get_children():
		if child.get("panel_id") != null:
			ids.append(child.panel_id)
	return ids


func _saved() -> Dictionary:
	var parsed = JSON.parse_string(FileAccess.get_file_as_string("user://dock_layouts.json"))
	return parsed if parsed is Dictionary else {}


func run() -> void:
	if not await boot("Tester"):
		return
	docks = scene.docks

	docks.reset_layout()
	check("the default layout puts the character panels on the left", _ids(docks.left_column) == ["character", "attributes", "equipment", "spells", "skills"], str(_ids(docks.left_column)))
	check("and the world panels on the right", _ids(docks.right_column).slice(0, 4) == ["world", "surroundings", "pack", "quests"], str(_ids(docks.right_column)))
	var all_open := true
	for id in docks.panels:
		if docks.panels[id].collapsed:
			all_open = false
	check("every panel starts open", all_open)

	# collapse
	docks.panels["attributes"].set_collapsed(true, true)
	check("a collapsed panel is marked collapsed", docks.panels["attributes"].collapsed)
	check("and the layout is saved to disk", FileAccess.file_exists("user://dock_layouts.json"))
	docks.panels["attributes"].set_collapsed(false, true)

	# drag and drop: lift the Pack card and drop it at the top of the left dock
	var pack = docks.panels["pack"]
	var data = pack._get_drag_data(Vector2(40, 12))
	check("lifting a card starts a drag carrying that card", data is Dictionary and data.get("dock_panel") == pack)
	check("the left dock accepts it", docks.left_column._can_drop_data(Vector2(100, 1), data))
	docks.left_column._drop_data(Vector2(100, 1), data)
	docks.left_column.notification(Node.NOTIFICATION_DRAG_END)
	check("dropping it moves the card to the top of the left dock", pack.get_parent() == docks.left_column and _ids(docks.left_column)[0] == "pack", str(_ids(docks.left_column)))
	var saved_pack: Dictionary = {}
	for key in _saved():
		if _saved()[key] is Dictionary and _saved()[key].has("pack"):
			saved_pack = _saved()[key]["pack"]
	check("and the move is remembered", saved_pack.get("dock", "") == "left", str(saved_pack))
	var leftovers := 0
	for child in docks.left_column.get_children():
		if child.get("panel_id") == null:
			leftovers += 1
	check("the drop preview is gone once the drag ends", leftovers == 0, "%d stray children" % leftovers)

	# each character keeps their own layout
	docks.use_layout_for("test-server", "Alpha")
	docks.left_column.move_child(pack, 0)
	docks.save_layout()
	docks.use_layout_for("test-server", "Beta")
	check("a character met for the first time starts from the layout on screen", pack.get_parent() == docks.left_column)
	docks.reset_layout()
	check("and rearranging for them leaves the default order", pack.get_parent() == docks.right_column)
	docks.use_layout_for("test-server", "Alpha")
	check("another character's layout comes back when they do", pack.get_parent() == docks.left_column and _ids(docks.left_column)[0] == "pack", str(_ids(docks.left_column)))

	# cooldown bars
	scene._apply_cooldown({"duration": 3.0, "remaining": 3.0})
	await wait(1.2)
	check("the attack bar drains while the attack cools down", scene.attack_bar.value > 0.0 and scene.attack_bar.value < 1.0 and scene._attack_status.text != "Ready",
		"value %.2f status %s" % [scene.attack_bar.value, scene._attack_status.text])
	await wait(2.5)
	check("and is empty and says Ready when it is done", scene.attack_bar.value == 0.0 and scene._attack_status.text == "Ready",
		"value %.2f status %s" % [scene.attack_bar.value, scene._attack_status.text])

	check("the abilities panel has a bar for Gloom Wave", await until(func(): return docks._ability_rows.has("gloom_wave"), 10.0))
	docks.apply_cooldowns([{"id": "gloom_wave", "duration": 2.0, "remaining": 2.0}])
	await wait(0.8)
	var row: Dictionary = docks._ability_rows["gloom_wave"]
	check("an ability on cooldown shows a draining bar and its time", row["bar"].value > 0.0 and row["bar"].value < 1.0 and row["time"].text != "Ready",
		"value %.2f time %s" % [row["bar"].value, row["time"].text])
	await wait(1.6)
	check("and is ready again afterwards", row["bar"].value == 0.0 and row["time"].text == "Ready", "value %.2f time %s" % [row["bar"].value, row["time"].text])
