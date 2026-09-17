# scripts/core/ActionHandler.gd
class_name ActionHandler
extends RefCounted

const DistrictLayout = preload("res://scripts/generators/DistrictLayout.gd")
const DistrictBlueprint = preload("res://scripts/generators/DistrictBlueprint.gd")

signal district_preview_changed(preview: Dictionary)

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
					region_mgr.set_connection_label_source(src_id, final_target, dir)
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
			if inv:
				region_mgr.add_exit(new_id, inv, src)
				region_mgr.set_connection_label_source(src, new_id, direction)
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

func rename_room_label(room_id: String, new_name: String):
	if not region_mgr.data.rooms.has(room_id) or new_name.strip_edges() == "": return
	var old_name := str(region_mgr.data.rooms[room_id].get("name", "Unnamed"))
	if old_name == new_name: return
	cmd_proc.commit(
		func():
			region_mgr.data.rooms[room_id]["name"] = new_name
			region_mgr.mark_room_dirty(room_id)
			graph_controller.update_specific_node(room_id, region_mgr.data)
			main_node._refresh_view(); main_node._update_explorer_dirty_state(),
		func():
			region_mgr.data.rooms[room_id]["name"] = old_name
			region_mgr.mark_room_dirty(room_id)
			graph_controller.update_specific_node(room_id, region_mgr.data)
			main_node._refresh_view(); main_node._update_explorer_dirty_state(),
		"Rename Room Label"
	)

func swap_room_labels(first_id: String, second_id: String):
	if first_id == second_id or not region_mgr.data.rooms.has(first_id) or not region_mgr.data.rooms.has(second_id): return
	var first_name := str(region_mgr.data.rooms[first_id].get("name", "Unnamed"))
	var second_name := str(region_mgr.data.rooms[second_id].get("name", "Unnamed"))
	cmd_proc.commit(
		func(): _apply_label_swap(first_id, second_id, second_name, first_name),
		func(): _apply_label_swap(first_id, second_id, first_name, second_name),
		"Swap Room Labels"
	)

func _apply_label_swap(first_id: String, second_id: String, first_name: String, second_name: String):
	region_mgr.data.rooms[first_id]["name"] = first_name
	region_mgr.data.rooms[second_id]["name"] = second_name
	region_mgr.mark_room_dirty(first_id); region_mgr.mark_room_dirty(second_id)
	graph_controller.update_specific_node(first_id, region_mgr.data); graph_controller.update_specific_node(second_id, region_mgr.data)
	main_node._refresh_view(); main_node._update_explorer_dirty_state()

func preview_district_attachment(room_ids: Array, anchor_room_id: String, target_room_id: String, direction: String) -> Dictionary:
	var preview = DistrictLayout.preview_attachment(region_mgr.data.rooms, room_ids, anchor_room_id, target_room_id, direction)
	district_preview_changed.emit(preview)
	return preview

func apply_district_attachment(room_ids: Array, preview: Dictionary):
	if not preview.get("valid", false):
		return
	var positions: Dictionary = preview.get("positions", {})
	var plan: Dictionary = preview.get("connection_plan", {})
	var source_id := str(plan.get("source", ""))
	var target_id := str(plan.get("target", ""))
	var direction := str(plan.get("direction", ""))
	if source_id == "" or target_id == "" or direction == "" or not region_mgr.data.rooms.has(source_id) or not region_mgr.data.rooms.has(target_id):
		return
	var old_positions := {}
	for room_id in room_ids:
		if region_mgr.data.rooms.has(room_id):
			old_positions[room_id] = Vector2(region_mgr.data.rooms[room_id]._editor_pos[0], region_mgr.data.rooms[room_id]._editor_pos[1])
	var old_source_exits: Dictionary = region_mgr.data.rooms[source_id].get("exits", {}).duplicate(true)
	var old_target_exits: Dictionary = region_mgr.data.rooms[target_id].get("exits", {}).duplicate(true)
	var inverse := str(plan.get("inverse_direction", ""))
	var two_way := bool(plan.get("two_way", false))
	cmd_proc.commit(
		func():
			for room_id in positions:
				region_mgr.set_room_pos(room_id, positions[room_id])
				region_mgr.mark_room_dirty(room_id)
			region_mgr.add_exit(source_id, direction, target_id)
			if two_way and inverse != "":
				region_mgr.add_exit(target_id, inverse, source_id)
			region_mgr.mark_room_dirty(source_id)
			region_mgr.mark_room_dirty(target_id)
			main_node._refresh_view()
			main_node._update_explorer_dirty_state(),
		func():
			for room_id in old_positions:
				region_mgr.set_room_pos(room_id, old_positions[room_id])
				region_mgr.mark_room_dirty(room_id)
			region_mgr.data.rooms[source_id]["exits"] = old_source_exits.duplicate(true)
			region_mgr.data.rooms[target_id]["exits"] = old_target_exits.duplicate(true)
			region_mgr.mark_room_dirty(source_id)
			region_mgr.mark_room_dirty(target_id)
			main_node._refresh_view()
			main_node._update_explorer_dirty_state(),
		"Attach District (%d Rooms)" % positions.size()
	)
	district_preview_changed.emit({})

