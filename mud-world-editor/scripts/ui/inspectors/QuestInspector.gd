# scripts/ui/inspectors/QuestInspector.gd
#
# Quest authoring, against the schema the engine actually reads.
#
# The previous version of this file wrote `{id, description, type: "KILL",
# target, count, next}` per stage. The engine reads `stage.objective.type` and
# routes only the types it knows, and stage order is the list order
# (`stage_index`), not a `next` pointer. A stage added there therefore passed
# content validation with zero errors and could never be completed -- the worst
# kind of editor bug, because it looks like it works. `QuestSchema` holds the
# engine's vocabulary; `QuestObjectiveEditor` edits one objective; this file
# arranges the stages, the alternative routes, the turn-in and the dialogue.
#
# Every key this inspector does not model is preserved untouched, including the
# engine's own runtime bookkeeping (`_spawn_on_entry_triggered` and friends),
# because a stage is written back verbatim apart from what the author changed.

class_name QuestInspector
extends RefCounted

signal data_modified
signal database_modified
signal request_graph_edit(quest_id)

var container: VBoxContainer
var database_mgr: DatabaseManager
var world_mgr: WorldManager
var cur_id: String
var cur_data: Dictionary

var stages_box: VBoxContainer


func _init(c: VBoxContainer, db_mgr: DatabaseManager, w_mgr: WorldManager):
	container = c
	database_mgr = db_mgr
	world_mgr = w_mgr


func build(id: String, data: Dictionary):
	cur_id = id
	cur_data = data
	if not cur_data.has("stages") or not (cur_data["stages"] is Array):
		cur_data["stages"] = []

	container.add_child(InspectorStyle.create_section_header("QUEST CONFIG", Color.GOLD))
	var card = InspectorStyle.create_card()
	var vbox = card.get_child(0).get_child(0)
	container.add_child(card)

	vbox.add_child(InspectorStyle.lbl("Quest ID: " + cur_id, Color.WHITE))

	var btn_graph = Button.new(); btn_graph.text = "Visualize Graph"
	InspectorStyle.apply_button_style(btn_graph, Color.VIOLET)
	btn_graph.pressed.connect(func(): request_graph_edit.emit(cur_id))
	vbox.add_child(btn_graph)
	vbox.add_child(HSeparator.new())

	vbox.add_child(InspectorStyle.lbl("Title:", InspectorStyle.COLOR_TEXT_DIM))
	var title_ed = LineEdit.new(); title_ed.text = cur_data.get("title", "")
	title_ed.text_changed.connect(func(t): cur_data.title = t; database_modified.emit())
	InspectorStyle.apply_input_style(title_ed); vbox.add_child(title_ed)

	vbox.add_child(InspectorStyle.lbl("Summary:", InspectorStyle.COLOR_TEXT_DIM))
	var desc_ed = TextEdit.new(); desc_ed.custom_minimum_size.y = 60
	desc_ed.text = cur_data.get("description", "")
	desc_ed.text_changed.connect(func(): cur_data.description = desc_ed.text; database_modified.emit())
	InspectorStyle.apply_input_style(desc_ed); vbox.add_child(desc_ed)
	_add_quest_extras()

	_build_stages_section()


func _add_quest_extras():
	var known := ["title", "description", "type", "stages", "rewards"]
	var extras: Array = []
	for key in cur_data:
		if not known.has(str(key)):
			extras.append(key)
	extras.sort()
	if extras.is_empty():
		return
	var note := Label.new()
	note.text = "Other quest fields (kept as authored): %s" % ", ".join(extras)
	note.add_theme_font_size_override("font_size", 11)
	note.modulate = Color(0.7, 0.72, 0.6)
	container.add_child(note)


# --- stages -------------------------------------------------------------------

func _build_stages_section():
	container.add_child(HSeparator.new())
	var header_box = HBoxContainer.new()
	header_box.add_child(InspectorStyle.create_section_header("QUEST STAGES", Color.CYAN))
	var spacer = Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header_box.add_child(spacer)

	var btn_add = Button.new(); btn_add.text = "+ Add Stage"
	InspectorStyle.apply_button_style(btn_add, Color(0.2, 0.3, 0.4))
	btn_add.pressed.connect(_add_stage)
	header_box.add_child(btn_add)
	container.add_child(header_box)

	var hint := Label.new()
	hint.text = "Stages run in order; a stage is satisfied by its objective or by any one of its alternative routes."
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.add_theme_font_size_override("font_size", 11)
	hint.modulate = Color(0.65, 0.68, 0.74)
	container.add_child(hint)

	stages_box = VBoxContainer.new()
	stages_box.add_theme_constant_override("separation", 12)
	container.add_child(stages_box)

	_refresh_stages()


