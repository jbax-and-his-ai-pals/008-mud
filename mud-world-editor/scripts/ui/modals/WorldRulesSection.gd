# scripts/ui/modals/WorldRulesSection.gd
#
# Seven small ruleset sections, each validated by
# `content_set.py::_validate_simple_ruleset_sections`: economy, locksmithing,
# calendar, spawning, elites, npc_naming and player_defaults. A field is
# written only when the author changed it, so untouched values (and keys this
# form does not show) keep their exact authored form; a cleared text or list
# field removes its key and falls back to the engine default.

class_name WorldRulesSection
extends RefCounted

# [section, path within the section, label, kind, extra]
const FIELDS := [
	["economy", "currency_name", "Currency name", "text", "gold"],
	["locksmithing", "skill", "Lockpicking skill (empty: locks cannot be picked)", "text", "lockpicking"],
	["calendar", "day_names", "Day names (comma-separated)", "list", ""],
	["calendar", "month_names", "Month names (comma-separated)", "list", ""],
	["calendar", "start_time.hour", "Clock starts at hour", "int", [0, 23]],
	["calendar", "start_time.minute", "and minute", "int", [0, 59]],
	["spawning", "no_spawn_keywords", "No ambient spawns in rooms whose id or name contains (comma-separated)", "list", ""],
	["elites", "chance", "Elite chance per ambient spawn", "number", [0.0, 1.0, 0.01]],
	["elites", "stat_multiplier", "Elite stat multiplier", "number", [0.05, 10.0, 0.05]],
	["elites", "loot_guaranteed_chance", "Elite minimum drop chance", "number", [0.0, 1.0, 0.01]],
	["elites", "loot_quantity_multiplier", "Elite loot quantity multiplier", "number", [0.05, 10.0, 0.05]],
	["elites", "name_pattern", "Elite name pattern ({prefix} {name})", "text", "{prefix} {name}"],
	["elites", "prefixes", "Elite prefixes (comma-separated)", "list", ""],
	["npc_naming", "random_name_pattern", "Random NPC name pattern ({first_name} {title})", "text", "{first_name}"],
	["npc_naming", "first_names", "First names (comma-separated)", "list", ""],
	["player_defaults", "player_class", "Default player class", "text", "Adventurer"],
	["player_defaults", "magic.known_spells", "Default known spells (ability ids, comma-separated)", "list", ""],
]
const ENGINE_DEFAULTS := {
	"calendar.start_time.hour": 0, "calendar.start_time.minute": 0,
	"elites.chance": 0.0, "elites.stat_multiplier": 1.5,
	"elites.loot_guaranteed_chance": 1.0, "elites.loot_quantity_multiplier": 1.5,
}

var on_change: Callable
var database: DatabaseManager
var baseline: Dictionary = {}
var controls: Dictionary = {}
var inventory_rows: VBoxContainer
var inventory_baseline: Array = []


func build(box: VBoxContainer, changed: Callable) -> void:
	on_change = changed
	box.add_child(InspectorStyle.create_sub_header("World Rules"))
	var hint := InspectorStyle.lbl("Setting-wide defaults. An empty field uses the engine default.", InspectorStyle.COLOR_TEXT_DIM)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(hint)
	var current_section := ""
	var time_row: HBoxContainer = null
	for spec in FIELDS:
		if spec[0] != current_section:
			current_section = spec[0]
			box.add_child(InspectorStyle.lbl(current_section.capitalize(), InspectorStyle.COLOR_ACCENT))
		var key := "%s.%s" % [spec[0], spec[1]]
		match str(spec[3]):
			"text", "list":
				var row := VBoxContainer.new(); box.add_child(row)
				row.add_child(InspectorStyle.lbl(spec[2], InspectorStyle.COLOR_TEXT_DIM))
				var field := LineEdit.new(); field.name = key.replace(".", "_"); field.placeholder_text = str(spec[4])
				InspectorStyle.apply_input_style(field); field.text_changed.connect(func(_t): _changed()); row.add_child(field)
				controls[key] = field
			"int", "number":
				var parent: HBoxContainer
				if spec[1].begins_with("start_time.") and time_row != null:
					parent = time_row
				else:
					parent = HBoxContainer.new(); parent.add_theme_constant_override("separation", 8); box.add_child(parent)
					if spec[1].begins_with("start_time."): time_row = parent
				parent.add_child(InspectorStyle.lbl(spec[2], InspectorStyle.COLOR_TEXT_DIM))
				var spin := SpinBox.new(); spin.name = key.replace(".", "_")
				spin.min_value = spec[4][0]; spin.max_value = spec[4][1]; spin.step = spec[4][2] if spec[3] == "number" else 1
				spin.custom_minimum_size.x = 90; InspectorStyle.apply_input_style(spin)
				spin.value_changed.connect(func(_v): _changed()); parent.add_child(spin)
				controls[key] = spin
	var header := HBoxContainer.new(); box.add_child(header)
	header.add_child(InspectorStyle.lbl("Starting inventory (used when a set has no backgrounds)", InspectorStyle.COLOR_TEXT_DIM))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = "+ Starting Item"; InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS)
	add.pressed.connect(func(): _add_inventory_row("", 1); _changed()); header.add_child(add)
	inventory_rows = VBoxContainer.new(); inventory_rows.add_theme_constant_override("separation", 4); box.add_child(inventory_rows)


