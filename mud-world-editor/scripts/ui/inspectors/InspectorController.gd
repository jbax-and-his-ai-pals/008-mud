# scripts/ui/inspectors/InspectorController.gd
class_name InspectorController
extends RefCounted

signal request_rename(old, new)
signal request_connection_modal
signal connection_created(src, dir, target, twoway)
signal target_selected_in_connector(target_id)
signal request_save_template(room_id) 
signal save_triggered
signal reload_triggered
signal data_modified
signal database_modified
signal request_graph_edit_mode(quest_id) # New Signal

var panel: Panel
var vbox_main: VBoxContainer
var content_container: VBoxContainer
var save_reload_container: HBoxContainer

var region_mgr: RegionManager
var world_mgr: WorldManager
var database_mgr: DatabaseManager

var connection_editor: ConnectionEditor
var action_handler: ActionHandler # Injected for MultiInspector

# Active Sub-Inspector
var current_inspector: RefCounted = null

const QUEST_INSPECTOR_SCRIPT = preload("res://scripts/ui/inspectors/QuestInspector.gd")
const MULTI_INSPECTOR_SCRIPT = preload("res://scripts/ui/inspectors/MultiRoomInspector.gd")

func setup(parent: Node, _region_mgr: RegionManager, _world_mgr: WorldManager, _db_mgr: DatabaseManager):
	region_mgr = _region_mgr
	world_mgr = _world_mgr
	database_mgr = _db_mgr
	
	connection_editor = ConnectionEditor.new(region_mgr)
	connection_editor.connection_created.connect(func(src,d,t,two): connection_created.emit(src,d,t,two))
	connection_editor.target_selected.connect(func(id): target_selected_in_connector.emit(id))
	
	panel = Panel.new()
	panel.anchor_left = 0.75; panel.anchor_right = 1.0
	panel.anchor_bottom = 0.96 
	var style = StyleBoxFlat.new()
	style.bg_color = InspectorStyle.COLOR_BG_MAIN
	style.set_border_width_all(0); style.border_width_left = 1
	style.border_color = Color(0.25, 0.25, 0.28)
	style.shadow_size = 4
	panel.add_theme_stylebox_override("panel", style)
	parent.add_child(panel)
	
	panel.visible = false 
	panel.gui_input.connect(_on_panel_gui_input)
	
	vbox_main = VBoxContainer.new()
	vbox_main.set_anchors_preset(Control.PRESET_FULL_RECT)
	vbox_main.offset_left = 16; vbox_main.offset_top = 16; vbox_main.offset_right = -16; vbox_main.offset_bottom = -16
	vbox_main.add_theme_constant_override("separation", 12)
	panel.add_child(vbox_main)

	var scroll = ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	vbox_main.add_child(scroll)
	
	content_container = VBoxContainer.new()
	content_container.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content_container.add_theme_constant_override("separation", 16)
	scroll.add_child(content_container)

	save_reload_container = HBoxContainer.new()
	save_reload_container.custom_minimum_size.y = 40
	save_reload_container.add_theme_constant_override("separation", 10)
	vbox_main.add_child(save_reload_container)

	var btn_save = Button.new(); btn_save.text="SAVE DATA"; btn_save.size_flags_horizontal = 3
	btn_save.pressed.connect(func(): save_triggered.emit())
	InspectorStyle.apply_button_style(btn_save, InspectorStyle.COLOR_SUCCESS.darkened(0.2))
	save_reload_container.add_child(btn_save)
	
	var btn_reload = Button.new(); btn_reload.text="RELOAD"; btn_reload.size_flags_horizontal = 3
	btn_reload.pressed.connect(func(): reload_triggered.emit())
	InspectorStyle.apply_button_style(btn_reload, InspectorStyle.COLOR_DANGER.darkened(0.2))
	save_reload_container.add_child(btn_reload)

# Public Injection for MultiInspector
func set_action_handler(handler: ActionHandler):
	action_handler = handler

var cur_mode = "none"

func clear_selection(hide_panel: bool = true):
	cur_mode = "none"
	current_inspector = null
	_clear_box(content_container)
	save_reload_container.visible = true
	if hide_panel: panel.visible = false
	target_selected_in_connector.emit("") 

func load_room(id: String, data: Dictionary):
	clear_selection(false)
	cur_mode = "room"
	panel.visible = true
	
	var insp = RoomInspector.new(content_container, region_mgr, database_mgr, world_mgr)
	current_inspector = insp
	
	insp.data_modified.connect(func(): data_modified.emit())
	insp.request_rename.connect(func(o, n): request_rename.emit(o, n))
	insp.request_connection_form.connect(func(rid, rname): load_connection_form(rid, rname, world_mgr.get_global_hierarchy(), region_mgr.current_filename))
	insp.request_save_template.connect(func(rid): request_save_template.emit(rid))
	
	insp.build(id, data)