func _refresh_stages():
	for c in stages_box.get_children(): c.queue_free()
	var stages: Array = cur_data.get("stages", [])
	for index in range(stages.size()):
		if stages[index] is Dictionary:
			stages_box.add_child(_create_stage_card(stages[index], index))


func _add_stage():
	var stages: Array = cur_data.get("stages", [])
	var stage := {
		"stage_index": stages.size(),
		"description": "",
		"objective": {"type": "kill"},
	}
	stages.append(stage)
	cur_data["stages"] = stages
	database_modified.emit()
	_refresh_stages()


func _create_stage_card(stage: Dictionary, index: int) -> PanelContainer:
	var pc = InspectorStyle.create_card()
	var vbox = pc.get_child(0).get_child(0)

	var hb_top = HBoxContainer.new()
	hb_top.add_child(InspectorStyle.lbl("Stage %d" % (index + 1), Color.CYAN))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	hb_top.add_child(spacer)

	var move_up := Button.new(); move_up.text = "↑"
	move_up.tooltip_text = "Move this stage earlier"
	move_up.disabled = index == 0
	InspectorStyle.apply_button_style(move_up)
	move_up.pressed.connect(func(): _move_stage(index, -1))
	hb_top.add_child(move_up)

	var move_down := Button.new(); move_down.text = "↓"
	move_down.tooltip_text = "Move this stage later"
	move_down.disabled = index == cur_data.stages.size() - 1
	InspectorStyle.apply_button_style(move_down)
	move_down.pressed.connect(func(): _move_stage(index, 1))
	hb_top.add_child(move_down)

	var btn_del = Button.new(); btn_del.text = "X"
	btn_del.tooltip_text = "Remove this stage"
	InspectorStyle.apply_button_style(btn_del, Color(0.4, 0.1, 0.1))
	btn_del.pressed.connect(func(): _remove_stage(index))
	hb_top.add_child(btn_del)
	vbox.add_child(hb_top)

	var ed_desc = LineEdit.new(); ed_desc.text = stage.get("description", "")
	ed_desc.placeholder_text = "Journal entry for this stage"
	InspectorStyle.apply_input_style(ed_desc)
	ed_desc.text_changed.connect(func(t): stage["description"] = t; database_modified.emit())
	vbox.add_child(ed_desc)

	_add_objective_section(vbox, stage, index)
	_add_alternative_routes(vbox, stage, index)
	_add_stage_tail_fields(vbox, stage)
	_add_other_stage_keys(vbox, stage)
	return pc


func _add_objective_section(vbox: VBoxContainer, stage: Dictionary, index: int):
	var header := Label.new()
	header.text = "Objective"
	header.add_theme_font_size_override("font_size", 12)
	header.modulate = Color(0.8, 0.85, 0.95)
	vbox.add_child(header)

	if not (stage.get("objective") is Dictionary):
		stage["objective"] = {}
	var objective: Dictionary = stage["objective"]
	var editor := QuestObjectiveEditor.new(vbox, objective, database_mgr)
	editor.changed.connect(func(): database_modified.emit())
	editor.rebuild_requested.connect(_refresh_stages)
	editor.build()


# `objectives_any`: completing any one route satisfies the stage (manager.py).
func _add_alternative_routes(vbox: VBoxContainer, stage: Dictionary, index: int):
	var routes: Array = stage.get("objectives_any", []) if stage.get("objectives_any") is Array else []
	var header := HBoxContainer.new()
	var label := InspectorStyle.lbl("Alternative routes (any one satisfies the stage)", InspectorStyle.COLOR_TEXT_DIM)
	label.add_theme_font_size_override("font_size", 11)
	header.add_child(label)
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var add := Button.new(); add.text = "+ Route"
	InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var list: Array = stage.get("objectives_any", [])
		list.append({"type": "kill"})
		stage["objectives_any"] = list
		database_modified.emit()
		_refresh_stages()
	)
	header.add_child(add)
	vbox.add_child(header)

	if routes.is_empty():
		return
	for route_index in range(routes.size()):
		if not (routes[route_index] is Dictionary):
			continue
		var row := HBoxContainer.new()
		var remove := Button.new(); remove.text = "X"
		remove.tooltip_text = "Remove this route"
		InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			(routes as Array).remove_at(route_index)
			if routes.is_empty(): stage.erase("objectives_any")
			database_modified.emit()
			_refresh_stages()
		)
		row.add_child(remove)
		vbox.add_child(row)

		var route: Dictionary = routes[route_index]
		var editor := QuestObjectiveEditor.new(vbox, route, database_mgr)
		editor.changed.connect(func(): database_modified.emit())
		editor.rebuild_requested.connect(_refresh_stages)
		editor.build()


