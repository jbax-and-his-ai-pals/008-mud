# scripts/generators/DistrictBlueprint.gd
class_name DistrictBlueprint
extends RefCounted

const RegionGenerator = preload("res://scripts/generators/RegionGenerator.gd")

const ALGORITHMS := {
	"grid": RegionGenerator.Algo.GRID,
	"maze": RegionGenerator.Algo.MAZE,
	"hub": RegionGenerator.Algo.HUB,
	"crescent": RegionGenerator.Algo.CRESCENT,
	"ring": RegionGenerator.Algo.RING,
	"highway": RegionGenerator.Algo.HIGHWAY,
	"spiral": RegionGenerator.Algo.SPIRAL,
	"house": RegionGenerator.Algo.HOUSE,
	"town": RegionGenerator.Algo.TOWN,
	"city": RegionGenerator.Algo.CITY,
	"castle": RegionGenerator.Algo.CASTLE,
}

# Generate a sparse, self-contained district. Ports are role-based rather
# than hard-coded room IDs: a reroll may replace internal rooms while keeping
# the public "north gate" or "market entrance" contract intact.
static func generate(definition: Dictionary) -> Dictionary:
	var validation := validate(definition)
	if not validation.is_empty():
		return {"ok": false, "errors": validation, "district": {}, "rooms": {}}
	var district_id := str(definition["id"])
	var generator: Dictionary = definition.get("generator", {})
	var algorithm_name := str(generator.get("algorithm", "grid")).to_lower()
	var params: Dictionary = generator.get("params", {}).duplicate(true)
	params["seed"] = int(definition.get("seed", 0))
	var generated = RegionGenerator.generate(ALGORITHMS[algorithm_name], params)
	var rooms := {}
	var id_map := {}
	for raw_id in generated:
		var room_id := district_id + "__" + str(raw_id)
		id_map[raw_id] = room_id
	for raw_id in generated:
		var room: Dictionary = generated[raw_id].duplicate(true)
		var exits: Dictionary = room.get("exits", {})
		for direction in exits:
			if id_map.has(exits[direction]):
				exits[direction] = id_map[exits[direction]]
		room["exits"] = exits
		if not room.has("properties"):
			room["properties"] = {}
		room["properties"]["_district_id"] = district_id
		rooms[id_map[raw_id]] = room
	var ports := _derive_ports(rooms, definition.get("ports", []))
	var district = {
		"id": district_id,
		"name": str(definition.get("name", district_id.capitalize())),
		"kind": str(definition.get("kind", "generic")),
		"seed": int(definition.get("seed", 0)),
		"generator": generator.duplicate(true),
		"ports": ports,
		"members": rooms.keys(),
		"reroll_policy": definition.get("reroll_policy", {"preserve_ports": true, "preserve_named_landmarks": true}).duplicate(true),
	}
	return {"ok": true, "errors": [], "district": district, "rooms": rooms}

static func preview_reroll(definition: Dictionary, new_seed: int) -> Dictionary:
	var candidate := definition.duplicate(true)
	candidate["seed"] = new_seed
	var generated = generate(candidate)
	if not generated.get("ok", false):
		return generated
	generated["preview_only"] = true
	generated["summary"] = "%d generated rooms; %d reusable port roles." % [generated["rooms"].size(), generated["district"]["ports"].size()]
	return generated

static func validate(definition: Dictionary) -> Array:
	var errors: Array = []
	var district_id := str(definition.get("id", "")).strip_edges()
	if district_id == "":
		errors.append("District needs a stable id.")
	elif not district_id.is_valid_identifier():
		errors.append("District id must be a valid identifier.")
	var generator = definition.get("generator", {})
	if not generator is Dictionary:
		errors.append("District generator must be a dictionary.")
		return errors
	var algorithm_name := str(generator.get("algorithm", "")).to_lower()
	if not ALGORITHMS.has(algorithm_name):
		errors.append("Unknown district generator '%s'." % algorithm_name)
	for port in definition.get("ports", []):
		if not port is Dictionary:
			errors.append("Each district port must be a dictionary.")
			continue
		var direction := str(port.get("direction", "")).to_lower()
		if not Constants.DIR_VECTORS.has(direction):
			errors.append("Port '%s' needs a known direction." % str(port.get("id", "unnamed")))
	return errors

static func _derive_ports(rooms: Dictionary, requested_ports: Array) -> Array:
	var ports: Array = []
	for requested in requested_ports:
		var direction := str(requested.get("direction", "")).to_lower()
		var room_id := _furthest_room_in_direction(rooms, direction)
		if room_id == "":
			continue
		ports.append({
			"id": str(requested.get("id", direction + "_port")),
			"direction": direction,
			"role": str(requested.get("role", "entrance")),
			"room_id": room_id,
		})
	return ports

static func _furthest_room_in_direction(rooms: Dictionary, direction: String) -> String:
	var vector: Vector2 = Constants.DIR_VECTORS.get(direction, Vector2.ZERO)
	var best_id := ""
	var best_score := -INF
	for room_id in rooms:
		var pos := _room_position(rooms[room_id])
		var score := pos.dot(vector)
		if score > best_score or (is_equal_approx(score, best_score) and str(room_id) < best_id):
			best_score = score
			best_id = str(room_id)
	return best_id

static func _room_position(room: Dictionary) -> Vector2:
	var raw = room.get("_editor_pos", [0, 0])
	return Vector2(float(raw[0]), float(raw[1])) if raw is Array and raw.size() >= 2 else Vector2.ZERO
