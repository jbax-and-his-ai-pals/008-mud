# scripts/ui/inspectors/sub_inspectors/MagicInspector.gd
class_name MagicInspector
extends RefCounted

signal database_modified

var container: VBoxContainer
var cur_data: Dictionary
var known_groups: Dictionary = {}
var effects_box: VBoxContainer
# The ability's own id and the manager, so the group can be filed in the editor's
# state instead of in content the engine refuses (see `magic_group_assignments`).
var ability_id: String = ""
var db_manager: DatabaseManager = null

# Copies of the engine's vocabulary (magic/spell.py), kept equal by
# schema_parity_smoke.gd. A target the cast command does not resolve casts on
# yourself; an effect type the executor does not know does nothing.
const TARGET_TYPES := ["self", "friendly", "enemy", "all_enemies", "item"]
const TARGET_LABELS := {
	"self": "Self", "friendly": "Friendly (you or an ally)", "enemy": "Enemy",
	"all_enemies": "All Enemies Here", "item": "Item or Container",
}
# The keys each effect type reads besides `type` and `damage_type`.
const EFFECT_FIELDS := {
	"damage": ["value"], "heal": ["value"], "life_tap": ["value"],
	"apply_dot": ["dot_name", "dot_duration", "dot_damage_per_tick", "dot_tick_interval", "dot_damage_type", "effect_data"],
	"apply_effect": ["effect_data", "dot_duration", "base_duration"],
	"cleanse": ["effect_data"], "remove_curse": [],
	"summon": ["summon_template_id", "summon_duration", "max_summons"],
	"unlock": [], "lock": [],
}
const MESSAGE_PLACEHOLDERS := {
	"cast_message": ["caster_name", "spell_name"],
	"hit_message": ["caster_name", "target_name", "spell_name", "value", "damage_type"],
	"heal_message": ["caster_name", "target_name", "spell_name", "value"],
	"self_heal_message": ["caster_name", "target_name", "spell_name", "value"],
	"remove_curse_item_message": ["target_name"],
	"remove_curse_equipment_message": ["target_name", "value"],
}
const EFFECT_NOTES := {
	"remove_curse": "Lifts the curse from a targeted item, or from every cursed item the target wears.",
	"unlock": "Opens a locked container (and sets off an undisarmed trap). Needs the Item target.",
	"lock": "Locks a container. Needs the Item target.",
}
const CLEANSE_DEFAULT_TAGS := ["poison", "disease", "curse"]

func build(c: VBoxContainer, data: Dictionary, groups: Dictionary, id: String = "", db_mgr: DatabaseManager = null):
	container = c
	cur_data = data
	known_groups = groups
	ability_id = id
	db_manager = db_mgr
	_build_spell_details()
	_build_effects()
	_build_messages()

func _build_spell_details():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Ability Details"))
	var card := InspectorStyle.create_card()
	var box: VBoxContainer = card.get_child(0).get_child(0)
	container.add_child(card)

	box.add_child(InspectorStyle.lbl("Ability Group", InspectorStyle.COLOR_TEXT_DIM))
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
	# The group is the editor's own filing, not the engine's: `magic_group` is not
	# a `Spell` field, and `Spell.from_dict` passes content straight into a
	# constructor with no `**kwargs` -- so writing it into the entry made the group
	# picker a button that stopped the ability from loading. It is kept in
	# `editor/magic_groups.json` now.
	group_picker.item_selected.connect(func(index):
		if db_manager != null:
			db_manager.set_magic_group(ability_id, str(group_picker.get_item_metadata(index)))
		database_modified.emit()
	)
	box.add_child(group_picker)

	var grid := GridContainer.new(); grid.columns = 2
	grid.add_theme_constant_override("h_separation", 14)
	grid.add_theme_constant_override("v_separation", 8)
	box.add_child(grid)
	_add_number_field(grid, "Cost", "mana_cost", 10.0, 0.0, 999.0, 1.0)
	_add_number_field(grid, "Level Required", "level_required", 1.0, 1.0, 99.0, 1.0)
	_add_number_field(grid, "Cooldown (sec)", "cooldown", 5.0, 0.0, 999.0, 0.25)
	# "Cast Time" and "Range" used to be fields here, writing `cast_time` and
	# `range` into the entry. The engine has no such fields on `Spell`, and an
	# unknown keyword is not ignored -- it raises, and the ability is not loaded.
	_add_target_field(grid)

