# tests/quest_inspector_smoke.gd
#
# The quest surface must write what the engine reads.
#
# The inspector it replaces wrote `{id, description, type: "KILL", target, count,
# next}` while the engine routes `stage.objective.type` and reads stage order
# from the list. A stage authored that way passed content validation with zero
# errors and could never be completed. Run with:
#
#   godot --headless --path mud-world-editor --script tests/quest_inspector_smoke.gd
#
# The last check is the one that matters: after adding a stage through the
# inspector, the *engine's own validator* is run over the fixture. Anything this
# editor writes that the game cannot load fails here.

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
	content_set_root = ProjectSettings.globalize_path("res://").path_join("../tmp/quest_inspector/content_set")
	data_root = content_set_root.path_join("data")
	python_exe = _python_from_args()
	if python_exe == "":
		python_exe = _probe_python()
	_build_fixture()
	DataRoot._resolved = content_set_root
	DataRoot._source = "test fixture"

	_check_existing_stage_is_left_alone()
	_check_a_new_stage_uses_the_engine_schema()
	_check_stage_order_and_index()
	_check_unmodelled_keys_survive()
	_check_choice_outcomes()
	_check_schema_vocabulary()

	if python_exe != "":
		_check_the_engine_accepts_what_this_wrote()
	else:
		print("\n[engine validation]")
		print("  skip  no Python interpreter found; pass --python <path>")

	if failure_count > 0:
		push_error("quest inspector smoke failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- cases -------------------------------------------------------------------

func _check_existing_stage_is_left_alone() -> void:
	print("\n[an existing stage]")
	var data := _quest_data()
	var stage: Dictionary = data["stages"][0]
	_assert(stage.has("objective"), "the fixture stage starts with an objective")
	_assert(not stage.has("type"), "and no stage-level `type`")

	var inspector := _inspector(data)
	_assert(stage.has("objective"), "rendering it does not replace the objective")
	_assert(str(stage["objective"].get("type", "")) == "deliver", "with a different type")
	_assert(stage.has("turn_in_id"), "and the turn-in survives rendering")
	_assert(stage.has("completion_dialogue"), "as does the completion dialogue")
	_free_holders()


func _check_a_new_stage_uses_the_engine_schema() -> void:
	print("\n[a stage added here]")
	var data := _quest_data()
	var inspector := _inspector(data)
	inspector._add_stage()

	var stages: Array = data["stages"]
	_assert(stages.size() == 2, "the stage is added")
	var stage: Dictionary = stages[1]
	_assert(stage.has("objective"), "the new stage has an objective")
	_assert(not stage.has("type"), "and no stage-level `type` the engine would ignore")
	_assert(not stage.has("target"), "and no `target`/`count`/`next` fields from the old shape")
	_assert(int(stage.get("stage_index", -1)) == 1, "its index is its position")
	_assert(QuestSchema.has_type(str(stage["objective"].get("type", ""))),
		"and its objective type is one the engine routes")
	_free_holders()


func _check_stage_order_and_index() -> void:
	print("\n[stage order]")
	var data := _quest_data()
	var inspector := _inspector(data)
	inspector._add_stage()
	inspector._add_stage()
	data["stages"][0]["description"] = "first"
	data["stages"][2]["description"] = "last"

	inspector._move_stage(0, 1)
	_assert(data["stages"][0]["description"] == "", "moving reorders the list")
	_assert(data["stages"][1]["description"] == "first", "the moved stage landed where it was sent")
	_assert(data["stages"][1]["stage_index"] == 1, "and its index was renumbered to match")

	inspector._remove_stage(0)
	_assert(data["stages"].size() == 2, "removing drops one stage")
	_assert(data["stages"][0]["stage_index"] == 0 and data["stages"][1]["stage_index"] == 1,
		"and the remaining stages are renumbered from zero")
	_free_holders()


func _check_unmodelled_keys_survive() -> void:
	print("\n[keys this inspector does not model]")
	var data := _quest_data()
	var stage: Dictionary = data["stages"][0]
	stage["start_dialogue"] = "Said when the stage begins."
	stage["_spawn_on_entry_triggered"] = true
	stage["some_future_field"] = {"a": 1}

	var inspector := _inspector(data)
	inspector._add_stage()
	_assert(stage.get("start_dialogue", "") == "Said when the stage begins.",
		"an authored stage field survives")
	_assert(stage.get("_spawn_on_entry_triggered", false) == true,
		"the engine's own runtime bookkeeping survives")
	_assert(stage.get("some_future_field", {}) == {"a": 1},
		"and a field neither side knows about is kept, not dropped")
	_free_holders()


func _check_choice_outcomes() -> void:
	print("\n[negotiation outcomes]")
	var data := _quest_data()
	data["stages"].append({
		"stage_index": 1,
		"description": "Talk them down",
		"objective": {
			"type": "negotiate",
			"target_npc_id": "quest_giver",
			"skill": "persuasion",
			"difficulty": 12,
			"choices": {"peaceful": {"complete": true}, "rough": {"next_stage": 0}},
		},
	})
	var inspector := _inspector(data)
	var objective: Dictionary = data["stages"][1]["objective"]
	_assert(QuestSchema.authored_fields("negotiate").has("choices"), "choices is a field of negotiate")
	var extras := QuestSchema.extra_keys(objective)
	_assert(extras.is_empty(), "and a well-formed negotiate objective has nothing unmodelled: %s" % str(extras))
	_free_holders()


func _check_schema_vocabulary() -> void:
	print("\n[the schema itself]")
	var types := QuestSchema.type_ids()
	for expected in ["kill", "fetch", "deliver", "scout", "negotiate", "relationship", "discover_n", "craft_quality", "gather_types", "clear_region", "escort"]:
		_assert(types.has(expected), "the engine's `%s` objective is offered" % expected)
	_assert(QuestSchema.authored_fields("kill").has("target_template_id"),
		"kill names the field the tracker reads")
	_assert(QuestSchema.authored_fields("gather_types").has("required_item_ids"),
		"gather_types names the field the validator reads")
	_assert(QuestSchema.is_runtime_key("current_quantity"), "runtime fields are known to be runtime")
	_assert(not QuestSchema.extra_keys({"type": "kill", "target_template_id": "wolf"}).has("target_template_id"),
		"a modelled field is not reported as an extra")
	_assert(QuestSchema.extra_keys({"type": "kill", "mystery": 1}) == ["mystery"],
		"an unmodelled field is")


# The proof: everything written above is handed to the engine's validator.
func _check_the_engine_accepts_what_this_wrote() -> void:
	print("\n[the engine's verdict]")
	var data := DatabaseManager.new()
	data.load_all()
	var quest_id: String = str(data.quests.keys()[0])
	var quest: Dictionary = data.quests[quest_id]
	var inspector := _inspector_on(quest)
	inspector._add_stage()
	# Give the new stage a complete objective, the way an author would.
	quest["stages"][1]["objective"] = {"type": "kill", "target_template_id": "quest_giver", "required_quantity": 1}
	var saved := data.save_all()
	_assert(saved.get("ok", false), "the quest saves: %s" % str(saved.get("errors", [])))
	_free_holders()

	var result := EngineValidator.run(content_set_root, repo_root, python_exe)
	_assert(result.get("ran", false), "the validator runs: %s" % result.get("error", ""))
	var quest_errors: Array = []
	for issue in result.get("issues", []):
		if str(issue.get("path", "")).contains("quests"):
			quest_errors.append(issue)
	_assert(quest_errors.is_empty(),
		"a stage authored here validates: %s" % str(quest_errors))
	_assert(result.get("ok", false), "and the content set as a whole passes: %s" % str(result.get("issues", [])))


# --- fixture -----------------------------------------------------------------

func _quest_data() -> Dictionary:
	return {
		"title": "A Small Errand",
		"type": "deliver",
		"description": "Take the probe to the giver.",
		"stages": [{
			"stage_index": 0,
			"description": "Hand it over.",
			"objective": {
				"type": "deliver",
				"item_template_id": "item_probe",
				"recipient_template_id": "quest_giver",
				"recipient_name": "The Giver",
			},
			"turn_in_id": "quest_giver",
			"completion_dialogue": "Thank you.",
		}],
		"rewards": {"xp": 10, "gold": 5},
	}


func _inspector(data: Dictionary) -> QuestInspector:
	return _inspector_on(data)


func _inspector_on(data: Dictionary) -> QuestInspector:
	# The inspector is a Control-building helper: give it a container and let it
	# render, exactly as the Content Library does.
	var holder := VBoxContainer.new()
	root.add_child(holder)
	holders.append(holder)
	var inspector := QuestInspector.new(holder, DatabaseManager.new(), null)
	inspector.build("quest_fixture", data)
	return inspector


# The inspector is RefCounted; what it built are Controls under `root`.
func _free_holders() -> void:
	for holder in holders:
		if is_instance_valid(holder):
			holder.queue_free()
	holders.clear()


func _build_fixture() -> void:
	_remove_recursive(content_set_root)
	DirAccess.make_dir_recursive_absolute(data_root.path_join("items"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("npcs"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("regions"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("quests"))
	# A quests-capable set is required to have campaigns/ too (content_set.py).
	DirAccess.make_dir_recursive_absolute(data_root.path_join("campaigns"))
	DirAccess.make_dir_recursive_absolute(content_set_root.path_join("rules"))
	DirAccess.make_dir_recursive_absolute(content_set_root.path_join("presentation"))

	SaveIO.write_json(content_set_root.path_join("content_set.manifest.json"), {
		"id": "quest_fixture", "title": "Quest Fixture", "version": "0.1.0",
		"manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
		"paths": {
			"content_root": "data",
			"ruleset": "rules/ruleset.json",
			"presentation": "presentation/default.json",
		},
		"start": {"scenario_id": "fixture", "region_id": "fixture", "room_id": "start"},
		"capabilities": ["inventory", "quests"],
	})
	SaveIO.write_json(content_set_root.path_join("presentation/default.json"), {
		"presentation_id": "quest_fixture", "display_name": "Quest Fixture",
	})
	SaveIO.write_json(content_set_root.path_join("rules/ruleset.json"), {"ruleset_id": "quest_fixture"})
	SaveIO.write_json(data_root.path_join("regions/fixture.json"), {
		"region_id": "fixture", "rooms": {"start": {"name": "Start", "exits": {}}},
	})
	SaveIO.write_json(data_root.path_join("items/library.json"), {
		"item_probe": {"name": "probe", "type": "Item", "value": 5, "weight": 0.1},
	})
	SaveIO.write_json(data_root.path_join("npcs/people.json"), {
		"quest_giver": {"name": "The Giver", "health": 20, "friendly": true},
	})
	SaveIO.write_json(data_root.path_join("quests/quests.json"), {
		"quest_fixture": _quest_data(),
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
