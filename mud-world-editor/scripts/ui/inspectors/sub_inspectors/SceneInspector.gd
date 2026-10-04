# scripts/ui/inspectors/sub_inspectors/SceneInspector.gd
#
# One scene (`data/scenes/*.json`, `engine/world/scenes.py`): something the player watches, a few beats told a moment
# apart with things happening between them. Each beat is a line of text, the wait before it, how fast a client types
# it out, and the effects that happen as it is told (the same rows a conversation uses, `EffectRows`): people leave,
# a fight begins, the player is carried somewhere. Opening a scene writes nothing; keys this inspector does not model
# survive.
#
# Reached through `preload`, not a `class_name` (see SceneSchema.gd).
extends RefCounted

signal database_modified

const SCHEMA = preload("res://scripts/data/SceneSchema.gd")
const EFFECT_ROWS = preload("res://scripts/ui/inspectors/panels/EffectRows.gd")
# How fast a client reveals text (engine/utils/pacing.py): the same names a conversation's nodes use.
const TEXT_PACES := {"brisk": 180, "measured": 110, "slow": 70, "solemn": 40}

var container: VBoxContainer
var cur_data: Dictionary
var cur_id: String
var database_mgr: DatabaseManager
var beats_box: VBoxContainer


func _init(c: VBoxContainer, db_mgr: DatabaseManager):
	container = c
	database_mgr = db_mgr


## A new scene is valid before anything is typed: one beat with a line to tell.
static func data_defaults() -> Dictionary:
	return {"beats": [{"text": "Something happens."}]}


