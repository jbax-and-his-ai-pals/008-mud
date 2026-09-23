# scripts/ui/inspectors/sub_inspectors/KnowledgeInspector.gd
#
# Knowledge topic authoring: `data/knowledge/topics.json`
# (`engine/core/knowledge_manager.py`) -- the "ask <npc> about <topic>" system.
#
# A response's `conditions` are deliberately not `engine/conditions.py`'s
# `KNOWN_KINDS` (the shared dialogue/title/quest-availability language):
# `KnowledgeManager._check_conditions` is its own, separate vocabulary keyed on
# the NPC being asked (`region_id`, `faction`, `template_id`) and on player/
# world state (`knowledge_state`, `campaign_state`, `campaign_outcome`,
# `quest_state`), and every key present in the object must hold at once (a
# flat AND). The constants below copy `knowledge_manager.py`'s
# KNOWLEDGE_CONDITION_KINDS and state tuples; schema_parity_smoke.gd checks the
# copy against them. `effects` is the one place this reuses a
# shared language: it is exactly `engine/dialogue/effects.py`'s, so the picker
# and shape hints come from `DialogueSchema.gd` rather than a second table.

class_name KnowledgeInspector
extends RefCounted

signal database_modified

var container: VBoxContainer
var cur_data: Dictionary
var database_mgr: DatabaseManager

const CONDITION_KINDS := [
	"region_id", "faction", "template_id",
	"knowledge_state", "campaign_state", "campaign_outcome", "quest_state",
]
const KNOWLEDGE_STATES := ["known", "discussed", "revealed"]
const CAMPAIGN_STATES := ["active", "completed", "not_active"]
const QUEST_STATES := ["active", "completed"]


func _init(c: VBoxContainer, db_mgr: DatabaseManager):
	container = c
	database_mgr = db_mgr


func build(id: String, data: Dictionary):
	cur_data = data
	container.add_child(InspectorStyle.create_section_header("TOPIC: %s" % id.to_upper(), Color(0.55, 0.75, 0.85)))
	_build_identity()
	_build_responses()


func _build_identity():
	var card := InspectorStyle.create_card()
	var vbox: VBoxContainer = card.get_child(0).get_child(0)
	container.add_child(card)

	vbox.add_child(InspectorStyle.lbl("Display name:", InspectorStyle.COLOR_TEXT_DIM))
	var name_ed := LineEdit.new(); name_ed.text = str(cur_data.get("display_name", ""))
	InspectorStyle.apply_input_style(name_ed)
	name_ed.text_changed.connect(func(text): cur_data["display_name"] = text; database_modified.emit())
	vbox.add_child(name_ed)

	var kw_header := HBoxContainer.new(); kw_header.add_child(InspectorStyle.lbl("Keywords", InspectorStyle.COLOR_TEXT_DIM))
	var kw_spacer := Control.new(); kw_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; kw_header.add_child(kw_spacer)
	var add_kw := Button.new(); add_kw.text = "+ Keyword"; InspectorStyle.apply_button_style(add_kw, Color(0.2, 0.3, 0.4))
	add_kw.pressed.connect(func():
		var list := _keywords().duplicate(); list.append("")
		cur_data["keywords"] = list
		database_modified.emit()
		_refresh_keywords(container.find_child("KeywordRows", true, false)))
	kw_header.add_child(add_kw); vbox.add_child(kw_header)
	var kw_rows := VBoxContainer.new(); kw_rows.name = "KeywordRows"; kw_rows.add_theme_constant_override("separation", 4); vbox.add_child(kw_rows)
	_refresh_keywords(kw_rows)


func _keywords() -> Array:
	var list = cur_data.get("keywords", [])
	return list if list is Array else []


func _refresh_keywords(rows: VBoxContainer):
	for child in rows.get_children(): child.queue_free()
	var list := _keywords()
	for index in range(list.size()):
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
		var field := LineEdit.new(); field.text = str(list[index]); field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_input_style(field)
		field.text_changed.connect(func(new_text):
			var live: Array = cur_data.get("keywords", [])
			if index < live.size(): live[index] = new_text
			database_modified.emit())
		row.add_child(field)
		var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			var live: Array = cur_data.get("keywords", [])
			if index < live.size(): live.remove_at(index)
			if live.is_empty(): cur_data.erase("keywords")
			database_modified.emit()
			_refresh_keywords(rows))
		row.add_child(remove); rows.add_child(row)
	if list.is_empty(): rows.add_child(InspectorStyle.lbl("None.", InspectorStyle.COLOR_TEXT_DIM))