func _add_number_field(grid: GridContainer, label: String, key: String, fallback: float, min_value: float, max_value: float, step: float):
	var field := VBoxContainer.new(); field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	field.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var input := SpinBox.new(); input.name = key; input.min_value = min_value; input.max_value = max_value; input.step = step
	input.value = float(cur_data.get(key, fallback)); InspectorStyle.apply_input_style(input)
	input.value_changed.connect(func(value): _set_value(key, value))
	field.add_child(input); grid.add_child(field)

func _add_target_field(grid: GridContainer):
	var field := VBoxContainer.new(); field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	field.add_child(InspectorStyle.lbl("Target", InspectorStyle.COLOR_TEXT_DIM))
	var picker := OptionButton.new(); picker.name = "TargetType"; InspectorStyle.apply_input_style(picker)
	var current := str(cur_data.get("target_type", "enemy"))
	var options: Array = TARGET_TYPES.duplicate()
	# An authored value the engine does not resolve is shown as what it is, not
	# silently replaced by the first option.
	if not options.has(current): options.append(current)
	for target in options:
		picker.add_item(TARGET_LABELS.get(target, "Unknown: %s" % target))
		picker.set_item_metadata(picker.item_count - 1, target)
		if target == current: picker.select(picker.item_count - 1)
	picker.item_selected.connect(func(index):
		_set_value("target_type", picker.get_item_metadata(index))
		_refresh_effects()
	)
	field.add_child(picker); grid.add_child(field)

# --- effects -------------------------------------------------------------------

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
	for child in effects_box.get_children():
		effects_box.remove_child(child); child.queue_free()
	var effects: Array = cur_data.get("effects", [])
	if effects.is_empty():
		var note := Label.new()
		note.text = "No effects. The engine does not load an ability without at least one."
		note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; note.modulate = InspectorStyle.COLOR_DANGER
		effects_box.add_child(note)
		return
	for index in effects.size():
		if effects[index] is Dictionary: effects_box.add_child(_effect_card(index, effects[index]))

