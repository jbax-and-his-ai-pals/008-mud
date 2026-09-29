# scripts/ui/inspectors/sub_inspectors/TriggerInspector.gd
#
# One trigger (`data/triggers/*.json`, `engine/world/triggers.py`): something that happens
# when the player walks into a room. Its condition and its effects are the same rows a
# conversation uses (`ConditionRows`, `EffectRows`), so what can be said there can be said
# here. Opening a trigger writes nothing; keys this inspector does not model survive.
#
# Reached through `preload`, not a `class_name` (see TriggerSchema.gd).
extends RefCounted

signal database_modified

const SCHEMA = preload("res://scripts/data/TriggerSchema.gd")
const EFFECT_ROWS = preload("res://scripts/ui/inspectors/panels/EffectRows.gd")
const CONDITION_ROWS = preload("res://scripts/ui/inspectors/panels/ConditionRows.gd")

var container: VBoxContainer
var cur_data: Dictionary
var cur_id: String
var database_mgr: DatabaseManager


func _init(c: VBoxContainer, db_mgr: DatabaseManager):
	container = c
	database_mgr = db_mgr


## A new trigger is valid before anything is typed: a room to fire in (the first the set
## has, when it has one) and one line of narration. Never a placeholder the validator
## would refuse.
static func data_defaults() -> Dictionary:
	var trigger := {"effects": {"message": "Something happens here."}}
	var refs := room_refs()
	if not refs.is_empty():
		var parts: PackedStringArray = str(refs[0]).split(":")
		trigger["on"] = {"event": "on_enter", "region": parts[0], "room": parts[1]}
	return trigger


## Every `region:room` this set defines, read from the region files the engine reads.
static func room_refs() -> Array:
	var refs: Array = []
	var dir_path := DataRoot.content_dir("regions")
	var dir := DirAccess.open(dir_path)
	if dir == null:
		return refs
	var files: Array = []
	for file_name in dir.get_files():
		if file_name.ends_with(".json"):
			files.append(file_name)
	files.sort()
	for file_name in files:
		var region = JSON.parse_string(FileAccess.get_file_as_string(dir_path.path_join(file_name)))
		if not (region is Dictionary) or region.get("themes") is Dictionary:
			continue
		var region_id := str(region.get("region_id", file_name.get_basename())).strip_edges()
		var rooms = region.get("rooms", {})
		if region_id == "" or not (rooms is Dictionary):
			continue
		for room_id in rooms:
			refs.append("%s:%s" % [region_id, str(room_id)])
	return refs


func build(id: String, data: Dictionary):
	cur_id = id
	cur_data = data
	container.add_child(InspectorStyle.create_section_header("TRIGGER: %s" % id.to_upper(), Color(0.95, 0.72, 0.4)))
	_build_when_it_fires()
	container.add_child(HSeparator.new())
	CONDITION_ROWS.build(
		container, cur_data.get("when"), database_mgr, "Only if", "(always)",
		func(): database_modified.emit(),
		func(kind: String):
			if kind == "":
				cur_data.erase("when")
			else:
				cur_data["when"] = {"kind": kind}
			database_modified.emit()
			_rebuild(),
		func(replacement: Dictionary):
			cur_data["when"] = replacement
			database_modified.emit()
	)
	_build_once()
	container.add_child(HSeparator.new())
	EFFECT_ROWS.build(container, cur_data, "Effects (what happens):", database_mgr, func(): database_modified.emit())
	_build_note()
	_build_extras()


func _rebuild():
	for child in container.get_children():
		container.remove_child(child)
		child.queue_free()
	build(cur_id, cur_data)


func _on() -> Dictionary:
	var on = cur_data.get("on")
	return on if on is Dictionary else {}


func _set_on(key: String, value) -> void:
	var on := _on()
	on[key] = value
	if not on.has("event"):
		on["event"] = SCHEMA.EVENTS[0]
	cur_data["on"] = on
	database_modified.emit()