func _responses() -> Array:
	var list = cur_data.get("responses", [])
	return list if list is Array else []


func _build_responses():
	container.add_child(HSeparator.new())
	var header := HBoxContainer.new(); header.add_child(InspectorStyle.create_sub_header("Responses"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = "+ Response"; InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var list := _responses().duplicate(true); list.append({"text": "", "priority": 0})
		cur_data["responses"] = list
		database_modified.emit()
		_refresh_responses(container.find_child("ResponseRows", true, false)))
	header.add_child(add); container.add_child(header)
	var rows := VBoxContainer.new(); rows.name = "ResponseRows"; rows.add_theme_constant_override("separation", 8)
	container.add_child(rows)
	_refresh_responses(rows)


func _refresh_responses(rows: VBoxContainer):
	for child in rows.get_children(): child.queue_free()
	var list := _responses()
	for index in range(list.size()):
		if not (list[index] is Dictionary): continue
		var response: Dictionary = list[index]
		var card := InspectorStyle.create_card(); var vbox: VBoxContainer = card.get_child(0).get_child(0)
		rows.add_child(card)

		var top_row := HBoxContainer.new(); top_row.add_theme_constant_override("separation", 6)
		top_row.add_child(InspectorStyle.lbl("Priority", InspectorStyle.COLOR_TEXT_DIM))
		var priority := SpinBox.new(); priority.min_value = -100; priority.max_value = 100; priority.step = 1
		priority.value = int(response.get("priority", 0)); priority.custom_minimum_size.x = 60
		InspectorStyle.apply_input_style(priority)
		priority.value_changed.connect(func(value): response["priority"] = int(value); database_modified.emit())
		top_row.add_child(priority)
		var top_spacer := Control.new(); top_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; top_row.add_child(top_spacer)
		var remove_response := Button.new(); remove_response.text = "Remove Response"
		InspectorStyle.apply_button_style(remove_response, Color(0.4, 0.1, 0.1))
		remove_response.pressed.connect(func():
			var live: Array = cur_data.get("responses", [])
			if index < live.size(): live.remove_at(index)
			if live.is_empty(): cur_data.erase("responses")
			database_modified.emit()
			_refresh_responses(rows))
		top_row.add_child(remove_response)
		vbox.add_child(top_row)

		var text_ed := TextEdit.new(); text_ed.custom_minimum_size.y = 48
		text_ed.text = str(response.get("text", ""))
		InspectorStyle.apply_input_style(text_ed)
		text_ed.text_changed.connect(func(): response["text"] = text_ed.text; database_modified.emit())
		vbox.add_child(text_ed)

		_build_conditions(vbox, response)
		_build_effects(vbox, response)
	if list.is_empty(): rows.add_child(InspectorStyle.lbl("No responses.", InspectorStyle.COLOR_TEXT_DIM))


# --- conditions -----------------------------------------------------------

func _default_condition_value(kind: String):
	match kind:
		"knowledge_state": return {"topic_id": "", "state": "known"}
		"campaign_state": return {"campaign_id": "", "state": "active"}
		"campaign_outcome": return {"campaign_id": "", "outcome": ""}
		"quest_state": return {"state": "active"}
		_: return ""


func _build_conditions(parent: VBoxContainer, response: Dictionary):
	var header := HBoxContainer.new(); header.add_child(InspectorStyle.lbl("Conditions (all must hold):", InspectorStyle.COLOR_TEXT_DIM))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = "+ Condition"; InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	var rows := VBoxContainer.new(); rows.add_theme_constant_override("separation", 4)
	add.pressed.connect(func():
		var conditions: Dictionary = response.get("conditions", {}) if response.get("conditions") is Dictionary else {}
		var kind := ""
		for candidate in CONDITION_KINDS:
			if not conditions.has(candidate): kind = candidate; break
		if kind == "": return
		conditions[kind] = _default_condition_value(kind)
		response["conditions"] = conditions
		database_modified.emit()
		_refresh_conditions(rows, response))
	header.add_child(add); parent.add_child(header); parent.add_child(rows)
	_refresh_conditions(rows, response)


func _refresh_conditions(rows: VBoxContainer, response: Dictionary):
	for child in rows.get_children(): child.queue_free()
	var conditions: Dictionary = response.get("conditions", {}) if response.get("conditions") is Dictionary else {}
	var keys: Array = conditions.keys(); keys.sort()
	for kind_variant in keys:
		var current_kind: String = str(kind_variant)
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
		var kind_picker := OptionButton.new()
		for candidate in CONDITION_KINDS:
			kind_picker.add_item(candidate); kind_picker.set_item_metadata(kind_picker.item_count - 1, candidate)
		kind_picker.select(maxi(0, CONDITION_KINDS.find(current_kind)))
		InspectorStyle.apply_button_style(kind_picker)
		kind_picker.item_selected.connect(func(index):
			var chosen := str(kind_picker.get_item_metadata(index))
			if chosen == current_kind or conditions.has(chosen):
				_refresh_conditions(rows, response)
				return
			conditions.erase(current_kind)
			conditions[chosen] = _default_condition_value(chosen)
			database_modified.emit()
			_refresh_conditions(rows, response))
		row.add_child(kind_picker)

		_build_condition_value_fields(row, conditions, current_kind, rows, response)

		var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			conditions.erase(current_kind)
			if conditions.is_empty(): response.erase("conditions")
			database_modified.emit()
			_refresh_conditions(rows, response))
		row.add_child(remove)
		rows.add_child(row)
	if keys.is_empty(): rows.add_child(InspectorStyle.lbl("None.", InspectorStyle.COLOR_TEXT_DIM))


