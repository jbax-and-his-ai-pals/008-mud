# scripts/ui/inspectors/sub_inspectors/EncounterInspector.gd
#
# One encounter zone (`data/encounters/*.json`, `engine/world/encounters.py`): somewhere walking is dangerous. The region it
# covers (and optionally some of its rooms), what may come with its weight, the chance on arriving, how many, a cooldown and
# the line said. Opening a zone writes nothing; a field cleared is erased, and keys this inspector does not model survive.
#
# Reached through `preload`, not a `class_name` (see EncounterSchema.gd).
extends RefCounted

signal database_modified

const SCHEMA = preload("res://scripts/data/EncounterSchema.gd")
const CONDITION_ROWS = preload("res://scripts/ui/inspectors/panels/ConditionRows.gd")

var container: VBoxContainer
var cur_data: Dictionary
var cur_id: String
var database_mgr: DatabaseManager


func _init(c: VBoxContainer, db_mgr: DatabaseManager):
	container = c
	database_mgr = db_mgr


## A new zone is valid before anything else is typed: a region and a creature the set has (the caller picks the first of each).
static func data_defaults(region_id: String = "", monster_id: String = "") -> Dictionary:
	return {"region": region_id, "monsters": [monster_id] if monster_id != "" else [], "chance": 0.1}


## "slime, drakee:3" <-> ["slime", {"npc": "drakee", "weight": 3}]. A weight of 1 is left off.
static func monsters_text(monsters) -> String:
	if not (monsters is Array): return ""
	var parts: Array = []
	for entry in monsters:
		if entry is String: parts.append(entry)
		elif entry is Dictionary:
			var weight = entry.get("weight", 1)
			var plain := str(int(weight)) if typeof(weight) in [TYPE_INT, TYPE_FLOAT] and is_equal_approx(float(weight), round(float(weight))) else str(weight)
			parts.append("%s:%s" % [str(entry.get("npc", "")), plain] if str(weight) != "1" else str(entry.get("npc", "")))
	return ", ".join(parts)


static func monsters_from_text(text: String) -> Array:
	var out: Array = []
	for part in text.split(",", false):
		var bits := str(part).strip_edges().split(":")
		var id := str(bits[0]).strip_edges()
		if id == "": continue
		if bits.size() > 1 and str(bits[1]).strip_edges().is_valid_float() and not is_equal_approx(float(str(bits[1]).strip_edges()), 1.0):
			var weight := float(str(bits[1]).strip_edges())
			out.append({"npc": id, "weight": int(weight) if is_equal_approx(weight, round(weight)) else weight})
		else:
			out.append(id)
	return out


func build(id: String, data: Dictionary):
	cur_id = id
	cur_data = data
	container.add_child(InspectorStyle.create_section_header("ENCOUNTER ZONE: %s" % id.to_upper(), Color(0.95, 0.6, 0.45)))
	_text_row("Region it covers", "region", "EncounterRegion", "region id", true)
	container.add_child(InspectorStyle.lbl("Only these rooms of it (comma-separated; empty: the whole region)", InspectorStyle.COLOR_TEXT_DIM))
	var rooms := LineEdit.new(); rooms.name = "EncounterRooms"
	rooms.text = ", ".join(PackedStringArray(cur_data.get("rooms", []))) if cur_data.get("rooms") is Array else ""
	InspectorStyle.apply_input_style(rooms)
	rooms.text_changed.connect(func(text):
		var values: Array = []
		for part in text.split(","):
			if part.strip_edges() != "": values.append(part.strip_edges())
		if values.is_empty(): cur_data.erase("rooms")
		else: cur_data["rooms"] = values
		database_modified.emit())
	container.add_child(rooms)
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.lbl("What may come (NPC template ids; 'id:3' weights it three times as likely)", InspectorStyle.COLOR_TEXT_DIM))
	var monsters := LineEdit.new(); monsters.name = "EncounterMonsters"
	monsters.text = monsters_text(cur_data.get("monsters", []))
	monsters.placeholder_text = "slime:3, drakee"
	InspectorStyle.apply_input_style(monsters)
	monsters.text_changed.connect(func(text):
		cur_data["monsters"] = monsters_from_text(text)
		database_modified.emit())
	container.add_child(monsters)
	_number_row("Chance on arriving in one of its rooms (0 to 1)", "chance", "EncounterChance", 0.0, 1.0, 0.01, true)
	_count_rows()
	_number_row("Seconds before another may find the same player (0: none)", "cooldown", "EncounterCooldown", 0.0, 3600.0, 1.0, false)
	_text_row("Said when something comes ({name} is what came)", "message", "EncounterMessage", "{name} appears!", false)
	var gate := VBoxContainer.new(); gate.name = "EncounterWhen"; container.add_child(gate)
	_build_when(gate)
	_text_row("Note (for authors; the game never shows it)", "note", "EncounterNote", "what this zone is for", false)
	_build_extras()


