# scripts/controllers/view_builders/LocalViewBuilder.gd
class_name LocalViewBuilder
extends RefCounted

const ROOM_SCENE = preload("res://scenes/RoomScene.tscn")
const LayoutOptimizer = preload("res://scripts/generators/LayoutOptimizer.gd")
const ROOM_CLEARANCE = Vector2(224, 128)

var container: Node2D
var room_nodes: Dictionary = {}

# Signals forwarded from nodes
signal node_selected(id)
signal node_double_clicked(id)
signal node_drag_started(id)
signal node_dragging(id, current_pos)
signal node_dragged(id, final_pos)
signal node_right_clicked(id)
signal connection_drag_started(id)
signal creation_drag_started(id, pos)
signal label_clicked(id)
signal label_drag_started(id)
signal label_dragged(id)
signal label_drag_ended(id)

func _init(p_container: Node2D):
	container = p_container

func build(region_data: Dictionary, snap_enabled: bool, world_data: Dictionary = {}):
	clear()
	var rooms = region_data.get("rooms", {})
	if rooms.is_empty(): return

	for rid in rooms:
		var r_data = rooms[rid]
		var ep = r_data.get("_editor_pos", [0, 0])
		var pos = Vector2(ep[0], ep[1])
		_spawn_room_node(rid, pos, r_data, snap_enabled)

	var external_links = {}
	var stored_proxies = region_data.get("_proxy_positions", {})

	for rid in rooms:
		var r_exits = rooms[rid].get("exits", {})
		for dir in r_exits:
			var target = r_exits[dir]
			if ":" in target and not external_links.has(target):
				if stored_proxies.has(target):
					var p = stored_proxies[target]
					external_links[target] = Vector2(p[0], p[1])
				else:
					var src_pos = room_nodes[rid].position
					var visual_direction = _external_visual_direction(rooms[rid], str(dir))
					external_links[target] = _find_proxy_position(src_pos, visual_direction, external_links)

	for ext_id in external_links:
		_create_proxy_node(ext_id, external_links[ext_id], snap_enabled, world_data)

func clear():
	for c in container.get_children(): c.queue_free()
	room_nodes.clear()

func _spawn_room_node(id, pos, data, snap_enabled):
	var node = ROOM_SCENE.instantiate()
	node.position = pos
	node.snap_step = 32 if snap_enabled else 0
	
	node.set_info(data.get("name", "Unnamed"), id)
	
	# Initial update (default view)
	update_node_visuals(node, data, "Default")
	_connect_node_signals(node, id)
	
	container.add_child(node)
	room_nodes[id] = node

func _create_proxy_node(full_id, pos, snap_enabled, world_data: Dictionary = {}):
	var parts = full_id.split(":")
	var target_region_id := str(parts[0])
	var target_room_id := str(parts[1]) if parts.size() > 1 else ""
	var node = ROOM_SCENE.instantiate()
	node.position = pos
	node.snap_step = 32 if snap_enabled else 0

	node.set_info(target_region_id.capitalize(), _proxy_room_name(world_data, target_region_id, target_room_id))
	node.set_as_proxy(true)

	_connect_node_signals(node, full_id)
	container.add_child(node)
	room_nodes[full_id] = node

func _proxy_room_name(world_data: Dictionary, region_id: String, room_id: String) -> String:
	var room = world_data.get(region_id, {}).get("rooms", {}).get(room_id, {})
	if room is Dictionary and room.has("name"):
		return str(room.name)
	return room_id

func _external_visual_direction(room_data: Dictionary, exit_name: String) -> String:
	var layout = room_data.get("_editor_exit_layout", {}).get(exit_name, {})
	if layout is Dictionary and layout.has("visual_direction"):
		return str(layout["visual_direction"])
	if Constants.DIR_VECTORS.has(exit_name.to_lower()):
		return exit_name.to_lower()
	return Constants.MAP_DIRECTION_ALIASES.get(exit_name.to_lower(), "east")

func _find_proxy_position(source_pos: Vector2, direction: String, existing_proxies: Dictionary) -> Vector2:
	var vector: Vector2 = Constants.DIR_VECTORS.get(direction, Vector2.RIGHT)
	for distance in range(1, 17):
		var candidate = source_pos + vector * LayoutOptimizer.ROOM_SPACING * distance
		if not _proxy_collides(candidate, existing_proxies):
			return candidate
	return source_pos + vector * LayoutOptimizer.ROOM_SPACING * 17

func _proxy_collides(candidate: Vector2, existing_proxies: Dictionary) -> bool:
	for room_id in room_nodes:
		if abs(candidate.x - room_nodes[room_id].position.x) < ROOM_CLEARANCE.x and abs(candidate.y - room_nodes[room_id].position.y) < ROOM_CLEARANCE.y:
			return true
	for proxy_id in existing_proxies:
		var proxy_pos: Vector2 = existing_proxies[proxy_id]
		if abs(candidate.x - proxy_pos.x) < ROOM_CLEARANCE.x and abs(candidate.y - proxy_pos.y) < ROOM_CLEARANCE.y:
			return true
	return false

func _connect_node_signals(node: Node, id: String):
	node.room_selected.connect(func(_i): node_selected.emit(id))
	node.room_double_clicked.connect(func(_i): node_double_clicked.emit(id))
	node.drag_started.connect(func(): node_drag_started.emit(id))
	node.right_clicked.connect(func(): node_right_clicked.emit(id))
	node.connection_drag_started.connect(func(_i): connection_drag_started.emit(id))
	node.creation_drag_started.connect(func(_i, pos): creation_drag_started.emit(id, pos))
	node.dragged.connect(func(pos): node_dragging.emit(id, pos))
	node.drag_ended.connect(func(): node_dragged.emit(id, node.position))
	node.label_clicked.connect(func(_i): label_clicked.emit(id))
	node.label_drag_started.connect(func(_i): label_drag_started.emit(id))
	node.label_dragged.connect(func(_i): label_dragged.emit(id))
	node.label_drag_ended.connect(func(_i): label_drag_ended.emit(id))

func update_node_visuals(node, data, view_mode = "Default"):
	var props = data.get("properties", {})
	var has_npcs = data.has("initial_npcs") and data.initial_npcs.size() > 0
	var has_items = data.has("items") and data.items.size() > 0
	var is_start = props.get("is_start_node", false)
	var custom_icon_id = props.get("icon", "")
	
	node.update_icons(has_npcs, has_items, is_start, custom_icon_id, props)
	
	var col = _get_room_color(props) # Default
	if view_mode != "Default":
		var mode_key = view_mode.to_lower()
		col = _get_mode_color(props, mode_key, col)
		
	node.set_node_color(col)

func _get_room_color(p): 
	if p.get("dark", false): return Color(0.15, 0.05, 0.25)
	if p.get("safe_zone", false): return Color(0.15, 0.35, 0.15)
	if p.get("outdoors", false): return Color(0.3, 0.25, 0.2)
	return Color(0.2, 0.2, 0.2)

func _get_mode_color(props: Dictionary, key: String, default_col: Color) -> Color:
	if not props.has(key): return default_col.darkened(0.5) # Dim nodes without the property
	
	var val = props[key]
	if typeof(val) == TYPE_BOOL:
		return Color.GREEN if val else Color.RED
	elif typeof(val) == TYPE_STRING:
		# Hash string to a stable color
		var h = (abs(val.hash()) % 1000) / 1000.0
		# Use HSV for distinct but pleasant colors (S=0.6, V=0.7)
		return Color.from_hsv(h, 0.6, 0.7)
	
	return default_col