func _build_condition_value_fields(row: HBoxContainer, conditions: Dictionary, kind: String, rows: VBoxContainer, response: Dictionary):
	if kind == "region_id" or kind == "faction" or kind == "template_id":
		var field := LineEdit.new(); field.text = str(conditions.get(kind, "")); field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_input_style(field)
		field.text_changed.connect(func(text): conditions[kind] = text; database_modified.emit())
		row.add_child(field)
		return

	var value: Dictionary = conditions.get(kind, {}) if conditions.get(kind) is Dictionary else {}
	conditions[kind] = value

	if kind == "knowledge_state":
		var topic_field := LineEdit.new(); topic_field.text = str(value.get("topic_id", "")); topic_field.placeholder_text = "topic id"
		topic_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(topic_field)
		topic_field.text_changed.connect(func(text): value["topic_id"] = text; database_modified.emit())
		row.add_child(topic_field)
		var state_picker := _enum_picker(KNOWLEDGE_STATES, str(value.get("state", "known")))
		state_picker.item_selected.connect(func(index): value["state"] = KNOWLEDGE_STATES[index]; database_modified.emit())
		row.add_child(state_picker)
	elif kind == "campaign_state":
		var campaign_field := LineEdit.new(); campaign_field.text = str(value.get("campaign_id", "")); campaign_field.placeholder_text = "campaign id"
		campaign_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(campaign_field)
		campaign_field.text_changed.connect(func(text): value["campaign_id"] = text; database_modified.emit())
		row.add_child(campaign_field)
		var state_picker := _enum_picker(CAMPAIGN_STATES, str(value.get("state", "active")))
		state_picker.item_selected.connect(func(index): value["state"] = CAMPAIGN_STATES[index]; database_modified.emit())
		row.add_child(state_picker)
	elif kind == "campaign_outcome":
		var campaign_field := LineEdit.new(); campaign_field.text = str(value.get("campaign_id", "")); campaign_field.placeholder_text = "campaign id"
		campaign_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(campaign_field)
		campaign_field.text_changed.connect(func(text): value["campaign_id"] = text; database_modified.emit())
		row.add_child(campaign_field)
		var outcome_field := LineEdit.new(); outcome_field.text = str(value.get("outcome", "")); outcome_field.placeholder_text = "outcome"
		outcome_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(outcome_field)
		outcome_field.text_changed.connect(func(text): value["outcome"] = text; database_modified.emit())
		row.add_child(outcome_field)
	elif kind == "quest_state":
		var state_picker := _enum_picker(QUEST_STATES, str(value.get("state", "active")))
		state_picker.item_selected.connect(func(index): value["state"] = QUEST_STATES[index]; database_modified.emit())
		row.add_child(state_picker)
		var from_this := CheckBox.new(); from_this.text = "from this NPC"
		from_this.button_pressed = bool(value.get("from_this_npc", false))
		from_this.toggled.connect(func(pressed):
			if pressed: value["from_this_npc"] = true
			else: value.erase("from_this_npc")
			database_modified.emit())
		row.add_child(from_this)
		var pattern_field := LineEdit.new(); pattern_field.text = str(value.get("id_pattern", "")); pattern_field.placeholder_text = "id contains..."
		pattern_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(pattern_field)
		pattern_field.text_changed.connect(func(text):
			if text == "": value.erase("id_pattern")
			else: value["id_pattern"] = text
			database_modified.emit())
		row.add_child(pattern_field)


