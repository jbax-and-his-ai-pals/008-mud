# scripts/ui/inspectors/RoomInspector.gd
class_name RoomInspector
extends RefCounted

signal data_modified
signal request_rename(old, new)
signal request_connection_form(id, name)
signal request_save_template(room_id) # New Signal

# Sub-panel controllers
var props_panel: RoomPropertiesPanel
var conn_panel: RoomConnectionsPanel
var content_panel: RoomContentPanel

var container: VBoxContainer
var region_mgr: RegionManager
var database_mgr: DatabaseManager
var world_mgr: WorldManager
var cur_id: String
var cur_data: Dictionary

const PROPS_PANEL_SCRIPT = preload("res://scripts/ui/inspectors/panels/RoomPropertiesPanel.gd")
const CONN_PANEL_SCRIPT = preload("res://scripts/ui/inspectors/panels/RoomConnectionsPanel.gd")
const CONTENT_PANEL_SCRIPT = preload("res://scripts/ui/inspectors/panels/RoomContentPanel.gd")

func _init(c: VBoxContainer, r_mgr: RegionManager, d_mgr: DatabaseManager, w_mgr: WorldManager):
	container = c
	region_mgr = r_mgr
	database_mgr = d_mgr
	world_mgr = w_mgr

func build(id: String, data: Dictionary):
	cur_id = id
	cur_data = data
	
	if not cur_data.has("properties"): cur_data.properties = {}
	if not cur_data.has("exits"): cur_data.exits = {}

	_build_general_info()
	
	props_panel = PROPS_PANEL_SCRIPT.new()
	props_panel.build(container, cur_data.properties)
	props_panel.data_modified.connect(func(): data_modified.emit())

	conn_panel = CONN_PANEL_SCRIPT.new()
	conn_panel.build(container, cur_id, cur_data.get("name", "Unnamed"), cur_data.exits, region_mgr, world_mgr)
	conn_panel.data_modified.connect(func(): data_modified.emit())
	conn_panel.request_connection_form.connect(func(cid, cname): request_connection_form.emit(cid, cname))

	content_panel = CONTENT_PANEL_SCRIPT.new()
	content_panel.build(container, cur_data, database_mgr)
	content_panel.data_modified.connect(func(): data_modified.emit())
	
	# Template Button
	container.add_child(HSeparator.new())
	var btn_tmpl = Button.new(); btn_tmpl.text = "Save as Template"
	btn_tmpl.pressed.connect(func(): request_save_template.emit(cur_id))
	InspectorStyle.apply_button_style(btn_tmpl, Color(0.3, 0.3, 0.2))
	container.add_child(btn_tmpl)

func _build_general_info():
	container.add_child(InspectorStyle.create_section_header("GENERAL INFO", InspectorStyle.COLOR_ACCENT))
	var card = InspectorStyle.create_card()
	var vbox = card.get_child(0).get_child(0)
	container.add_child(card)
	
	var id_box = HBoxContainer.new()
	id_box.add_child(InspectorStyle.lbl("ID:", InspectorStyle.COLOR_TEXT_DIM))
	var id_edit = LineEdit.new(); id_edit.text = cur_id; id_edit.size_flags_horizontal = 3
	id_edit.text_submitted.connect(func(t): request_rename.emit(cur_id, t))
	InspectorStyle.apply_input_style(id_edit)
	id_box.add_child(id_edit)
	vbox.add_child(id_box)
	
	var name_box = HBoxContainer.new()
	name_box.add_child(InspectorStyle.lbl("Name:", InspectorStyle.COLOR_TEXT_DIM))
	var name_edit = LineEdit.new(); name_edit.text = cur_data.get("name", ""); name_edit.size_flags_horizontal = 3
	name_edit.text_changed.connect(func(t): cur_data.name=t; data_modified.emit())
	InspectorStyle.apply_input_style(name_edit)
	name_box.add_child(name_edit)
	vbox.add_child(name_box)
	
	vbox.add_child(InspectorStyle.lbl("Description:", InspectorStyle.COLOR_TEXT_DIM))
	var desc_edit = TextEdit.new(); desc_edit.custom_minimum_size.y = 160
	desc_edit.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	desc_edit.text = cur_data.get("description", "")
	desc_edit.text_changed.connect(func(): cur_data.description=desc_edit.text; data_modified.emit())
	InspectorStyle.apply_input_style(desc_edit)
	vbox.add_child(desc_edit)