func _effect_card(index: int, effect: Dictionary) -> PanelContainer:
	var card := PanelContainer.new(); card.name = "Effect_%d" % index
	card.add_theme_stylebox_override("panel", _dark_card_style())
	var margin := MarginContainer.new(); margin.add_theme_constant_override("margin_left", 8); margin.add_theme_constant_override("margin_right", 8)
	margin.add_theme_constant_override("margin_top", 6); margin.add_theme_constant_override("margin_bottom", 6)
	card.add_child(margin)
	var box := VBoxContainer.new(); box.add_theme_constant_override("separation", 6); margin.add_child(box)

	var title := HBoxContainer.new(); title.add_child(InspectorStyle.lbl("Effect %d" % (index + 1), InspectorStyle.COLOR_TEXT_DIM))
	var effect_type := str(effect.get("type", ""))
	var type_picker := OptionButton.new(); type_picker.name = "EffectType"; InspectorStyle.apply_input_style(type_picker)
	var types: Array = EFFECT_FIELDS.keys()
	if not types.has(effect_type): types.append(effect_type)
	for option in types:
		type_picker.add_item(str(option).replace("_", " ").capitalize() if EFFECT_FIELDS.has(option) else "Unknown: %s" % option)
		type_picker.set_item_metadata(type_picker.item_count - 1, option)
		if option == effect_type: type_picker.select(type_picker.item_count - 1)
	type_picker.item_selected.connect(func(choice): _retype(index, str(type_picker.get_item_metadata(choice))))
	title.add_child(type_picker)
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; title.add_child(spacer)
	var remove := Button.new(); remove.text = "×"; remove.flat = true; remove.tooltip_text = "Remove this effect"
	remove.pressed.connect(func(): _remove_effect(index)); title.add_child(remove); box.add_child(title)

	var grid := GridContainer.new(); grid.columns = 3; grid.add_theme_constant_override("h_separation", 8); box.add_child(grid)
	match effect_type:
		"damage", "life_tap":
			grid.add_child(_labeled("Amount", _effect_number(index, "value", -9999, 9999, 1, 0.0)))
			grid.add_child(_labeled("Damage Type", _damage_type_picker(index, "damage_type")))
		"heal":
			grid.add_child(_labeled("Amount", _effect_number(index, "value", -9999, 9999, 1, 0.0)))
		"apply_dot":
			grid.add_child(_labeled("Name", _effect_text(index, "dot_name", "Burning")))
			grid.add_child(_labeled("Damage / Tick", _effect_number(index, "dot_damage_per_tick", -9999, 9999, 1, 5.0)))
			grid.add_child(_labeled("Damage Type", _damage_type_picker(index, "dot_damage_type")))
			grid.add_child(_labeled("Duration (sec)", _effect_number(index, "dot_duration", 0.5, 9999, 0.5, 10.0)))
			grid.add_child(_labeled("Tick Every (sec)", _effect_number(index, "dot_tick_interval", 0.5, 9999, 0.5, 3.0)))
		"apply_effect":
			_build_applied_effect(box, grid, index, effect)
		"cleanse":
			var tags := LineEdit.new(); tags.name = "Tags"; InspectorStyle.apply_input_style(tags)
			var data: Dictionary = effect.get("effect_data", {}) if effect.get("effect_data") is Dictionary else {}
			tags.text = ", ".join(PackedStringArray(data.get("tags", CLEANSE_DEFAULT_TAGS)))
			tags.placeholder_text = "poison, disease, curse"
			tags.text_changed.connect(func(text): _set_effect_data(index, "tags", _split_tags(text)))
			tags.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			box.add_child(_labeled("Removes effects tagged", tags))
		"summon":
			grid.add_child(_labeled("Creature", _summon_picker(index, str(effect.get("summon_template_id", "")))))
			grid.add_child(_labeled("Lasts (sec, 0 = until dismissed)", _effect_number(index, "summon_duration", 0, 99999, 1, 0.0)))
			grid.add_child(_labeled("Max At Once (0 = no cap)", _effect_number(index, "max_summons", 0, 99, 1, 0.0, true)))
		_:
			if EFFECT_NOTES.has(effect_type):
				box.add_child(_note(EFFECT_NOTES[effect_type]))
			elif not EFFECT_FIELDS.has(effect_type):
				box.add_child(_note("The engine does not execute '%s', so this effect does nothing. Choose a type above." % effect_type))
	if effect_type in ["unlock", "lock"] and str(cur_data.get("target_type", "enemy")) != "item":
		box.add_child(_note("This ability's target is not Item, so the %s never reaches a container." % effect_type))
	return card

