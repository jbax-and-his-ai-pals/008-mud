# scripts/ui/inspectors/DatabaseInspector.gd
class_name DatabaseInspector
extends RefCounted

signal data_modified
signal database_modified
## A rename is a question, not an edit: the entry may be named by recipes, loot
## tables or spawner weights, and only the index knows where. Main answers it.
signal request_entry_rename(type, old_id, new_id)

var container: VBoxContainer
var cur_mode: String
var cur_id: String
var cur_data: Dictionary

# Sub Inspectors
var npc_inspector: NPCInspector
var item_inspector: ItemInspector
var magic_inspector: MagicInspector

# Reference
var db_mgr_ref: DatabaseManager 

const NPC_INSP_SCRIPT = preload("res://scripts/ui/inspectors/sub_inspectors/NPCInspector.gd")
const ITEM_INSP_SCRIPT = preload("res://scripts/ui/inspectors/sub_inspectors/ItemInspector.gd")
const MAGIC_INSP_SCRIPT = preload("res://scripts/ui/inspectors/sub_inspectors/MagicInspector.gd")

func _init(c: VBoxContainer):
	container = c

func set_db_manager(mgr):
	db_mgr_ref = mgr

func build(type: String, id: String, data: Dictionary):
	cur_mode = type
	cur_id = id
	cur_data = data
	
	var color = Color.GREEN if type == "npc" else Color.AQUAMARINE
	container.add_child(InspectorStyle.create_section_header("%s DATABASE" % type.to_upper(), color))
	
	_build_header_card()
	
	if type == "npc":
		npc_inspector = NPC_INSP_SCRIPT.new()
		# The manager carries the contract catalog, which the NPC inspector needs
		# for the content set's own stat vocabulary -- and the set's other NPCs,
		# which is where that vocabulary comes from when nothing is declared.
		npc_inspector.build(container, cur_data, db_mgr_ref)
		npc_inspector.database_modified.connect(func(): database_modified.emit())
	elif type == "item":
		item_inspector = ITEM_INSP_SCRIPT.new()
		# The manager carries the contract catalog, which the item inspector needs
		# to offer families and roll tables instead of making the author type ids.
		item_inspector.build(container, cur_data, db_mgr_ref)
		item_inspector.database_modified.connect(func(): database_modified.emit())
	elif type == "magic":
		magic_inspector = MAGIC_INSP_SCRIPT.new()
		# The id and the manager, so the ability's group is filed in the editor's
		# own state rather than written into content the engine refuses.
		magic_inspector.build(container, cur_data, db_mgr_ref.magic_groups, cur_id, db_mgr_ref)
		magic_inspector.database_modified.connect(func(): database_modified.emit())

func _build_header_card():
	var card = InspectorStyle.create_card(); var vbox = card.get_child(0).get_child(0)
	container.add_child(card)
	
	vbox.add_child(InspectorStyle.lbl("ID:", InspectorStyle.COLOR_TEXT_DIM))
	
	var ed_id = LineEdit.new()
	ed_id.text = cur_id
	InspectorStyle.apply_input_style(ed_id)
	ed_id.text_submitted.connect(func(new_id):
		var wanted := str(new_id).strip_edges()
		if wanted != "" and wanted != cur_id:
			request_entry_rename.emit(cur_mode, cur_id, wanted)
	)
	vbox.add_child(ed_id)
	
	# Name
	vbox.add_child(InspectorStyle.lbl("Name:", InspectorStyle.COLOR_TEXT_DIM))
	var ed_name = LineEdit.new(); ed_name.text = cur_data.get("name", "")
	ed_name.text_changed.connect(func(t): cur_data.name=t; database_modified.emit())
	InspectorStyle.apply_input_style(ed_name); vbox.add_child(ed_name)
	
	# Description
	vbox.add_child(InspectorStyle.lbl("Description:", InspectorStyle.COLOR_TEXT_DIM))
	var ed_desc = TextEdit.new(); ed_desc.custom_minimum_size.y=60; ed_desc.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	ed_desc.text = cur_data.get("description", "")
	ed_desc.text_changed.connect(func(): cur_data.description=ed_desc.text; database_modified.emit())
	InspectorStyle.apply_input_style(ed_desc); vbox.add_child(ed_desc)
