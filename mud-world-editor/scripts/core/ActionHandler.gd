# scripts/core/ActionHandler.gd
class_name ActionHandler
extends RefCounted

var state: EditorState
var main_node: Node2D 
var cmd_proc: CommandProcessor
var region_mgr: RegionManager
var world_mgr: WorldManager
var graph_controller: GraphController
var ui_mgr: EditorUIManager
var inspector: InspectorController

func setup(p_main: Node2D, p_state: EditorState, p_cmd: CommandProcessor, p_rm: RegionManager, p_wm: WorldManager, p_gc: GraphController, p_ui: EditorUIManager, p_insp: InspectorController):
	main_node = p_main
	state = p_state
	cmd_proc = p_cmd
	region_mgr = p_rm
	world_mgr = p_wm
	graph_controller = p_gc
	ui_mgr = p_ui
	inspector = p_insp

func create_connection(src_id: String, dir: String, target_id: String, two_way: bool):
	var final_target = target_id
	if ":" in target_id:
		var parts = target_id.split(":")
		if parts[0] == region_mgr.data.region_id:
			final_target = parts[1]

	cmd_proc.commit(
		func():
			region_mgr.add_exit(src_id, dir, final_target)
			if two_way:
				var inv_dir = Constants.INV_DIR_MAP.get(dir.to_lower(), "")
				if inv_dir and not ":" in final_target:
					region_mgr.add_exit(final_target, inv_dir, src_id)
			main_node._refresh_view()
			region_mgr.mark_room_dirty(src_id)
			if region_mgr.data.rooms.has(final_target):
				region_mgr.mark_room_dirty(final_target)
			main_node._update_explorer_dirty_state(),
		func():
			region_mgr.remove_exit(src_id, dir)
			if two_way and not ":" in final_target:
				region_mgr.remove_exit(final_target, Constants.INV_DIR_MAP.get(dir.to_lower(), ""))
			main_node._refresh_view()
			region_mgr.mark_room_dirty(src_id)
			if region_mgr.data.rooms.has(final_target):
				region_mgr.mark_room_dirty(final_target)
			main_node._update_explorer_dirty_state(),
		"Add Connection"
	)

func create_room_from_anchor(direction: String):
	var src = state.creating_conn.src_id
	var pos = state.creating_conn.end_pos
	var new_id = "room_" + str(Time.get_ticks_msec()) + "_" + str(randi() % 1000)
	var inv = Constants.INV_DIR_MAP.get(direction.to_lower(), "")
	var r_data = { "name": "New Room", "description": "", "exits": {}, "properties": {}, "_editor_pos": [pos.x, pos.y] }
	
	cmd_proc.commit(
		func():
			region_mgr.add_room_data(new_id, r_data)
			region_mgr.add_exit(src, direction, new_id)
			if inv: region_mgr.add_exit(new_id, inv, src)
			main_node._refresh_view()
			main_node._on_node_click(new_id, false)
			region_mgr.mark_room_dirty(new_id)
			region_mgr.mark_room_dirty(src)
			main_node._update_explorer_dirty_state(),
		func():
			region_mgr.remove_exit(src, direction)
			region_mgr.remove_room_data(new_id)
			main_node._refresh_view()
			region_mgr.mark_room_dirty(src)
			main_node._update_explorer_dirty_state(),
		"Create Room Directional"
	)