func _build_applied_effect(box: VBoxContainer, grid: GridContainer, index: int, effect: Dictionary):
	var data: Dictionary = effect.get("effect_data", {}) if effect.get("effect_data") is Dictionary else {}
	var effect_name := LineEdit.new(); effect_name.name = "EffectName"; effect_name.text = str(data.get("name", ""))
	effect_name.placeholder_text = "Weaken"; InspectorStyle.apply_input_style(effect_name)
	effect_name.text_changed.connect(func(text): _set_effect_data(index, "name", text))
	grid.add_child(_labeled("Effect Name", effect_name))
	var kind := LineEdit.new(); kind.name = "EffectKind"; kind.text = str(data.get("type", ""))
	kind.placeholder_text = "stat_mod"; InspectorStyle.apply_input_style(kind)
	kind.tooltip_text = "stat_mod applies the modifiers below; any other kind is a named effect other rules look for (e.g. Stun)."
	kind.text_submitted.connect(func(text): _set_effect_data(index, "type", text.strip_edges()); _refresh_effects())
	kind.focus_exited.connect(func(): if str(_effect_data(index).get("type", "")) != kind.text.strip_edges(): _set_effect_data(index, "type", kind.text.strip_edges()); _refresh_effects())
	grid.add_child(_labeled("Kind", kind))
	# The executor takes effect_data.base_duration, else the effect's dot_duration;
	# the field edits whichever this effect already uses.
	var duration_key := "dot_duration" if effect.has("dot_duration") and not data.has("base_duration") else "base_duration"
	var duration := SpinBox.new(); duration.name = "Duration"; duration.min_value = 0; duration.max_value = 99999; duration.step = 0.5
	duration.value = float(effect.get("dot_duration", 0.0)) if duration_key == "dot_duration" else float(data.get("base_duration", 0.0))
	InspectorStyle.apply_input_style(duration)
	duration.tooltip_text = "0 = never wears off"
	duration.value_changed.connect(func(value):
		if duration_key == "dot_duration":
			if value > 0: _set_effect_value(index, "dot_duration", value)
			else: _erase_effect_value(index, "dot_duration")
		elif value > 0: _set_effect_data(index, "base_duration", value)
		else: _erase_effect_data(index, "base_duration")
	)
	grid.add_child(_labeled("Duration (sec, 0 = never ends)", duration))
	if str(data.get("type", "")) != "stat_mod": return

	var header := HBoxContainer.new(); header.add_child(InspectorStyle.lbl("Modifiers", InspectorStyle.COLOR_TEXT_DIM))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = "+ Modifier"; add.flat = true
	add.pressed.connect(func(): _add_modifier(index)); header.add_child(add); box.add_child(header)
	var modifiers: Dictionary = data.get("modifiers", {}) if data.get("modifiers") is Dictionary else {}
	if modifiers.is_empty(): box.add_child(_note("A stat_mod needs at least one modifier."))
	var row_index := 0
	for stat in modifiers.keys():
		var row := HBoxContainer.new(); row.name = "Modifier_%d" % row_index; row_index += 1
		var stat_field := LineEdit.new(); stat_field.name = "Stat"; stat_field.text = str(stat); stat_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_input_style(stat_field)
		stat_field.text_submitted.connect(func(text): _rename_modifier(index, str(stat), text.strip_edges()))
		stat_field.focus_exited.connect(func(): _rename_modifier(index, str(stat), stat_field.text.strip_edges()))
		row.add_child(stat_field)
		var amount := SpinBox.new(); amount.name = "Amount"; amount.min_value = -9999; amount.max_value = 9999; amount.step = 1
		amount.value = float(modifiers[stat]); InspectorStyle.apply_input_style(amount)
		amount.value_changed.connect(func(value): _set_modifier(index, str(stat), value))
		row.add_child(amount)
		var drop := Button.new(); drop.text = "×"; drop.flat = true
		drop.pressed.connect(func(): _remove_modifier(index, str(stat)))
		row.add_child(drop); box.add_child(row)

func _effect_number(index: int, key: String, min_value: float, max_value: float, step: float, fallback: float, zero_erases: bool = false) -> SpinBox:
	var effect: Dictionary = cur_data["effects"][index]
	var input := SpinBox.new(); input.name = key; input.min_value = min_value; input.max_value = max_value; input.step = step
	input.value = float(effect.get(key, fallback)); InspectorStyle.apply_input_style(input)
	input.value_changed.connect(func(value):
		if zero_erases and value == 0: _erase_effect_value(index, key)
		else: _set_effect_value(index, key, value)
	)
	return input

func _effect_text(index: int, key: String, placeholder: String) -> LineEdit:
	var input := LineEdit.new(); input.name = key; input.text = str(cur_data["effects"][index].get(key, ""))
	input.placeholder_text = placeholder; InspectorStyle.apply_input_style(input)
	input.text_changed.connect(func(text): _set_effect_value(index, key, text))
	return input

func _damage_type_picker(index: int, key: String) -> OptionButton:
	var picker := OptionButton.new(); picker.name = key; InspectorStyle.apply_input_style(picker)
	var channels: Array = db_manager.combat_vocabulary.damage_types if db_manager != null else []
	var current := str(cur_data["effects"][index].get(key, ""))
	picker.add_item("(default)"); picker.set_item_metadata(0, "")
	for channel in channels:
		picker.add_item(str(channel)); picker.set_item_metadata(picker.item_count - 1, str(channel))
		if str(channel) == current: picker.select(picker.item_count - 1)
	if current != "" and not channels.has(current):
		picker.add_item("Unknown: %s" % current); picker.set_item_metadata(picker.item_count - 1, current); picker.select(picker.item_count - 1)
	picker.item_selected.connect(func(choice):
		var value := str(picker.get_item_metadata(choice))
		if value.is_empty(): _erase_effect_value(index, key)
		else: _set_effect_value(index, key, value)
	)
	return picker

