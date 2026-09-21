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
var selected_district_id: String = ""
var highlighted_target_id: String = ""
var connection_preview: Dictionary = {"active": false, "source_id": "", "target_id": ""}
var district_preview: Dictionary = {"active": false, "valid": false, "positions": {}, "rooms": {}, "district": {}}
var district_dragging: Dictionary = {"active": false, "mouse_start": Vector2.ZERO, "positions": {}}

# Interaction State (temporary state during an action)
var dragging_conn: Dictionary = {"active": false, "start": Vector2.ZERO, "end": Vector2.ZERO, "src": ""}
# The world-view equivalent of dragging_conn: a connection dragged from one
# region's shape toward another, rather than from a specific room. Kept
# separate from dragging_conn (whose "src" is always a room in the
# currently open region) rather than reused, since a region drag's source
# room may belong to a region that isn't even loaded yet.
var world_dragging_conn: Dictionary = {"active": false, "start": Vector2.ZERO, "end": Vector2.ZERO, "src_region": "", "src_room": ""}
# An already-committed district (not the placement-preview flow above)
# being dragged as one rigid unit -- every member room's start position,
# offset live by the same delta, so the district's shape, its interior
# connections, and its connections out to the rest of the region all move
# together the same way a multi-room selection drag already does.
var district_move_dragging: Dictionary = {"active": false, "district_id": "", "mouse_start": Vector2.ZERO, "positions": {}}
var creating_conn: Dictionary = { "active": false, "start_pos": Vector2.ZERO, "end_pos": Vector2.ZERO, "src_id": "" }

# True while the connection form is open, which is a *mode* rather than a panel:
# in it, a click on the map means "make this the far end of the connection", not
# "select this room". Without this, dragging a room and picking a target are the
# same gesture, and an author aiming at a room to connect it moves it instead --
# a change that survives into the save and is easy not to notice.
#
# Set by the inspector when the form opens, cleared when it closes for any reason.
var connection_mode: bool = false
var is_box_selecting: bool = false
var box_select_start: Vector2 = Vector2.ZERO
var drag_start_positions: Dictionary = {}

func clear_selection():
	selected_ids.clear()
	selected_district_id = ""

func set_selection(ids: Array):
	selected_ids = ids
	if not ids.is_empty(): selected_district_id = ""

func set_district_selection(district_id: String):
	selected_district_id = district_id
	selected_ids.clear()

func clear_district_selection():
	selected_district_id = ""

func add_to_selection(id: String):
	selected_district_id = ""
	if not selected_ids.has(id):
		selected_ids.append(id)

func remove_from_selection(id: String):
	if selected_ids.has(id):
		selected_ids.erase(id)

func is_selected(id: String) -> bool:
	return selected_ids.has(id)