func create_generated_district(definition: Dictionary, target_room_id: String, direction: String):
	var generated := DistrictBlueprint.generate(definition)
	if not generated.get("ok", false):
		push_error("District generation failed: " + "; ".join(generated.get("errors", [])))
		return
	var district: Dictionary = generated["district"]
	var ports: Array = district.get("ports", [])
	if ports.is_empty() or not region_mgr.data.rooms.has(target_room_id):
		push_error("District needs an entry port and a valid target room.")
		return
	var entry_id := str(ports[0].get("room_id", ""))
	var combined: Dictionary = region_mgr.data.rooms.duplicate(true)
	for room_id in generated["rooms"]:
		combined[room_id] = generated["rooms"][room_id].duplicate(true)
	var preview := DistrictLayout.preview_attachment(combined, generated["rooms"].keys(), entry_id, target_room_id, direction)
	district_preview_changed.emit(preview)
	if not preview.get("valid", false):
		push_error("District does not fit: " + "; ".join(preview.get("errors", [])))
		return
	var positions: Dictionary = preview["positions"]
	var district_id := str(district["id"])
	cmd_proc.commit(
		func():
			for room_id in generated["rooms"]:
				var room: Dictionary = generated["rooms"][room_id].duplicate(true)
				var pos: Vector2 = positions[room_id]
				room["_editor_pos"] = [pos.x, pos.y]
				region_mgr.add_room_data(room_id, room)
				region_mgr.mark_room_dirty(room_id)
			region_mgr.set_district(district_id, district)
			region_mgr.add_exit(target_room_id, direction, entry_id)
			var inverse := str(Constants.INV_DIR_MAP.get(direction, ""))
			if inverse != "":
				region_mgr.add_exit(entry_id, inverse, target_room_id)
				region_mgr.set_connection_label_source(target_room_id, entry_id, direction)
			region_mgr.mark_room_dirty(target_room_id)
			main_node._refresh_view(); main_node._update_explorer_dirty_state(),
		func():
			region_mgr.remove_exit(target_room_id, direction)
			for room_id in generated["rooms"]: region_mgr.remove_room_data(room_id)
			region_mgr.remove_district(district_id)
			region_mgr.mark_room_dirty(target_room_id)
			main_node._refresh_view(); main_node._update_explorer_dirty_state(),
		"Create District: " + district.get("name", district_id)
	)

# A generated district remains only a ghost until commit_district_placement.
# The editor can freely move this data without adding rooms to RegionManager.
func begin_district_placement(definition: Dictionary, world_center: Vector2):
	var generated := DistrictBlueprint.generate(definition)
	if not generated.get("ok", false):
		push_error("District generation failed: " + "; ".join(generated.get("errors", [])))
		return
	var rooms: Dictionary = generated["rooms"]
	var positions := {}
	var centroid := Vector2.ZERO
	for room_id in rooms: centroid += _room_pos(rooms[room_id])
	centroid /= max(rooms.size(), 1)
	var offset := world_center - centroid
	for room_id in rooms: positions[room_id] = _room_pos(rooms[room_id]) + offset
	district_preview_changed.emit({"active": true, "valid": _preview_positions_fit(positions), "phase": "placement", "positions": positions, "rooms": rooms, "district": generated["district"], "connection_plan": {}, "selected_port": "", "target_room": "", "direction": "north", "direction_auto": true, "active_endpoint": "source"})

func update_district_placement_positions(positions: Dictionary):
	if positions.is_empty(): return
	# Repositioning is deliberately non-destructive: authors can refine the
	# footprint without having to rebuild the connection they already chose.
	district_preview_changed.emit({"active": true, "valid": _preview_positions_fit(positions), "phase": "placement", "positions": positions, "rooms": state.district_preview.get("rooms", {}), "district": state.district_preview.get("district", {}), "connection_plan": {}, "selected_port": state.district_preview.get("selected_port", ""), "target_room": state.district_preview.get("target_room", ""), "direction": state.district_preview.get("direction", "north"), "direction_auto": state.district_preview.get("direction_auto", true), "active_endpoint": state.district_preview.get("active_endpoint", "source")})