func build(id: String, data: Dictionary):
	cur_id = id
	cur_data = data
	if not (cur_data.get("beats") is Array):
		cur_data["beats"] = []
	container.add_child(InspectorStyle.create_section_header("SCENE: %s" % id.to_upper(), Color(0.85, 0.65, 0.95)))
	_build_header()
	container.add_child(HSeparator.new())
	var beats_header := HBoxContainer.new()
	beats_header.add_child(InspectorStyle.create_sub_header("Beats"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	beats_header.add_child(spacer)
	var add := Button.new(); add.name = "AddBeat"; add.text = "+ Beat"
	InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(add_beat)
	beats_header.add_child(add)
	container.add_child(beats_header)
	beats_box = VBoxContainer.new(); beats_box.name = "Beats"
	beats_box.add_theme_constant_override("separation", 8)
	container.add_child(beats_box)
	_fill_beats()
	_build_extras()


func _build_header() -> void:
	var lock := CheckBox.new(); lock.name = "SceneLock"
	lock.text = "The player watches: they cannot act until it ends"
	lock.button_pressed = cur_data.get("lock", true) != false
	lock.toggled.connect(func(on):
		if on:
			cur_data.erase("lock")
		else:
			cur_data["lock"] = false
		database_modified.emit())
	container.add_child(lock)
	container.add_child(InspectorStyle.lbl("Note (for authors; the game never shows it)", InspectorStyle.COLOR_TEXT_DIM))
	var note := LineEdit.new(); note.name = "SceneNote"
	note.text = str(cur_data.get("note", ""))
	note.placeholder_text = "what this scene is for"
	InspectorStyle.apply_input_style(note)
	note.text_changed.connect(func(text):
		if text.strip_edges() == "":
			cur_data.erase("note")
		else:
			cur_data["note"] = text
		database_modified.emit())
	container.add_child(note)


# Public because it is the structural operation a caller (and a test) drives.
func add_beat() -> void:
	var beats: Array = cur_data.get("beats", []) if cur_data.get("beats") is Array else []
	beats.append({"text": ""})
	cur_data["beats"] = beats
	database_modified.emit()
	_fill_beats()


func _clear(node: Node) -> void:
	# Rows are named, so a replaced row must be gone at once (a queued free would leave its name taken).
	for child in node.get_children():
		node.remove_child(child)
		child.queue_free()


func _fill_beats() -> void:
	if beats_box == null:
		return
	_clear(beats_box)
	var beats: Array = cur_data.get("beats", []) if cur_data.get("beats") is Array else []
	if beats.is_empty():
		beats_box.add_child(InspectorStyle.lbl("No beats: a scene needs at least one to tell or do something.", InspectorStyle.COLOR_TEXT_DIM))
	for index in range(beats.size()):
		if beats[index] is Dictionary:
			beats_box.add_child(_beat_card(beats, index))


func _beat_card(beats: Array, index: int) -> PanelContainer:
	var beat: Dictionary = beats[index]
	var pc := InspectorStyle.create_card()
	pc.name = "Beat%d" % index
	var vbox := pc.get_child(0).get_child(0)

	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.lbl("Beat %d" % (index + 1), Color(0.85, 0.65, 0.95)))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	for spec in [["MoveUp", "^", -1], ["MoveDown", "v", 1]]:
		var move := Button.new(); move.name = spec[0]; move.text = spec[1]
		move.tooltip_text = "Tell it earlier" if spec[2] < 0 else "Tell it later"
		move.disabled = index + spec[2] < 0 or index + spec[2] >= beats.size()
		var step: int = spec[2]
		move.pressed.connect(func():
			var held = beats[index]
			beats[index] = beats[index + step]
			beats[index + step] = held
			database_modified.emit()
			_fill_beats())
		header.add_child(move)
	var remove := Button.new(); remove.name = "RemoveBeat"; remove.text = "X"
	remove.tooltip_text = "Remove this beat"
	InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
	remove.pressed.connect(func():
		beats.remove_at(index)
		database_modified.emit()
		_fill_beats())
	header.add_child(remove)
	vbox.add_child(header)

	var text := TextEdit.new(); text.name = "Text"
	text.custom_minimum_size.y = 54
	text.text = str(beat.get("text", ""))
	text.placeholder_text = "What is told (colour and link markup works, as in a conversation)"
	InspectorStyle.apply_input_style(text)
	text.text_changed.connect(func():
		if text.text.strip_edges() == "":
			beat.erase("text")
		else:
			beat["text"] = text.text
		database_modified.emit())
	vbox.add_child(text)

	var timing := HBoxContainer.new()
	timing.add_child(InspectorStyle.lbl("Wait before it (seconds)", InspectorStyle.COLOR_TEXT_DIM))
	var after := SpinBox.new(); after.name = "After"
	after.min_value = 0; after.max_value = SCHEMA.MAX_WAIT; after.step = 0.5; after.custom_minimum_size.x = 80
	after.value = float(beat.get("after", SCHEMA.default_wait(index)))
	InspectorStyle.apply_input_style(after)
	after.value_changed.connect(func(value):
		beat["after"] = int(value) if is_equal_approx(value, round(value)) else snappedf(value, 0.5)
		database_modified.emit())
	timing.add_child(after)
	timing.add_child(InspectorStyle.lbl("Typed", InspectorStyle.COLOR_TEXT_DIM))
	timing.add_child(_pace_picker(beat))
	vbox.add_child(timing)

	EFFECT_ROWS.build(vbox, beat, "Effects (as it is told)", database_mgr, func(): database_modified.emit())
	return pc


## How fast a client types the beat out. Instant is the default and writes nothing; a speed the engine accepts but
## this list has no name for is shown as it is, not replaced.
func _pace_picker(beat: Dictionary) -> OptionButton:
	var picker := OptionButton.new(); picker.name = "Pace"
	var current = beat.get("pace", "")
	picker.add_item("Instant"); picker.set_item_metadata(0, "")
	for pace_name in TEXT_PACES:
		picker.add_item("%s (%d chars/sec)" % [str(pace_name).capitalize(), TEXT_PACES[pace_name]])
		picker.set_item_metadata(picker.item_count - 1, pace_name)
	var selected := 0
	for i in range(picker.item_count):
		if str(picker.get_item_metadata(i)) == str(current): selected = i
	if str(current) != "" and selected == 0 and str(current) != "instant":
		picker.add_item("Custom: %s" % str(current)); picker.set_item_metadata(picker.item_count - 1, current)
		selected = picker.item_count - 1
	picker.select(selected)
	InspectorStyle.apply_button_style(picker)
	picker.item_selected.connect(func(index):
		var value = picker.get_item_metadata(index)
		if str(value) == "":
			if beat.has("pace"):
				beat.erase("pace"); database_modified.emit()
		elif beat.get("pace") != value:
			beat["pace"] = value; database_modified.emit())
	return picker


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
	note.text = "Other scene fields (kept as authored): %s" % ", ".join(extras)
	note.add_theme_font_size_override("font_size", 11)
	note.modulate = Color(0.7, 0.72, 0.6)
	container.add_child(note)
