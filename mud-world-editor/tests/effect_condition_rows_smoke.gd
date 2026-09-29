# tests/effect_condition_rows_smoke.gd
#
# One editor for an effects mapping and one for a condition, shared by the
# dialogue, knowledge and title inspectors.
#
# The inspectors each carried a copy, and the copies had drifted. Each check below
# is a thing an author could not do (or a thing that silently went wrong) before
# they were shared, so this file fails against the previous inspectors:
#
#   * `advance_quest: true` -- "every active quest" -- could not be authored: the
#     value box turned the text `true` into the string "true".
#   * Digits typed into a text-valued effect became a number, so a flag called
#     "42" was stored as 42.
#   * `give_gold` was a text box; it is a whole number, and now says so.
#   * Changing an effect's key carried the old value over (a flag name became a
#     gold amount).
#   * The dialogue "+ Effect" wrote `set_flag` over an existing `set_flag`.
#   * Clearing the last effect left `"effects": {}` behind.
#   * A title's composite (`all` / `any` / `not`) condition could not be seen or
#     changed at all; only the dialogue inspector had a box for it.
#
# Run with:
#
#   godot --headless --path mud-world-editor --script tests/effect_condition_rows_smoke.gd

extends SceneTree

const RowProbe = preload("res://tests/lib/RowProbe.gd")

var failure_count := 0
var scratch: String = ""
var database: DatabaseManager


