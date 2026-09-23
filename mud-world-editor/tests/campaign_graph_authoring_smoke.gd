# tests/campaign_graph_authoring_smoke.gd
#
# A campaign's node graph was read-only. CampaignInspector now edits nodes
# (type, quest, outcome) and their ordered transitions. fantasy_frontier's
# bandit_rebellion is the fixture; the edited set is finally run through the
# engine's validator (content_set.py::_validate_campaigns).
#
#   godot --headless --path mud-world-editor --script tests/campaign_graph_authoring_smoke.gd

extends SceneTree

const CAMPAIGN := "bandit_rebellion"

var failures := 0
var fixture := ""
var inspectors: Array = []


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/campaign-graph-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "test fixture"
	var path := DataRoot.content_dir("campaigns").path_join(CAMPAIGN + ".json")
	var original := FileAccess.get_file_as_string(path)

	print("\n[opening the real graph]")
	var manager := DatabaseManager.new()
	var before := JSON.stringify(manager.campaigns[CAMPAIGN])
	var holder := _inspect(manager)
	_assert(JSON.stringify(manager.campaigns[CAMPAIGN]) == before, "building the graph editor writes nothing")
	_assert(holder.find_child("Node_confront_lieutenant", true, false) != null, "every node has a card")
	var lieutenant: Node = holder.find_child("Node_confront_lieutenant", true, false)
	_assert(_triggers(lieutenant) == ["VIOLENT_SUCCESS", "PEACEFUL_SUCCESS"], "a branching node shows its transitions in order")
	manager.mark_dirty("campaign", CAMPAIGN)
	manager.save_all()
	_assert(FileAccess.get_file_as_string(path) == original, "an unedited save is byte-identical")

	print("\n[editing]")
	manager = DatabaseManager.new()
	holder = _inspect(manager)
	var campaign: Dictionary = manager.campaigns[CAMPAIGN]
	var nodes: Dictionary = campaign["nodes"]

	var id_field: LineEdit = holder.find_child("Node_intro_investigation", true, false).find_child("NodeId", true, false)
	id_field.text = "scout_forest"; id_field.text_submitted.emit("scout_forest")
	_assert(nodes.has("scout_forest") and not nodes.has("intro_investigation"), "a node can be renamed")
	_assert(campaign["start_node_id"] == "scout_forest", "renaming the start node moves the start with it")

	lieutenant = holder.find_child("Node_confront_lieutenant", true, false)
	_button(lieutenant.find_child("Transition_1", true, false), "^").pressed.emit()
	_assert(nodes["confront_lieutenant"]["transitions"][0]["trigger"] == "PEACEFUL_SUCCESS", "transitions can be reordered (order decides which fires)")

	lieutenant = holder.find_child("Node_confront_lieutenant", true, false)
	var chance: SpinBox = lieutenant.find_child("Transition_0", true, false).find_child("Chance", true, false)
	chance.value = 0.4
	_assert(is_equal_approx(float(nodes["confront_lieutenant"]["transitions"][0]["chance"]), 0.4), "a transition's chance is written")

	_button(holder, "+ Node").pressed.emit()
	var new_id := "node_7"
	_assert(nodes.has(new_id) and nodes[new_id]["type"] == "END", "a new node starts as a valid END node")
	var new_card: Node = holder.find_child("Node_" + new_id, true, false)
	_edit(new_card.find_child("Outcome", true, false), "STALEMATE")
	_assert(nodes[new_id]["outcome"] == "STALEMATE", "its outcome is written")

	var envoy: Node = holder.find_child("Node_diplomatic_envoy", true, false)
	_button(envoy, "+ Transition").pressed.emit()
	envoy = holder.find_child("Node_diplomatic_envoy", true, false)
	var added: Node = envoy.find_child("Transition_1", true, false)
	_pick(added.find_child("Trigger", true, false), "VIOLENT_SUCCESS")
	_pick(added.find_child("Target", true, false), new_id)
	_assert(nodes["diplomatic_envoy"]["transitions"][1] == {"trigger": "VIOLENT_SUCCESS", "target_node_id": new_id, "narrative_text": ""}, "a transition can be added and pointed at the new node")
	# Behind the envoy's unconditional SUCCESS it could never fire (the engine
	# refuses that), so it moves ahead of it.
	_button(holder.find_child("Node_diplomatic_envoy", true, false).find_child("Transition_1", true, false), "^").pressed.emit()
	_assert(nodes["diplomatic_envoy"]["transitions"][0]["trigger"] == "VIOLENT_SUCCESS", "and moved ahead of the SUCCESS that would shadow it")

	print("\n[retyping and removing]")
	var war: Node = holder.find_child("Node_end_war", true, false)
	_pick(war.find_child("Type", true, false), "QUEST")
	_assert(not nodes["end_war"].has("outcome") and nodes["end_war"]["transitions"] == [], "retyping END to QUEST drops the outcome")
	war = holder.find_child("Node_end_war", true, false)
	_pick(war.find_child("Type", true, false), "END")
	_assert(nodes["end_war"]["outcome"] == "complete" and not nodes["end_war"].has("transitions"), "and back to END drops the transitions")
	_edit(holder.find_child("Node_end_war", true, false).find_child("Outcome", true, false), "TOTAL_VICTORY")

	manager.mark_dirty("campaign", CAMPAIGN)
	_assert(manager.save_all().get("ok", false), "the edited campaign saves")
	_assert(_engine_accepts(repo), "and the engine's validator accepts the edited graph")

	holder = _inspect(manager)
	_button(holder.find_child("Node_" + new_id, true, false), "Remove Node").pressed.emit()
	var dangling: OptionButton = holder.find_child("Node_diplomatic_envoy", true, false).find_child("Transition_0", true, false).find_child("Target", true, false)
	_assert(str(dangling.text).begins_with("Missing:"), "a transition to a removed node is shown as missing, not dropped")
	manager.mark_dirty("campaign", CAMPAIGN)
	manager.save_all()
	_assert(not _engine_accepts(repo), "and the engine refuses that graph until it is fixed")

	if failures > 0: push_error("campaign graph authoring failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _engine_accepts(repo: String) -> bool:
	var output: Array = []
	var python := repo.path_join(".venv/Scripts/python.exe")
	if not FileAccess.file_exists(python): python = repo.path_join(".venv/bin/python")
	var code := OS.execute(python, [repo.path_join("toolkit/content_set_validator.py"), fixture], output, true)
	if code != 0: print("    validator: ", "\n".join(output).right(400))
	return code == 0


func _inspect(manager: DatabaseManager) -> Node:
	var holder := VBoxContainer.new(); root.add_child(holder)
	var inspector := CampaignInspector.new(holder, manager); inspectors.append(inspector)
	inspector.build(CAMPAIGN, manager.campaigns[CAMPAIGN])
	return holder


func _triggers(card: Node) -> Array:
	var out: Array = []
	var index := 0
	while card.find_child("Transition_%d" % index, true, false) != null:
		var picker: OptionButton = card.find_child("Transition_%d" % index, true, false).find_child("Trigger", true, false)
		out.append(str(picker.get_item_metadata(picker.selected)))
		index += 1
	return out


func _pick(picker: OptionButton, value: String):
	for index in range(picker.item_count):
		if str(picker.get_item_metadata(index)) == value:
			picker.select(index); picker.item_selected.emit(index); return
	_assert(false, "picker offers '%s'" % value)


func _button(node: Node, text: String) -> Button:
	if node is Button and str(node.text) == text: return node
	for child in node.get_children():
		var found := _button(child, text)
		if found != null: return found
	return null


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _edit(field: LineEdit, value: String):
	field.text = value; field.text_changed.emit(value)


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
