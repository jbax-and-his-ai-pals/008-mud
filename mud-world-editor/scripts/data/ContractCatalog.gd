# scripts/data/ContractCatalog.gd
#
# The editor's view of the content contracts.
#
# The registry (`server/engine/contracts/`) decides what a content set may
# declare; this reads the same file so the editor's controls come from the same
# declarations rather than from a hand-written list that drifts. When the editor
# offers a family or a generation profile in an inspector, the options are the
# ones this file contains.
#
# The editor does not get to invent fields. Anything it writes is validated by
# the engine's schema on the next content check, so a control that offered an
# unknown field would produce content that fails the build — which is why the
# catalog is read-only about schema and only enumerates what content declares.

class_name ContractCatalog
extends RefCounted

# Must match `engine.contracts.registry.SCHEMA_VERSION`. A mismatch is reported
# rather than papered over: the editor would otherwise happily edit fields the
# running engine does not read.
const KNOWN_SCHEMA_VERSION := 1

const RELATIVE_PATH := "data/contracts/world_contracts.json"

var schema_version: int = 0
var source_path: String = ""
var issues: PackedStringArray = PackedStringArray()
var families: Dictionary = {}
var generation_profiles: Dictionary = {}
var resources: Dictionary = {}
var abilities: Dictionary = {}
var effect_packets: Dictionary = {}


func load_contracts() -> bool:
	source_path = DataRoot.root().path_join(RELATIVE_PATH)
	if not FileAccess.file_exists(source_path):
		# A content set without contracts is legal; the engine falls back to its
		# neutral defaults.
		return false

	var parsed := JSON.new()
	if parsed.parse(FileAccess.get_file_as_string(source_path)) != OK:
		issues.append("could not parse %s" % source_path)
		return false
	var payload = parsed.get_data()
	if typeof(payload) != TYPE_DICTIONARY:
		issues.append("%s must contain an object" % source_path)
		return false

	# Godot's JSON parser returns numbers as floats, so an integer-looking field
	# arrives as 1.0. Accept it when it *is* whole, and say so when it is not --
	# the schema calls this an int, and a fractional version would be a typo.
	var declared = payload.get("schema_version", null)
	if not (typeof(declared) == TYPE_INT or typeof(declared) == TYPE_FLOAT):
		issues.append("schema_version must be an integer")
		return false
	if typeof(declared) == TYPE_FLOAT and declared != floor(declared):
		issues.append("schema_version must be a whole number (got %s)" % str(declared))
		return false
	schema_version = int(declared)
	if schema_version != KNOWN_SCHEMA_VERSION:
		issues.append("content declares schema_version %d; this editor understands %d"
			% [schema_version, KNOWN_SCHEMA_VERSION])
		return false

	families = _index(payload.get("item_families", []))
	generation_profiles = _index(payload.get("generation_profiles", []))
	resources = _index(payload.get("resources", []))
	abilities = _index(payload.get("abilities", []))
	effect_packets = _index(payload.get("effect_packets", []))

	_check_references(payload)
	return issues.is_empty()


func _index(entries) -> Dictionary:
	var out := {}
	if typeof(entries) != TYPE_ARRAY:
		return out
	for entry in entries:
		if typeof(entry) != TYPE_DICTIONARY:
			continue
		var identifier := str(entry.get("id", "")).strip_edges()
		if identifier != "":
			out[identifier] = entry
	return out


# Mirrors the registry's reference pass, so the editor reports the same problems
# the validator will: a profile must belong to a family that exists.
func _check_references(payload: Dictionary) -> void:
	for profile_id in generation_profiles:
		var family := str(generation_profiles[profile_id].get("item_family", ""))
		if family != "" and not families.has(family):
			issues.append("generation_profiles.%s references missing item family '%s'"
				% [profile_id, family])
	for family_id in families:
		var profile := str(families[family_id].get("generation_profile", ""))
		if profile != "" and not generation_profiles.has(profile):
			issues.append("item_families.%s references missing generation profile '%s'"
				% [family_id, profile])


func family_ids() -> Array:
	var ids := families.keys()
	ids.sort()
	return ids


func profile_ids() -> Array:
	var ids := generation_profiles.keys()
	ids.sort()
	return ids


# What an item inspector should offer for a template that declares a family.
func item_class_for_family(family_id: String) -> String:
	if not families.has(family_id):
		return ""
	return str(families[family_id].get("item_class", ""))


func generation_profile_for_family(family_id: String) -> String:
	if not families.has(family_id):
		return ""
	return str(families[family_id].get("generation_profile", ""))


func describe() -> String:
	if schema_version == 0:
		return "contracts: none declared"
	var summary := "contracts: schema %d, %d families, %d profiles, %d resources, %d abilities" % [
		schema_version, families.size(), generation_profiles.size(),
		resources.size(), abilities.size(),
	]
	if not issues.is_empty():
		summary += " (%d issue(s))" % issues.size()
	return summary
