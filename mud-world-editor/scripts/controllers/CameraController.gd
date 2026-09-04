# scripts/controllers/CameraController.gd

class_name CameraController
extends RefCounted

var camera: Camera2D
var ui_mgr: EditorUIManager
var is_panning: bool = false

func setup(_camera: Camera2D, _ui_mgr: EditorUIManager):
	camera = _camera
	ui_mgr = _ui_mgr

func handle_input(event: InputEvent) -> bool:
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP: 
			zoom(1.1)
			return true
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN: 
			zoom(1.0 / 1.1)
			return true
		elif event.button_index == MOUSE_BUTTON_LEFT:
			is_panning = event.pressed
	
	if event is InputEventMouseMotion and is_panning:
		camera.position -= event.relative / camera.zoom
		return true
		
	return false

func zoom(factor: float):
	camera.zoom = (camera.zoom * factor).clamp(Vector2(0.1,0.1), Vector2(5,5))
	ui_mgr.update_status_zoom(camera.zoom)

func focus_on(target_pos: Vector2, force: bool = false):
	var vp_rect = camera.get_viewport_rect()
	var visible_size = vp_rect.size / camera.zoom
	if force:
		_tween_to(target_pos)
	else:
		var margin = visible_size * 0.25 
		var diff = target_pos - camera.position
		if abs(diff.x) > margin.x or abs(diff.y) > margin.y:
			_tween_to(target_pos)

func center_on_nodes(nodes: Dictionary):
	if nodes.is_empty(): return
	var avg = Vector2.ZERO
	for id in nodes: avg += nodes[id].position
	if nodes.size() > 0: avg /= nodes.size()
	camera.position = avg

func _tween_to(pos: Vector2):
	var tween = camera.create_tween()
	tween.tween_property(camera, "position", pos, 0.4).set_trans(Tween.TRANS_QUART).set_ease(Tween.EASE_OUT)