func load_region_root(data: Dictionary):
	clear_selection(false)
	cur_mode = "region_root"
	panel.visible = true
	
	var insp = RegionInspector.new(content_container)
	current_inspector = insp
	insp.data_modified.connect(func(): data_modified.emit())
	insp.build(data.get("region_id", "Unknown"), data)

func load_db_object(type: String, id: String, data: Dictionary):
	clear_selection(false)
	cur_mode = type
	panel.visible = true
	
	if type == "quest":
		var insp = QUEST_INSPECTOR_SCRIPT.new(content_container, database_mgr, world_mgr)
		current_inspector = insp
		insp.database_modified.connect(func(): database_modified.emit())
		insp.request_graph_edit.connect(func(qid): request_graph_edit_mode.emit(qid))
		insp.build(id, data)
	else:
		var insp = DatabaseInspector.new(content_container)
		insp.set_db_manager(database_mgr)
		current_inspector = insp
		insp.database_modified.connect(func(): database_modified.emit())
		insp.build(type, id, data)

func load_external_ref(full_id: String):
	clear_selection(false) 
	panel.visible = true
	content_container.add_child(InspectorStyle.create_section_header("EXTERNAL REFERENCE", Color.CYAN))
	var card = InspectorStyle.create_card(); var vbox = card.get_child(0).get_child(0)
	content_container.add_child(card)
	vbox.add_child(InspectorStyle.lbl(full_id, InspectorStyle.COLOR_TEXT_DIM))
	vbox.add_child(InspectorStyle.lbl("Node is in another file.", Color.GRAY))

func load_multi_selection(ids: Array):
	clear_selection(false)
	cur_mode = "multi"
	panel.visible = true
	
	var insp = MULTI_INSPECTOR_SCRIPT.new(content_container, region_mgr, action_handler)
	current_inspector = insp
	insp.data_modified.connect(func(): data_modified.emit())
	insp.build(ids)

func load_connection_form(src_id: String, src_name: String, hierarchy: Dictionary, cur_filename: String, target_id: String = "", dir: String = ""):
	cur_mode = "connection"
	save_reload_container.visible = false
	panel.visible = true 
	_clear_box(content_container)
	connection_editor.build_ui(content_container, src_id, src_name, hierarchy, cur_filename, target_id, dir)
	
	var margin_c = content_container.get_child(content_container.get_child_count()-1)
	if margin_c and margin_c.get_child_count() > 0:
		var btn_box = margin_c.get_child(0)
		var btn_c = btn_box.get_child(1) 
		if not btn_c.pressed.is_connected(_on_connect_cancel):
			btn_c.pressed.connect(_on_connect_cancel)

func set_connection_target(region_id: String, room_id: String):
	if cur_mode != "connection": return
	connection_editor.set_target(region_id, room_id)

func _on_connect_cancel():
	target_selected_in_connector.emit("") 
	if region_mgr.data.rooms.has(connection_editor.conn_src_id): 
		load_room(connection_editor.conn_src_id, region_mgr.data.rooms[connection_editor.conn_src_id])
	else: clear_selection()

func _clear_box(b): for c in b.get_children(): c.queue_free()
func _on_panel_gui_input(event): if event is InputEventMouseButton and event.button_index in [4,5]: panel.get_viewport().set_input_as_handled()

func load_world_mode():
	clear_selection(false) 
	cur_mode = "world"
	panel.visible = true
	content_container.add_child(InspectorStyle.create_section_header("WORLD MAP", Color.GOLD))
	var card = InspectorStyle.create_card(); var vbox = card.get_child(0).get_child(0)
	content_container.add_child(card)
	vbox.add_child(InspectorStyle.lbl("Arrangement Mode", Color.WHITE))

func load_quest_mode(quest_id: String):
	clear_selection(false)
	cur_mode = "quest_graph"
	panel.visible = true
	content_container.add_child(InspectorStyle.create_section_header("QUEST GRAPH: " + quest_id, Color.VIOLET))
	var card = InspectorStyle.create_card(); var vbox = card.get_child(0).get_child(0)
	content_container.add_child(card)
	vbox.add_child(InspectorStyle.lbl("Graph View", Color.WHITE))
	
	var btn = Button.new(); btn.text = "Back to Form View"
	InspectorStyle.apply_button_style(btn)
	btn.pressed.connect(func(): load_db_object("quest", quest_id, database_mgr.quests[quest_id]))
	vbox.add_child(btn)
