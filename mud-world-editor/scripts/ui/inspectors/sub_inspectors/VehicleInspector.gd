# scripts/ui/inspectors/sub_inspectors/VehicleInspector.gd
#
# One vehicle (`data/vehicles/*.json`, `engine/world/vehicles.py`): something the player boards to go where they cannot
# go on foot. Its name, what it looks like, the room it waits in at the start, the words said when the player climbs
# aboard and down, and the biomes it may be set down in. Opening a vehicle writes nothing; a field cleared is erased,
# and keys this inspector does not model survive.
#
# Reached through `preload`, not a `class_name` (see VehicleSchema.gd).
extends RefCounted

signal database_modified

const SCHEMA = preload("res://scripts/data/VehicleSchema.gd")

var container: VBoxContainer
var cur_data: Dictionary
var cur_id: String
var database_mgr: DatabaseManager


func _init(c: VBoxContainer, db_mgr: DatabaseManager):
	container = c
	database_mgr = db_mgr


## A new vehicle is valid before anything else is typed: it has a name.
static func data_defaults() -> Dictionary:
	return {"name": "the new vehicle"}


func build(id: String, data: Dictionary):
	cur_id = id
	cur_data = data
	container.add_child(InspectorStyle.create_section_header("VEHICLE: %s" % id.to_upper(), Color(0.6, 0.85, 0.9)))
	_text_row("Name (how the game calls it)", "name", "VehicleName", "the skimmer", true)
	_text_row("Description", "description", "VehicleDescription", "what it looks like", false)
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Where it waits at the start"))
	_start_rows()
	container.add_child(HSeparator.new())
	_text_row("Said when the player climbs aboard", "board_text", "VehicleBoardText", "You climb aboard.", false)
	_text_row("Said when the player climbs down", "disembark_text", "VehicleDisembarkText", "You climb down.", false)
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.lbl("May be set down in these biomes (comma-separated; empty: anywhere). A room can always allow it with its `docks` property.", InspectorStyle.COLOR_TEXT_DIM))
	var biomes := LineEdit.new(); biomes.name = "VehicleBiomes"
	biomes.text = ", ".join(PackedStringArray(cur_data.get("lands_in_biomes", []))) if cur_data.get("lands_in_biomes") is Array else ""
	biomes.placeholder_text = "desert, plain"
	InspectorStyle.apply_input_style(biomes)
	biomes.text_changed.connect(func(text):
		var values: Array = []
		for part in text.split(","):
			if part.strip_edges() != "": values.append(part.strip_edges())
		if values.is_empty(): cur_data.erase("lands_in_biomes")
		else: cur_data["lands_in_biomes"] = values
		database_modified.emit())
	container.add_child(biomes)
	_text_row("Note (for authors; the game never shows it)", "note", "VehicleNote", "what this vehicle is for", false)
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


# The start is `{region, room}` or absent: both boxes empty erases it; one filled in is kept as typed (the engine
# validator refuses half of one).
func _start_rows() -> void:
	var start: Dictionary = cur_data.get("start", {}) if cur_data.get("start") is Dictionary else {}
	var region := LineEdit.new(); region.name = "VehicleStartRegion"; region.text = str(start.get("region", "")); region.placeholder_text = "region id"
	var room := LineEdit.new(); room.name = "VehicleStartRoom"; room.text = str(start.get("room", "")); room.placeholder_text = "room id"
	for field in [region, room]:
		InspectorStyle.apply_input_style(field)
		field.text_changed.connect(func(_text): _write_start(region, room))
		container.add_child(field)


func _write_start(region: LineEdit, room: LineEdit) -> void:
	var region_id := region.text.strip_edges()
	var room_id := room.text.strip_edges()
	if region_id == "" and room_id == "":
		cur_data.erase("start")
	else:
		cur_data["start"] = {"region": region_id, "room": room_id}
	database_modified.emit()


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
	note.text = "Other vehicle fields (kept as authored): %s" % ", ".join(extras)
	note.add_theme_font_size_override("font_size", 11)
	note.modulate = Color(0.7, 0.72, 0.6)
	container.add_child(note)
