# Verifies ExplorerPanel groups a region's rooms by district (falling back
# to a flat list for a district-less region or an ungrouped room), and that
# selecting a room by id finds it under however many levels of nesting that
# takes, un-collapsing every ancestor along the way.
extends SceneTree

const ExplorerPanel = preload("res://scripts/ui/panels/ExplorerPanel.gd")

var failures := 0

func _init() -> void:
	var panel := ExplorerPanel.new()
	root.add_child(panel)
	panel.setup()

	var hierarchy := {
		"town": {
			"filename": "town.json",
			"rooms": {
				"town_square": "Town Square",
				"west_lane": "West Lane",
				"lonely_room": "Lonely Room",
			},
			"districts": {
				"civic_core": {"name": "Civic Core", "color": "#4e8bb5", "members": ["town_square", "west_lane"]},
			},
		},
	}
	panel.update_data(hierarchy, "town.json", "")

	var root_item := panel.explorer_tree.get_root()
	var region_item := root_item.get_children()[0]
	_assert(region_item.get_metadata(0).id == "town", "the region item is still the top-level node")

	var district_item: TreeItem = null
	var lonely_item: TreeItem = null
	for child in region_item.get_children():
		var meta = child.get_metadata(0)
		if meta and meta.get("type", "") == "district": district_item = child
		if meta and meta.get("id", "") == "lonely_room": lonely_item = child
	_assert(district_item != null, "a district with matching rooms gets its own tree item under the region")
	_assert(lonely_item != null, "a room with no district still sits directly under the region")

	if district_item:
		var member_ids: Array = []
		for child in district_item.get_children():
			member_ids.append(child.get_metadata(0).id)
		member_ids.sort()
		_assert(member_ids == ["town_square", "west_lane"], "the district item's children are exactly its member rooms, got %s" % [member_ids])

	# Selecting a room nested under a district must un-collapse the region
	# AND the district, and land the actual Tree selection on that room.
	region_item.collapsed = true
	if district_item: district_item.collapsed = true
	panel._apply_room_selection("west_lane")
	var selected := panel.explorer_tree.get_selected()
	_assert(selected != null and selected.get_metadata(0).id == "west_lane", "selecting a nested room actually selects it")
	_assert(not region_item.collapsed, "selecting a nested room un-collapses its region")
	if district_item: _assert(not district_item.collapsed, "selecting a nested room un-collapses its district")

	# A room with no district must still be selectable directly under the
	# region, same as before districts existed.
	panel._apply_room_selection("lonely_room")
	var selected_lonely := panel.explorer_tree.get_selected()
	_assert(selected_lonely != null and selected_lonely.get_metadata(0).id == "lonely_room", "a district-less room is still selectable")

	quit(1 if failures > 0 else 0)

func _assert(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error("Explorer district grouping smoke test failed: " + message)
