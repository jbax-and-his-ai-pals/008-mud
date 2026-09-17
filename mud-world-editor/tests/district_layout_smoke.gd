extends SceneTree

const DistrictLayout = preload("res://scripts/generators/DistrictLayout.gd")

var failures := 0

func _init() -> void:
	var rooms := {
		"square": {"_editor_pos": [0, 0], "exits": {}},
		"gate": {"_editor_pos": [600, 0], "exits": {"east": "lane"}},
		"lane": {"_editor_pos": [856, 0], "exits": {"west": "gate", "southeast": "diagonal"}},
		"diagonal": {"_editor_pos": [1112, 192], "exits": {"northwest": "lane"}},
	}
	var preview = DistrictLayout.preview_attachment(rooms, ["gate", "lane", "diagonal"], "gate", "square", "east")
	_assert(preview.valid, "sparse diagonal district fits beside its target")
	_assert(preview.positions["gate"] == Vector2(256, 0), "attachment port sits one unit east of target")
	_assert(preview.connection_plan.direction == "east", "preview returns the connection plan")

	rooms["blocker"] = {"_editor_pos": [512, 0], "exits": {}}
	var blocked = DistrictLayout.preview_attachment(rooms, ["gate", "lane", "diagonal"], "gate", "square", "east")
	_assert(not blocked.valid, "collision blocks the preview")
	_assert(blocked.errors.any(func(message): return "blocker" in message), "collision names the blocking room")

	var disconnected = DistrictLayout.preview_attachment(rooms, ["gate", "diagonal"], "gate", "square", "north")
	_assert(not disconnected.valid, "disconnected selections are rejected")
	_assert(disconnected.errors.any(func(message): return "disconnected" in message), "continuity error explains the problem")
	quit(1 if failures > 0 else 0)

func _assert(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error("DistrictLayout smoke test failed: " + message)