func _enum_picker(options: Array, current: String) -> OptionButton:
	var picker := OptionButton.new()
	for option in options: picker.add_item(str(option))
	picker.select(maxi(0, options.find(current)))
	InspectorStyle.apply_button_style(picker)
	return picker


# --- effects ----------------------------------------------------------------
# Exactly `engine/dialogue/effects.py`'s vocabulary -- `DialogueSchema.gd` is
# the one copy of it in the editor, so this reads from it rather than
# retyping the key list or the shape hints a second time.

func _build_effects(parent: VBoxContainer, response: Dictionary):
	var header := HBoxContainer.new(); header.add_child(InspectorStyle.lbl("Effects:", InspectorStyle.COLOR_TEXT_DIM))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = "+ Effect"; InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	var rows := VBoxContainer.new(); rows.add_theme_constant_override("separation", 4)
	add.pressed.connect(func():
		var effects: Dictionary = response.get("effects", {}) if response.get("effects") is Dictionary else {}
		var known: Array = DialogueSchema.effect_keys()
		var chosen := ""
		for candidate in known:
			if not effects.has(candidate): chosen = str(candidate); break
		if chosen == "": return
		effects[chosen] = ""
		response["effects"] = effects
		database_modified.emit()
		_refresh_effects(rows, response))
	header.add_child(add); parent.add_child(header); parent.add_child(rows)
	_refresh_effects(rows, response)


func _refresh_effects(rows: VBoxContainer, response: Dictionary):
	for child in rows.get_children(): child.queue_free()
	var effects: Dictionary = response.get("effects", {}) if response.get("effects") is Dictionary else {}
	for key in effects.keys():
		var current_key: String = str(key)
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
		var picker := OptionButton.new()
		var keys: Array = DialogueSchema.effect_keys()
		if not DialogueSchema.has_effect(current_key): keys.append(current_key)
		for candidate in keys: picker.add_item(str(candidate))
		picker.select(maxi(0, keys.find(current_key)))
		InspectorStyle.apply_button_style(picker)
		var value = effects[key]
		picker.item_selected.connect(func(selected):
			var chosen := str(keys[selected])
			if chosen == current_key: return
			effects.erase(current_key)
			effects[chosen] = value
			database_modified.emit()
			_refresh_effects(rows, response))
		row.add_child(picker)

		var value_ed := LineEdit.new()
		value_ed.text = JSON.stringify(value) if (value is Dictionary or value is Array) else str(value)
		value_ed.placeholder_text = DialogueSchema.effect_shape(current_key)
		value_ed.tooltip_text = DialogueSchema.effect_shape(current_key)
		value_ed.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_input_style(value_ed)
		value_ed.text_changed.connect(func(text):
			var trimmed: String = str(text).strip_edges()
			if trimmed == "":
				effects.erase(current_key)
				value_ed.modulate = Color.WHITE
			elif trimmed.begins_with("{") or trimmed.begins_with("["):
				var parsed = JSON.parse_string(trimmed)
				if parsed == null:
					value_ed.modulate = Color(1.0, 0.6, 0.6)
					return
				effects[current_key] = parsed
				value_ed.modulate = Color.WHITE
			elif trimmed.is_valid_int():
				effects[current_key] = int(trimmed)
				value_ed.modulate = Color.WHITE
			else:
				effects[current_key] = trimmed
				value_ed.modulate = Color.WHITE
			database_modified.emit())
		row.add_child(value_ed)

		var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			effects.erase(current_key)
			if effects.is_empty(): response.erase("effects")
			database_modified.emit()
			_refresh_effects(rows, response))
		row.add_child(remove)
		rows.add_child(row)
	if effects.is_empty(): rows.add_child(InspectorStyle.lbl("None.", InspectorStyle.COLOR_TEXT_DIM))
