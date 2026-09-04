# scripts/controllers/view_builders/WorldViewBuilder.gd
class_name WorldViewBuilder
extends RefCounted

const REGION_SCENE_SCRIPT = preload("res://scripts/scenes/RegionScene.gd")
const WORLD_SCALE = 0.1

var container: Node2D
var world_region_nodes: Dictionary = {}

signal region_node_selected(region_id)
signal region_moved(region_id, old_pos, new_pos)
signal request_region_edit(region_id)
signal region_dragged

func _init(p_container: Node2D):
	container = p_container

func build(all_world_data: Dictionary, positions: Dictionary, current_region_data: Dictionary, current_region_filename: String):
	clear()
	
	var working_data = all_world_data.duplicate(true)
	if current_region_filename != "":
		var live_rid = current_region_data.get("region_id", "")
		if live_rid != "" and working_data.has(live_rid):
			working_data[live_rid] = current_region_data
			
	var default_offset_x = 0.0
	for rid in working_data:
		var region_pos = Vector2.ZERO
		if positions.has(rid):
			region_pos = Vector2(positions[rid][0], positions[rid][1]) * WORLD_SCALE
		else:
			region_pos = Vector2(default_offset_x, 0) * WORLD_SCALE
			default_offset_x += 1200 
		
		var r_node = REGION_SCENE_SCRIPT.new()
		r_node.position = region_pos
		r_node.scale = Vector2(WORLD_SCALE, WORLD_SCALE)
		r_node.setup(rid, working_data[rid], _get_region_color(rid))
		
		# Connect signals
		r_node.region_selected.connect(func(id): region_node_selected.emit(id))
		r_node.region_moved_committed.connect(func(old, new): region_moved.emit(rid, old / WORLD_SCALE, new / WORLD_SCALE))
		r_node.request_edit.connect(func(id): request_region_edit.emit(id))
		# When a region node is dragged, forward a signal so Main knows an object drag is happening.
		r_node.region_dragged.connect(func(_pos): region_dragged.emit())
		
		container.add_child(r_node)
		world_region_nodes[rid] = r_node

func clear():
	for c in container.get_children(): c.queue_free()
	world_region_nodes.clear()

func _get_region_color(rid: String) -> Color:
	var hash = rid.hash()
	var h = float(hash % 1000) / 1000.0
	return Color.from_hsv(h, 0.4, 0.3)
