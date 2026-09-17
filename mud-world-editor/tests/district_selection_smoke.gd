# Verifies GraphController.get_district_id_at, the click hit-test behind
# "clicking empty space inside a district selects it": it must resolve to
# the same territory the background renderer paints (built from the same
# _build_district_fields/_resolve_district_field_index), return "" outside
# every district, and leave the selection highlight (EditorState) able to
# tell one district's fill/ridge apart from the rest.
extends SceneTree

const GraphController = preload("res://scripts/controllers/GraphController.gd")
const LocalViewBuilder = preload("res://scripts/controllers/view_builders/LocalViewBuilder.gd")
const EditorState = preload("res://scripts/core/EditorState.gd")

var failures := 0

func _init() -> void:
	var container := Node2D.new()
	root.add_child(container)

	# Two districts, each a tight cluster of rooms, far enough apart that a
	# point near either cluster unambiguously belongs to it and a point far
	# from both belongs to neither.
	var region_data := {
		"rooms": {
			"town_square": {"_editor_pos": [0, 0], "name": "Town Square", "exits": {"west": "west_lane"}},
			"west_lane": {"_editor_pos": [-256, 0], "name": "West Lane", "exits": {"east": "town_square"}},
			"market_square": {"_editor_pos": [900, 0], "name": "Market Square", "exits": {}},
		},
		"properties": {
			"districts": {
				"civic_core": {"name": "Civic Core", "members": ["town_square", "west_lane"]},
				"market_row": {"name": "Market Row", "members": ["market_square"]},
			}
		}
	}

	var builder := LocalViewBuilder.new(container)
	builder.build(region_data, false)

	var gc := GraphController.new()
	gc.local_view_builder = builder
	gc.region_data = region_data
	gc.editor_state = EditorState.new()
	gc.current_mode = GraphController.ViewMode.LOCAL

	_assert(gc.get_district_id_at(Vector2(-128, 0)) == "civic_core", "a point between civic_core's rooms resolves to civic_core")
	_assert(gc.get_district_id_at(Vector2(900, 0)) == "market_row", "a point on market_row's own room resolves to market_row")
	_assert(gc.get_district_id_at(Vector2(9999, 9999)) == "", "a point far from every district resolves to nothing")

	# The world view and quest view never hit-test districts -- they are a
	# local-view-only concept.
	gc.current_mode = GraphController.ViewMode.WORLD
	_assert(gc.get_district_id_at(Vector2(-128, 0)) == "", "the hit-test is inert outside the local view")
	gc.current_mode = GraphController.ViewMode.LOCAL

	# Selecting a district is mutually exclusive with room selection in
	# both directions -- Main._select_district and EditorState mirror this
	# so the inspector and the highlight never disagree about what's active.
	var state := gc.editor_state
	state.set_selection(["town_square"])
	state.set_district_selection("civic_core")
	_assert(state.selected_district_id == "civic_core", "selecting a district records its id")
	_assert(state.selected_ids.is_empty(), "selecting a district clears any room selection")
	state.set_selection(["town_square"])
	_assert(state.selected_district_id == "", "selecting a room clears any district selection")

	quit(1 if failures > 0 else 0)

func _assert(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error("District selection smoke test failed: " + message)
