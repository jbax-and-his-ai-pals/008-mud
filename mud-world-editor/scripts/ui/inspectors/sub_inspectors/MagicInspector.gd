# scripts/ui/inspectors/sub_inspectors/MagicInspector.gd
class_name MagicInspector
extends RefCounted

signal database_modified

var container: VBoxContainer
var cur_data: Dictionary
var known_groups: Dictionary = {}
var effects_box: VBoxContainer

const TARGET_TYPES := ["self", "friendly", "enemy", "all_friendly", "all_enemies", "area"]
const EFFECT_TYPES := ["damage", "heal", "apply_dot", "apply_effect", "summon"]

func build(c: VBoxContainer, data: Dictionary, groups: Dictionary):
	container = c
	cur_data = data
	known_groups = groups
	_build_spell_details()
	_build_effects()
	_build_messages()

func _build_spell_details():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Spell Details"))
	var card := InspectorStyle.create_card()
	var box: VBoxContainer = card.get_child(0).get_child(0)
	container.add_child(card)

	box.add_child(InspectorStyle.lbl("Spell Group", InspectorStyle.COLOR_TEXT_DIM))
	var group_picker := OptionButton.new(); InspectorStyle.apply_input_style(group_picker)
	var group_ids: Array = known_groups.keys()
	group_ids.sort_custom(func(a, b): return str(known_groups[a].get("name", a)).nocasecmp_to(str(known_groups[b].get("name", b))) < 0)
	var current_group := _group_id()
	var selected := 0
	for group_id_variant in group_ids:
		var group_id := str(group_id_variant)
		group_picker.add_item(str(known_groups[group_id].get("name", group_id)))
		group_picker.set_item_metadata(group_picker.item_count - 1, group_id)
		if group_id == current_group: selected = group_picker.item_count - 1
	group_picker.select(selected)
	group_picker.item_selected.connect(func(index): _set_value("magic_group", group_picker.get_item_metadata(index)))
	box.add_child(group_picker)

	var grid := GridContainer.new(); grid.columns = 2
	grid.add_theme_constant_override("h_separation", 14)
	grid.add_theme_constant_override("v_separation", 8)
	box.add_child(grid)
	_add_number_field(grid, "Mana Cost", "mana_cost", 0.0, 0.0, 999.0, 1.0)
	_add_number_field(grid, "Level Required", "level_required", 1.0, 1.0, 99.0, 1.0)
	_add_number_field(grid, "Cooldown (sec)", "cooldown", 0.0, 0.0, 999.0, 0.25)
	_add_number_field(grid, "Cast Time (sec)", "cast_time", 0.0, 0.0, 60.0, 0.1)
	_add_number_field(grid, "Range", "range", 0.0, 0.0, 999.0, 1.0)
	_add_target_field(grid)

func _add_number_field(grid: GridContainer, label: String, key: String, fallback: float, min_value: float, max_value: float, step: float):
	var field := VBoxContainer.new(); field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	field.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var input := SpinBox.new(); input.min_value = min_value; input.max_value = max_value; input.step = step
	input.value = float(cur_data.get(key, fallback)); InspectorStyle.apply_input_style(input)
	input.value_changed.connect(func(value): _set_value(key, value))
	field.add_child(input); grid.add_child(field)

func _add_target_field(grid: GridContainer):
	var field := VBoxContainer.new(); field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	field.add_child(InspectorStyle.lbl("Target", InspectorStyle.COLOR_TEXT_DIM))
	var picker := OptionButton.new(); InspectorStyle.apply_input_style(picker)
	var current := str(cur_data.get("target_type", "enemy"))
	var selected := 0
	for target in TARGET_TYPES:
		picker.add_item(target.replace("_", " ").capitalize())
		picker.set_item_metadata(picker.item_count - 1, target)
		if target == current: selected = picker.item_count - 1
	picker.select(selected)
	picker.item_selected.connect(func(index): _set_value("target_type", picker.get_item_metadata(index)))
	field.add_child(picker); grid.add_child(field)

func _build_effects():
	container.add_child(HSeparator.new())
	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.create_sub_header("Effects"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = "+ Effect"; InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS.darkened(0.2))
	add.pressed.connect(_add_effect)
	header.add_child(add); container.add_child(header)
	effects_box = VBoxContainer.new(); effects_box.add_theme_constant_override("separation", 8)
	container.add_child(effects_box)
	_refresh_effects()

func _refresh_effects():
	for child in effects_box.get_children(): child.queue_free()
	var effects: Array = cur_data.get("effects", [])
	if effects.is_empty():
		var note := Label.new()
		note.text = "No structured effects. Add one, or retain this spell's legacy effect fields below."
		note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; note.modulate = InspectorStyle.COLOR_TEXT_DIM
		effects_box.add_child(note)
		return
	for index in effects.size():
		effects_box.add_child(_effect_card(index, effects[index]))

