# tests/item_authoring_smoke.gd
#
# The item inspector's salvage section, and what the engine makes of it.
#
# What a template breaks down into was, until now, hand-written JSON: the
# property is a nested object and the property editor only offers string,
# number, bool and equip-slot rows, so the eleven fantasy templates that say
# "leather, not iron" were the only ones that could say anything at all.
#
# Run with:
#
#   godot --headless --path mud-world-editor --script tests/item_authoring_smoke.gd -- --python <path>
#
# The last check hands the saved template to the engine's validator, so what the
# inspector wrote is resolved against the content set's real item ids and
# families.

extends SceneTree

const SaveIO = preload("res://scripts/data/SaveIO.gd")

var failure_count := 0
var repo_root: String = ""
var content_set_root: String = ""
var data_root: String = ""
var python_exe: String = ""
var holders: Array = []


func _init() -> void:
	repo_root = ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	content_set_root = ProjectSettings.globalize_path("res://").path_join("../tmp/item_authoring/content_set")
	data_root = content_set_root.path_join("data")
	python_exe = _python_from_args()
	if python_exe == "":
		python_exe = _probe_python()
	_build_fixture()
	DataRoot._resolved = content_set_root
	DataRoot._source = "test fixture"

	_check_items_load()
	_check_salvage_output_is_editable()
	_check_container_and_resource_node_authoring()
	_check_a_written_salvage_output_is_kept()

	if python_exe != "":
		_check_the_engine_accepts_what_this_wrote()
	else:
		print("\n[engine validation]")
		print("  skip  no Python interpreter found; pass --python <path>")

	if failure_count > 0:
		push_error("item authoring smoke failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- cases -------------------------------------------------------------------

func _check_items_load() -> void:
	print("\n[items load]")
	var database := DatabaseManager.new()
	_assert(database.items.has("item_lattice_shard"), "an item in data/items/ is loaded")
	_assert(database.catalog.has_family("salvaged_part"),
		"and the contracts the salvage editor offers come with it")


func _check_salvage_output_is_editable() -> void:
	print("\n[salvage output]")
	var database := DatabaseManager.new()
	var crystal: Dictionary = database.items["item_lattice_shard"]
	var holder := _inspector_for(crystal, database)

	# The switch is how an author says "this template answers for itself"; the
	# eleven fantasy templates that break the family rule are exactly this.
	var toggles := _check_boxes(holder)
	var found := false
	for box in toggles:
		if box.text == "declare its own output":
			found = true
			# Nothing authored yet, so no property should exist.
			_assert(not crystal.get("properties", {}).has("salvage_output"),
				"the switch starts off for a template that declares nothing")
			box.button_pressed = true
			box.toggled.emit(true)
	_assert(found, "the inspector offers a salvage output switch: %d toggles" % toggles.size())
	if not found:
		return
	_assert(crystal["properties"].has("salvage_output"),
		"turning it on is what writes the property")

	# And the reference itself is edited by name, not as JSON.
	var fields := _line_edits(holder)
	var picks: Array = []
	for line in fields:
		if line.placeholder_text.begins_with("item family") or line.placeholder_text.begins_with("item template"):
			picks.append(line)
	_assert(not picks.is_empty(), "the row asks what it breaks into: %d reference fields" % picks.size())
	if picks.is_empty():
		return
	picks[0].text_changed.emit("item_scrap_alloy")
	_assert(
		str(crystal["properties"]["salvage_output"].get("item_id", "")) == "item_scrap_alloy",
		"and writes the engine's field: %s" % str(crystal["properties"]["salvage_output"]),
	)

	# A family reference is the interesting case -- it reaches members the author
	# never listed -- so it has to be reachable from the kind picker. The item
	# inspector has other OptionButtons (the item class, the family, the roll
	# table), so this one is found by name.
	var pickers := _named(holder, "ReferenceKindPicker")
	_assert(not pickers.is_empty(), "with a kind picker")
	if pickers.is_empty():
		return
	var picker: OptionButton = pickers[0]
	var labels: Array = []
	for index in range(picker.item_count): labels.append(picker.get_item_text(index))
	_assert(labels == ["item_id", "item_family", "capability"],
		"offering the engine's three kinds in its resolution order: %s" % str(labels))

	# A template id is not a family name, so switching empties the field rather
	# than saving something the validator will reject.
	picker.item_selected.emit(1)
	var authored: Dictionary = crystal["properties"]["salvage_output"]
	_assert(not authored.has("item_id"), "switching kind clears the one it is no longer using")
	_assert(str(authored.get("item_family", "")) == "",
		"and does not carry a value the new kind does not know")


func _check_a_written_salvage_output_is_kept() -> void:
	print("\n[what the author wrote survives]")
	var database := DatabaseManager.new()
	var shard: Dictionary = database.items["item_lattice_shard"]
	var family := str(shard.get("item_family", ""))
	_assert(family != "", "the fixture template names a family")
	_assert(database.catalog.family_ids().has(family),
		"which the editor offers as a suggestion: %s" % str(database.catalog.family_ids()))


func _check_container_and_resource_node_authoring() -> void:
	print("\n[containers and gathering resources]")
	var database := DatabaseManager.new()
	var chest: Dictionary = database.items["item_field_chest"]
	var chest_holder := _inspector_for(chest, database)
	var node: Dictionary = database.items["item_ore_vein"]
	var node_holder := _inspector_for(node, database)
	var labels := _labels(chest_holder)
	var label_text: Array = []
	for label in labels: label_text.append(label.text)
	_assert(label_text.has("Starting contents"), "a container exposes its starting contents")
	var node_labels := _labels(node_holder)
	var node_text: Array = []
	for label in node_labels: node_text.append(label.text)
	_assert(node_text.has("Primary yield"), "a resource node exposes its primary yield")
	_assert(node_text.has("Alternate yields"), "and alternate yields")
	_assert(node_text.has("Material grade"), "with a structured material-grade control")
	_assert(node_text.has("Substitute resources"), "and a structured substitute-resource list")
	for button in _buttons(chest_holder):
		if button.text == "+ Item": button.pressed.emit()
	_assert(chest.get("properties", {}).get("contains", []).size() == 1, "adding a contained item writes the engine array")
	for button in _buttons(node_holder):
		if button.text == "+ Yield": button.pressed.emit()
	_assert(node.get("properties", {}).get("yield_table", []).size() == 1, "adding an alternate yield writes the engine array")


# The proof: the engine resolves what the inspector wrote.
func _check_the_engine_accepts_what_this_wrote() -> void:
	print("\n[the engine's verdict]")
	var database := DatabaseManager.new()
	var shard: Dictionary = database.items["item_lattice_shard"]
	shard["properties"]["salvage_output"] = {
		"item_family": "salvaged_part",
		"quantity_per_weight": 2.5,
	}
	database.mark_dirty("item", "item_lattice_shard")
	var saved := database.save_all()
	_assert(saved.get("ok", false), "the edited template saves: %s" % str(saved.get("errors", [])))

	var result := EngineValidator.run(content_set_root, repo_root, python_exe)
	_assert(result.get("ran", false), "the validator runs: %s" % result.get("error", ""))
	_assert(result.get("ok", false),
		"a template whose salvage output names a family validates: %s" % str(result.get("issues", [])))


# --- helpers -----------------------------------------------------------------

func _inspector_for(item: Dictionary, database: DatabaseManager) -> VBoxContainer:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	holders.append(holder)
	var inspector := ItemInspector.new()
	inspector.build(holder, item, database)
	return holder


func _line_edits(node: Node) -> Array:
	var found: Array = []
	if node is LineEdit:
		found.append(node)
	for child in node.get_children():
		found.append_array(_line_edits(child))
	return found


func _check_boxes(node: Node) -> Array:
	var found: Array = []
	if node is CheckBox:
		found.append(node)
	for child in node.get_children():
		found.append_array(_check_boxes(child))
	return found


func _buttons(node: Node) -> Array:
	var found: Array = []
	if node is Button: found.append(node)
	for child in node.get_children(): found.append_array(_buttons(child))
	return found


func _labels(node: Node) -> Array:
	var found: Array = []
	if node is Label: found.append(node)
	for child in node.get_children(): found.append_array(_labels(child))
	return found


func _named(node: Node, wanted: String) -> Array:
	var found: Array = []
	if node.name == wanted:
		found.append(node)
	for child in node.get_children():
		found.append_array(_named(child, wanted))
	return found


func _option_buttons(node: Node) -> Array:
	var found: Array = []
	if node is OptionButton:
		found.append(node)
	for child in node.get_children():
		found.append_array(_option_buttons(child))
	return found


func _build_fixture() -> void:
	_remove_recursive(content_set_root)
	DirAccess.make_dir_recursive_absolute(data_root.path_join("items"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("npcs"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("regions"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("contracts"))
	DirAccess.make_dir_recursive_absolute(content_set_root.path_join("rules"))
	DirAccess.make_dir_recursive_absolute(content_set_root.path_join("presentation"))

	SaveIO.write_json(content_set_root.path_join("content_set.manifest.json"), {
		"id": "item_fixture", "title": "Item Fixture", "version": "0.1.0",
		"manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
		"paths": {
			"content_root": "data",
			"ruleset": "rules/ruleset.json",
			"presentation": "presentation/default.json",
		},
		"start": {"scenario_id": "fixture", "region_id": "fixture", "room_id": "start"},
		"capabilities": ["inventory", "crafting"],
	})
	SaveIO.write_json(content_set_root.path_join("presentation/default.json"), {
		"presentation_id": "item_fixture", "display_name": "Item Fixture",
	})
	SaveIO.write_json(content_set_root.path_join("rules/ruleset.json"), {
		"crafting": {
			"salvage_rules": {
				"by_family": {"salvaged_part": {"item_id": "item_scrap_alloy"}},
				"default_item_id": "item_scrap_alloy",
			},
		},
	})
	SaveIO.write_json(data_root.path_join("regions/fixture.json"), {
		"region_id": "fixture", "rooms": {"start": {"name": "Start", "exits": {}}},
	})
	SaveIO.write_json(data_root.path_join("contracts/world_contracts.json"), {
		"schema_version": 1,
		"label": "Item fixture contracts",
		"item_families": [
			{
				"id": "salvaged_part", "label": "salvaged part", "item_class": "Junk",
				"capabilities": ["crafting_material"], "generation_profile": "salvage_grade",
			},
		],
		"generation_profiles": [
			{
				"id": "salvage_grade", "label": "Salvage grade", "item_family": "salvaged_part",
				"property_prefix": "component", "name_template": "{size} {quality} {base}",
			},
		],
	})
	SaveIO.write_json(data_root.path_join("items/components.json"), {
		"_comment": "kept",
		"item_scrap_alloy": {"name": "scrap alloy", "type": "Item", "value": 9, "weight": 0.4},
		"item_lattice_shard": {
			"name": "lattice shard", "type": "Item", "value": 210, "weight": 0.3,
			"item_family": "salvaged_part", "properties": {},
		},
		"item_field_chest": {
			"name": "field chest", "type": "Container", "value": 20, "weight": 4,
			"properties": {"capacity": 40, "locked": false, "is_open": true, "contains": []},
		},
		"item_ore_vein": {
			"name": "ore vein", "type": "ResourceNode", "properties": {
				"resource_item_id": "item_scrap_alloy", "charges": 3, "respawn_days": 1,
			},
		},
	})


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		var child := path.path_join(name)
		if dir.current_is_dir():
			_remove_recursive(child)
		else:
			DirAccess.remove_absolute(child)
		name = dir.get_next()
	dir.list_dir_end()
	DirAccess.remove_absolute(path)


func _python_from_args() -> String:
	var args := OS.get_cmdline_user_args()
	for index in range(args.size()):
		if args[index] == "--python" and index + 1 < args.size():
			return args[index + 1]
	return ""


func _probe_python() -> String:
	var candidates := [
		repo_root.path_join(".venv/Scripts/python.exe"),
		repo_root.path_join(".venv/bin/python"),
		repo_root.path_join(".conda/python.exe"),
		"python",
	]
	for candidate in candidates:
		if candidate == "python" or FileAccess.file_exists(candidate):
			return candidate
	return ""


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		push_error("FAIL: " + message)