func _add_stage_tail_fields(vbox: VBoxContainer, stage: Dictionary):
	var grid := VBoxContainer.new()
	grid.add_theme_constant_override("separation", 4)
	vbox.add_child(grid)

	# turn_in_id
	var turn_row := HBoxContainer.new()
	var turn_label := InspectorStyle.lbl("Turn in to", InspectorStyle.COLOR_TEXT_DIM)
	turn_label.custom_minimum_size.x = 210
	turn_row.add_child(turn_label)
	var turn := LineEdit.new(); turn.text = str(stage.get("turn_in_id", ""))
	turn.placeholder_text = "npc template id"
	turn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(turn)
	turn.text_changed.connect(func(t):
		if t.strip_edges() == "": stage.erase("turn_in_id")
		else: stage["turn_in_id"] = t.strip_edges()
		database_modified.emit()
	)
	turn_row.add_child(turn)
	InspectorStyle.add_suggestion_button(turn_row, turn, func(): return database_mgr.get_npc_ids())
	grid.add_child(turn_row)

	# completion_dialogue
	var dialogue_header := HBoxContainer.new()
	var dialogue_label := InspectorStyle.lbl("Completion dialogue", InspectorStyle.COLOR_TEXT_DIM)
	dialogue_label.add_theme_font_size_override("font_size", 11)
	dialogue_header.add_child(dialogue_label)
	grid.add_child(dialogue_header)
	var dialogue := TextEdit.new()
	dialogue.custom_minimum_size.y = 48
	dialogue.text = str(stage.get("completion_dialogue", ""))
	InspectorStyle.apply_input_style(dialogue)
	dialogue.text_changed.connect(func():
		var text := dialogue.text
		if text.strip_edges() == "": stage.erase("completion_dialogue")
		else: stage["completion_dialogue"] = text
		database_modified.emit()
	)
	grid.add_child(dialogue)

	# spawn_on_entry, using the field names manager.py reads.
	_add_spawn_row(grid, stage, "spawn_on_entry")
	_add_spawn_row(grid, stage, "spawn_on_start")


func _add_spawn_row(grid: VBoxContainer, stage: Dictionary, key: String):
	var row := HBoxContainer.new()
	var label := InspectorStyle.lbl(key.replace("_", " ").capitalize(), InspectorStyle.COLOR_TEXT_DIM)
	label.custom_minimum_size.x = 210
	label.tooltip_text = str(QuestSchema.STAGE_FIELDS.get(key, ""))
	row.add_child(label)
	var line := LineEdit.new()
	line.placeholder_text = "{template_id, region_id, room_id}"
	line.text = JSON.stringify(stage.get(key)) if stage.has(key) else ""
	line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(line)
	line.text_changed.connect(func(text):
		var trimmed: String = str(text).strip_edges()
		if trimmed == "":
			stage.erase(key)
			line.modulate = Color.WHITE
		else:
			var parsed = JSON.parse_string(trimmed)
			if typeof(parsed) == TYPE_DICTIONARY:
				stage[key] = parsed
				line.modulate = Color.WHITE
			else:
				line.modulate = Color(1.0, 0.6, 0.6)
		database_modified.emit()
	)
	row.add_child(line)
	grid.add_child(row)


# Anything else this inspector does not model: named, and left exactly as it is.
func _add_other_stage_keys(vbox: VBoxContainer, stage: Dictionary):
	var modelled := ["stage_index", "description", "objective", "objectives_any",
		"turn_in_id", "completion_dialogue", "spawn_on_entry", "spawn_on_start"]
	var extras: Array = []
	for key in stage:
		if not modelled.has(str(key)):
			extras.append(key)
	extras.sort()
	if extras.is_empty():
		return
	var note := Label.new()
	note.text = "Other stage fields (kept as authored): %s" % ", ".join(extras)
	note.add_theme_font_size_override("font_size", 11)
	note.modulate = Color(0.7, 0.72, 0.6)
	vbox.add_child(note)


# --- structure ----------------------------------------------------------------

func _remove_stage(index: int):
	var stages: Array = cur_data.get("stages", [])
	if index < 0 or index >= stages.size():
		return
	stages.remove_at(index)
	_renumber_stages()
	database_modified.emit()
	_refresh_stages()


func _move_stage(index: int, delta: int):
	var stages: Array = cur_data.get("stages", [])
	var target := index + delta
	if target < 0 or target >= stages.size():
		return
	var stage = stages[index]
	stages[index] = stages[target]
	stages[target] = stage
	_renumber_stages()
	database_modified.emit()
	_refresh_stages()


# The engine reads stage order from the list, and `stage_index` is what the
# journal shows; keeping the two in step here means an author never has to.
func _renumber_stages():
	var stages: Array = cur_data.get("stages", [])
	for index in range(stages.size()):
		if stages[index] is Dictionary:
			stages[index]["stage_index"] = index
