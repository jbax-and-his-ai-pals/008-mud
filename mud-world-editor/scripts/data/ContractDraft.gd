# scripts/data/ContractDraft.gd
# Safe editing model for data/contracts/world_contracts.json. Forms own only the
# sections they render; the rest of the engine contract round-trips verbatim.
class_name ContractDraft
extends RefCounted

const ConfigurationSave = preload("res://scripts/data/ConfigurationSave.gd")

var path := ""
var disk_hash := ""
var original: Dictionary = {}
var data: Dictionary = {}

static func load(contract_path: String) -> Dictionary:
	if not FileAccess.file_exists(contract_path):
		return {"ok": false, "error": "No contract file exists at %s." % contract_path}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(contract_path))
	if not (parsed is Dictionary): return {"ok": false, "error": "Contract file must contain a JSON object."}
	var shape := ConfigurationSave.shape_error(parsed, ["resources", "item_families", "generation_profiles", "attack_profiles", "defense_profiles", "effect_packets", "abilities", "work"], ["stats", "stats.roles", "stats.short"])
	if shape != "": return {"ok": false, "error": shape}
	for profile in parsed.get("generation_profiles", []):
		shape = ConfigurationSave.shape_error(profile, ["rarity_tiers", "size_tiers", "quality_tiers"], [])
		if shape != "": return {"ok": false, "error": shape}
	var draft := ContractDraft.new()
	draft.disk_hash = FileAccess.get_sha256(contract_path)
	draft.path = contract_path; draft.original = parsed.duplicate(true); draft.data = parsed.duplicate(true)
	return {"ok": true, "draft": draft}

func is_dirty() -> bool: return JSON.stringify(data) != JSON.stringify(original)

func set_resources(resources: Array): data["resources"] = _clean_entries(resources, "id")
func set_item_families(families: Array): data["item_families"] = _clean_entries(families, "id")
func set_generation_profiles(profiles: Array): data["generation_profiles"] = _clean_entries(profiles, "id")
func set_attack_profiles(profiles: Array): data["attack_profiles"] = _clean_entries(profiles, "id")
func set_defense_profiles(profiles: Array): data["defense_profiles"] = _clean_entries(profiles, "id")
func set_abilities(entries: Array): data["abilities"] = _clean_entries(entries, "id")
func set_effect_packets(entries: Array): data["effect_packets"] = _clean_entries(entries, "id")
func set_work(entries: Array): data["work"] = _clean_entries(entries, "id")
func set_stats(stats: Dictionary): data["stats"] = stats.duplicate(true)

func validate() -> Array:
	var errors: Array = []
	if data.get("schema_version", 0) != ContractCatalog.KNOWN_SCHEMA_VERSION:
		errors.append("schema_version must be %d." % ContractCatalog.KNOWN_SCHEMA_VERSION)
	var families := _entries("item_families", errors)
	var resources := _entries("resources", errors)
	var profiles := _entries("generation_profiles", errors)
	var attack_profiles := _entries("attack_profiles", errors)
	var defense_profiles := _entries("defense_profiles", errors)
	var abilities := _entries("abilities", errors)
	var effects := _entries("effect_packets", errors)
	var work := _entries("work", errors)
	_validate_ids(families, "item_families", errors)
	_validate_ids(resources, "resources", errors)
	_validate_ids(profiles, "generation_profiles", errors)
	_validate_ids(attack_profiles, "attack_profiles", errors)
	_validate_ids(defense_profiles, "defense_profiles", errors)
	_validate_ids(abilities, "abilities", errors)
	_validate_ids(effects, "effect_packets", errors)
	_validate_ids(work, "work", errors)
	var stats = data.get("stats", {})
	if not (stats is Dictionary): errors.append("stats must be an object.")
	var family_ids := {}
	var resource_ids := {}
	var attack_ids := {}
	var defense_ids := {}
	var effect_ids := {}
	for family in families: family_ids[str(family.get("id", ""))] = true
	for resource in resources: resource_ids[str(resource.get("id", ""))] = true
	for profile in attack_profiles: attack_ids[str(profile.get("id", ""))] = true
	for profile in defense_profiles: defense_ids[str(profile.get("id", ""))] = true
	for effect in effects: effect_ids[str(effect.get("id", ""))] = true
	for family in families:
		var attack_id := str(family.get("attack_profile", "")).strip_edges()
		var defense_id := str(family.get("defense_profile", "")).strip_edges()
		var resource_id := str(family.get("resource", "")).strip_edges()
		if attack_id != "" and not attack_ids.has(attack_id): errors.append("item family '%s' references missing attack profile '%s'." % [family.get("id", ""), attack_id])
		if defense_id != "" and not defense_ids.has(defense_id): errors.append("item family '%s' references missing defense profile '%s'." % [family.get("id", ""), defense_id])
		if resource_id != "" and not resource_ids.has(resource_id): errors.append("item family '%s' references missing resource '%s'." % [family.get("id", ""), resource_id])
	for profile in profiles:
		var family_id := str(profile.get("item_family", "")).strip_edges()
		if family_id != "" and not family_ids.has(family_id): errors.append("generation profile '%s' references missing item family '%s'." % [profile.get("id", ""), family_id])
	for ability in abilities:
		var effect_id := str(ability.get("effect_packet", "")).strip_edges()
		if effect_id != "" and not effect_ids.has(effect_id): errors.append("ability '%s' references missing effect packet '%s'." % [ability.get("id", ""), effect_id])
		var cost: Dictionary = ability.get("cost", {}) if ability.get("cost", {}) is Dictionary else {}
		var cost_resource := str(cost.get("resource", "")).strip_edges()
		if cost_resource != "" and not resource_ids.has(cost_resource): errors.append("ability '%s' costs missing resource '%s'." % [ability.get("id", ""), cost_resource])
	for effect in effects:
		var effect_resource := str(effect.get("resource", "")).strip_edges()
		if effect_resource != "" and not resource_ids.has(effect_resource): errors.append("effect packet '%s' references missing resource '%s'." % [effect.get("id", ""), effect_resource])
	return errors

func save() -> Dictionary:
	var errors := validate()
	if not errors.is_empty(): return {"ok": false, "error": "\n".join(errors)}
	var result := ConfigurationSave.write(path, data, disk_hash)
	if result.get("ok", false):
		original = data.duplicate(true)
		disk_hash = FileAccess.get_sha256(path)
	return result

func _entries(key: String, errors: Array) -> Array:
	var value = data.get(key, [])
	if not (value is Array): errors.append("%s must be a list." % key); return []
	var out: Array = []
	for entry in value:
		if entry is Dictionary: out.append(entry)
		else: errors.append("%s entries must be objects." % key)
	return out

static func _clean_entries(entries: Array, _id_key: String) -> Array:
	# Invalid rows must reach validation instead of disappearing on save.
	return entries.duplicate(true)

static func _validate_ids(entries: Array, label: String, errors: Array):
	var seen := {}
	for entry in entries:
		var identifier := str(entry.get("id", "")).strip_edges()
		if identifier == "": errors.append("%s needs an id." % label)
		elif seen.has(identifier): errors.append("%s repeats '%s'." % [label, identifier])
		seen[identifier] = true
