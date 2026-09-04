# scripts/core/EditorState.gd
class_name EditorState
extends RefCounted

# Manages the active state of the editor.

# View & Tool State
var is_world_view: bool = false
var snap_enabled: bool = false
var cur_tool_mode = EditorUIManager.ToolMode.SELECT
var cur_tool_data: Dictionary = {}

# Selection State
var selected_ids: Array = []
var highlighted_target_id: String = ""
var connection_preview: Dictionary = {"active": false, "source_id": "", "target_id": ""}

# Interaction State (temporary state during an action)
var dragging_conn: Dictionary = {"active": false, "start": Vector2.ZERO, "end": Vector2.ZERO, "src": ""}
var creating_conn: Dictionary = { "active": false, "start_pos": Vector2.ZERO, "end_pos": Vector2.ZERO, "src_id": "" }
var is_box_selecting: bool = false
var box_select_start: Vector2 = Vector2.ZERO
var drag_start_positions: Dictionary = {}

func clear_selection():
	selected_ids.clear()

func set_selection(ids: Array):
	selected_ids = ids

func add_to_selection(id: String):
	if not selected_ids.has(id):
		selected_ids.append(id)

func remove_from_selection(id: String):
	if selected_ids.has(id):
		selected_ids.erase(id)

func is_selected(id: String) -> bool:
	return selected_ids.has(id)