func load(ruleset: Dictionary, db: DatabaseManager) -> void:
	database = db
	baseline = {}
	for spec in FIELDS:
		baseline[spec[0]] = ruleset.get(spec[0], null)
	for spec in FIELDS:
		var key := "%s.%s" % [spec[0], spec[1]]
		var value = _read_path(ruleset, key)
		var control = controls[key]
		match str(spec[3]):
			"text": control.text = str(value) if value is String else ""
			"list": control.text = ", ".join(value) if value is Array else ""
			_: control.value = float(value) if typeof(value) in [TYPE_INT, TYPE_FLOAT] else float(ENGINE_DEFAULTS.get(key, 0))
		control.set_meta("loaded", _control_value(control))
	for child in inventory_rows.get_children(): inventory_rows.remove_child(child); child.queue_free()
	var defaults = ruleset.get("player_defaults", {})
	var entries = defaults.get("starting_inventory", []) if defaults is Dictionary else []
	inventory_baseline = entries.duplicate(true) if entries is Array else []
	for entry in inventory_baseline:
		if entry is String: _add_inventory_row(entry, 1, true)
		elif entry is Dictionary: _add_inventory_row(str(entry.get("item_id", "")), int(entry.get("quantity", 1)), false)


## The sections this form owns, as they should be written.
func compose() -> Dictionary:
	var out := {}
	for name in baseline:
		if baseline[name] is Dictionary: out[name] = baseline[name].duplicate(true)
	for spec in FIELDS:
		var key := "%s.%s" % [spec[0], spec[1]]
		var control = controls[key]
		if _control_value(control) == control.get_meta("loaded"): continue
		if not out.has(spec[0]): out[spec[0]] = {}
		var section: Dictionary = out[spec[0]]
		match str(spec[3]):
			"text":
				var text := (control as LineEdit).text.strip_edges()
				if text == "": _erase_path(section, spec[1])
				else: _write_path(section, spec[1], text)
			"list":
				var values := _split((control as LineEdit).text)
				if values.is_empty(): _erase_path(section, spec[1])
				else: _write_path(section, spec[1], values)
			"int": _write_path(section, spec[1], int((control as SpinBox).value))
			_: _write_path(section, spec[1], snappedf((control as SpinBox).value, 0.01))
	var inventory := _inventory()
	if JSON.stringify(SaveIO._normalize_numbers(inventory)) != JSON.stringify(SaveIO._normalize_numbers(inventory_baseline)):
		if not out.has("player_defaults"): out["player_defaults"] = {}
		if inventory.is_empty(): out["player_defaults"].erase("starting_inventory")
		else: out["player_defaults"]["starting_inventory"] = inventory
	for name in out.keys():
		if out[name] is Dictionary and out[name].is_empty() and not (baseline.get(name) is Dictionary): out.erase(name)
	return out


func changed() -> bool:
	var current := compose()
	for name in current:
		if JSON.stringify(SaveIO._normalize_numbers(current[name])) != JSON.stringify(SaveIO._normalize_numbers(baseline.get(name))): return true
	for name in baseline:
		if baseline[name] is Dictionary and not current.has(name): return true
	return false


func _add_inventory_row(item_id: String, quantity: int, was_string := false) -> void:
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6); row.set_meta("was_string", was_string)
	var picker := OptionButton.new(); picker.name = "Item"; picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var labels := {}
	var ids: Array = database.get_item_ids() if database != null else []
	for id in ids:
		if database.items.get(id) is Dictionary: labels[id] = "%s — %s" % [str(database.items[id].get("name", id)), id]
	QuestGenerationSection._fill_picker(picker, ids, labels, item_id, "Choose item")
	InspectorStyle.apply_button_style(picker); picker.item_selected.connect(func(index): picker.select(index); _changed()); row.add_child(picker)
	var spin := SpinBox.new(); spin.name = "Quantity"; spin.min_value = 1; spin.max_value = 999; spin.step = 1; spin.value = quantity
	spin.custom_minimum_size.x = 70; InspectorStyle.apply_input_style(spin); spin.value_changed.connect(func(_v): _changed()); row.add_child(spin)
	var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
	remove.pressed.connect(func(): inventory_rows.remove_child(row); row.queue_free(); _changed()); row.add_child(remove)
	inventory_rows.add_child(row)


## A plain-string entry stays a string while its quantity is 1, so an
## unedited list round-trips in the shape it was written.
func _inventory() -> Array:
	var out: Array = []
	for row in inventory_rows.get_children():
		var item_id := QuestGenerationSection._picked(row.get_node("Item"))
		if item_id == "": continue
		var quantity := int((row.get_node("Quantity") as SpinBox).value)
		if bool(row.get_meta("was_string", false)) and quantity == 1: out.append(item_id)
		else: out.append({"item_id": item_id, "quantity": quantity})
	return out


static func _read_path(ruleset: Dictionary, key: String):
	var value = ruleset
	for part in key.split("."):
		if not (value is Dictionary) or not value.has(part): return null
		value = value[part]
	return value


static func _write_path(section: Dictionary, path: String, value) -> void:
	var parts := path.split(".")
	var target := section
	for index in range(parts.size() - 1):
		if not (target.get(parts[index]) is Dictionary): target[parts[index]] = {}
		target = target[parts[index]]
	target[parts[-1]] = value


static func _erase_path(section: Dictionary, path: String) -> void:
	var parts := path.split(".")
	var target = section
	for index in range(parts.size() - 1):
		if not (target is Dictionary) or not (target.get(parts[index]) is Dictionary): return
		target = target[parts[index]]
	target.erase(parts[-1])


static func _control_value(control):
	if control is LineEdit: return control.text
	return control.value


static func _split(text: String) -> Array:
	var out: Array = []
	for value in text.split(","):
		if value.strip_edges() != "": out.append(value.strip_edges())
	return out


func _changed() -> void:
	if on_change.is_valid(): on_change.call()
