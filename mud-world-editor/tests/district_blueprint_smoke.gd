extends SceneTree

const DistrictBlueprint = preload("res://scripts/generators/DistrictBlueprint.gd")
var failures := 0

func _init() -> void:
	var blueprint := {
		"id": "market_block",
		"name": "Market Block",
		"kind": "market",
		"seed": 417,
		"generator": {"algorithm": "grid", "params": {"rows": 3, "cols": 3, "room_density": 1.0, "conn_density": 0.0}},
		"ports": [{"id": "west_gate", "direction": "west"}, {"id": "south_lane", "direction": "south"}],
	}
	var first = DistrictBlueprint.generate(blueprint)
	var second = DistrictBlueprint.generate(blueprint)
	_assert(first.ok and second.ok, "valid district blueprint generates")
	_assert(first.rooms.size() == second.rooms.size() and first.rooms.keys() == second.rooms.keys(), "seeded generation is reproducible")
	_assert(first.district.ports.size() == 2, "requested directional ports are exposed")
	for room_id in first.rooms:
		_assert(first.rooms[room_id].properties._district_id == "market_block", "generated room records its district identity")
	var reroll = DistrictBlueprint.preview_reroll(blueprint, 418)
	_assert(reroll.ok and reroll.preview_only, "reroll returns a non-mutating preview")
	quit(1 if failures > 0 else 0)

func _assert(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error("DistrictBlueprint smoke test failed: " + message)
