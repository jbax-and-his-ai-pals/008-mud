# scripts/generators/TerritoryShape.gd
# The generic "cell-grid ownership -> smooth polygon" pipeline behind
# district territory backgrounds (GraphController) and, now, world-view
# region shapes (RegionScene). Nothing here knows about districts or
# regions specifically -- it only ever sees an `owners: Dictionary`
# (Vector2i cell -> integer field id) and a `field_index`, so any caller
# with its own reason to raster something into cells can reuse the exact
# same despeckling/tracing/smoothing without duplicating it.
class_name TerritoryShape
extends RefCounted

# A cell whose 4-neighbors are mostly one other field is noise, not a real
# feature -- whatever rule decided ownership was reasonable in isolation,
# but can flip a single stray cell right at a seam, which then shows up
# downstream as a small jagged notch or spike the simplification pass has
# no reason to remove (a lone flipped cell is a real, if tiny, deviation
# from any chord near it). Requiring 3 of 4 neighbors to agree before
# reassigning a cell is deliberately strict: it only cleans up single-cell
# pockets and leaves genuine thin necks or corridors (which are many cells
# wide, so never look this isolated) alone.
static func despeckle_owners(owners: Dictionary) -> Dictionary:
	var neighbor_offsets := [Vector2i(0, -1), Vector2i(0, 1), Vector2i(1, 0), Vector2i(-1, 0)]
	var cleaned := owners.duplicate()
	for cell in owners:
		var current: int = owners[cell]
		var counts: Dictionary = {}
		for offset in neighbor_offsets:
			if not owners.has(cell + offset): continue
			var neighbor_owner: int = owners[cell + offset]
			counts[neighbor_owner] = counts.get(neighbor_owner, 0) + 1
		var best_owner := current
		var best_count: int = counts.get(current, 0)
		for owner in counts:
			if counts[owner] > best_count:
				best_count = counts[owner]
				best_owner = owner
		if best_owner != current and best_count >= 3: cleaned[cell] = best_owner
	return cleaned

# Walks the owned-cell mask for one field into one or more closed,
# world-space vertex loops (its outer boundary, plus any hole it has been
# squeezed into by a neighbor -- rare, but not assumed away). Every owned
# cell contributes its clockwise-facing edges wherever the neighbor across
# that edge belongs to someone else (or nobody); those directed edges chain
# start-to-end into full loops because a raster region's boundary always
# does, regardless of its shape.
static func trace_boundary_loops(owners: Dictionary, field_index: int, cell_size: float) -> Array:
	var next_vertex: Dictionary = {}
	var vertex_by_key: Dictionary = {}
	for cell in owners:
		if int(owners[cell]) != field_index: continue
		var cx: int = cell.x
		var cy: int = cell.y
		var tl := Vector2(cx, cy) * cell_size
		var tr := Vector2(cx + 1, cy) * cell_size
		var br := Vector2(cx + 1, cy + 1) * cell_size
		var bl := Vector2(cx, cy + 1) * cell_size
		if int(owners.get(Vector2i(cx, cy - 1), -1)) != field_index: _add_boundary_edge(next_vertex, vertex_by_key, tl, tr)
		if int(owners.get(Vector2i(cx + 1, cy), -1)) != field_index: _add_boundary_edge(next_vertex, vertex_by_key, tr, br)
		if int(owners.get(Vector2i(cx, cy + 1), -1)) != field_index: _add_boundary_edge(next_vertex, vertex_by_key, br, bl)
		if int(owners.get(Vector2i(cx - 1, cy), -1)) != field_index: _add_boundary_edge(next_vertex, vertex_by_key, bl, tl)
	var visited: Dictionary = {}
	var loops: Array = []
	for start_key in next_vertex.keys():
		if visited.has(start_key): continue
		var loop: Array = []
		var current_key: String = start_key
		var guard := 0
		while not visited.has(current_key) and next_vertex.has(current_key) and guard < 100000:
			visited[current_key] = true
			loop.append(vertex_by_key[current_key])
			current_key = _boundary_vertex_key(next_vertex[current_key])
			guard += 1
		if loop.size() >= 3: loops.append(loop)
	return loops

static func _boundary_vertex_key(v: Vector2) -> String:
	return "%d:%d" % [roundi(v.x), roundi(v.y)]

static func _add_boundary_edge(next_vertex: Dictionary, vertex_by_key: Dictionary, from: Vector2, to: Vector2) -> void:
	var from_key := _boundary_vertex_key(from)
	vertex_by_key[from_key] = from
	vertex_by_key[_boundary_vertex_key(to)] = to
	next_vertex[from_key] = to

