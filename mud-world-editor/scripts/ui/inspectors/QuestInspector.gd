# scripts/ui/inspectors/QuestInspector.gd
class_name QuestInspector
extends RefCounted

signal data_modified
signal database_modified
signal request_graph_edit(quest_id) # New Signal

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
	if not cur_data.has("stages"): cur_data["stages"] = []
	
	container.add_child(InspectorStyle.create_section_header("QUEST CONFIG", Color.GOLD))
	var card = InspectorStyle.create_card()
	var vbox = card.get_child(0).get_child(0)
	container.add_child(card)
	
	vbox.add_child(InspectorStyle.lbl("Quest ID: " + cur_id, Color.WHITE))
	
	# Graph Edit Button
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
	
	_build_stages_section()

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
	
	stages_box = VBoxContainer.new()
	stages_box.add_theme_constant_override("separation", 12)
	container.add_child(stages_box)
	
	_refresh_stages()

func _refresh_stages():
	for c in stages_box.get_children(): c.queue_free()
	
	var stages = cur_data.get("stages", [])
	for i in range(stages.size()):
		stages_box.add_child(_create_stage_card(stages[i], i))

func _add_stage():
	var new_stage = {
		"id": "stage_" + str(cur_data.stages.size() + 1),
		"description": "",
		"type": "KILL",
		"target": "",
		"count": 1,
		"next": "",
		"_editor_pos": [cur_data.stages.size() * 200, 0] # Auto position
	}
	cur_data.stages.append(new_stage)
	database_modified.emit()
	_refresh_stages()

func _create_stage_card(stage: Dictionary, index: int) -> PanelContainer:
	var pc = InspectorStyle.create_card()
	var vbox = pc.get_child(0).get_child(0)
	
	# Header
	var hb_top = HBoxContainer.new()
	var lbl_idx = InspectorStyle.lbl("Stage %d" % (index + 1), Color.CYAN)
	hb_top.add_child(lbl_idx)
	
	var ed_id = LineEdit.new(); ed_id.text = stage.get("id", ""); ed_id.placeholder_text = "Stage ID"
	ed_id.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(ed_id)
	ed_id.text_changed.connect(func(t): stage.id = t; database_modified.emit())
	hb_top.add_child(ed_id)
	
	var btn_del = Button.new(); btn_del.text = "X"
	InspectorStyle.apply_button_style(btn_del, Color(0.4, 0.1, 0.1))
	btn_del.pressed.connect(func(): cur_data.stages.remove_at(index); database_modified.emit(); _refresh_stages())
	hb_top.add_child(btn_del)
	vbox.add_child(hb_top)
	
	# Description
	var ed_desc = LineEdit.new(); ed_desc.text = stage.get("description", ""); ed_desc.placeholder_text = "Journal Entry / Description"
	InspectorStyle.apply_input_style(ed_desc)
	ed_desc.text_changed.connect(func(t): stage.description = t; database_modified.emit())
	vbox.add_child(ed_desc)
	
	# Logic Row
	var hb_logic = HBoxContainer.new()
	
	# Type
	var opt_type = OptionButton.new()
	var types = ["KILL", "COLLECT", "TALK", "GOTO", "INTERACT"]
	for t in types: opt_type.add_item(t)
	var curr_type = stage.get("type", "KILL")
	var type_idx = types.find(curr_type)
	if type_idx != -1: opt_type.selected = type_idx
	InspectorStyle.apply_button_style(opt_type)
	opt_type.item_selected.connect(func(idx): stage.type = types[idx]; database_modified.emit())
	hb_logic.add_child(opt_type)
	
	# Target (Smart Suggestion based on type)
	var ed_target = LineEdit.new(); ed_target.text = str(stage.get("target", ""))
	ed_target.placeholder_text = "Target ID"
	ed_target.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(ed_target)
	ed_target.text_changed.connect(func(t): stage.target = t; database_modified.emit())
	hb_logic.add_child(ed_target)
	
	# Suggestion Button
	InspectorStyle.add_suggestion_button(hb_logic, ed_target, func():
		var t = opt_type.get_item_text(opt_type.selected)
		if t == "KILL" or t == "TALK": return database_mgr.get_npc_ids()
		if t == "COLLECT": return database_mgr.get_item_ids()
		return [] # No suggestions for GOTO yet (needs room list access)
	)
	
	# Count
	var sb_count = SpinBox.new(); sb_count.value = stage.get("count", 1)
	sb_count.tooltip_text = "Required Count"
	InspectorStyle.apply_input_style(sb_count)
	sb_count.value_changed.connect(func(v): stage.count = v; database_modified.emit())
	hb_logic.add_child(sb_count)
	
	vbox.add_child(hb_logic)
	
	# Next Stage
	var hb_next = HBoxContainer.new()
	hb_next.add_child(InspectorStyle.lbl("Next:", Color.GRAY))
	var ed_next = LineEdit.new(); ed_next.text = stage.get("next", ""); ed_next.placeholder_text = "Next Stage ID (empty = finish)"
	ed_next.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(ed_next)
	ed_next.text_changed.connect(func(t): stage.next = t; database_modified.emit())
	hb_next.add_child(ed_next)
	vbox.add_child(hb_next)
	
	return pc
