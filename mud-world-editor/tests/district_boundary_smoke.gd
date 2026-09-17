# Verifies the boundary-tracing and Catmull-Rom smoothing behind district
# territory backgrounds (GraphController._on_draw_district_backgrounds):
# raster-mask edge-following turns a district's owned cells into closed
# vertex loops, which are then simplified and smoothed into the curve
# actually drawn.
extends SceneTree

const GraphController = preload("res://scripts/controllers/GraphController.gd")

var failures := 0

func _init() -> void:
	var gc := GraphController.new()

	# A simple 2x2 block of cells owned by field 0, isolated square. Should
	# trace to exactly one closed loop of 4 corners at cell_size=64.
	var owners := {
		Vector2i(0, 0): 0, Vector2i(1, 0): 0,
		Vector2i(0, 1): 0, Vector2i(1, 1): 0,
	}
	var loops = gc._trace_field_boundary_loops(owners, 0, 64.0)
	_assert(loops.size() == 1, "a solid block traces to exactly one loop, got %d" % loops.size())
	if loops.size() == 1:
		var simplified = gc._simplify_collinear_loop(loops[0])
		_assert(simplified.size() == 4, "a rectangular block simplifies to its 4 corners, got %d" % simplified.size())
		var smoothed = gc._smooth_closed_loop(simplified, 6)
		_assert(smoothed.size() == simplified.size() * 6, "smoothing samples every segment, got %d points" % smoothed.size())
		# Catmull-Rom passes exactly through each original vertex at t=0.
		for corner in simplified:
			var found := false
			for point in smoothed:
				if point.distance_to(corner) < 0.01: found = true
			_assert(found, "the smoothed curve still passes through corner %s" % corner)

	# Two side-by-side fields must each trace their own loop, and the shared
	# edge must not appear in the other's boundary as an internal seam.
	var two_field_owners := {
		Vector2i(0, 0): 0, Vector2i(0, 1): 0,
		Vector2i(1, 0): 1, Vector2i(1, 1): 1,
	}
	var loops_a = gc._trace_field_boundary_loops(two_field_owners, 0, 64.0)
	var loops_b = gc._trace_field_boundary_loops(two_field_owners, 1, 64.0)
	_assert(loops_a.size() == 1 and loops_b.size() == 1, "each side of a shared border traces its own single loop")

	# Empty ownership for a field with no cells should trace to zero loops,
	# not crash.
	var empty_loops = gc._trace_field_boundary_loops(owners, 5, 64.0)
	_assert(empty_loops.is_empty(), "a field with no owned cells has no loops")

	quit(1 if failures > 0 else 0)

func _assert(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error("District boundary smoothing verification failed: " + message)
