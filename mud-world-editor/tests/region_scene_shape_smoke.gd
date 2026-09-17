# Verifies RegionScene.setup() shapes a region's world-view card from its
# own rooms (TerritoryShape.dilate_to_owners + the same trace/simplify/
# smooth pipeline district territory uses), instead of a plain bounding
# rectangle: connected rooms merge into one shape, genuinely disconnected
# clusters stay separate, and content_rect always bounds whatever shape
# actually got drawn.
extends SceneTree

const RegionScene = preload("res://scripts/scenes/RegionScene.gd")

var failures := 0

func _init() -> void:
	var connected_data := {
		"rooms": {
			"a": {"_editor_pos": [0, 0], "exits": {"east": "b"}},
			"b": {"_editor_pos": [200, 0], "exits": {"west": "a"}},
		}
	}
	var connected := RegionScene.new()
	connected.setup("connected_region", connected_data, Color.WHITE)
	_assert(connected.shape_loops.size() == 1, "two connected rooms merge into a single shape, got %d loops" % connected.shape_loops.size())
	if connected.shape_loops.size() == 1:
		_assert(connected.shape_loops[0].size() >= 3, "the merged shape is a real polygon, not a degenerate sliver")
	for point in connected.shape_loops[0] if not connected.shape_loops.is_empty() else []:
		_assert(connected.content_rect.has_point(point), "content_rect bounds every point of the shape it was derived from")

	var disconnected_data := {
		"rooms": {
			"a": {"_editor_pos": [0, 0], "exits": {}},
			"b": {"_editor_pos": [2000, 2000], "exits": {}},
		}
	}
	var disconnected := RegionScene.new()
	disconnected.setup("disconnected_region", disconnected_data, Color.WHITE)
	_assert(disconnected.shape_loops.size() == 2, "two far-apart, unconnected rooms stay as two separate shapes, got %d" % disconnected.shape_loops.size())

	var empty := RegionScene.new()
	empty.setup("empty_region", {"rooms": {}}, Color.WHITE)
	_assert(empty.content_rect.size.x > 0 and empty.content_rect.size.y > 0, "a room-less region still gets a sane, non-empty content_rect")

	quit(1 if failures > 0 else 0)

func _assert(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error("RegionScene shape smoke test failed: " + message)