# Collapses a run of small cell-grid steps down to its real corners. A
# diagonal-ish boundary at this cell size is a long staircase of tiny
# alternating steps; every one of those steps is a genuine direction change,
# so simple collinearity checks cannot remove them, but they are also not a
# real feature of the shape -- just this grid's resolution. Douglas-Peucker
# keeps only the points a straight chord could not approximate within
# `tolerance`, so a whole staircase run collapses to the two points at its
# ends wherever it is, in fact, straight-ish.
#
# A closed loop needs an anchor point to open it into the chain the
# algorithm actually operates on; anchoring on the loop's own first point
# is arbitrary, but harmlessly so: the recursive algorithm below always
# keeps both ends of whatever chain it is given and only discards a point
# when a straight chord already approximates it, so no real corner can be
# lost regardless of where the seam falls.
static func simplify_douglas_peucker(loop: Array, tolerance: float) -> Array:
	var n := loop.size()
	if n < 5: return loop
	var unrolled: Array = loop.duplicate()
	unrolled.append(loop[0])
	var simplified := _douglas_peucker_open(unrolled, tolerance)
	if simplified.size() >= 2 and simplified[0].is_equal_approx(simplified[simplified.size() - 1]):
		simplified = simplified.slice(0, simplified.size() - 1)
	return simplified if simplified.size() >= 3 else loop

static func _douglas_peucker_open(points: Array, tolerance: float) -> Array:
	var n := points.size()
	if n < 3: return points
	var start: Vector2 = points[0]
	var end: Vector2 = points[n - 1]
	var max_dist := 0.0
	var split_index := 0
	for i in range(1, n - 1):
		var nearest := Geometry2D.get_closest_point_to_segment(points[i], start, end)
		var dist: float = points[i].distance_to(nearest)
		if dist > max_dist:
			max_dist = dist
			split_index = i
	if max_dist <= tolerance:
		return [start, end]
	var left := _douglas_peucker_open(points.slice(0, split_index + 1), tolerance)
	var right := _douglas_peucker_open(points.slice(split_index, n), tolerance)
	var combined: Array = left.duplicate()
	combined.append_array(right.slice(1, right.size()))
	return combined

# Chaikin corner-cutting: each edge contributes two new points a quarter of
# the way in from each end, replacing the original corner. Unlike a spline
# through every point, this can only ever move a boundary *inward* toward
# its own edges, never bulge past them -- which is what keeps two
# independently-smoothed adjacent shapes' shared border tight against each
# other rather than drifting apart, and keeps the curve calm instead of
# overshooting at sharp corners. A few iterations converge quickly; more
# than that just re-rounds an already-round shape.
static func chaikin_smooth(loop: Array, iterations: int = 3) -> Array:
	var points := loop
	for _iteration in range(iterations):
		var n := points.size()
		if n < 3: break
		var next: Array = []
		for i in range(n):
			var p0: Vector2 = points[i]
			var p1: Vector2 = points[(i + 1) % n]
			next.append(p0.lerp(p1, 0.25))
			next.append(p0.lerp(p1, 0.75))
		points = next
	return points

# The full pipeline for one field: trace -> simplify -> smooth. Returns one
# entry per closed loop the field's mask traced to (almost always one).
static func build_smooth_loops(owners: Dictionary, field_index: int, cell_size: float, simplify_tolerance: float, chaikin_iterations: int = 4) -> Array:
	var loops: Array = []
	for loop in trace_boundary_loops(owners, field_index, cell_size):
		var simplified := simplify_douglas_peucker(loop, simplify_tolerance)
		loops.append(chaikin_smooth(simplified, chaikin_iterations))
	return loops

# Dilates a set of positions and segments into a single-field cell-owner
# mask: any cell within `radius` of a position or of the nearest point on a
# segment is owned. This is the single-field case of the reserved-room/
# corridor rules district territory uses for several competing fields --
# with nothing to compete against, "owns this cell" is simply "close
# enough to something that belongs here."
static func dilate_to_owners(bounds: Rect2, cell_size: float, radius: float, positions: Array, segments: Array) -> Dictionary:
	var owners: Dictionary = {}
	var min_x := int(floor(bounds.position.x / cell_size))
	var max_x := int(ceil(bounds.end.x / cell_size))
	var min_y := int(floor(bounds.position.y / cell_size))
	var max_y := int(ceil(bounds.end.y / cell_size))
	for cell_x in range(min_x, max_x):
		for cell_y in range(min_y, max_y):
			var sample := (Vector2(cell_x, cell_y) + Vector2(0.5, 0.5)) * cell_size
			var closest := INF
			for pos in positions:
				closest = minf(closest, sample.distance_to(pos))
				if closest <= radius: break
			if closest > radius:
				for segment in segments:
					var nearest := Geometry2D.get_closest_point_to_segment(sample, segment["from"], segment["to"])
					closest = minf(closest, sample.distance_to(nearest))
					if closest <= radius: break
			if closest <= radius:
				owners[Vector2i(cell_x, cell_y)] = 0
	return owners
