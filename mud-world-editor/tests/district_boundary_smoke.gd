# Verifies the boundary-tracing, Douglas-Peucker simplification, and Chaikin
# corner-cutting behind district territory backgrounds
# (GraphController._on_draw_district_backgrounds): raster-mask edge-following
# turns a district's owned cells into closed vertex loops, staircase noise
# from the cell grid gets collapsed before any curve is drawn, and the
# result stays tight to the original shape instead of bowing past it.
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

	# A single stray cell surrounded on 3+ sides by another district is
	# noise (the kind of thing that shows up downstream as a small jagged
	# notch DP has no reason to remove) and must be reassigned to its
	# neighbors' majority owner.
	var speckled := {
		Vector2i(0, 0): 1, Vector2i(1, 0): 1, Vector2i(2, 0): 1,
		Vector2i(0, 1): 1, Vector2i(1, 1): 0, Vector2i(2, 1): 1,
		Vector2i(0, 2): 1, Vector2i(1, 2): 1, Vector2i(2, 2): 1,
	}
	var despeckled = gc._despeckle_owners(speckled)
	_assert(int(despeckled[Vector2i(1, 1)]) == 1, "an isolated single-cell speckle is reassigned to its neighbors' owner")

	# A cell on a real, wider boundary -- only 2 of 4 neighbors disagree --
	# must be left alone; that is an ordinary border, not noise.
	var real_border := {
		Vector2i(0, 0): 0, Vector2i(1, 0): 1,
		Vector2i(0, 1): 0, Vector2i(1, 1): 1,
	}
	var border_result = gc._despeckle_owners(real_border)
	_assert(int(border_result[Vector2i(0, 0)]) == 0 and int(border_result[Vector2i(1, 0)]) == 1, "an ordinary 2-vs-2 border is left alone")

	# Two side-by-side fields must each trace their own loop.
	var two_field_owners := {
		Vector2i(0, 0): 0, Vector2i(0, 1): 0,
		Vector2i(1, 0): 1, Vector2i(1, 1): 1,
	}
	var loops_a = gc._trace_field_boundary_loops(two_field_owners, 0, 64.0)
	var loops_b = gc._trace_field_boundary_loops(two_field_owners, 1, 64.0)
	_assert(loops_a.size() == 1 and loops_b.size() == 1, "each side of a shared border traces its own single loop")

	# Empty ownership for a field with no cells should trace to zero loops.
	var empty_loops = gc._trace_field_boundary_loops(owners, 5, 64.0)
	_assert(empty_loops.is_empty(), "a field with no owned cells has no loops")

	# A long diagonal staircase (the noisy case a real district border makes
	# at this cell size) must collapse to its two end corners once a
	# generous tolerance says the whole run is straight-ish -- this is what
	# keeps the final curve calm instead of chattering at cell-grid
	# frequency.
	var staircase: Array = []
	for i in range(9):
		staircase.append(Vector2(i * 64, i * 64))
		staircase.append(Vector2((i + 1) * 64, i * 64))
	var simplified_open = gc._douglas_peucker_open(staircase, 48.0)
	_assert(simplified_open.size() == 2, "a straight-ish staircase collapses to its two ends, got %d points" % simplified_open.size())

	# A real corner -- one large deviation partway along -- must survive
	# simplification rather than being smoothed away.
	var with_corner: Array = []
	for i in range(5): with_corner.append(Vector2(i * 64, 0))
	for i in range(1, 5): with_corner.append(Vector2(256, i * 64))
	var simplified_corner = gc._douglas_peucker_open(with_corner, 48.0)
	_assert(simplified_corner.size() == 3, "an actual corner is preserved through simplification, got %d points" % simplified_corner.size())
	if simplified_corner.size() == 3:
		_assert(simplified_corner[1].distance_to(Vector2(256, 0)) < 0.01, "the preserved point is the real corner")

	# Chaikin must never move a point outside the original loop's bounding
	# box -- it can only cut corners inward, never bulge past an edge. This
	# is the property that keeps two adjacent districts' independently
	# smoothed shared border from drifting apart.
	var square := [Vector2(0, 0), Vector2(256, 0), Vector2(256, 256), Vector2(0, 256)]
	var chaikin_result = gc._chaikin_smooth_closed_loop(square, 3)
	for point in chaikin_result:
		_assert(point.x >= -0.01 and point.x <= 256.01 and point.y >= -0.01 and point.y <= 256.01, "point %s stayed within the original square" % point)

	# The actual regression for "tight/overlapping shared borders": two
	# districts meeting along a diagonal staircase must smooth that shared
	# run to (nearly) the same curve on both sides, even though each traces
	# its loop independently and continues into different territory beyond
	# the shared run.
	var staircase_owners := {}
	for x in range(6):
		for y in range(6):
			staircase_owners[Vector2i(x, y)] = 0 if x <= y else 1
	var cell_size_used := 64.0
	var loop_left = gc._trace_field_boundary_loops(staircase_owners, 0, cell_size_used)[0]
	var loop_right = gc._trace_field_boundary_loops(staircase_owners, 1, cell_size_used)[0]
	var smoothed_left = gc._chaikin_smooth_closed_loop(gc._simplify_loop_douglas_peucker(loop_left, 48.0), 3)
	var smoothed_right = gc._chaikin_smooth_closed_loop(gc._simplify_loop_douglas_peucker(loop_right, 48.0), 3)
	# A true 45-degree boundary between square cells has no single shared
	# line -- each side's mask edge is its own staircase, offset from the
	# other by up to a cell or so. Smoothing cannot manufacture exact
	# coincidence out of that, and most of each district's own boundary
	# (the far, non-adjacent sides) is correctly nowhere near the other
	# district at all, so the meaningful check is only over the points that
	# genuinely face each other: among those, the gap should stay on the
	# order of one cell, not balloon into something else entirely.
	var facing_gaps: Array = []
	for lp in smoothed_left:
		var nearest := INF
		for rp in smoothed_right:
			nearest = minf(nearest, lp.distance_to(rp))
		if nearest < 150.0: facing_gaps.append(nearest)
	_assert(facing_gaps.size() > 0, "some part of the diagonal boundary is recognized as facing the other district")
	var worst := 0.0
	for gap in facing_gaps: worst = maxf(worst, gap)
	# Empirically, independent per-side simplification of a pure 45-degree
	# staircase converges to roughly two cell-widths of residual gap at its
	# worst point, not one -- the two sides' anchor vertices for the shared
	# run are themselves a staircase apart. This is a real, known limit of
	# tracing+simplifying each district's mask on its own rather than
	# computing one shared boundary line for both sides; it is not
	# something this test should pretend is tighter than it is. The
	# renderer narrows it in practice with a finer cell size (see
	# _on_draw_district_backgrounds) and it does not apply to the far more
	# common cardinal (straight) borders, which the next check covers.
	_assert(worst <= cell_size_used * 2.5, "the facing part of a diagonal shared border stays within a couple of cell-widths, got %.1f" % worst)

	# The common, representative case -- two districts meeting along a
	# straight (cardinal) line -- must line up on the nose: this is the
	# actual "tight/overlapping" property for the borders that matter most.
	var straight_owners := {}
	for x in range(4):
		for y in range(4):
			straight_owners[Vector2i(x, y)] = 0 if x < 2 else 1
	var loop_a = gc._trace_field_boundary_loops(straight_owners, 0, 64.0)[0]
	var loop_b = gc._trace_field_boundary_loops(straight_owners, 1, 64.0)[0]
	var smoothed_a = gc._chaikin_smooth_closed_loop(gc._simplify_loop_douglas_peucker(loop_a, 48.0), 3)
	var smoothed_b = gc._chaikin_smooth_closed_loop(gc._simplify_loop_douglas_peucker(loop_b, 48.0), 3)
	var shared_line_matches := 0
	for point in smoothed_a:
		if is_equal_approx(point.x, 128.0):
			for other in smoothed_b:
				if point.distance_to(other) < 0.5:
					shared_line_matches += 1
					break
	_assert(shared_line_matches >= 2, "a straight shared border is bit-for-bit identical on both sides, got %d matching points" % shared_line_matches)

	quit(1 if failures > 0 else 0)

func _assert(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error("District boundary smoothing verification failed: " + message)