func handle_context_action(action_id: int):
	if not ui_mgr.context_menu.has_meta("target_id"): return
	
	var target_id = ui_mgr.context_menu.get_meta("target_id")
	var target_type = ui_mgr.context_menu.get_meta("target_type")
	
	if target_type == "room":
		if action_id == 0: # Rename
			main_node._on_node_click(target_id, false)
			
		elif action_id == 3: # Set Start
			cmd_proc.commit(
				func():
					for rid in region_mgr.data.rooms: region_mgr.data.rooms[rid].get("properties", {}).erase("is_start_node")
					if not region_mgr.data.rooms[target_id].has("properties"): region_mgr.data.rooms[target_id].properties = {}
					region_mgr.data.rooms[target_id].properties["is_start_node"] = true
					main_node._on_data_modified(),
				func(): pass, 
				"Set Start Node"
			)
		elif action_id == 99: # Delete request
			ui_mgr.show_delete_room_prompt(target_id)
			
	elif target_type == "region":
		if action_id == 200: # Load Region
			var hierarchy = world_mgr.get_global_hierarchy()
			if hierarchy.has(target_id):
				main_node._load_region(hierarchy[target_id].filename)

	elif target_type == "db_entry":
		var kind = ui_mgr.context_menu.get_meta("db_kind")
		if action_id == 300: # Edit
			ui_mgr.request_select_db_entry.emit(kind, target_id)
		elif action_id == 301: # Delete
			ui_mgr.request_delete_db_entry.emit(kind, target_id)

func execute_delete_room(room_id: String, remove_incoming: bool):
	var old_room_data = region_mgr.data.rooms[room_id].duplicate(true)
	var incoming_links = []
	if remove_incoming:
		incoming_links = region_mgr.find_incoming_connections(room_id)
	
	cmd_proc.commit(
		func(): 
			region_mgr.remove_room_data(room_id)
			for link in incoming_links:
				region_mgr.remove_exit(link.source, link.dir)
				region_mgr.mark_room_dirty(link.source)
			
			main_node._refresh_view()
			main_node._deselect_all()
			main_node._update_explorer_dirty_state(),
		func(): 
			region_mgr.add_room_data(room_id, old_room_data)
			for link in incoming_links:
				region_mgr.add_exit(link.source, link.dir, room_id)
				region_mgr.mark_room_dirty(link.source)
				
			main_node._refresh_view()
			main_node._update_explorer_dirty_state(),
		"Delete Room"
	)

func commit_batch_move(delta: Vector2):
	if state.is_world_view: return
	
	var move_data = {}
	for id in state.selected_ids:
		var old_pos = state.drag_start_positions.get(id, Vector2.ZERO)
		var new_pos = old_pos + delta
		move_data[id] = {"old": old_pos, "new": new_pos}

	cmd_proc.commit(
		func():
			for id in move_data:
				region_mgr.set_room_pos(id, move_data[id].new)
				graph_controller.update_specific_node(id, region_mgr.data)
				region_mgr.mark_room_dirty(id)
			main_node._update_explorer_dirty_state()
			graph_controller.queue_redraw(),
		func():
			for id in move_data:
				region_mgr.set_room_pos(id, move_data[id].old)
				graph_controller.update_specific_node(id, region_mgr.data)
				region_mgr.mark_room_dirty(id)
			main_node._update_explorer_dirty_state()
			graph_controller.queue_redraw(),
		"Move %d Rooms" % move_data.size()
	)

func commit_batch_properties(ids: Array, key: String, new_val, old_vals: Dictionary):
	cmd_proc.commit(
		func():
			for id in ids:
				if not region_mgr.data.rooms.has(id): continue
				if not region_mgr.data.rooms[id].has("properties"): region_mgr.data.rooms[id].properties = {}
				
				if new_val == null: # Deletion
					region_mgr.data.rooms[id].properties.erase(key)
				else:
					region_mgr.data.rooms[id].properties[key] = new_val
				
				region_mgr.mark_room_dirty(id)
				graph_controller.update_specific_node(id, region_mgr.data)
			inspector.data_modified.emit(),
		func():
			for id in ids:
				if not region_mgr.data.rooms.has(id): continue
				var prev = old_vals.get(id)
				if prev == null:
					if region_mgr.data.rooms[id].has("properties"):
						region_mgr.data.rooms[id].properties.erase(key)
				else:
					if not region_mgr.data.rooms[id].has("properties"): region_mgr.data.rooms[id].properties = {}
					region_mgr.data.rooms[id].properties[key] = prev
					
				region_mgr.mark_room_dirty(id)
				graph_controller.update_specific_node(id, region_mgr.data)
			inspector.data_modified.emit(),
		"Batch Edit: %s" % key
	)
