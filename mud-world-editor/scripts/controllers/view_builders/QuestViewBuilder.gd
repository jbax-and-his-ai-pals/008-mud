# scripts/controllers/view_builders/QuestViewBuilder.gd
class_name QuestViewBuilder
extends RefCounted

const QUEST_NODE_SCRIPT = preload("res://scripts/scenes/QuestNode.gd")

var container: Node2D
var quest_nodes: Dictionary = {} # stage_idx -> Node

signal node_selected(idx)
signal node_moved(idx, pos)
signal node_dragged

func _init(c: Node2D):
	container = c

func build(quest_data: Dictionary):
	clear()
	if not quest_data.has("stages"): return
	
	var stages = quest_data.stages
	
	# Auto-layout if positions missing
	for i in range(stages.size()):
		var s = stages[i]
		if not s.has("_editor_pos"):
			s["_editor_pos"] = [i * 250, 0] # Default linear layout
			
		var pos = Vector2(s._editor_pos[0], s._editor_pos[1])
		_spawn_node(i, s, pos)

	# Queue redraw for connections handled by GraphController or local draw
	container.queue_redraw()

func _spawn_node(idx, data, pos):
	var node = Control.new()
	node.set_script(QUEST_NODE_SCRIPT)
	node.setup(idx, data)
	node.position = pos
	
	node.selected.connect(func(i): node_selected.emit(i))
	node.dragged.connect(func(p): node_moved.emit(idx, p); container.queue_redraw())
	node.drag_ended.connect(func(): node_dragged.emit())
	
	container.add_child(node)
	quest_nodes[idx] = node

func clear():
	for c in container.get_children(): c.queue_free()
	quest_nodes.clear()

func draw_connections(canvas: Node2D, quest_data: Dictionary):
	if not quest_data.has("stages"): return
	var stages = quest_data.stages
	
	for i in range(stages.size()):
		var s = stages[i]
		var next_id = s.get("next", "")
		
		# Find target index by ID
		var target_idx = -1
		if next_id != "":
			for j in range(stages.size()):
				if stages[j].get("id", "") == next_id:
					target_idx = j
					break
		# Default next
		elif i < stages.size() - 1:
			target_idx = i + 1
			
		if target_idx != -1 and quest_nodes.has(i) and quest_nodes.has(target_idx):
			var n1 = quest_nodes[i]
			var n2 = quest_nodes[target_idx]
			var p1 = n1.position + n1.custom_minimum_size / 2
			var p2 = n2.position + n2.custom_minimum_size / 2
			
			canvas.draw_line(p1, p2, Color.WHITE, 2.0)
			# Draw Arrow
			var dir = (p2 - p1).normalized()
			var tip = p2 - (dir * 40)
			var a1 = tip - dir.rotated(0.5) * 10
			var a2 = tip - dir.rotated(-0.5) * 10
			canvas.draw_colored_polygon(PackedVector2Array([tip, a1, a2]), Color.WHITE)