func _build_when_it_fires() -> void:
	var card = InspectorStyle.create_card()
	var vbox = card.get_child(0).get_child(0)
	container.add_child(InspectorStyle.create_sub_header("Fires when"))
	container.add_child(card)

	var event_row := HBoxContainer.new()
	event_row.add_child(InspectorStyle.lbl("Event:", InspectorStyle.COLOR_TEXT_DIM))
	var event_picker := OptionButton.new()
	event_picker.name = "TriggerEvent"
	var events: Array = SCHEMA.EVENTS.duplicate()
	var current_event := str(_on().get("event", SCHEMA.EVENTS[0]))
	if not events.has(current_event):
		events.append(current_event)   # an event this editor does not know stays visible
	for event in events:
		event_picker.add_item("the player enters a room" if str(event) == "on_enter" else str(event))
		event_picker.set_item_metadata(event_picker.item_count - 1, str(event))
	event_picker.select(events.find(current_event))
	event_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_button_style(event_picker)
	event_picker.item_selected.connect(func(index): _set_on("event", str(event_picker.get_item_metadata(index))))
	event_row.add_child(event_picker)
	vbox.add_child(event_row)

	var room_row := HBoxContainer.new()
	room_row.add_child(InspectorStyle.lbl("Room:", InspectorStyle.COLOR_TEXT_DIM))
	var room_picker := OptionButton.new()
	room_picker.name = "TriggerRoom"
	var refs := room_refs()
	var current_ref := ""
	if _on().has("region") and _on().has("room"):
		current_ref = "%s:%s" % [str(_on()["region"]), str(_on()["room"])]
	var choices: Array = refs.duplicate()
	if current_ref != "" and not choices.has(current_ref):
		choices.append(current_ref)   # a room the set does not define stays visible, so it can be fixed
	room_picker.add_item("(choose a room)")
	room_picker.set_item_metadata(0, "")
	for ref in choices:
		room_picker.add_item(str(ref) if refs.has(ref) else "Missing: %s" % ref)
		room_picker.set_item_metadata(room_picker.item_count - 1, str(ref))
	room_picker.select(choices.find(current_ref) + 1 if current_ref != "" else 0)
	room_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_button_style(room_picker)
	room_picker.item_selected.connect(func(index):
		var ref := str(room_picker.get_item_metadata(index))
		if ref == "":
			return
		var parts: PackedStringArray = ref.split(":")
		var on := _on()
		on["region"] = parts[0]
		on["room"] = parts[1]
		if not on.has("event"):
			on["event"] = SCHEMA.EVENTS[0]
		cur_data["on"] = on
		database_modified.emit()
	)
	room_row.add_child(room_picker)
	vbox.add_child(room_row)


func _build_once() -> void:
	var row := HBoxContainer.new()
	row.add_child(InspectorStyle.lbl("How often:", InspectorStyle.COLOR_TEXT_DIM))
	var picker := OptionButton.new()
	picker.name = "TriggerOnce"
	for choice in SCHEMA.ONCE_CHOICES:
		picker.add_item(str(choice["label"]))
		picker.set_item_metadata(picker.item_count - 1, str(choice["value"]))
	var current: String = SCHEMA.once_choice_of(cur_data)
	for index in range(picker.item_count):
		if str(picker.get_item_metadata(index)) == current:
			picker.select(index)
	picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	picker.tooltip_text = "Once for each player is a flag on the player; once for the whole world is a latch in the world's own state, which a restart keeps."
	InspectorStyle.apply_button_style(picker)
	picker.item_selected.connect(func(index):
		SCHEMA.set_once_choice(cur_data, str(picker.get_item_metadata(index)))
		database_modified.emit()
	)
	row.add_child(picker)
	container.add_child(row)


func _build_note() -> void:
	var row := HBoxContainer.new()
	row.add_child(InspectorStyle.lbl("Note:", InspectorStyle.COLOR_TEXT_DIM))
	var note := LineEdit.new()
	note.name = "TriggerNote"
	note.text = str(cur_data.get("note", ""))
	note.placeholder_text = "for authors; the game never reads it"
	note.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(note)
	note.text_changed.connect(func(text):
		var trimmed := str(text).strip_edges()
		if trimmed == "":
			cur_data.erase("note")
		else:
			cur_data["note"] = str(text)
		database_modified.emit()
	)
	row.add_child(note)
	container.add_child(row)


func _build_extras() -> void:
	var extras: Array = []
	for key in cur_data:
		if not SCHEMA.KEYS.has(str(key)):
			extras.append(str(key))
	extras.sort()
	if extras.is_empty():
		return
	var note := Label.new()
	note.text = "Other trigger fields (kept as authored): %s" % ", ".join(extras)
	note.add_theme_font_size_override("font_size", 11)
	note.modulate = Color(0.7, 0.72, 0.6)
	container.add_child(note)