func _summon_picker(index: int, current: String) -> OptionButton:
	var picker := OptionButton.new(); picker.name = "summon_template_id"; InspectorStyle.apply_input_style(picker)
	# Only a `minion` follows its summoner and expires (npcs/ai/dispatcher.py).
	var minions: Array = []
	if db_manager != null:
		for template_id in db_manager.npcs:
			if db_manager.npcs[template_id] is Dictionary and str(db_manager.npcs[template_id].get("behavior_type", "")) == "minion":
				minions.append(str(template_id))
	minions.sort()
	if current.is_empty():
		picker.add_item("(choose a minion)"); picker.set_item_metadata(0, "")
	for template_id in minions:
		picker.add_item(str(db_manager.npcs[template_id].get("name", template_id)))
		picker.set_item_metadata(picker.item_count - 1, template_id)
		if template_id == current: picker.select(picker.item_count - 1)
	if not current.is_empty() and not minions.has(current):
		var reason := "Not a minion" if db_manager != null and db_manager.npcs.has(current) else "Missing"
		picker.add_item("%s: %s" % [reason, current]); picker.set_item_metadata(picker.item_count - 1, current); picker.select(picker.item_count - 1)
	picker.item_selected.connect(func(choice):
		var value := str(picker.get_item_metadata(choice))
		if not value.is_empty(): _set_effect_value(index, "summon_template_id", value)
	)
	return picker

# --- messages ------------------------------------------------------------------

func _build_messages():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Messages"))
	var card := InspectorStyle.create_card(); var box: VBoxContainer = card.get_child(0).get_child(0); container.add_child(card)
	box.add_child(_note("Empty uses the engine's default. Only the placeholders shown are filled; the engine refuses any other."))
	for key in MESSAGE_PLACEHOLDERS:
		var label := str(key).trim_suffix("_message").replace("_", " ").capitalize() + " Message"
		var hint := " ".join(PackedStringArray(MESSAGE_PLACEHOLDERS[key].map(func(name): return "{%s}" % name)))
		box.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
		var input := LineEdit.new(); input.name = key; input.text = str(cur_data.get(key, "")); input.placeholder_text = hint
		InspectorStyle.apply_input_style(input)
		input.text_changed.connect(func(text):
			if text.is_empty():
				if cur_data.has(key): cur_data.erase(key); database_modified.emit()
			else: _set_value(key, text)
		)
		box.add_child(input)

# --- writes --------------------------------------------------------------------

func _set_value(key: String, value):
	if cur_data.get(key) == value: return
	cur_data[key] = value; database_modified.emit()

func _effect(index: int) -> Dictionary:
	var effects: Array = cur_data.get("effects", [])
	if index < 0 or index >= effects.size() or not effects[index] is Dictionary: return {}
	return effects[index]

func _set_effect_value(index: int, key: String, value):
	var effect := _effect(index)
	if effect.is_empty() or effect.get(key) == value: return
	effect[key] = value; database_modified.emit()

func _erase_effect_value(index: int, key: String):
	var effect := _effect(index)
	if effect.erase(key): database_modified.emit()

func _effect_data(index: int) -> Dictionary:
	var effect := _effect(index)
	if effect.is_empty(): return {}
	if not effect.get("effect_data") is Dictionary: effect["effect_data"] = {}
	return effect["effect_data"]

func _set_effect_data(index: int, key: String, value):
	var data := _effect_data(index)
	if _effect(index).is_empty() or data.get(key) == value: return
	data[key] = value; database_modified.emit()

func _erase_effect_data(index: int, key: String):
	if _effect_data(index).erase(key): database_modified.emit()

func _add_modifier(index: int):
	var data := _effect_data(index)
	if not data.get("modifiers") is Dictionary: data["modifiers"] = {}
	var stat := "stat"; var n := 2
	while data["modifiers"].has(stat): stat = "stat_%d" % n; n += 1
	data["modifiers"][stat] = 0
	database_modified.emit(); _refresh_effects()

