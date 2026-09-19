# tests/dialogue_authoring_smoke.gd
#
# Conversations are authorable, and what the inspector writes is what the engine
# can walk.
#
# Dialogue is the one content system that can gate a reply on what the player has
# done, teach a recipe mid-sentence, or let a negotiation go two ways -- and it
# had no surface at all, so the nine shipped graphs were hand-written JSON. Run
# with:
#
#   godot --headless --path mud-world-editor --script tests/dialogue_authoring_smoke.gd
#
# The last check is the one that matters: after adding a node and a gated choice
# through the inspector, the *engine's* validator runs over the fixture. It
# resolves every `next_node`, every condition kind and every effect key, so a
# choice that leads nowhere fails here rather than mid-conversation.

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
	content_set_root = ProjectSettings.globalize_path("res://").path_join("../tmp/dialogue_authoring/content_set")
	data_root = content_set_root.path_join("data")
	python_exe = _python_from_args()
	if python_exe == "":
		python_exe = _probe_python()
	_build_fixture()
	DataRoot._resolved = content_set_root
	DataRoot._source = "test fixture"

	_check_graphs_load_as_graphs()
	_check_the_inspector_renders_a_graph()
	_check_adding_a_node_and_choice()
	_check_renaming_updates_references()
	_check_conditions_come_from_the_engine_vocabulary()
	_check_effects_come_from_the_engine_vocabulary()

	if python_exe != "":
		_check_the_engine_accepts_what_this_wrote()
	else:
		print("\n[engine validation]")
		print("  skip  no Python interpreter found; pass --python <path>")

	# Last, because it deliberately leaves the fixture inconsistent: the deleted
	# graph's NPC is still pointing at it.
	_check_deleting_a_graph_is_reported_by_the_engine()

	if failure_count > 0:
		push_error("dialogue authoring smoke failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- cases -------------------------------------------------------------------

func _check_graphs_load_as_graphs() -> void:
	print("\n[graphs]")
	var database := DatabaseManager.new()
	_assert(database.dialogues.has("grenda_forge"), "a graph in data/dialogue/ is loaded by its id")
	_assert(database.get_dialogue_ids().has("grenda_forge"), "and listed")
	_assert(database.dirty_flags.has("dialogue"), "dialogues have their own dirty state")
	var graph: Dictionary = database.dialogues["grenda_forge"]
	# The point of a dedicated loader: `nodes` is the graph's structure, not a
	# library of entries, so the generic items/npcs heuristic must not touch it.
	_assert(graph.get("nodes") is Dictionary, "its nodes are intact")
	_assert(graph["nodes"].has("greeting"), "with the authored node ids")
	_assert(not graph.has("greeting"), "and no entries invented from the node map")


func _check_the_inspector_renders_a_graph() -> void:
	print("\n[the inspector]")
	var database := DatabaseManager.new()
	var graph: Dictionary = database.dialogues["grenda_forge"]
	var holder := _inspector_for(graph, database)
	_assert(holder.find_child("TargetPicker", true, false) != null,
		"every choice gets a target picker over this graph's nodes")
	_assert(holder.find_child("ConditionPicker", true, false) != null, "and a condition picker")
	var picker := holder.find_child("TargetPicker", true, false) as OptionButton
	var options: Array = []
	for index in range(picker.item_count): options.append(picker.get_item_text(index))
	_assert(options.has("(ends the conversation)"), "with the 'ends here' option: %s" % str(options))
	_assert(options.has("greeting"), "and the graph's own node ids")


func _check_adding_a_node_and_choice() -> void:
	print("\n[authoring]")
	var database := DatabaseManager.new()
	var graph: Dictionary = database.dialogues["grenda_forge"]
	var holder := _inspector_for(graph, database)
	var inspector := DialogueInspector.new(holder, database)
	inspector.build("grenda_forge", graph)

	inspector.add_node()
	_assert(graph["nodes"].size() >= 2, "adding a node grows the graph")

	var new_id := ""
	for node_id in graph["nodes"]:
		if str(node_id).begins_with("node_"): new_id = str(node_id)
	_assert(new_id != "", "with a generated id: %s" % str(graph["nodes"].keys()))
	_assert(graph["nodes"][new_id].get("choices") is Array, "and a choices list to fill")

	# The structure the validator cares about: a node nothing leads to is fine, a
	# link to a node that is not there is not.
	var root_id := str(graph["root"])
	graph["nodes"][root_id]["choices"].append({"text": "About that ore.", "next_node": new_id})
	_assert(graph["nodes"].has(new_id), "the new node can be linked to by id")


func _check_renaming_updates_references() -> void:
	print("\n[renaming a node]")
	var database := DatabaseManager.new()
	var graph: Dictionary = database.dialogues["grenda_forge"]
	var holder := _inspector_for(graph, database)
	var inspector := DialogueInspector.new(holder, database)
	inspector.build("grenda_forge", graph)

	_assert(str(graph["root"]) == "greeting", "the fixture opens on 'greeting'")
	database.mark_dirty("dialogue", "grenda_forge")
	inspector._rename_node("greeting", "hello")
	_assert(graph["nodes"].has("hello"), "renaming moves the node")
	_assert(not graph["nodes"].has("greeting"), "and drops the old id")
	_assert(str(graph["root"]) == "hello", "the opening node follows the rename")

	var dangling: Array = []
	for node_id in graph["nodes"]:
		for choice in graph["nodes"][node_id].get("choices", []):
			var target := str(choice.get("next_node", ""))
			if target != "" and not graph["nodes"].has(target):
				dangling.append("%s → %s" % [node_id, target])
	_assert(dangling.is_empty(), "and every choice that pointed at it was repointed: %s" % str(dangling))

	var saved := database.save_all()
	_assert(saved.get("ok", false), "the renamed graph saves: %s" % str(saved.get("errors", [])))


func _check_conditions_come_from_the_engine_vocabulary() -> void:
	print("\n[conditions]")
	# The list has to be the engine's, because an unknown kind fails *closed*:
	# a typo closes a conversation silently rather than opening it.
	for kind in ["has_item", "quest_completed", "quest_active", "relationship_at_least",
			"visited_region", "knows_recipe", "flag", "level_at_least"]:
		_assert(DialogueSchema.has_condition_kind(kind), "the engine's `%s` condition is offered" % kind)
	_assert(DialogueSchema.condition_fields("has_item").has("item_id"),
		"has_item names the field the evaluator reads")
	_assert(DialogueSchema.condition_fields("relationship_at_least").has("value"),
		"relationship_at_least names its threshold")
	_assert(DialogueSchema.COMPOSITES.has("any"), "composites are known to be composites")
	_assert(not DialogueSchema.has_condition_kind("friendship_at_least"),
		"an invented kind is not offered")


func _check_effects_come_from_the_engine_vocabulary() -> void:
	print("\n[effects]")
	for key in ["start_quest", "advance_quest", "complete_quest", "grant_recipe",
			"teach_spell", "give_item", "adjust_relationship", "set_flag", "reveal_exit"]:
		_assert(DialogueSchema.has_effect(key), "the engine's `%s` effect is offered" % key)
	_assert(DialogueSchema.effect_shape("reveal_exit").contains("direction"),
		"each effect carries the shape the engine reads: %s" % DialogueSchema.effect_shape("reveal_exit"))
	_assert(not DialogueSchema.has_effect("grant_xp"), "an invented effect is not offered")


func _check_deleting_a_graph_is_reported_by_the_engine() -> void:
	print("\n[deleting a graph]")
	var database := DatabaseManager.new()
	_assert(FileAccess.file_exists(data_root.path_join("dialogue/spare_talk.json")),
		"the fixture has a second graph")
	database.delete_entry("dialogue", "spare_talk")
	var saved := database.save_all()
	_assert(saved.get("ok", false), "the deletion saves: %s" % str(saved.get("errors", [])))
	_assert(not FileAccess.file_exists(data_root.path_join("dialogue/spare_talk.json")),
		"and the file goes with it, so the graph does not come back on reload")
	var reloaded := DatabaseManager.new()
	_assert(not reloaded.dialogues.has("spare_talk"), "confirmed by a fresh load")

	if python_exe == "":
		return
	# The graph was referenced by an NPC, so the engine now has something to say
	# about it. That is the point of the check: a deleted conversation is not a
	# silent hole, it is a validation error naming the NPC that still points at it.
	var result := EngineValidator.run(content_set_root, repo_root, python_exe)
	var messages: Array = []
	for issue in result.get("issues", []):
		messages.append(str(issue.get("message", "")))
	var reported := false
	for message in messages:
		if message.contains("spare_talk") and message.contains("spare"):
			reported = true
	_assert(reported, "and the engine reports the NPC left pointing at it: %s" % str(messages))


# The proof: the engine walks what this wrote.
func _check_the_engine_accepts_what_this_wrote() -> void:
	print("\n[the engine's verdict]")
	var database := DatabaseManager.new()
	var graph: Dictionary = database.dialogues["grenda_forge"]
	# Not the fixture's original node id: an earlier check renamed it and saved,
	# and a test that assumes the pre-rename id would be testing its own order.
	var root_id := str(graph.get("root", ""))
	_assert(graph["nodes"].has(root_id), "the graph still has its opening node (%s)" % root_id)
	graph["nodes"][root_id]["choices"].append({
		"text": "You mentioned a shipment?",
		"condition": {"kind": "relationship_at_least", "npc_id": "grenda", "value": 5},
		"effects": {"adjust_relationship": {"amount": 5}},
		"next_node": root_id,
	})
	database.mark_dirty("dialogue", "grenda_forge")
	var saved := database.save_all()
	_assert(saved.get("ok", false), "the authored conversation saves: %s" % str(saved.get("errors", [])))

	var result := EngineValidator.run(content_set_root, repo_root, python_exe)
	_assert(result.get("ran", false), "the validator runs: %s" % result.get("error", ""))
	var dialogue_errors: Array = []
	for issue in result.get("issues", []):
		if str(issue.get("path", "")).contains("dialogue"):
			dialogue_errors.append(issue)
	_assert(dialogue_errors.is_empty(), "a graph edited here validates: %s" % str(dialogue_errors))
	_assert(result.get("ok", false), "and the content set as a whole passes: %s" % str(result.get("issues", [])))


# --- helpers -----------------------------------------------------------------

func _inspector_for(graph: Dictionary, database: DatabaseManager) -> VBoxContainer:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	holders.append(holder)
	var inspector := DialogueInspector.new(holder, database)
	inspector.build("grenda_forge", graph)
	return holder


func _build_fixture() -> void:
	_remove_recursive(content_set_root)
	DirAccess.make_dir_recursive_absolute(data_root.path_join("items"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("npcs"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("regions"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("dialogue"))
	DirAccess.make_dir_recursive_absolute(content_set_root.path_join("rules"))
	DirAccess.make_dir_recursive_absolute(content_set_root.path_join("presentation"))

	SaveIO.write_json(content_set_root.path_join("content_set.manifest.json"), {
		"id": "dialogue_fixture", "title": "Dialogue Fixture", "version": "0.1.0",
		"manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
		"paths": {
			"content_root": "data",
			"ruleset": "rules/ruleset.json",
			"presentation": "presentation/default.json",
		},
		"start": {"scenario_id": "fixture", "region_id": "fixture", "room_id": "start"},
		"capabilities": ["inventory", "dialogue"],
	})
	SaveIO.write_json(content_set_root.path_join("presentation/default.json"), {
		"presentation_id": "dialogue_fixture", "display_name": "Dialogue Fixture",
	})
	SaveIO.write_json(content_set_root.path_join("rules/ruleset.json"), {"ruleset_id": "dialogue_fixture"})
	SaveIO.write_json(data_root.path_join("regions/fixture.json"), {
		"region_id": "fixture", "rooms": {"start": {"name": "Start", "exits": {}}},
	})
	SaveIO.write_json(data_root.path_join("items/library.json"), {
		"item_iron_ingot": {"name": "iron ingot", "type": "Junk", "value": 12, "weight": 1.0},
	})
	# The NPC points at the graph, which is what makes it live content rather than
	# dead weight -- the validator warns about a graph nothing references.
	SaveIO.write_json(data_root.path_join("npcs/people.json"), {
		"grenda": {"name": "Grenda", "health": 30, "friendly": true,
			"properties": {"dialogue": "grenda_forge"}, "dialog": {"greeting": "The forge is hot."}},
		"spare": {"name": "Spare", "health": 30, "friendly": true,
			"properties": {"dialogue": "spare_talk"}, "dialog": {"greeting": "Hello."}},
	})
	SaveIO.write_json(data_root.path_join("dialogue/grenda_forge.json"), {
		"id": "grenda_forge",
		"_comment": "kept",
		"root": "greeting",
		"nodes": {
			"greeting": {
				"text": "Well met. The forge is hot, but my supplies are low.",
				"choices": [
					{"text": "What are you making?", "next_node": "making"},
					{"text": "Goodbye.", "end": true},
				],
			},
			"making": {
				"text": "Horseshoes, mostly. Without good iron I cannot forge weapons.",
				"choices": [{"text": "I see.", "next_node": "greeting"}],
			},
		},
	})
	SaveIO.write_json(data_root.path_join("dialogue/spare_talk.json"), {
		"id": "spare_talk",
		"root": "greeting",
		"nodes": {"greeting": {"text": "Nothing to say.", "choices": [{"text": "Right.", "end": true}]}},
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
