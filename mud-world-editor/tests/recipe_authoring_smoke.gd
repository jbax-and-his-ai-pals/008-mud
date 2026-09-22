# tests/recipe_authoring_smoke.gd
#
# Recipes are authorable, and what the inspector writes is what the engine reads.
#
# `data/crafting/*.json` had no surface at all: the editor could edit the items a
# recipe consumes and produces but not the recipe, so the system that connects
# them was hand-written JSON only. Run with:
#
#   godot --headless --path mud-world-editor --script tests/recipe_authoring_smoke.gd
#
# The last check hands the saved recipe to the engine's validator, which resolves
# `result_item_id` and every `ingredients[].item_id` against real templates and
# checks quality-tier ids -- so a recipe authored here is one the game can load.

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
	content_set_root = ProjectSettings.globalize_path("res://").path_join("../tmp/recipe_authoring/content_set")
	data_root = content_set_root.path_join("data")
	python_exe = _python_from_args()
	if python_exe == "":
		python_exe = _probe_python()
	_build_fixture()
	DataRoot._resolved = content_set_root
	DataRoot._source = "test fixture"

	_check_recipes_load()
	_check_the_inspector_edits_the_engine_fields()
	_check_station_picker_uses_authored_stations()
	_check_ingredients_and_tiers_are_structural()
	_check_an_ingredient_can_name_a_rule()
	_check_a_new_recipe_is_usable()
	_check_unmodelled_keys_survive()

	if python_exe != "":
		_check_the_engine_accepts_what_this_wrote()
	else:
		print("\n[engine validation]")
		print("  skip  no Python interpreter found; pass --python <path>")

	if failure_count > 0:
		push_error("recipe authoring smoke failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- cases -------------------------------------------------------------------

func _check_recipes_load() -> void:
	print("\n[recipes load]")
	var database := DatabaseManager.new()
	_assert(database.recipes.has("fabricate_patch_kit"), "a recipe in data/crafting/ is loaded")
	_assert(database.get_recipe_ids().has("fabricate_patch_kit"), "and listed")
	_assert(database.dirty_flags.has("recipe"), "recipes have their own dirty state")


func _check_the_inspector_edits_the_engine_fields() -> void:
	print("\n[the inspector]")
	var database := DatabaseManager.new()
	var recipe: Dictionary = database.recipes["fabricate_patch_kit"]
	var holder := _inspector_for(recipe, database)

	# Drive the widgets the way the panel does: find the control by name and emit
	# its signal. A test that only called the setter would not prove the wiring.
	var fields := _line_edits(holder)
	_assert(not fields.is_empty(), "the inspector renders editable fields")
	var result_field: LineEdit = null
	for line in fields:
		if line.placeholder_text.begins_with("item template id this recipe makes"):
			result_field = line
			break
	_assert(result_field != null, "including the result item")
	if result_field != null:
		result_field.text_changed.emit("item_servo_cluster")
		_assert(str(recipe.get("result_item_id", "")) == "item_servo_cluster",
			"and edits write the engine's field: %s" % str(recipe.get("result_item_id", "")))


func _check_station_picker_uses_authored_stations() -> void:
	print("\n[crafting stations]")
	var database := DatabaseManager.new()
	var recipe: Dictionary = database.recipes["fabricate_patch_kit"]
	var holder := _inspector_for(recipe, database)
	var station_picker: OptionButton = null
	for picker in _option_buttons(holder):
		if picker.item_count > 1 and str(picker.get_item_metadata(1)) == "fabricator":
			station_picker = picker
			break
	_assert(station_picker != null, "the station control offers station types authored by item templates")
	if station_picker == null: return
	station_picker.item_selected.emit(1)
	_assert(str(recipe.get("station_required", "")) == "fabricator", "choosing a station writes its engine-facing type")
	station_picker.item_selected.emit(0)
	_assert(recipe.get("station_required") == null, "the first option restores handcrafting")


func _check_ingredients_and_tiers_are_structural() -> void:
	print("\n[ingredients and tiers]")
	var database := DatabaseManager.new()
	var recipe: Dictionary = database.recipes["fabricate_patch_kit"]
	recipe["ingredients"] = [{"item_id": "item_servo_cluster", "quantity": 1}]
	recipe["quality_tiers"] = [{"id": "field", "label": "Field", "min_crafts": 1, "value_multiplier": 1.0}]
	var holder := _inspector_for(recipe, database)

	var boxes := _vbox_children(holder)
	_assert(boxes.size() >= 3, "the inspector builds sections for ingredients, tiers and milestones")

	# The add buttons are the structural affordance; find them by label.
	var add_buttons := _buttons(holder)
	var labels: Array = []
	for button in add_buttons: labels.append(button.text)
	_assert(labels.has("+ Ingredient"), "there is an add-ingredient control: %s" % str(labels))
	_assert(labels.has("+ Tier"), "an add-tier control")
	_assert(labels.has("+ Milestone"), "and an add-milestone control")

	for button in add_buttons:
		if button.text == "+ Ingredient":
			button.pressed.emit()
	_assert(recipe["ingredients"].size() == 2, "adding an ingredient appends one")

	for button in add_buttons:
		if button.text == "+ Tier":
			button.pressed.emit()
	_assert(recipe["quality_tiers"].size() == 2, "adding a tier appends one")
	_assert(str(recipe["quality_tiers"][1].get("id", "")) != "", "with an id, so it is usable immediately")
	_assert(float(recipe["quality_tiers"][1].get("value_multiplier", 0.0)) == 1.0,
		"and a neutral value multiplier")


# An ingredient may name a rule -- a family, or a capability -- rather than one
# template. The picker writes exactly one reference, because the engine resolves
# `item_id` first and would silently ignore anything else on the same ingredient.
func _check_an_ingredient_can_name_a_rule() -> void:
	print("\n[ingredients that name a rule]")
	var database := DatabaseManager.new()
	_assert(database.catalog.capability_ids().has("crafting_material"),
		"the editor knows the capabilities this set declares: %s" % str(database.catalog.capability_ids()))

	var recipe: Dictionary = database.recipes["fabricate_patch_kit"]
	recipe["ingredients"] = [{"item_id": "item_servo_cluster", "quantity": 1}]
	var holder := _inspector_for(recipe, database)

	var pickers := _named(holder, "ReferenceKindPicker")
	_assert(pickers.size() == 1, "each ingredient row offers a reference kind: %d" % pickers.size())
	if pickers.is_empty():
		return
	var picker: OptionButton = pickers[0]
	_assert(picker.item_count == 3, "with the engine's three kinds")
	var labels: Array = []
	for index in range(picker.item_count): labels.append(picker.get_item_text(index))
	_assert(labels == ["item_id", "item_family", "capability"], "in the engine's resolution order: %s" % str(labels))
	_assert(picker.selected == 0, "defaulting to the kind the ingredient already uses")

	# A template id is not a family name, so switching kinds empties the field
	# rather than leaving a value that would save as an invalid reference.
	picker.item_selected.emit(1)
	var ingredient: Dictionary = recipe["ingredients"][0]
	_assert(not ingredient.has("item_id"), "switching the kind clears the kind it is no longer using")
	_assert(str(ingredient.get("item_family", "")) == "",
		"and does not carry a value the new kind does not know: %s" % str(ingredient))

	var fields := _line_edits(holder)
	var reference_field: LineEdit = null
	for line in fields:
		if line.placeholder_text.begins_with("item family"):
			reference_field = line
			break
	_assert(reference_field != null, "the field now asks for a family")
	if reference_field != null:
		reference_field.text_changed.emit("salvaged_part")
		_assert(str(ingredient.get("item_family", "")) == "salvaged_part",
			"which is what the editor writes: %s" % str(ingredient))

	ingredient["min_material_quality"] = 2
	database.mark_dirty("recipe", "fabricate_patch_kit")

	# A template reference is one exact thing, so a grade floor on it would be a
	# second, contradictory answer; switching back must take it with it.
	var pickers_after := _named(holder, "ReferenceKindPicker")
	_assert(pickers_after.size() == 1, "the row still has its picker")
	if not pickers_after.is_empty():
		pickers_after[0].item_selected.emit(0)
		_assert(not ingredient.has("min_material_quality"),
			"a grade floor goes away when the reference stops being a rule")
		ingredient["item_id"] = "item_servo_cluster"


func _check_a_new_recipe_is_usable() -> void:
	print("\n[a new recipe]")
	var database := DatabaseManager.new()
	database.add_recipe("new_recipe", {
		"name": "New recipe", "description": "Creates something.",
		"result_item_id": "", "result_quantity": 1, "station_required": null,
		"ingredients": [], "aliases": [],
	})
	_assert(database.recipes.has("new_recipe"), "it is added to the library")
	# An empty result is honest rather than a placeholder id the validator would
	# reject; the inspector shows it as an empty field to fill in.
	_assert(str(database.recipes["new_recipe"].get("result_item_id", "")) == "",
		"and starts without inventing a result item")


func _check_unmodelled_keys_survive() -> void:
	print("\n[keys the inspector does not model]")
	var database := DatabaseManager.new()
	var recipe: Dictionary = database.recipes["fabricate_patch_kit"]
	recipe["some_future_field"] = {"a": 1}
	var holder := _inspector_for(recipe, database)
	_assert(recipe.get("some_future_field", {}) == {"a": 1}, "an unmodelled recipe field is kept")
	var notes := _labels(holder)
	var mentioned := false
	for note in notes:
		if note.text.contains("some_future_field"): mentioned = true
	_assert(mentioned, "and named, so an author can see it is there")


# The proof: the engine resolves what the inspector wrote.
func _check_the_engine_accepts_what_this_wrote() -> void:
	print("\n[the engine's verdict]")
	var database := DatabaseManager.new()
	var recipe: Dictionary = database.recipes["fabricate_patch_kit"]
	recipe["result_item_id"] = "item_patch_kit"
	recipe["station_required"] = "fabricator"
	# One ingredient of each kind, so the validator is asked to resolve a
	# template, a family and a capability from the same recipe.
	recipe["ingredients"] = [
		{"item_id": "item_servo_cluster", "quantity": 2},
		{"item_family": "salvaged_part", "quantity": 1, "min_material_quality": 1},
		{"capability": "crafting_material", "quantity": 1},
	]
	recipe["quality_tiers"] = [
		{"id": "field", "label": "Field", "min_crafts": 1, "value_multiplier": 1.0},
		{"id": "clean", "label": "Clean", "min_crafts": 5, "value_multiplier": 1.4},
	]
	database.mark_dirty("recipe", "fabricate_patch_kit")
	var saved := database.save_all()
	_assert(saved.get("ok", false), "the edited recipe saves: %s" % str(saved.get("errors", [])))

	var result := EngineValidator.run(content_set_root, repo_root, python_exe)
	_assert(result.get("ran", false), "the validator runs: %s" % result.get("error", ""))
	# Errors only, and only for the files this check authored. The path filter used
	# to be the bare word "crafting", which also matched the skill audit's
	# `engine:crafting_manager` warning -- an accurate advisory about a set that
	# names a skill without declaring a level, and not this check's business.
	var recipe_errors: Array = []
	for issue in result.get("issues", []):
		if str(issue.get("severity", "")) != "error":
			continue
		if str(issue.get("path", "")).contains("crafting/"):
			recipe_errors.append(issue)
	_assert(recipe_errors.is_empty(), "a recipe edited here validates: %s" % str(recipe_errors))
	_assert(result.get("ok", false), "and the content set as a whole passes: %s" % str(result.get("issues", [])))


# --- helpers -----------------------------------------------------------------

func _inspector_for(recipe: Dictionary, database: DatabaseManager) -> VBoxContainer:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	holders.append(holder)
	var inspector := RecipeInspector.new(holder, database)
	inspector.build("probe_recipe", recipe)
	return holder


func _line_edits(node: Node) -> Array:
	var found: Array = []
	if node is LineEdit:
		found.append(node)
	for child in node.get_children():
		found.append_array(_line_edits(child))
	return found


func _buttons(node: Node) -> Array:
	var found: Array = []
	if node is Button:
		found.append(node)
	for child in node.get_children():
		found.append_array(_buttons(child))
	return found


# The reference-kind pickers. `_buttons` would find them too (`OptionButton`
# extends `Button`) but not the ones that are actually pickers.
func _option_buttons(node: Node) -> Array:
	var found: Array = []
	if node is OptionButton:
		found.append(node)
	for child in node.get_children():
		found.append_array(_option_buttons(child))
	return found


func _named(node: Node, wanted: String) -> Array:
	var found: Array = []
	if node.name == wanted:
		found.append(node)
	for child in node.get_children():
		found.append_array(_named(child, wanted))
	return found


func _labels(node: Node) -> Array:
	var found: Array = []
	if node is Label:
		found.append(node)
	for child in node.get_children():
		found.append_array(_labels(child))
	return found


func _vbox_children(node: Node) -> Array:
	var found: Array = []
	if node is VBoxContainer:
		found.append(node)
	for child in node.get_children():
		found.append_array(_vbox_children(child))
	return found


func _build_fixture() -> void:
	_remove_recursive(content_set_root)
	DirAccess.make_dir_recursive_absolute(data_root.path_join("items"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("npcs"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("regions"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("crafting"))
	DirAccess.make_dir_recursive_absolute(content_set_root.path_join("rules"))
	DirAccess.make_dir_recursive_absolute(content_set_root.path_join("presentation"))

	SaveIO.write_json(content_set_root.path_join("content_set.manifest.json"), {
		"id": "recipe_fixture", "title": "Recipe Fixture", "version": "0.1.0",
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
		"presentation_id": "recipe_fixture", "display_name": "Recipe Fixture",
	})
	SaveIO.write_json(content_set_root.path_join("rules/ruleset.json"), {"ruleset_id": "recipe_fixture"})
	SaveIO.write_json(data_root.path_join("regions/fixture.json"), {
		"region_id": "fixture", "rooms": {"start": {"name": "Start", "exits": {}}},
	})
	SaveIO.write_json(data_root.path_join("items/components.json"), {
		"item_servo_cluster": {
			"name": "servo cluster", "type": "Junk", "value": 20, "weight": 0.5,
			"item_family": "salvaged_part",
		},
		"item_cell_stack": {
			"name": "cell stack", "type": "Junk", "value": 40, "weight": 0.9,
			"item_family": "salvaged_part",
		},
	})
	SaveIO.write_json(data_root.path_join("items/supplies.json"), {
		"item_patch_kit": {"name": "patch kit", "type": "Consumable", "value": 30, "weight": 0.4},
		"item_field_fabricator": {"name": "field fabricator", "type": "Interactive", "properties": {"crafting_station_type": "fabricator"}},
	})
	DirAccess.make_dir_recursive_absolute(data_root.path_join("contracts"))
	SaveIO.write_json(data_root.path_join("contracts/world_contracts.json"), {
		"schema_version": 1,
		"label": "Recipe fixture contracts",
		"item_families": [
			{
				"id": "salvaged_part", "label": "salvaged part", "item_class": "Junk",
				"capabilities": ["crafting_material"],
			},
		],
	})
	SaveIO.write_json(data_root.path_join("crafting/fabrication.json"), {
		"_comment": "kept",
		"fabricate_patch_kit": {
			"name": "Fabricate Patch Kit",
			"aliases": ["patch kit", "kit"],
			"description": "Pack sealant and gauze into something you can carry.",
			"result_item_id": "item_patch_kit",
			"result_quantity": 1,
			"station_required": null,
			"ingredients": [
				{"item_id": "item_servo_cluster", "quantity": 1},
				{"item_id": "item_cell_stack", "quantity": 1},
			],
			"quality_tiers": [
				{"id": "field", "label": "Field", "min_crafts": 1, "value_multiplier": 1.0},
			],
			"familiarity_milestones": [
				{"count": 1, "label": "Rough hands", "message": "Your first kit is ugly and probably works."},
			],
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