func _effect_card(index: int, effect: Dictionary) -> PanelContainer:
	var card := PanelContainer.new(); card.add_theme_stylebox_override("panel", _dark_card_style())
	var margin := MarginContainer.new(); margin.add_theme_constant_override("margin_left", 8); margin.add_theme_constant_override("margin_right", 8)
	margin.add_theme_constant_override("margin_top", 6); margin.add_theme_constant_override("margin_bottom", 6)
	card.add_child(margin)
	var box := VBoxContainer.new(); box.add_theme_constant_override("separation", 6); margin.add_child(box)
	var title := HBoxContainer.new(); title.add_child(InspectorStyle.lbl("Effect %d" % (index + 1), InspectorStyle.COLOR_TEXT_DIM))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; title.add_child(spacer)
	var remove := Button.new(); remove.text = "×"; remove.flat = true
	remove.pressed.connect(func(): _remove_effect(index)); title.add_child(remove); box.add_child(title)
	var row := GridContainer.new(); row.columns = 4; row.add_theme_constant_override("h_separation", 8); box.add_child(row)
	var type_picker := OptionButton.new(); InspectorStyle.apply_input_style(type_picker)
	var current_type := str(effect.get("type", "damage")); var selected := 0
	for effect_type in EFFECT_TYPES:
		type_picker.add_item(effect_type.replace("_", " ").capitalize())
		type_picker.set_item_metadata(type_picker.item_count - 1, effect_type)
		if effect_type == current_type: selected = type_picker.item_count - 1
	type_picker.select(selected)
	type_picker.item_selected.connect(func(choice): _set_effect_value(index, "type", type_picker.get_item_metadata(choice)))
	row.add_child(_labeled("Type", type_picker))
	var amount := SpinBox.new(); amount.min_value = -9999; amount.max_value = 9999; amount.step = 1
	amount.value = float(effect.get("value", effect.get("dot_damage_per_tick", 0.0))); InspectorStyle.apply_input_style(amount)
	amount.value_changed.connect(func(value): _set_effect_amount(index, value))
	row.add_child(_labeled("Amount", amount))
	var damage_type := LineEdit.new(); damage_type.text = str(effect.get("damage_type", "")); damage_type.placeholder_text = "fire, holy…"
	InspectorStyle.apply_input_style(damage_type); damage_type.text_changed.connect(func(text): _set_effect_value(index, "damage_type", text))
	row.add_child(_labeled("Damage Type", damage_type))
	var duration := SpinBox.new(); duration.min_value = 0; duration.max_value = 9999; duration.step = 0.5
	duration.value = float(effect.get("dot_duration", effect.get("duration", 0.0))); InspectorStyle.apply_input_style(duration)
	duration.value_changed.connect(func(value): _set_effect_duration(index, value))
	row.add_child(_labeled("Duration", duration))
	return card

func _build_messages():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Narrative & Legacy Fields"))
	var card := InspectorStyle.create_card(); var box: VBoxContainer = card.get_child(0).get_child(0); container.add_child(card)
	_add_message_field(box, "Cast Message", "cast_message", "{caster_name} casts…")
	_add_message_field(box, "Hit Message", "hit_message", "{target_name} is struck…")
	var legacy_note := Label.new()
	legacy_note.text = "Existing effect_type, effect_data, and dot_* fields remain supported for older spells; new spells should prefer structured effects above."
	legacy_note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; legacy_note.modulate = InspectorStyle.COLOR_TEXT_DIM
	box.add_child(legacy_note)

func _add_message_field(parent: VBoxContainer, label: String, key: String, placeholder: String):
	parent.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var input := LineEdit.new(); input.text = str(cur_data.get(key, "")); input.placeholder_text = placeholder
	InspectorStyle.apply_input_style(input); input.text_changed.connect(func(text): _set_value(key, text))
	parent.add_child(input)

func _labeled(label: String, control: Control) -> VBoxContainer:
	var box := VBoxContainer.new(); box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM)); box.add_child(control)
	return box

func _set_value(key: String, value):
	if cur_data.get(key) == value: return
	cur_data[key] = value; database_modified.emit()

func _set_effect_value(index: int, key: String, value):
	var effects: Array = cur_data.get("effects", [])
	if index < 0 or index >= effects.size(): return
	var effect: Dictionary = effects[index]
	if effect.get(key) == value: return
	effect[key] = value; effects[index] = effect; cur_data["effects"] = effects
	database_modified.emit()

func _set_effect_amount(index: int, value):
	var effects: Array = cur_data.get("effects", [])
	if index < 0 or index >= effects.size(): return
	var effect: Dictionary = effects[index]
	_set_effect_value(index, "dot_damage_per_tick" if effect.get("type") == "apply_dot" else "value", value)

func _set_effect_duration(index: int, value):
	var effects: Array = cur_data.get("effects", [])
	if index < 0 or index >= effects.size(): return
	var effect: Dictionary = effects[index]
	_set_effect_value(index, "dot_duration" if effect.get("type") == "apply_dot" else "duration", value)

func _add_effect():
	if not cur_data.has("effects"): cur_data["effects"] = []
	cur_data.effects.append({"type": "damage", "value": 0.0})
	database_modified.emit(); _refresh_effects()

func _remove_effect(index: int):
	var effects: Array = cur_data.get("effects", [])
	if index < 0 or index >= effects.size(): return
	effects.remove_at(index); cur_data["effects"] = effects
	database_modified.emit(); _refresh_effects()

func _dark_card_style() -> StyleBoxFlat:
	var style := StyleBoxFlat.new(); style.bg_color = Color(0.09, 0.1, 0.13)
	style.border_color = Color(0.25, 0.3, 0.38); style.set_border_width_all(1); style.set_corner_radius_all(4)
	return style

func _group_id() -> String:
	var explicit := str(cur_data.get("magic_group", "")).strip_edges()
	if not explicit.is_empty(): return explicit
	var source := str(cur_data.get("_filename", "")).get_file().replace(".json", "")
	match source:
		"buff_spells", "restoration_spells": return "restoration"
		"debuff_spells": return "curses"
		"elemental_spells": return "elemental"
		"offensive_spells": return "evocation"
		"summoning_spells": return "conjuration"
		"utility_spells": return "utility"
	return "general"