func _init() -> void:
	scratch = ProjectSettings.globalize_path("res://").path_join("../tmp/effect_condition_rows")
	DirAccess.make_dir_recursive_absolute(scratch)
	DataRoot._resolved = scratch
	DataRoot._source = "test fixture"
	database = DatabaseManager.new()

	_check_a_whole_number_effect_is_a_number_box()
	_check_true_is_a_bool_where_the_engine_takes_it()
	_check_digits_stay_text_where_the_value_is_text()
	_check_lists_and_objects_stay_authorable()
	_check_changing_the_key_does_not_carry_a_wrong_value()
	_check_adding_an_effect_never_replaces_one()
	_check_clearing_the_last_effect_removes_the_mapping()
	_check_the_knowledge_inspector_shares_it()
	_check_the_character_effects_have_typed_rows()
	_check_a_consumable_can_be_given_effects()
	_check_a_title_composite_condition_can_be_seen_and_changed()
	_check_a_title_requirement_composite_can_be_changed()
	_check_the_dialogue_condition_still_works()

	if failure_count > 0:
		push_error("effect and condition rows smoke failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- effects -----------------------------------------------------------------

func _dialogue_holder(choice: Dictionary) -> Array:
	var graph := {"id": "probe", "root": "start", "nodes": {"start": {"text": "Hello.", "choices": [choice]}}}
	var holder := VBoxContainer.new()
	root.add_child(holder)
	var inspector := DialogueInspector.new(holder, database)
	inspector.build("probe", graph)
	return [holder, graph]


func _check_a_whole_number_effect_is_a_number_box() -> void:
	print("\n[give_gold is a number]")
	var choice := {"text": "Take this.", "end": true, "effects": {"give_gold": 5}}
	var holder: VBoxContainer = _dialogue_holder(choice)[0]
	var widget := RowProbe.value_widget(holder, "give_gold")
	_assert(widget is SpinBox, "a whole-number effect gets a number box, not free text (%s)" % str(widget))
	if widget is SpinBox:
		_assert(int(widget.value) == 5, "showing the authored amount")
		# A SpinBox reports a change on the next idle pass, which a headless run
		# does not wait for, so the signal is sent the way the text boxes' is.
		widget.value = 25
		widget.value_changed.emit(25.0)
		_assert(typeof(choice["effects"]["give_gold"]) == TYPE_INT and choice["effects"]["give_gold"] == 25,
			"and writing a whole number: %s" % str(choice["effects"]["give_gold"]))


func _check_true_is_a_bool_where_the_engine_takes_it() -> void:
	print("\n[true is a bool]")
	var choice := {"text": "Onward.", "end": true, "effects": {"advance_quest": "q_first"}}
	var holder: VBoxContainer = _dialogue_holder(choice)[0]
	var widget := RowProbe.value_widget(holder, "advance_quest")
	_assert(widget is LineEdit, "an id-valued effect is a text box")
	if widget is LineEdit:
		RowProbe.type_into(widget, "true")
		_assert(typeof(choice["effects"]["advance_quest"]) == TYPE_BOOL and choice["effects"]["advance_quest"] == true,
			"`true` means every active quest, so it is written as true, not \"true\": %s" % str(choice["effects"]["advance_quest"]))
		RowProbe.type_into(widget, "q_second")
		_assert(choice["effects"]["advance_quest"] == "q_second", "and a quest id is still a quest id")


func _check_digits_stay_text_where_the_value_is_text() -> void:
	print("\n[a flag called 42]")
	var choice := {"text": "Sure.", "end": true, "effects": {"set_flag": "x"}}
	var holder: VBoxContainer = _dialogue_holder(choice)[0]
	var widget := RowProbe.value_widget(holder, "set_flag")
	if widget is LineEdit:
		RowProbe.type_into(widget, "42")
		_assert(typeof(choice["effects"]["set_flag"]) == TYPE_STRING and choice["effects"]["set_flag"] == "42",
			"digits typed into a flag name stay text: %s" % str(choice["effects"]["set_flag"]))
	else:
		_assert(false, "set_flag has a text box")


func _check_lists_and_objects_stay_authorable() -> void:
	print("\n[list and object forms]")
	var choice := {"text": "Sure.", "end": true, "effects": {"set_flag": "x", "give_item": "item_a"}}
	var holder: VBoxContainer = _dialogue_holder(choice)[0]
	var flags := RowProbe.value_widget(holder, "set_flag")
	RowProbe.type_into(flags, '["door_open", "guard_alerted"]')
	_assert(choice["effects"]["set_flag"] is Array and choice["effects"]["set_flag"].size() == 2,
		"set_flag takes a list of flags: %s" % str(choice["effects"]["set_flag"]))
	var items := RowProbe.value_widget(holder, "give_item")
	RowProbe.type_into(items, '{"item_a": 2}')
	_assert(choice["effects"]["give_item"] is Dictionary and choice["effects"]["give_item"].size() == 1,
		"give_item takes {id: quantity}: %s" % str(choice["effects"]["give_item"]))
	RowProbe.type_into(items, '{"item_a": ')
	_assert(choice["effects"]["give_item"] is Dictionary,
		"and half-typed JSON does not overwrite what was there")
	# An authored list is shown as JSON, so opening the inspector shows it as it is.
	var reopened := {"text": "Sure.", "end": true, "effects": {"set_flag": ["king_ordered", "obeyed_king"]}}
	var again: VBoxContainer = _dialogue_holder(reopened)[0]
	_assert(RowProbe.line_showing(again, '["king_ordered","obeyed_king"]') != null,
		"and a list already in the content is shown whole, not flattened")


func _check_changing_the_key_does_not_carry_a_wrong_value() -> void:
	print("\n[changing an effect]")
	var choice := {"text": "Take this.", "end": true, "effects": {"give_gold": 25}}
	var holder: VBoxContainer = _dialogue_holder(choice)[0]
	var row := RowProbe.effect_row(holder, "give_gold")
	var picker := row.get_child(0) as OptionButton
	var target := -1
	for index in range(picker.item_count):
		if picker.get_item_text(index) == "start_quest":
			target = index
	_assert(target >= 0, "start_quest is offered")
	picker.select(target)
	picker.item_selected.emit(target)
	var effects: Dictionary = choice["effects"]
	_assert(effects.has("start_quest") and not effects.has("give_gold"), "the effect changes its key: %s" % str(effects))
	_assert(str(effects.get("start_quest", "")) != "25",
		"but a gold amount does not become a quest id: %s" % str(effects.get("start_quest")))


func _check_adding_an_effect_never_replaces_one() -> void:
	print("\n[+ Effect]")
	var choice := {"text": "Sure.", "end": true, "effects": {"set_flag": "kept_flag", "give_gold": 3}}
	var holder: VBoxContainer = _dialogue_holder(choice)[0]
	var adds := RowProbe.buttons(holder, "+ Effect")
	_assert(adds.size() == 2, "the node and the choice each have an add button")
	var add: Button = adds.back()   # the choice's; the node's comes first
	add.pressed.emit()
	add.pressed.emit()
	var effects: Dictionary = choice["effects"]
	_assert(effects.size() == 4, "each press adds an effect: %s" % str(effects.keys()))
	_assert(effects.get("set_flag") == "kept_flag", "and none replaces an existing one: %s" % str(effects.get("set_flag")))
	_assert(typeof(effects.get("give_gold")) != TYPE_STRING, "a number-valued effect starts as a number")


func _check_clearing_the_last_effect_removes_the_mapping() -> void:
	print("\n[clearing the last effect]")
	var choice := {"text": "Sure.", "end": true, "effects": {"set_flag": "only"}}
	var holder: VBoxContainer = _dialogue_holder(choice)[0]
	RowProbe.type_into(RowProbe.value_widget(holder, "set_flag"), "")
	_assert(not choice.has("effects"), "an emptied mapping is removed, not left as {}: %s" % str(choice.get("effects")))
	var widget := RowProbe.value_widget(holder, "set_flag")
	RowProbe.type_into(widget, "back_again")
	_assert(choice.get("effects", {}).get("set_flag") == "back_again",
		"and typing again puts it back where the owner can see it: %s" % str(choice))


func _check_the_knowledge_inspector_shares_it() -> void:
	print("\n[knowledge topics]")
	var topic := {"display_name": "Ore", "keywords": ["ore"], "responses": [
		{"text": "Iron, mostly.", "effects": {"complete_quest": "q_ore", "give_gold": 4}}]}
	var holder := VBoxContainer.new()
	root.add_child(holder)
	KnowledgeInspector.new(holder, database).build("ore", topic)
	var effects: Dictionary = topic["responses"][0]["effects"]
	RowProbe.type_into(RowProbe.value_widget(holder, "complete_quest"), "true")
	_assert(typeof(effects["complete_quest"]) == TYPE_BOOL, "the same `true` rule: %s" % str(effects["complete_quest"]))
	var gold := RowProbe.value_widget(holder, "give_gold")
	_assert(gold is SpinBox, "and the same number box for gold")


func _check_the_character_effects_have_typed_rows() -> void:
	print("
[character effects]")
	var choice := {"text": "Rest.", "end": true, "effects": {"take_gold": 30, "restore": "all", "message": "You sleep."}}
	var holder: VBoxContainer = _dialogue_holder(choice)[0]
	var gold := RowProbe.value_widget(holder, "take_gold")
	_assert(gold is SpinBox, "the price of a service is a number box (%s)" % str(gold))
	if gold is SpinBox:
		gold.value = 45
		gold.value_changed.emit(45.0)
		_assert(choice["effects"]["take_gold"] == 45, "and writes a whole number")
	var restore := RowProbe.value_widget(holder, "restore")
	_assert(restore is LineEdit and (restore as LineEdit).text == "all", "restore shows what was authored")
	RowProbe.type_into(restore, '{"resource": "health", "amount": "full"}')
	_assert(choice["effects"]["restore"] is Dictionary, "and takes the object form")
	RowProbe.type_into(restore, "mana")
	_assert(choice["effects"]["restore"] == "mana", "or one resource by name: %s" % str(choice["effects"]["restore"]))
	_assert(RowProbe.value_widget(holder, "message") is LineEdit, "a message is plain text")
	# A fresh effect starts as a value the engine accepts, of the right type.
	for candidate in ["restore", "take_gold", "raise", "forget_spell"]:
		_assert(DialogueSchema.has_effect(candidate), "`%s` is offered" % candidate)
	_assert(DialogueSchema.default_effect_value("restore") == "all", "restore starts as all")
	_assert(typeof(DialogueSchema.default_effect_value("take_gold")) == TYPE_INT, "take_gold starts as a number")


func _consumable_holder(item: Dictionary) -> VBoxContainer:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	var inspector := ItemInspector.new()
	inspector.build(holder, item, database)
	return holder


func _check_a_consumable_can_be_given_effects() -> void:
	print("
[a consumable's effects]")
	var item := {"type": "Consumable", "name": "Heart Container", "description": "d",
		"properties": {"uses": 1, "effect_type": "heal", "effect_value": 20}}
	var holder := VBoxContainer.new()
	root.add_child(holder)
	# The database inspector puts the entry's header in this container first.
	var header := Label.new()
	header.name = "EntryHeader"
	holder.add_child(header)
	ItemInspector.new().build(holder, item, database)
	var picker := holder.find_child("ConsumableEffectType", true, false) as OptionButton
	_assert(picker != null, "a consumable has an effect type picker")
	if picker == null:
		return
	var offered: Array = []
	for index in range(picker.item_count):
		offered.append(picker.get_item_text(index))
	_assert(offered.has("effects") and offered.has("heal"), "offering what the engine runs: %s" % str(offered))
	_assert(not offered.has("poison"), "and nothing it does not")
	_assert(holder.find_child("ConsumableEffects", true, false) == null, "effects rows appear only for that type")

	var target := offered.find("effects")
	picker.select(target)
	picker.item_selected.emit(target)
	_assert(item["properties"]["effect_type"] == "effects", "choosing it writes the type: %s" % str(item["properties"]))
	_assert(holder.find_child("EntryHeader", true, false) != null,
		"and changing the type rebuilds only the consumable section, not what was already in the container")
	# The inspector rebuilt itself for the new type; find the new rows.
	var rebuilt := holder
	var add_buttons := RowProbe.buttons(rebuilt, "+ Effect")
	_assert(add_buttons.size() == 1, "and the effect rows appear")
	if add_buttons.size() == 1:
		(add_buttons[0] as Button).pressed.emit()
		_assert(item["properties"].get("effects") is Dictionary and item["properties"]["effects"].has("set_flag"),
			"adding one writes it under properties.effects: %s" % str(item["properties"]))

	# A consumable whose type the engine does not run is shown, not hidden.
	var odd := {"type": "Consumable", "name": "Fungus", "description": "d",
		"properties": {"uses": 1, "effect_type": "poison"}}
	var odd_holder := _consumable_holder(odd)
	var odd_picker := odd_holder.find_child("ConsumableEffectType", true, false) as OptionButton
	_assert(odd_picker != null and odd_picker.get_item_text(odd_picker.selected) == "poison",
		"an effect type the engine does not run stays visible so it can be fixed")

	# Not a consumable: no section.
	var sword := {"type": "Weapon", "name": "Sword", "description": "d", "properties": {}}
	_assert(_consumable_holder(sword).find_child("ConsumableEffectType", true, false) == null,
		"other item classes get no effect picker")


# --- conditions --------------------------------------------------------------

func _title_holder(title: Dictionary) -> VBoxContainer:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	TitleInspector.new(holder, database).build("probe", title)
	return holder


func _check_a_title_composite_condition_can_be_seen_and_changed() -> void:
	print("\n[a title's composite condition]")
	var composite := {"all": [{"kind": "flag", "flag": "a"}, {"not": {"kind": "flag", "flag": "b"}}]}
	var title := {"name": "The Bold", "description": "d", "condition": composite}
	var holder := _title_holder(title)
	var shown := RowProbe.line_showing(holder, JSON.stringify(composite))
	_assert(shown != null, "a condition with no `kind` is shown whole, as JSON, instead of an empty picker")
	if shown != null:
		RowProbe.type_into(shown, '{"any": [{"kind": "flag", "flag": "c"}]}')
		_assert(title["condition"].has("any") and not title["condition"].has("all"),
			"and editing it replaces the condition: %s" % str(title["condition"]))
		RowProbe.type_into(shown, '{"any": ')
		_assert(title["condition"].has("any"), "half-typed JSON changes nothing")


func _check_a_title_requirement_composite_can_be_changed() -> void:
	print("\n[a title requirement]")
	var composite := {"any": [{"kind": "flag", "flag": "a"}]}
	var title := {"name": "The Bold", "description": "d", "requirements": [composite]}
	var holder := _title_holder(title)
	var shown := RowProbe.line_showing(holder, JSON.stringify(composite))
	_assert(shown != null, "a composite requirement is shown whole")
	if shown != null:
		RowProbe.type_into(shown, '{"all": [{"kind": "flag", "flag": "z"}]}')
		_assert(title["requirements"][0].has("all"), "and replaced in place in the list: %s" % str(title["requirements"]))
	var picker := RowProbe.condition_picker(holder, "(none)")
	_assert(picker != null, "the kind picker is there, worded for a title")


func _check_the_dialogue_condition_still_works() -> void:
	print("\n[a dialogue condition]")
	var composite := {"not": {"kind": "flag", "flag": "spoken"}}
	var choice := {"text": "Sure.", "end": true, "condition": composite}
	var holder: VBoxContainer = _dialogue_holder(choice)[0]
	var shown := RowProbe.line_showing(holder, JSON.stringify(composite))
	_assert(shown != null, "a composite choice condition is shown whole")
	if shown != null:
		RowProbe.type_into(shown, '{"kind": "flag", "flag": "later"}')
		_assert(choice["condition"].get("kind") == "flag", "and replaced: %s" % str(choice["condition"]))
	var plain := {"text": "Sure.", "end": true, "condition": {"kind": "flag", "flag": "seen"}}
	var picker_holder: VBoxContainer = _dialogue_holder(plain)[0]
	var flag_field := RowProbe.line_showing(picker_holder, "seen")
	_assert(flag_field != null, "a kind's own field shows its value")
	if flag_field != null:
		RowProbe.type_into(flag_field, "heard")
		_assert(plain["condition"]["flag"] == "heard", "and edits it in place")
	var picker := RowProbe.condition_picker(picker_holder, "(always offered)")
	_assert(picker != null, "the picker keeps its dialogue wording")


# --- harness -----------------------------------------------------------------

func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		push_error("FAIL: " + message)
