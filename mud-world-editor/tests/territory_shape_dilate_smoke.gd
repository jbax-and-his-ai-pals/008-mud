# Verifies TerritoryShape.dilate_to_owners, the single-field case behind
# world-view region shapes: any cell within `radius` of a position or a
# segment is owned, with nothing to compete against (unlike district
# territory, which has several fields fighting over the same grid).
extends SceneTree

const TerritoryShape = preload("res://scripts/generators/TerritoryShape.gd")

var failures := 0

func _init() -> void:
	var bounds := Rect2(Vector2(-300, -300), Vector2(600, 600))
	var cell_size := 20.0
	var radius := 100.0

	# A single point dilates to a roughly circular disc: the cell exactly
	# at the point is owned, and one far outside the radius is not.
	var owners_single := TerritoryShape.dilate_to_owners(bounds, cell_size, radius, [Vector2.ZERO], [])
	_assert(owners_single.has(Vector2i(0, 0)), "the cell at the dilation center is owned")
	var far_cell := Vector2i(int(280 / cell_size), 0)
	_assert(not owners_single.has(far_cell), "a cell well outside the radius is not owned")

	# A segment between two far-apart points dilates a connected corridor
	# between them, not just two separate discs -- the whole point of
	# including connections, so a region's shape doesn't pinch at a
	# doorway between two of its own rooms.
	var far_a := Vector2(-250, 0)
	var far_b := Vector2(250, 0)
	var owners_bridged := TerritoryShape.dilate_to_owners(bounds, cell_size, radius, [far_a, far_b], [{"from": far_a, "to": far_b}])
	_assert(owners_bridged.has(Vector2i(0, 0)), "a segment's midpoint is owned even though it is far from either endpoint")

	# Without that segment, the midpoint between two far-apart points is
	# not owned by either disc -- confirms the bridge above is doing real
	# work, not something the radius alone would already cover.
	var owners_unbridged := TerritoryShape.dilate_to_owners(bounds, cell_size, radius, [far_a, far_b], [])
	_assert(not owners_unbridged.has(Vector2i(0, 0)), "without the connecting segment, the midpoint between two far discs is unowned")

	quit(1 if failures > 0 else 0)

func _assert(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error("Territory shape dilation smoke test failed: " + message)