func _preview_positions_fit(positions: Dictionary) -> bool:
	for candidate_id in positions:
		var candidate_pos: Vector2 = positions[candidate_id]
		for room_id in region_mgr.data.rooms:
			var pos := _room_pos(region_mgr.data.rooms[room_id])
			if abs(candidate_pos.x - pos.x) < DistrictLayout.ROOM_CLEARANCE.x and abs(candidate_pos.y - pos.y) < DistrictLayout.ROOM_CLEARANCE.y:
				return false
	return true

func commit_district_placement(preview: Dictionary, port_id: String, target_room_id: String, source_direction: String):
	if not preview.get("active", false) or not preview.get("valid", false): return
	var rooms: Dictionary = preview.get("rooms", {})
	var positions: Dictionary = preview.get("positions", {})
	var district: Dictionary = preview.get("district", {})
	if not rooms.has(port_id) or not region_mgr.data.rooms.has(target_room_id) or not Constants.DIR_VECTORS.has(source_direction):
		push_error("Choose a district port, destination room, and direction before confirming.")
		return
	if not _preview_positions_fit(positions):
		push_error("Move the district until its footprint no longer overlaps existing rooms.")
		return
	var connection_errors := DistrictLayout.validate_preview_connection(region_mgr.data.rooms, rooms, positions, port_id, target_room_id, source_direction)
	if not connection_errors.is_empty():
		push_error("Cannot create district connection: " + " ".join(connection_errors))
		return
	var district_id := str(district.get("id", ""))
	if district_id == "" or region_mgr.get_districts().has(district_id):
		push_error("District ID already exists. Choose a new ID before placing it.")
		return
	var target_direction := str(Constants.INV_DIR_MAP.get(source_direction, ""))
	if target_direction == "": return
	var stored_district := district.duplicate(true)
	# The selected ghost room becomes the actual public port.  This is what
	# lets the author inspect a generated footprint before deciding which door
	# should face the town, while keeping rerolls role-based later.
	for port in stored_district.get("ports", []):
		if str(port.get("id", "")) == "entry":
			port["room_id"] = port_id
			port["direction"] = source_direction
	cmd_proc.commit(
		func():
			for room_id in rooms:
				var room: Dictionary = rooms[room_id].duplicate(true)
				var pos: Vector2 = positions[room_id]; room["_editor_pos"] = [pos.x, pos.y]
				region_mgr.add_room_data(room_id, room); region_mgr.mark_room_dirty(room_id)
			region_mgr.set_district(district_id, stored_district)
			region_mgr.add_exit(port_id, source_direction, target_room_id)
			region_mgr.add_exit(target_room_id, target_direction, port_id)
			region_mgr.set_connection_label_source(port_id, target_room_id, source_direction)
			region_mgr.mark_room_dirty(target_room_id); main_node._refresh_view(); main_node._update_explorer_dirty_state(); district_preview_changed.emit({}),
		func():
			region_mgr.remove_exit(target_room_id, target_direction)
			for room_id in rooms: region_mgr.remove_room_data(room_id)
			region_mgr.remove_district(district_id); region_mgr.mark_room_dirty(target_room_id); main_node._refresh_view(); main_node._update_explorer_dirty_state(),
		"Create District: " + str(stored_district.get("name", district_id))
	)

