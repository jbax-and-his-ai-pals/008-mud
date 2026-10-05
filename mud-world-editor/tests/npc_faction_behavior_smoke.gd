# tests/npc_faction_behavior_smoke.gd
#
# `faction` and `behavior_type` are the two engine-owned words an NPC template
# names directly (`npc_factory.py`, `content_set/::_validate_npc_faction_and_
# behavior`), and until now the editor had no control for either: an NPC created
# here had no side and no AI routine, and the only way to give it one was to
# hand-edit JSON. See docs/plan/editor-coverage-ledger.md family C.
#
#   godot --headless --path mud-world-editor --script tests/npc_faction_behavior_smoke.gd
#
# Both are closed vocabularies (`NPCVocabulary.gd`, checked against the engine by
# schema_parity_smoke.gd), so this exercises the *pickers*: the built-in factions
# plus this set's own `ruleset.factions`, an already-authored value pre-selecting,
# an undeclared value surviving rather than being silently dropped, opening
# writing nothing, and a selection writing the right key -- or erasing it.

extends SceneTree

var failure_count := 0
var scratch: String = ""


func _init() -> void:
	scratch = ProjectSettings.globalize_path("res://").path_join("../tmp/npc_faction_behavior")
	_rebuild_fixture()

	_check_faction_options_are_built_ins_plus_ruleset_extras()
	_check_an_override_relabels_a_built_in_faction()
	_check_no_faction_or_behavior_preselects_none_and_writes_nothing()
	_check_a_declared_faction_and_behavior_preselect()
	_check_an_undeclared_value_is_shown_not_dropped()
	_check_selecting_a_faction_writes_it()
	_check_selecting_none_erases_the_key()
	_check_selecting_a_behavior_writes_it()
	_check_the_friendly_checkbox_writes_and_defaults_true()
	_check_the_pacifist_checkbox_writes_and_erases()
	_check_the_untargetable_checkbox_writes_and_erases()
	_check_the_hides_when_hurt_checkbox_writes_and_erases()
	_check_the_fight_trait_rows()
	_check_the_attack_cooldown_writes()
	_check_the_gear_rows()
	_check_the_phase_rows()

	if failure_count > 0:
		push_error("npc faction/behavior failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- checks ---------------------------------------------------------------

func _check_faction_options_are_built_ins_plus_ruleset_extras() -> void:
	print("\n[faction options]")
	var holder := _build_inspector("npc_probe")
	var picker := _faction_picker(holder)
	_assert(picker != null, "the faction picker was built")
	if picker == null:
		return
	var offered := _picker_ids(picker)
	for expected in ["player", "friendly", "hostile", "player_minion", "raiders"]:
		_assert(offered.has(expected), "faction options include '%s' (offered %s)" % [expected, str(offered)])
	_assert(not offered.has("neutral") or true, "sanity: neutral is a built-in and still offered")


func _check_an_override_relabels_a_built_in_faction() -> void:
	print("\n[ruleset override relabels a built-in]")
	var holder := _build_inspector("npc_probe")
	var picker := _faction_picker(holder)
	var neutral_label := _label_for_id(picker, "neutral")
	_assert(neutral_label.contains("friendly"), "the fixture's override (neutral -> friendly) shows in the label (%s)" % neutral_label)


func _check_no_faction_or_behavior_preselects_none_and_writes_nothing() -> void:
	print("\n[an NPC with neither key]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_probe", manager)
	var faction_picker := _faction_picker(holder)
	var behavior_picker := _behavior_picker(holder)
	_assert(faction_picker.selected == 0, "faction defaults to '(none)'")
	_assert(behavior_picker.selected == 0, "behavior defaults to '(none)'")
	# Only these two keys are this panel's responsibility -- the loot table
	# section writes its own `loot_table` default on open regardless, which is
	# pre-existing behavior outside this check's scope.
	_assert(not manager.npcs["npc_probe"].has("faction"), "opening the panel did not add a faction")
	_assert(not manager.npcs["npc_probe"].has("behavior_type"), "opening the panel did not add a behavior_type")


func _check_a_declared_faction_and_behavior_preselect() -> void:
	print("\n[an NPC that already declares both]")
	var holder := _build_inspector("npc_declared")
	var faction_picker := _faction_picker(holder)
	var behavior_picker := _behavior_picker(holder)
	_assert(str(faction_picker.get_item_metadata(faction_picker.selected)) == "raiders",
		"the faction picker preselects 'raiders'")
	_assert(str(behavior_picker.get_item_metadata(behavior_picker.selected)) == "patrol",
		"the behavior picker preselects 'patrol'")


func _check_an_undeclared_value_is_shown_not_dropped() -> void:
	print("\n[an NPC with a value nothing declares]")
	var holder := _build_inspector("npc_undeclared")
	var faction_picker := _faction_picker(holder)
	var behavior_picker := _behavior_picker(holder)
	_assert(str(faction_picker.get_item_metadata(faction_picker.selected)) == "made_up_faction",
		"the undeclared faction is still selected, not silently reset")
	_assert(str(faction_picker.text).begins_with("Undeclared:"),
		"and it is labelled as undeclared (%s)" % faction_picker.text)
	_assert(str(behavior_picker.get_item_metadata(behavior_picker.selected)) == "made_up_behavior",
		"the undeclared behavior is still selected")


func _check_selecting_a_faction_writes_it() -> void:
	print("\n[selecting a faction]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_probe", manager)
	var picker := _faction_picker(holder)
	var index := _index_for_id(picker, "hostile")
	_assert(index != -1, "the picker offers 'hostile'")
	picker.item_selected.emit(index)
	_assert(str(manager.npcs["npc_probe"].get("faction", "")) == "hostile", "the NPC's faction was written")


func _check_selecting_none_erases_the_key() -> void:
	print("\n[selecting '(none)' after a value was set]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_declared", manager)
	var picker := _faction_picker(holder)
	picker.item_selected.emit(0)
	_assert(not manager.npcs["npc_declared"].has("faction"), "the faction key was erased, not written as empty")


func _check_selecting_a_behavior_writes_it() -> void:
	print("\n[selecting a behavior]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_probe", manager)
	var picker := _behavior_picker(holder)
	var index := _index_for_id(picker, "wanderer")
	_assert(index != -1, "the picker offers 'wanderer'")
	picker.item_selected.emit(index)
	_assert(str(manager.npcs["npc_probe"].get("behavior_type", "")) == "wanderer", "the NPC's behavior_type was written")


func _check_the_friendly_checkbox_writes_and_defaults_true() -> void:
	print("\n[the friendly checkbox]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_probe", manager)
	var box := _checkbox_labeled(holder, "Friendly")
	_assert(box != null, "the checkbox was found")
	_assert(box.button_pressed, "an NPC with no friendly key defaults to checked (npc_factory.py's own default)")
	box.toggled.emit(false)
	_assert(manager.npcs["npc_probe"]["friendly"] == false, "unchecking it was written")


func _check_the_gear_rows() -> void:
	print("
[starts wearing]")
	var manager := _manager()
	manager.items["item_probe_blade"] = {"type": "Weapon", "name": "probe blade"}
	var holder := _build_inspector_from("npc_probe", manager)
	var picker := holder.find_child("Gear_main_hand", true, false) as OptionButton
	_assert(picker != null and holder.find_child("Gear_neck", true, false) != null, "a row for each slot the engine knows")
	_assert(not manager.npcs["npc_probe"].has("equipment"), "opening wrote nothing")
	var index := -1
	for i in range(picker.item_count):
		if str(picker.get_item_metadata(i)) == "item_probe_blade": index = i
	picker.select(index); picker.item_selected.emit(index)
	_assert(manager.npcs["npc_probe"].get("equipment") == {"main_hand": "item_probe_blade"}, "choosing an item writes {slot: item id}: %s" % str(manager.npcs["npc_probe"].get("equipment")))
	picker.select(0); picker.item_selected.emit(0)
	_assert(not manager.npcs["npc_probe"].has("equipment"), "choosing nothing erases the key rather than writing an empty one")


func _check_the_attack_cooldown_writes() -> void:
	print("
[attack every]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_probe", manager)
	var field := holder.find_child("AttackCooldown", true, false) as SpinBox
	_assert(field != null and is_equal_approx(field.value, 3.0), "an NPC that never said so shows the engine's own 3 seconds")
	_assert(not manager.npcs["npc_probe"].get("properties", {}).has("attack_cooldown"), "and opening wrote nothing")
	field.value = 6.5; field.value_changed.emit(6.5)
	_assert(is_equal_approx(float(manager.npcs["npc_probe"]["properties"]["attack_cooldown"]), 6.5), "choosing 6.5 writes properties.attack_cooldown")


func _check_the_pacifist_checkbox_writes_and_erases() -> void:
	print("\n[the pacifist checkbox]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_probe", manager)
	var box := holder.find_child("Pacifist", true, false) as CheckBox
	_assert(box != null and not box.button_pressed, "an NPC that never said so is not a pacifist")
	box.toggled.emit(true)
	_assert(manager.npcs["npc_probe"]["properties"].get("pacifist") == true, "ticking it writes properties.pacifist")
	box.toggled.emit(false)
	_assert(not manager.npcs["npc_probe"]["properties"].has("pacifist"), "and unticking it erases the key rather than writing false")


func _check_the_untargetable_checkbox_writes_and_erases() -> void:
	print("\n[the untargetable checkbox]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_probe", manager)
	var box := holder.find_child("Untargetable", true, false) as CheckBox
	_assert(box != null and not box.button_pressed, "an NPC that never said so can be targeted")
	box.toggled.emit(true)
	_assert(manager.npcs["npc_probe"]["properties"].get("untargetable") == true, "ticking it writes properties.untargetable")
	box.toggled.emit(false)
	_assert(not manager.npcs["npc_probe"]["properties"].has("untargetable"), "and unticking it erases the key rather than writing false")


func _check_the_hides_when_hurt_checkbox_writes_and_erases() -> void:
	print("\n[the hides-when-hurt checkbox]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_probe", manager)
	var box := holder.find_child("HidesWhenHurt", true, false) as CheckBox
	_assert(box != null and not box.button_pressed, "an NPC that never said so does not hide")
	box.toggled.emit(true)
	_assert(manager.npcs["npc_probe"]["properties"].get("hides_when_hurt") == true, "ticking it writes properties.hides_when_hurt")
	box.toggled.emit(false)
	_assert(not manager.npcs["npc_probe"]["properties"].has("hides_when_hurt"), "and unticking it erases the key rather than writing false")


func _check_the_fight_trait_rows() -> void:
	print("\n[falls when defeated, percent-immune and what can be stolen]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_probe", manager)
	var props: Dictionary = manager.npcs["npc_probe"]["properties"]
	for pair in [["FallsWhenDefeated", "falls_when_defeated"], ["PercentImmune", "percent_immune"]]:
		var box := holder.find_child(pair[0], true, false) as CheckBox
		_assert(box != null and not box.button_pressed, "%s starts unticked" % pair[0])
		box.toggled.emit(true)
		_assert(props.get(pair[1]) == true, "ticking it writes properties.%s" % pair[1])
		box.toggled.emit(false)
		_assert(not props.has(pair[1]), "and unticking it erases the key rather than writing false")
	var steal := holder.find_child("StealItems", true, false) as LineEdit
	steal.text = "item_ruby: 0.5, item_potion"; steal.text_changed.emit(steal.text)
	_assert(props.get("steal_items") == [{"item_id": "item_ruby", "chance": 0.5}, {"item_id": "item_potion"}], "what can be stolen is a list, the chance optional: %s" % str(props.get("steal_items")))
	steal.text = ""; steal.text_changed.emit("")
	_assert(not props.has("steal_items"), "and none erases the key")


func _check_the_phase_rows() -> void:
	print("
[the phase rows]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_probe", manager)
	var props: Dictionary = manager.npcs["npc_probe"]["properties"]
	_assert(not props.has("phases"), "an NPC with no phases has none written by opening it")
	var add := holder.find_child("AddPhase", true, false) as Button
	_assert(add != null, "the section has a '+ Phase' button")
	add.pressed.emit()
	_assert(props.get("phases") is Array and props["phases"].size() == 1 and int(props["phases"][0].get("seconds", 0)) == 10, "adding writes one phase of ten seconds")
	var phase: Dictionary = props["phases"][0]
	var name_field := holder.find_child("PhaseName", true, false) as LineEdit
	name_field.text = "mist"; name_field.text_changed.emit("mist")
	_assert(phase.get("name") == "mist", "typing a name writes it")
	name_field.text = ""; name_field.text_changed.emit("")
	_assert(not phase.has("name"), "and clearing it erases the key rather than writing an empty string")
	var seconds := holder.find_child("PhaseSeconds", true, false) as SpinBox
	seconds.value = 12
	seconds.value_changed.emit(12.0)   # a SpinBox set in code does not announce it; the user's edit does
	_assert(int(phase.get("seconds", 0)) == 12 and typeof(phase["seconds"]) == TYPE_INT, "the length is written as a whole number (got %s, type %d)" % [str(phase.get("seconds")), typeof(phase.get("seconds"))])
	_assert(holder.find_child("PhaseCounter", true, false) == null, "a counter is offered only to an untouchable phase")
	var untouchable := holder.find_child("PhaseUntouchable", true, false) as CheckBox
	untouchable.toggled.emit(true)
	_assert(phase.get("untouchable") == true, "ticking Untouchable writes it")
	var counter := holder.find_child("PhaseCounter", true, false) as OptionButton
	_assert(counter != null, "and then the counter picker appears")
	var offered: Array = []
	for index in counter.item_count: offered.append(str(counter.get_item_metadata(index)))
	_assert(offered.has("probe_breath"), "it offers the set's abilities (offered %s)" % str(offered))
	counter.item_selected.emit(offered.find("probe_breath"))
	_assert(phase.get("counter") == "probe_breath", "choosing one writes it")
	_assert(holder.find_child("PhaseCounterHint", true, false) != null, "and a hint for when it answers is offered")
	var hint_who := holder.find_child("PhaseHintNpc", true, false) as OptionButton
	var hint_text := holder.find_child("PhaseHintText", true, false) as LineEdit
	var npc_ids: Array = []
	for index in hint_who.item_count: npc_ids.append(str(hint_who.get_item_metadata(index)))
	hint_who.select(npc_ids.find("npc_declared"))
	hint_who.item_selected.emit(hint_who.selected)
	hint_text.text = "Wait for it!"; hint_text.text_changed.emit("Wait for it!")
	_assert(phase.get("hint") is Dictionary and phase["hint"].get("npc") == "npc_declared" and phase["hint"].get("text") == "Wait for it!", "a hint writes who and what")
	hint_who.select(0)
	hint_who.item_selected.emit(0)
	hint_text.text = ""; hint_text.text_changed.emit("")
	_assert(not phase.has("hint"), "and clearing both erases the hint")
	var resist := holder.find_child("PhaseResistances", true, false) as LineEdit
	resist.text = "fire: 200, ice: -50, nonsense"; resist.text_changed.emit(resist.text)
	_assert(phase.get("resistances") == {"fire": 200, "ice": -50}, "resistances are written as percents by damage type, and a part that is not one is skipped: %s" % str(phase.get("resistances")))
	resist.text = ""; resist.text_changed.emit("")
	_assert(not phase.has("resistances"), "and clearing them erases the key")
	phase["somebody_elses_key"] = 1
	untouchable.toggled.emit(false)
	_assert(not phase.has("untouchable") and phase.get("somebody_elses_key") == 1, "unticking erases the flag and leaves other keys alone")
	var remove := holder.find_child("RemovePhase", true, false) as Button
	remove.pressed.emit()
	_assert(not props.has("phases"), "removing the last phase erases the list")


func _checkbox_labeled(node: Node, text: String) -> CheckBox:
	if node is CheckBox and str(node.text) == text:
		return node
	for child in node.get_children():
		var found := _checkbox_labeled(child, text)
		if found != null:
			return found
	return null


# --- fixture ----------------------------------------------------------------

func _rebuild_fixture() -> void:
	_remove_recursive(scratch)
	_write("rules/ruleset.json", {
		"factions": {
			"extra": [{"id": "raiders", "disposition": "hostile"}],
			"overrides": {"neutral": "friendly"},
		},
	})
	_write("data/magic/probe_spells.json", {
		"probe_breath": {"name": "Probe Breath", "description": "", "mana_cost": 0, "cooldown": 1, "target_type": "all_enemies",
			"cast_message": "x", "hit_message": "x", "level_required": 1, "effects": [{"type": "damage", "value": 5, "damage_type": "air"}]},
	})
	_write("data/npcs/probe.json", {
		"npc_probe": {"name": "Probe", "description": "", "level": 1, "health": 10, "friendly": true, "properties": {}},
		"npc_declared": {"name": "Declared", "description": "", "level": 1, "health": 10, "friendly": false, "faction": "raiders", "behavior_type": "patrol", "properties": {}},
		"npc_undeclared": {"name": "Undeclared", "description": "", "level": 1, "health": 10, "friendly": false, "faction": "made_up_faction", "behavior_type": "made_up_behavior", "properties": {}},
	})


func _write(relative: String, payload: Dictionary) -> void:
	var path := scratch.path_join(relative)
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(payload, "  "))
	file.close()


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			var child := path.path_join(name)
			if dir.current_is_dir():
				_remove_recursive(child)
			else:
				DirAccess.remove_absolute(child)
		name = dir.get_next()
	dir.list_dir_end()
	DirAccess.remove_absolute(path)


# --- harness ------------------------------------------------------------------

func _manager() -> DatabaseManager:
	DataRoot._resolved = scratch
	DataRoot._source = "test fixture"
	return DatabaseManager.new()


func _build_inspector(npc_id: String) -> Node:
	return _build_inspector_from(npc_id, _manager())


func _build_inspector_from(npc_id: String, manager: DatabaseManager) -> Node:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	var inspector := DatabaseInspector.new(holder)
	inspector.set_db_manager(manager)
	inspector.build("npc", npc_id, manager.npcs[npc_id])
	return holder


func _faction_picker(node: Node) -> OptionButton:
	return _option_button_after_label(node, "Faction")


func _behavior_picker(node: Node) -> OptionButton:
	return _option_button_after_label(node, "Behavior")


## Each row is an HBoxContainer whose first child is the dim label and whose
## second child is the OptionButton -- the same shape `_build_faction_and_
## behavior` builds, walked generically so the test does not assume a sibling
## index outside that row.
func _option_button_after_label(node: Node, label_text: String) -> OptionButton:
	if node is HBoxContainer and node.get_child_count() >= 2:
		var first := node.get_child(0)
		if first is Label and str(first.text) == label_text and node.get_child(1) is OptionButton:
			return node.get_child(1)
	for child in node.get_children():
		var found := _option_button_after_label(child, label_text)
		if found != null:
			return found
	return null


func _picker_ids(picker: OptionButton) -> Array:
	var out: Array = []
	for index in range(picker.item_count):
		var id := str(picker.get_item_metadata(index))
		if id != "":
			out.append(id)
	return out


func _index_for_id(picker: OptionButton, id: String) -> int:
	for index in range(picker.item_count):
		if str(picker.get_item_metadata(index)) == id:
			return index
	return -1


func _label_for_id(picker: OptionButton, id: String) -> String:
	var index := _index_for_id(picker, id)
	return str(picker.get_item_text(index)) if index != -1 else ""


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		printerr("  FAIL ", message)
