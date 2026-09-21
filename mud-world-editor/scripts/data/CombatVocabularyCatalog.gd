class_name CombatVocabularyCatalog
extends RefCounted

var damage_types: Array = []
var hazards: Dictionary = {}

func load() -> void:
	damage_types = []; hazards = {}
	var path := DataRoot.root().path_join("data/combat/elements.json")
	if not FileAccess.file_exists(path): return
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not (parsed is Dictionary): return
	var declared = parsed.get("valid_damage_types", [])
	if declared is Array:
		for value in declared:
			var text := str(value).strip_edges()
			if text != "" and not damage_types.has(text): damage_types.append(text)
	damage_types.sort()
	var declared_hazards = parsed.get("hazards", {})
	if declared_hazards is Dictionary: hazards = declared_hazards.duplicate(true)

func hazard_ids() -> Array:
	var ids: Array = hazards.keys(); ids.sort(); return ids
