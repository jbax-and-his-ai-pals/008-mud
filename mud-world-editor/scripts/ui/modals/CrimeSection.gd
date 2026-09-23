# scripts/ui/modals/CrimeSection.gd
#
# The ruleset's `crime` section (`core/crime_manager.py`, `commands/jail.py`,
# `world.py`), validated by `content_set.py::_validate_crime_and_debug_rules`.
# Like WorldRulesSection, a field is written only when the author changed it,
# so untouched numbers keep their authored form and unknown keys survive.
# An unset number shows 0 because that is what the engine uses for it.

class_name CrimeSection
extends RefCounted

# [path within `crime`, label, kind, extra]
const FIELDS := [
	["enabled", "Theft can be witnessed and punished", "bool", null],
	["witness.skill", "Skill a thief rolls against the sharpest onlooker", "text", "stealth"],
	["witness.base_difficulty", "Base difficulty", "int", [0, 1000]],
	["witness.rank_attribute", "Onlooker attribute that raises difficulty", "text", "level"],
	["witness.rank_multiplier", "per point of it", "number", [0.0, 100.0, 0.5]],
	["witness.authority_property", "NPC property marking authority", "text", "is_guard"],
	["witness.authority_bonus", "Difficulty added by authority", "int", [0, 1000]],
	["witness.excluded_factions", "Factions that never witness (comma-separated)", "list", "hostile"],
	["witness.xp_success", "Skill XP when unseen", "int", [0, 10000]],
	["witness.xp_caught", "Skill XP when caught", "int", [0, 10000]],
	["consequences.reputation_key", "Reputation lost when caught", "text", "town_guard"],
	["consequences.reputation_per_value", "Reputation lost per point of value", "number", [0.0, 100.0, 0.05]],
	["consequences.fine_rate", "Fine per point of value", "number", [0.0, 100.0, 0.1]],
	["consequences.fine_minimum", "Minimum fine", "int", [0, 100000]],
	["consequences.custody_value_threshold", "Jail when one theft is worth at least", "int", [0, 1000000]],
	["consequences.custody_cumulative_threshold", "or all thefts together at least", "int", [0, 1000000]],
	["consequences.custody_reputation_threshold", "or reputation falls to", "int", [-1000, 1000]],
	["custody.room_property", "Room property marking a jail cell", "text", "is_jail_cell"],
	["custody.release_destination_property", "Cell property naming where a released prisoner goes", "text", "release_destination"],
	["custody.base_seconds", "Sentence: base seconds", "int", [0, 100000]],
	["custody.seconds_per_value", "plus seconds per point of value", "number", [0.0, 1000.0, 0.1]],
	["custody.emergency_tool_item_id", "Tool slipped to a prisoner who meets the requirements below", "item", null],
	["custody.emergency_tool_durability", "Its durability", "int", [1, 1000]],
	["custody.escape_alert_margin", "Escape: failing a pick by this much alerts guards", "int", [0, 1000]],
	["custody.escape_sentence_penalty_seconds", "Seconds added to the sentence when caught escaping", "int", [0, 100000]],
	["custody.search_success_chance", "Chance searching the cell finds currency", "number", [0.0, 1.0, 0.01]],
	["custody.search_currency_min", "Currency found, from", "int", [0, 100000]],
	["custody.search_currency_max", "to", "int", [0, 100000]],
]
const PAIRED := ["witness.rank_multiplier", "consequences.custody_cumulative_threshold",
	"consequences.custody_reputation_threshold", "custody.seconds_per_value", "custody.emergency_tool_durability",
	"custody.search_currency_max"]

var on_change: Callable
var database: DatabaseManager
var baseline = null
var controls: Dictionary = {}
var requirement_rows: VBoxContainer
var requirement_baseline: Array = []


func build(box: VBoxContainer, changed: Callable) -> void:
	on_change = changed
	box.add_child(InspectorStyle.create_sub_header("Crime"))
	var hint := InspectorStyle.lbl("Theft, witnesses, fines and jail. With crime on, a skill, a reputation key and a room property some room carries are required.", InspectorStyle.COLOR_TEXT_DIM)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(hint)
	var group := ""
	var row: HBoxContainer = null
	for spec in FIELDS:
		var part := str(spec[0]).get_slice(".", 0) if "." in spec[0] else ""
		if part != group:
			group = part
			box.add_child(InspectorStyle.lbl(group.capitalize(), InspectorStyle.COLOR_ACCENT))
		if not (spec[0] in PAIRED) or row == null:
			row = HBoxContainer.new(); row.add_theme_constant_override("separation", 8); box.add_child(row)
		var control: Control
		match str(spec[2]):
			"bool":
				var check := CheckBox.new(); check.text = spec[1]; check.toggled.connect(func(_v): _changed()); control = check
			"text", "list":
				row.add_child(InspectorStyle.lbl(spec[1], InspectorStyle.COLOR_TEXT_DIM))
				var field := LineEdit.new(); field.placeholder_text = str(spec[3]); field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
				InspectorStyle.apply_input_style(field); field.text_changed.connect(func(_t): _changed()); control = field
			"item":
				row.add_child(InspectorStyle.lbl(spec[1], InspectorStyle.COLOR_TEXT_DIM))
				var picker := OptionButton.new(); picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
				InspectorStyle.apply_button_style(picker); picker.item_selected.connect(func(index): picker.select(index); _changed()); control = picker
			_:
				row.add_child(InspectorStyle.lbl(spec[1], InspectorStyle.COLOR_TEXT_DIM))
				var spin := SpinBox.new(); spin.min_value = spec[3][0]; spin.max_value = spec[3][1]
				spin.step = spec[3][2] if spec[2] == "number" else 1
				spin.custom_minimum_size.x = 90; InspectorStyle.apply_input_style(spin); spin.value_changed.connect(func(_v): _changed()); control = spin
		control.name = str(spec[0]).replace(".", "_")
		row.add_child(control)
		controls[spec[0]] = control
	var header := HBoxContainer.new(); box.add_child(header)
	header.add_child(InspectorStyle.lbl("Skills a prisoner needs to keep a hidden tool (all of them)", InspectorStyle.COLOR_TEXT_DIM))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = "+ Requirement"; InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS)
	add.pressed.connect(func(): _add_requirement("", 0); _changed()); header.add_child(add)
	requirement_rows = VBoxContainer.new(); requirement_rows.add_theme_constant_override("separation", 4); box.add_child(requirement_rows)


