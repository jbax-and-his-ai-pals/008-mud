# tests/spawner_inspector_smoke.gd
#
# The region spawner inspector (SpawnerInspector.gd) had no test, and its
# weight rows were handed a null refresh Callable (a lambda that captured
# itself before it was assigned): removing a creature changed the data, then
# errored and left the row on screen; re-picking a row's creature did the same.
# fantasy_frontier's swamp is the fixture (read only; nothing is saved).
#
#   godot --headless --path mud-world-editor --script tests/spawner_inspector_smoke.gd

extends SceneTree

var failures := 0


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	DataRoot._resolved = repo.path_join("content_sets/fantasy_frontier")
	DataRoot._source = "test fixture"
	var db := DatabaseManager.new()
	var region: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(DataRoot._resolved.path_join("data/regions/swamp.json")))
	var shipped: Dictionary = region["spawner"]["monster_types"].duplicate()
	var holder := VBoxContainer.new(); root.add_child(holder)
	var spawner := SpawnerInspector.new()
	spawner.build(holder, region, db)
	var modified := [0]
	spawner.data_modified.connect(func(): modified[0] += 1)

	print("\n[opening]")
	_assert(_rows(holder).size() == shipped.size(), "one row per creature (%d)" % _rows(holder).size())

	print("\n[removing a creature]")
	var slime := _row_for(holder, "slime")
	_x(slime).pressed.emit()
	_assert(not region["spawner"]["monster_types"].has("slime"), "the creature leaves the table")
	_assert(_row_for(holder, "slime") == null and _rows(holder).size() == shipped.size() - 1, "and its row leaves the screen at once")
	_assert(modified[0] == 1, "and the region is marked modified")

	print("\n[re-picking a row's creature]")
	var zombie := _row_for(holder, "zombie")
	var picker: OptionButton = zombie.get_child(0)
	var weight = region["spawner"]["monster_types"]["zombie"]
	for index in picker.item_count:
		if str(picker.get_item_metadata(index)) == "ghoul": picker.select(index); picker.item_selected.emit(index); break
	_assert(not region["spawner"]["monster_types"].has("zombie") and region["spawner"]["monster_types"].get("ghoul") == weight, "the row's weight moves to the new creature")
	_assert(_row_for(holder, "ghoul") != null and _row_for(holder, "zombie") == null, "and the list shows it")

	print("\n[adding]")
	var add: Button = null
	for node in holder.find_children("*", "Button", true, false):
		if str(node.text) == "Add Monster": add = node
	var add_picker: OptionButton = add.get_parent().get_child(0)
	for index in add_picker.item_count:
		if str(add_picker.get_item_metadata(index)) == "cave_bear": add_picker.select(index)
	add.pressed.emit()
	_assert(region["spawner"]["monster_types"].get("cave_bear") == 1.0 and _row_for(holder, "cave_bear") != null, "a picked creature is added at weight 1")
	(_row_for(holder, "cave_bear").get_child(1) as SpinBox).value = 6
	add.pressed.emit()
	_assert(region["spawner"]["monster_types"]["cave_bear"] == 6.0, "adding it again does not reset its weight")

	if failures > 0: push_error("spawner inspector smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


# The weight rows' inner HBoxContainers: [creature picker, weight, x].
func _rows(holder: Node) -> Array:
	var out: Array = []
	for node in holder.find_children("*", "HBoxContainer", true, false):
		if node.is_queued_for_deletion() or node.get_parent().is_queued_for_deletion(): continue
		if node.get_child_count() == 3 and node.get_child(0) is OptionButton and node.get_child(1) is SpinBox: out.append(node)
	return out


func _row_for(holder: Node, creature: String) -> Node:
	for row in _rows(holder):
		var picker: OptionButton = row.get_child(0)
		if str(picker.get_item_metadata(picker.selected)) == creature: return row
	return null


func _x(row: Node) -> Button:
	return row.get_child(2)


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