func _set_modifier(index: int, stat: String, value):
	var modifiers = _effect_data(index).get("modifiers")
	if modifiers is Dictionary and modifiers.get(stat) != value:
		modifiers[stat] = value; database_modified.emit()

func _rename_modifier(index: int, old_stat: String, new_stat: String):
	var modifiers = _effect_data(index).get("modifiers")
	if not modifiers is Dictionary or new_stat.is_empty() or new_stat == old_stat or modifiers.has(new_stat) or not modifiers.has(old_stat): return
	# Rebuilt in place so the order the author wrote survives the rename.
	var rebuilt := {}
	for stat in modifiers: rebuilt[new_stat if stat == old_stat else stat] = modifiers[stat]
	modifiers.clear(); modifiers.merge(rebuilt)
	database_modified.emit(); _refresh_effects.call_deferred()

func _remove_modifier(index: int, stat: String):
	var modifiers = _effect_data(index).get("modifiers")
	if modifiers is Dictionary and modifiers.erase(stat):
		database_modified.emit(); _refresh_effects()

# A new type keeps only what that type reads, with defaults that make it a
# working effect: every other key would be refused as unread.
func _retype(index: int, effect_type: String):
	var effect := _effect(index)
	if effect.is_empty() or str(effect.get("type", "")) == effect_type: return
	var reads: Array = ["damage_type"] + EFFECT_FIELDS.get(effect_type, [])
	for key in effect.keys():
		if str(key).begins_with("_") or key == "type": continue
		if not reads.has(key) or key == "effect_data": effect.erase(key)
	effect["type"] = effect_type
	if effect_type not in ["damage", "life_tap", "apply_dot"]: effect.erase("damage_type")
	match effect_type:
		"damage", "heal", "life_tap":
			if not effect.has("value"): effect["value"] = 0
		"apply_dot":
			for pair in [["dot_name", "Affliction"], ["dot_duration", 10], ["dot_damage_per_tick", 1]]:
				if not effect.has(pair[0]): effect[pair[0]] = pair[1]
		"apply_effect":
			effect.erase("dot_duration"); effect.erase("base_duration")
			effect["effect_data"] = {"type": "stat_mod", "name": "", "modifiers": {}, "base_duration": 10}
		"cleanse":
			effect["effect_data"] = {"tags": CLEANSE_DEFAULT_TAGS.duplicate()}
		"summon":
			if not effect.has("summon_template_id"): effect["summon_template_id"] = ""
	database_modified.emit(); _refresh_effects()

func _add_effect():
	if not cur_data.get("effects") is Array: cur_data["effects"] = []
	cur_data.effects.append({"type": "damage", "value": 0})
	database_modified.emit(); _refresh_effects()

func _remove_effect(index: int):
	var effects: Array = cur_data.get("effects", [])
	if index < 0 or index >= effects.size(): return
	effects.remove_at(index); cur_data["effects"] = effects
	database_modified.emit(); _refresh_effects()

# --- helpers -------------------------------------------------------------------

static func _split_tags(text: String) -> Array:
	var out: Array = []
	for part in text.split(","):
		var tag := part.strip_edges()
		if not tag.is_empty() and not out.has(tag): out.append(tag)
	return out

func _labeled(label: String, control: Control) -> VBoxContainer:
	var box := VBoxContainer.new(); box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM)); box.add_child(control)
	return box

func _note(text: String) -> Label:
	var note := Label.new(); note.text = text
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; note.modulate = InspectorStyle.COLOR_TEXT_DIM
	return note

func _dark_card_style() -> StyleBoxFlat:
	var style := StyleBoxFlat.new(); style.bg_color = Color(0.09, 0.1, 0.13)
	style.border_color = Color(0.25, 0.3, 0.38); style.set_border_width_all(1); style.set_corner_radius_all(4)
	return style

func _group_id() -> String:
	if db_manager != null:
		var assigned := db_manager.magic_group_of(ability_id)
		if not assigned.is_empty(): return assigned
	# A set written by an older editor may still carry the key; the manager
	# migrates it out of content on load and strips it on save.
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
