# tests/story_fields_authoring_smoke.gd
#
# The fields the story slice (ff4_slice) needed, each authorable in the editor and not only by hand:
#
#   * a conversation's alternate openings (`entries`) and a node that ends it (`end`);
#   * how fast a campaign transition's narrative is revealed (`pace`);
#   * the told moments before a stage's creature arrives (`spawn_on_start.intro`);
#   * how a summoned creature leaves (`properties.despawn_message`).
#
# Opening each panel writes nothing, an edit lands in the data as the engine reads it, a default is erased
# rather than written, and the engine's own validator accepts what was saved.
#
#   godot --headless --path mud-world-editor --script tests/story_fields_authoring_smoke.gd

extends SceneTree

const DIALOGUE := "ryn_summoner"
const CAMPAIGN := "the_package"
const QUEST := "quest_fog_drake"
const NPC := "titan_minion"

var failures := 0
var fixture := ""
var inspectors: Array = []


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/story-fields-%s/story_fixture" % Time.get_ticks_usec())
	_copy(repo.path_join("server/tests/sets/story_fixture"), fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "test fixture"

	_opening_writes_nothing()
	_dialogue_openings_and_ends()
	_campaign_pace()
	_arrival_beats()
	_departure_line()
	_the_engine_accepts_what_was_written(repo)

	if failures > 0: push_error("story fields authoring failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _file(kind: String, name: String) -> String:
	return DataRoot.content_dir(kind).path_join(name)


func _opening_writes_nothing() -> void:
	print("\n[opening writes nothing]")
	var paths := {
		"dialogue": _file("dialogue", DIALOGUE + ".json"), "campaign": _file("campaigns", CAMPAIGN + ".json"),
		"quest": _file("quests", "quests.json"), "npc": _file("npcs", "summons.json"),
	}
	var originals := {}
	for key in paths: originals[key] = FileAccess.get_file_as_string(paths[key])
	var manager := DatabaseManager.new()
	_open_dialogue(manager); _open_campaign(manager); _open_quest(manager); _open_npc(manager)
	manager.mark_dirty("dialogue", DIALOGUE); manager.mark_dirty("campaign", CAMPAIGN)
	manager.mark_dirty("quest", QUEST); manager.mark_dirty("npc", NPC)
	manager.save_all()
	for key in paths:
		_assert(FileAccess.get_file_as_string(paths[key]) == originals[key], "an unedited %s saves byte-identically" % key)


# --- dialogue ------------------------------------------------------------------

func _open_dialogue(manager: DatabaseManager) -> Node:
	var holder := VBoxContainer.new(); root.add_child(holder)
	var inspector := DialogueInspector.new(holder, manager); inspectors.append(inspector)
	inspector.build(DIALOGUE, manager.dialogues[DIALOGUE], manager)
	return holder


func _dialogue_openings_and_ends() -> void:
	print("\n[dialogue: alternate openings and a node that ends it]")
	var manager := DatabaseManager.new()
	var graph: Dictionary = manager.dialogues[DIALOGUE]
	var holder := _open_dialogue(manager)
	var entries: Array = graph["entries"]
	_assert(entries.size() == 2 and holder.find_child("Entries", true, false).get_child_count() == 2, "the graph's two openings are listed")
	_assert(str(entries[0]["node"]) == "relief", "in order")

	var first: OptionButton = holder.find_child("EntryNode", true, false)
	_assert(first.get_item_text(first.selected) == "relief", "each shows the node it says")
	var thanks_index := -1
	for i in range(first.item_count):
		if first.get_item_text(i) == "thanks": thanks_index = i
	first.select(thanks_index); first.item_selected.emit(thanks_index)
	_assert(entries[0]["node"] == "thanks", "choosing another node is written")

	holder.find_child("AddEntry", true, false).pressed.emit()
	_assert(graph["entries"].size() == 3 and graph["entries"][2].has("node") and not graph["entries"][2].has("condition"), "adding an opening appends one with no condition (always)")
	var removers := holder.find_children("RemoveEntry", "Button", true, false)
	removers[2].pressed.emit()
	_assert(graph["entries"].size() == 2, "and it can be removed")
	holder = _open_dialogue(manager)
	for _i in range(2):
		holder.find_children("RemoveEntry", "Button", true, false)[0].pressed.emit()
	_assert(not graph.has("entries"), "removing the last one erases the key, rather than leaving an empty list")

	# renaming a node updates an opening that points at it
	manager = DatabaseManager.new()
	graph = manager.dialogues[DIALOGUE]
	holder = _open_dialogue(manager)
	var card_name: LineEdit = null
	for field in holder.find_children("*", "LineEdit", true, false):
		if (field as LineEdit).text == "relief" and (field as LineEdit).tooltip_text.begins_with("Node id"): card_name = field
	card_name.text = "hand_in"; card_name.text_submitted.emit("hand_in")
	_assert(graph["entries"][0]["node"] == "hand_in" and graph["nodes"].has("hand_in"), "renaming a node moves the opening that points at it")

	# a node that ends the conversation
	manager = DatabaseManager.new()
	graph = manager.dialogues[DIALOGUE]
	holder = _open_dialogue(manager)
	var ends: Array = holder.find_children("EndsConversation", "CheckBox", true, false)
	var pressed := 0
	for box in ends:
		if (box as CheckBox).button_pressed: pressed += 1
	var expected := 0
	for node_id in graph["nodes"]:
		if graph["nodes"][node_id].get("end", false) == true: expected += 1
	_assert(ends.size() == graph["nodes"].size() and pressed == expected, "each node has the box, set where the file says it ends (%d of %d)" % [pressed, ends.size()])
	var greeting_box: CheckBox = null
	var order: Array = []
	for node_id in manager.dialogues[DIALOGUE]["nodes"]: order.append(node_id)
	var sorted_ids: Array = order.duplicate(); sorted_ids.sort()
	greeting_box = ends[sorted_ids.find("greeting")]
	greeting_box.button_pressed = true; greeting_box.toggled.emit(true)
	_assert(graph["nodes"]["greeting"].get("end") == true, "ticking it writes end: true on the node")
	greeting_box.button_pressed = false; greeting_box.toggled.emit(false)
	_assert(not graph["nodes"]["greeting"].has("end"), "and clearing it erases the key")
	manager.mark_dirty("dialogue", DIALOGUE)
	_assert(manager.save_all().get("ok", false), "the dialogue saves")


# --- campaign ------------------------------------------------------------------

func _open_campaign(manager: DatabaseManager) -> Node:
	var holder := VBoxContainer.new(); root.add_child(holder)
	var inspector := CampaignInspector.new(holder, manager); inspectors.append(inspector)
	inspector.build(CAMPAIGN, manager.campaigns[CAMPAIGN])
	return holder


func _campaign_pace() -> void:
	print("\n[campaign: how fast a transition's narrative is revealed]")
	var manager := DatabaseManager.new()
	var campaign: Dictionary = manager.campaigns[CAMPAIGN]
	var holder := _open_campaign(manager)
	var card: Node = holder.find_child("Node_deliver", true, false)
	var picker: OptionButton = card.find_child("NarrativePace", true, false)
	_assert(picker != null and picker.get_item_text(picker.selected).begins_with("Solemn"), "the transition shows the pace the file has")
	picker.select(0); picker.item_selected.emit(0)
	_assert(not campaign["nodes"]["deliver"]["transitions"][0].has("pace"), "Instant erases it")
	var brisk := -1
	for i in range(picker.item_count):
		if picker.get_item_text(i).begins_with("Brisk"): brisk = i
	picker.select(brisk); picker.item_selected.emit(brisk)
	_assert(campaign["nodes"]["deliver"]["transitions"][0].get("pace") == "brisk", "a named pace is written by name")
	# a transition with no pace opens on Instant and writes nothing
	var other: Node = holder.find_child("Node_orders", true, false)
	var other_picker: OptionButton = other.find_child("NarrativePace", true, false)
	_assert(other_picker.get_item_text(other_picker.selected) == "Instant" and not campaign["nodes"]["orders"]["transitions"][0].has("pace"), "one with none opens on Instant and stays that way")
	picker.select(3 if picker.item_count > 3 else 0); picker.item_selected.emit(picker.selected)
	manager.mark_dirty("campaign", CAMPAIGN)
	manager.save_all()


# --- quest ---------------------------------------------------------------------

func _open_quest(manager: DatabaseManager) -> Node:
	var holder := VBoxContainer.new(); root.add_child(holder)
	var inspector := QuestInspector.new(holder, manager, null); inspectors.append(inspector)
	inspector.build(QUEST, manager.quests[QUEST])
	return holder


func _arrival_beats() -> void:
	print("\n[quest: the beats before a creature arrives]")
	var manager := DatabaseManager.new()
	var stage: Dictionary = manager.quests[QUEST]["stages"][0]
	var spawn: Dictionary = stage["spawn_on_start"]
	var holder := _open_quest(manager)
	var rows := holder.find_children("Beat*", "HBoxContainer", true, false)
	_assert(rows.size() == (spawn["intro"] as Array).size(), "each beat the file has gets a row (%d)" % rows.size())
	var line: LineEdit = holder.find_child("SpawnOnStart", true, false)
	_assert(line != null and not line.text.contains("intro"), "the raw spawn line leaves the beats to their own rows (%s)" % (line.text if line != null else "no line"))

	var first_text: LineEdit = rows[0].find_child("Text", true, false)
	first_text.text = "The hum climbs."; first_text.text_changed.emit("The hum climbs.")
	_assert(spawn["intro"][0]["text"] == "The hum climbs.", "editing a beat's words is written")
	var after: SpinBox = rows[0].find_child("After", true, false)
	after.value = 4; after.value_changed.emit(4.0)
	_assert(spawn["intro"][0]["after"] == 4 and typeof(spawn["intro"][0]["after"]) == TYPE_INT, "the wait is written as a whole number: %s" % str(spawn["intro"][0]["after"]))
	var pace: OptionButton = rows[0].find_child("Pace", true, false)
	pace.select(0); pace.item_selected.emit(0)
	_assert(not spawn["intro"][0].has("pace"), "Instant erases a beat's pace")

	# editing the raw line must not lose the beats
	var typed := JSON.stringify({"template_id": "fog_drake", "region_id": "mistvale", "room_id": "village_square", "name_override": "Mist Drake"})
	line.text = typed; line.text_changed.emit(typed)
	_assert(spawn != stage["spawn_on_start"] and stage["spawn_on_start"].get("name_override") == "Mist Drake" and stage["spawn_on_start"].get("intro") is Array,
		"editing the spawn line keeps the beats")
	spawn = stage["spawn_on_start"]

	holder = _open_quest(manager)
	holder.find_child("AddBeat", true, false).pressed.emit()
	_assert((spawn["intro"] as Array).size() == 5 and spawn["intro"][4] == {"text": "", "after": 2}, "adding a beat appends an empty one two seconds on")
	holder.find_children("RemoveBeat", "Button", true, false)[4].pressed.emit()
	_assert((spawn["intro"] as Array).size() == 4, "and it can be removed")
	for _i in range(4):
		holder.find_children("RemoveBeat", "Button", true, false)[0].pressed.emit()
	_assert(not spawn.has("intro"), "removing the last beat erases the key")
	holder.find_child("AddBeat", true, false).pressed.emit()
	var beat_text: LineEdit = holder.find_children("Beat*", "HBoxContainer", true, false)[0].find_child("Text", true, false)
	beat_text.text = "The fog stirs."; beat_text.text_changed.emit("The fog stirs.")
	manager.mark_dirty("quest", QUEST)
	_assert(manager.save_all().get("ok", false), "the edited quest saves")


# --- npc -----------------------------------------------------------------------

func _open_npc(manager: DatabaseManager) -> Node:
	var holder := VBoxContainer.new(); root.add_child(holder)
	var inspector := DatabaseInspector.new(holder)
	inspector.set_db_manager(manager)
	inspector.build("npc", NPC, manager.npcs[NPC])
	return holder


func _departure_line() -> void:
	print("\n[npc: how a summoned creature leaves]")
	var manager := DatabaseManager.new()
	var properties: Dictionary = manager.npcs[NPC]["properties"]
	var holder := _open_npc(manager)
	var field: LineEdit = holder.find_child("DespawnMessage", true, false)
	_assert(field != null and field.text == str(properties["despawn_message"]), "the field shows the line the file has")
	field.text = "The Titan returns below."; field.text_changed.emit("The Titan returns below.")
	_assert(properties["despawn_message"] == "The Titan returns below.", "editing it is written")
	field.text = ""; field.text_changed.emit("")
	_assert(not properties.has("despawn_message"), "clearing it erases the key (the engine's own line applies)")
	field.text = "The Titan sinks back into the earth."; field.text_changed.emit(field.text)
	manager.mark_dirty("npc", NPC)
	_assert(manager.save_all().get("ok", false), "the edited creature saves")


# --- the engine's verdict ----------------------------------------------------------

func _the_engine_accepts_what_was_written(repo: String) -> void:
	print("\n[engine validation]")
	var output: Array = []
	var python := repo.path_join(".venv/Scripts/python.exe")
	if not FileAccess.file_exists(python): python = repo.path_join(".venv/bin/python")
	if not FileAccess.file_exists(python):
		print("  skip  no project Python interpreter found")
		return
	var code := OS.execute(python, [repo.path_join("toolkit/content_set_validator.py"), fixture], output, true)
	if code != 0: print("    validator: ", "\n".join(output).right(600))
	_assert(code == 0, "the engine's validator accepts what the panels wrote")


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