func reroll_district(district_id: String, new_seed: int):
	var districts := region_mgr.get_districts()
	if not districts.has(district_id):
		push_error("Unknown district '%s'." % district_id)
		return
	var old_district: Dictionary = districts[district_id].duplicate(true)
	var old_members: Array = old_district.get("members", [])
	var old_rooms := {}
	for room_id in old_members:
		if region_mgr.data.rooms.has(room_id): old_rooms[room_id] = region_mgr.data.rooms[room_id].duplicate(true)
	if old_rooms.is_empty():
		push_error("District '%s' has no live member rooms to reroll." % district_id)
		return
	var definition := {
		"id": district_id,
		"name": old_district.get("name", district_id),
		"kind": old_district.get("kind", "generic"),
		"seed": new_seed,
		"generator": old_district.get("generator", {}).duplicate(true),
		"ports": _port_requests(old_district.get("ports", [])),
		"reroll_policy": old_district.get("reroll_policy", {}).duplicate(true),
	}
	var generated := DistrictBlueprint.generate(definition)
	if not generated.get("ok", false):
		push_error("District reroll failed: " + "; ".join(generated.get("errors", [])))
		return
	var new_district: Dictionary = generated["district"]
	var port_map := _port_room_map(old_district.get("ports", []), new_district.get("ports", []))
	if port_map.is_empty():
		push_error("District reroll has no compatible port roles to preserve.")
		return
	var old_anchor := str(port_map.keys()[0])
	var new_anchor := str(port_map[old_anchor])
	var old_anchor_pos := _room_pos(old_rooms[old_anchor])
	var generated_anchor_pos := _room_pos(generated["rooms"][new_anchor])
	var offset := old_anchor_pos - generated_anchor_pos
	var new_rooms := {}
	for room_id in generated["rooms"]:
		var room: Dictionary = generated["rooms"][room_id].duplicate(true)
		var pos := _room_pos(room) + offset
		room["_editor_pos"] = [pos.x, pos.y]
		new_rooms[room_id] = room
	var collision_ids := _district_collisions(new_rooms, old_members)
	if not collision_ids.is_empty():
		push_error("District reroll would overlap: " + ", ".join(collision_ids))
		return
	var non_district_exits := {}
	for room_id in region_mgr.data.rooms:
		if not old_members.has(room_id):
			non_district_exits[room_id] = region_mgr.data.rooms[room_id].get("exits", {}).duplicate(true)
	cmd_proc.commit(
		func():
			for room_id in old_members: region_mgr.remove_room_data(room_id)
			for room_id in new_rooms: region_mgr.add_room_data(room_id, new_rooms[room_id].duplicate(true))
			_rewire_district_ports(port_map, old_rooms, new_rooms, non_district_exits)
			region_mgr.set_district(district_id, new_district)
			for room_id in new_rooms: region_mgr.mark_room_dirty(room_id)
			main_node._refresh_view(); main_node._update_explorer_dirty_state(),
		func():
			for room_id in new_rooms: region_mgr.remove_room_data(room_id)
			for room_id in old_rooms: region_mgr.add_room_data(room_id, old_rooms[room_id].duplicate(true))
			for room_id in non_district_exits:
				if region_mgr.data.rooms.has(room_id): region_mgr.data.rooms[room_id]["exits"] = non_district_exits[room_id].duplicate(true)
			region_mgr.set_district(district_id, old_district)
			for room_id in old_rooms: region_mgr.mark_room_dirty(room_id)
			main_node._refresh_view(); main_node._update_explorer_dirty_state(),
		"Reroll District: " + str(old_district.get("name", district_id))
	)

func _port_requests(ports: Array) -> Array:
	var requests: Array = []
	for port in ports:
		requests.append({"id": port.get("id", "port"), "direction": port.get("direction", "north"), "role": port.get("role", "entrance")})
	return requests

func _port_room_map(old_ports: Array, new_ports: Array) -> Dictionary:
	var new_by_id := {}
	for port in new_ports: new_by_id[str(port.get("id", ""))] = str(port.get("room_id", ""))
	var result := {}
	for port in old_ports:
		var port_id := str(port.get("id", ""))
		var old_room := str(port.get("room_id", ""))
		if old_room != "" and new_by_id.has(port_id): result[old_room] = new_by_id[port_id]
	return result

func _rewire_district_ports(port_map: Dictionary, old_rooms: Dictionary, new_rooms: Dictionary, external_exits: Dictionary):
	for external_id in external_exits:
		if not region_mgr.data.rooms.has(external_id): continue
		var exits: Dictionary = external_exits[external_id].duplicate(true)
		for direction in exits:
			if port_map.has(str(exits[direction])): exits[direction] = port_map[str(exits[direction])]
		region_mgr.data.rooms[external_id]["exits"] = exits
	for old_port in port_map:
		var new_port := str(port_map[old_port])
		if not old_rooms.has(old_port) or not new_rooms.has(new_port): continue
		var old_exits: Dictionary = old_rooms[old_port].get("exits", {})
		for direction in old_exits:
			if not old_rooms.has(str(old_exits[direction])):
				region_mgr.data.rooms[new_port]["exits"][direction] = old_exits[direction]

func _district_collisions(candidate_rooms: Dictionary, removed_members: Array) -> Array:
	var collisions: Array = []
	for candidate_id in candidate_rooms:
		var candidate_pos := _room_pos(candidate_rooms[candidate_id])
		for room_id in region_mgr.data.rooms:
			if removed_members.has(room_id): continue
			var pos := _room_pos(region_mgr.data.rooms[room_id])
			if abs(candidate_pos.x - pos.x) < DistrictLayout.ROOM_CLEARANCE.x and abs(candidate_pos.y - pos.y) < DistrictLayout.ROOM_CLEARANCE.y:
				if not collisions.has(str(room_id)): collisions.append(str(room_id))
	collisions.sort()
	return collisions

func _room_pos(room: Dictionary) -> Vector2:
	var raw = room.get("_editor_pos", [0, 0])
	return Vector2(float(raw[0]), float(raw[1])) if raw is Array and raw.size() >= 2 else Vector2.ZERO

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
