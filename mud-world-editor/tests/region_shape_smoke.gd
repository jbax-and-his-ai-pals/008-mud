# tests/region_shape_smoke.gd
#
# Every region's world-view shape is one clean outline around all its rooms.
#
# The shape is traced from a grid of cells near the region's rooms. Where two
# cells touched only at a corner the tracer followed one of the two outgoing
# edges and dropped the other, so the loop jumped across the pinch and crossed
# itself -- Godot then draws no fill for it, leaving Town as a bare, spiky
# outline with rooms outside it. Gaps between rooms also traced as extra
# loops, drawn as filled blobs inside the region.
#
#   godot --headless --path mud-world-editor --script tests/region_shape_smoke.gd

extends SceneTree

var failures := 0


func _initialize() -> void:
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	DataRoot._resolved = repo.path_join("content_sets/fantasy_frontier")
	DataRoot._source = "test fixture"
	var world_mgr = load("res://scripts/core/WorldManager.gd").new()
	var world: Dictionary = world_mgr.get_all_world_data()
	_assert(world.size() > 10, "the world loads (%d regions)" % world.size())
	var bad: Array = []
	for rid in world:
		var scene := RegionScene.new()
		scene.setup(rid, world[rid], Color.DIM_GRAY)
		var problems := _problems(scene)
		if not problems.is_empty(): bad.append("%s: %s" % [rid, ", ".join(problems)])
		scene.free()
	for line in bad: print("    " + line)
	_assert(bad.is_empty(), "every region is one fillable outline with all its rooms inside (%d bad)" % bad.size())
	if failures > 0: push_error("region shape smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _problems(scene: RegionScene) -> Array:
	var out: Array = []
	for loop in scene.shape_loops:
		if Geometry2D.triangulate_polygon(PackedVector2Array(loop)).is_empty():
			out.append("a loop cannot be filled"); break
	for loop_a in scene.shape_loops:
		for loop_b in scene.shape_loops:
			if loop_a != loop_b and Geometry2D.is_point_in_polygon(loop_a[0], PackedVector2Array(loop_b)):
				out.append("a loop sits inside another"); break
	var outside := 0
	for room_id in scene.cached_rooms:
		var center: Vector2 = scene.get_room_local_center(room_id)
		var inside := false
		for loop in scene.shape_loops:
			if Geometry2D.is_point_in_polygon(center, PackedVector2Array(loop)): inside = true; break
		if not inside: outside += 1
	if outside > 0: out.append("%d rooms outside" % outside)
	return out


func _assert(condition: bool, message: String) -> void:
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