func _text_row(label: String, key: String, node_name: String, placeholder: String, keep_key: bool) -> void:
	container.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var field := LineEdit.new(); field.name = node_name
	field.text = str(cur_data.get(key, "")); field.placeholder_text = placeholder
	InspectorStyle.apply_input_style(field)
	field.text_changed.connect(func(text):
		if text.strip_edges() == "" and not keep_key: cur_data.erase(key)
		else: cur_data[key] = text
		database_modified.emit())
	container.add_child(field)


# A number the author fills in. `keep_key` keeps it written even at 0 (the chance must be said); the others erase at 0.
func _number_row(label: String, key: String, node_name: String, low: float, high: float, step: float, keep_key: bool) -> void:
	container.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var spin := SpinBox.new(); spin.name = node_name; spin.min_value = low; spin.max_value = high; spin.step = step
	spin.value = float(cur_data.get(key, 0.0)); InspectorStyle.apply_input_style(spin)
	spin.value_changed.connect(func(value):
		if value <= 0.0 and not keep_key: cur_data.erase(key)
		else: cur_data[key] = int(value) if is_equal_approx(value, round(value)) and step >= 1.0 else value
		database_modified.emit())
	container.add_child(spin)


# `count` is a whole number, or [least, most]; one at 1 and the same most erases it (the default is one).
func _count_rows() -> void:
	var count = cur_data.get("count", 1)
	var low := 1
	var high := 1
	if count is Array and count.size() == 2: low = int(count[0]); high = int(count[1])
	elif typeof(count) in [TYPE_INT, TYPE_FLOAT]: low = int(count); high = int(count)
	container.add_child(InspectorStyle.lbl("How many come (least, most)", InspectorStyle.COLOR_TEXT_DIM))
	var row := HBoxContainer.new(); container.add_child(row)
	var least := SpinBox.new(); least.name = "EncounterLeast"; least.min_value = 1; least.max_value = 12; least.step = 1; least.value = low
	var most := SpinBox.new(); most.name = "EncounterMost"; most.min_value = 1; most.max_value = 12; most.step = 1; most.value = high
	for spin in [least, most]:
		InspectorStyle.apply_input_style(spin)
		spin.value_changed.connect(func(_value): _write_count(least, most))
		row.add_child(spin)


func _write_count(least: SpinBox, most: SpinBox) -> void:
	var low := int(least.value)
	var high := maxi(low, int(most.value))
	if low == 1 and high == 1: cur_data.erase("count")
	elif low == high: cur_data["count"] = low
	else: cur_data["count"] = [low, high]
	database_modified.emit()


# A condition the player must meet for the zone to be live (a world that goes quiet once a flag is set).
func _build_when(holder: VBoxContainer) -> void:
	for child in holder.get_children():
		holder.remove_child(child)
		child.queue_free()
	CONDITION_ROWS.build(
		holder, cur_data.get("when"), database_mgr, "Only while", "(always)",
		func(): database_modified.emit(),
		func(kind: String):
			if kind == "": cur_data.erase("when")
			else: cur_data["when"] = {"kind": kind}
			database_modified.emit()
			_build_when(holder),
		func(replacement: Dictionary):
			cur_data["when"] = replacement
			database_modified.emit()
	)


# Anything this inspector does not model: named, and left exactly as it is.
func _build_extras() -> void:
	var extras: Array = []
	for key in cur_data:
		if not SCHEMA.KEYS.has(str(key)):
			extras.append(key)
	extras.sort()
	if extras.is_empty():
		return
	var note := Label.new()
	note.text = "Other zone fields (kept as authored): %s" % ", ".join(extras)
	note.add_theme_font_size_override("font_size", 11)
	note.modulate = Color(0.7, 0.72, 0.6)
	container.add_child(note)