func load(ruleset: Dictionary, db: DatabaseManager) -> void:
	database = db
	var crime = ruleset.get("crime", null)
	baseline = crime.duplicate(true) if crime is Dictionary else null
	var source: Dictionary = crime if crime is Dictionary else {}
	for spec in FIELDS:
		var value = WorldRulesSection._read_path(source, spec[0])
		var control = controls[spec[0]]
		match str(spec[2]):
			"bool": control.button_pressed = value == true
			"text": control.text = str(value) if value is String else ""
			"list": control.text = ", ".join(value) if value is Array else ""
			"item":
				var ids: Array = database.get_item_ids() if database != null else []
				QuestGenerationSection._fill_picker(control, ids, {}, str(value) if value is String else "", "No tool")
			_: control.value = float(value) if typeof(value) in [TYPE_INT, TYPE_FLOAT] else 0.0
		control.set_meta("loaded", _value_of(control))
	for child in requirement_rows.get_children(): requirement_rows.remove_child(child); child.queue_free()
	var custody = source.get("custody", {})
	var requirements = custody.get("concealed_tool_requirements", []) if custody is Dictionary else []
	requirement_baseline = requirements.duplicate(true) if requirements is Array else []
	for entry in requirement_baseline:
		if entry is Dictionary: _add_requirement(str(entry.get("skill", "")), float(entry.get("minimum", 0)))


## The whole `crime` section as it should be written, or {} for none.
func compose() -> Dictionary:
	var out: Dictionary = baseline.duplicate(true) if baseline is Dictionary else {}
	for spec in FIELDS:
		var control = controls[spec[0]]
		if _value_of(control) == control.get_meta("loaded"): continue
		match str(spec[2]):
			"bool": WorldRulesSection._write_path(out, spec[0], (control as CheckBox).button_pressed)
			"text":
				var text := (control as LineEdit).text.strip_edges()
				if text == "": WorldRulesSection._erase_path(out, spec[0])
				else: WorldRulesSection._write_path(out, spec[0], text)
			"list":
				var values := WorldRulesSection._split((control as LineEdit).text)
				if values.is_empty(): WorldRulesSection._erase_path(out, spec[0])
				else: WorldRulesSection._write_path(out, spec[0], values)
			"item":
				var item_id := QuestGenerationSection._picked(control)
				if item_id == "": WorldRulesSection._erase_path(out, spec[0])
				else: WorldRulesSection._write_path(out, spec[0], item_id)
			"int": WorldRulesSection._write_path(out, spec[0], int((control as SpinBox).value))
			_: WorldRulesSection._write_path(out, spec[0], snappedf((control as SpinBox).value, 0.01))
	var requirements := _requirements()
	if JSON.stringify(SaveIO._normalize_numbers(requirements)) != JSON.stringify(SaveIO._normalize_numbers(requirement_baseline)):
		if requirements.is_empty(): WorldRulesSection._erase_path(out, "custody.concealed_tool_requirements")
		else: WorldRulesSection._write_path(out, "custody.concealed_tool_requirements", requirements)
	return out


func changed() -> bool:
	var before = baseline if baseline is Dictionary else {}
	return JSON.stringify(SaveIO._normalize_numbers(compose())) != JSON.stringify(SaveIO._normalize_numbers(before))


func _add_requirement(skill: String, minimum: float) -> void:
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
	var skill_field := LineEdit.new(); skill_field.name = "Skill"; skill_field.text = skill; skill_field.placeholder_text = "skill"
	skill_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(skill_field)
	skill_field.text_changed.connect(func(_t): _changed()); row.add_child(skill_field)
	row.add_child(InspectorStyle.lbl("at least", InspectorStyle.COLOR_TEXT_DIM))
	var spin := SpinBox.new(); spin.name = "Minimum"; spin.min_value = 0; spin.max_value = 1000; spin.step = 1; spin.value = minimum
	spin.custom_minimum_size.x = 80; InspectorStyle.apply_input_style(spin); spin.value_changed.connect(func(_v): _changed()); row.add_child(spin)
	var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
	remove.pressed.connect(func(): requirement_rows.remove_child(row); row.queue_free(); _changed()); row.add_child(remove)
	requirement_rows.add_child(row)


func _requirements() -> Array:
	var out: Array = []
	for row in requirement_rows.get_children():
		var skill := (row.get_node("Skill") as LineEdit).text.strip_edges()
		if skill != "": out.append({"skill": skill, "minimum": int((row.get_node("Minimum") as SpinBox).value)})
	return out


static func _value_of(control):
	if control is CheckBox: return control.button_pressed
	if control is OptionButton: return control.selected
	return WorldRulesSection._control_value(control)


func _changed() -> void:
	if on_change.is_valid(): on_change.call()
