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
var attack_profiles: Dictionary = {}
var defense_profiles: Dictionary = {}
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
	attack_profiles = _index(payload.get("attack_profiles", []))
	defense_profiles = _index(payload.get("defense_profiles", []))
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


# --- what an item inspector needs ---------------------------------------------
# These are read-only questions the editor asks while authoring an item: which
# family is this, what does that family make the engine build, and which roll
# tables does it ride.

func has_family(family_id: String) -> bool:
	return families.has(family_id)


func family_capabilities(family_id: String) -> Array:
	if not families.has(family_id):
		return []
	var capabilities = families[family_id].get("capabilities", [])
	return capabilities if capabilities is Array else []


func family_icon_style(family_id: String) -> String:
	if not families.has(family_id):
		return ""
	return str(families[family_id].get("icon_style", ""))


# Profiles that belong to this family. A template may name any of them; the
# family's own `generation_profile` is the default.
func profiles_for_family(family_id: String) -> Array:
	var ids: Array = []
	for profile_id in generation_profiles:
		if str(generation_profiles[profile_id].get("item_family", "")) == family_id:
			ids.append(profile_id)
	ids.sort()
	return ids


func profile(profile_id: String) -> Dictionary:
	return generation_profiles.get(profile_id, {})


# The roll bands a profile declares, for a picker that offers what this content
# set actually rolls rather than the fantasy set's four names.
func tier_ids(profile_id: String, tier_kind: String) -> Array:
	var tiers = profile(profile_id).get(tier_kind, [])
	var ids: Array = []
	if tiers is Array:
		for tier in tiers:
			if tier is Dictionary and str(tier.get("id", "")) != "":
				ids.append(str(tier["id"]))
	return ids


# Families whose engine class is `item_class` -- used to warn an author off a
# family that would change what their template builds.
func families_for_class(item_class: String) -> Array:
	var ids: Array = []
	for family_id in families:
		if str(families[family_id].get("item_class", "")) == item_class:
			ids.append(family_id)
	ids.sort()
	return ids


func family_ids_for_capability(capability: String) -> Array:
	var ids: Array = []
	for family_id in families:
		if family_capabilities(family_id).has(capability):
			ids.append(family_id)
	ids.sort()
	return ids


func ability_ids() -> Array:
	var ids := abilities.keys()
	ids.sort()
	return ids


# Every capability any family declares. A recipe may ask for "any item good
# enough to craft with" rather than naming templates, so the editor offers the
# capabilities this content set actually uses instead of a hard-coded list.
func capability_ids() -> Array:
	var seen := {}
	for family_id in families:
		for capability in family_capabilities(family_id):
			var text := str(capability).strip_edges()
			if text != "":
				seen[text] = true
	var ids := seen.keys()
	ids.sort()
	return ids


# --- reporting ----------------------------------------------------------------

# Everything this content set declares, grouped for a read-only browser. Each
# entry is {id, detail}: enough for an author to see the vocabulary their
# templates can name without opening the JSON.
func sections() -> Array:
	var out: Array = []
	out.append({"title": "Item families (%d)" % families.size(), "entries": _family_entries()})
	out.append({"title": "Generation profiles (%d)" % generation_profiles.size(), "entries": _simple_entries(
		generation_profiles, ["item_family", "size_bias", "quality_bias", "property_prefix", "name_template"])})
	out.append({"title": "Resources (%d)" % resources.size(), "entries": _simple_entries(
		resources, ["kind", "label", "short", "max_stat", "regeneration_stat", "regenerates"])})
	out.append({"title": "Attack profiles (%d)" % attack_profiles.size(), "entries": _simple_entries(
		attack_profiles, ["damage_type", "weapon_damage_type", "damage", "cooldown"])})
	out.append({"title": "Defense profiles (%d)" % defense_profiles.size(), "entries": _simple_entries(
		defense_profiles, ["defense", "material", "resistances"])})
	out.append({"title": "Abilities (%d)" % abilities.size(), "entries": _simple_entries(
		abilities, ["effect_packet", "cost", "cooldown", "target_type", "level_required"])})
	out.append({"title": "Effect packets (%d)" % effect_packets.size(), "entries": _simple_entries(
		effect_packets, ["kind", "resource", "value", "duration", "tags"])})
	return out


func _family_entries() -> Array:
	var entries: Array = []
	for family_id in families:
		var family: Dictionary = families[family_id]
		var parts: Array = ["class: %s" % str(family.get("item_class", "?"))]
		var capabilities := family_capabilities(family_id)
		if not capabilities.is_empty():
			parts.append("capabilities: %s" % ", ".join(capabilities))
		var profile := str(family.get("generation_profile", ""))
		if profile != "":
			parts.append("profile: %s" % profile)
		var icon := str(family.get("icon_style", ""))
		if icon != "":
			parts.append("icon: %s" % icon)
		var resource := str(family.get("resource", ""))
		if resource != "":
			parts.append("resource: %s" % resource)
		var attack := str(family.get("attack_profile", ""))
		if attack != "":
			parts.append("attack: %s" % attack)
		var defense := str(family.get("defense_profile", ""))
		if defense != "":
			parts.append("defense: %s" % defense)
		entries.append({"id": family_id, "detail": "  |  ".join(parts)})
	entries.sort_custom(func(a, b): return str(a["id"]) < str(b["id"]))
	return entries


func _simple_entries(index: Dictionary, keys: Array) -> Array:
	var entries: Array = []
	for entry_id in index:
		var entry: Dictionary = index[entry_id]
		var parts: Array = []
		for key in keys:
			if entry.has(key):
				parts.append("%s: %s" % [key, _render_value(entry[key])])
		entries.append({"id": entry_id, "detail": "  |  ".join(parts)})
	entries.sort_custom(func(a, b): return str(a["id"]) < str(b["id"]))
	return entries


func _render_value(value) -> String:
	if value is Dictionary:
		var parts: Array = []
		for key in value:
			parts.append("%s=%s" % [key, _render_value(value[key])])
		return "{" + ", ".join(parts) + "}"
	if value is Array:
		var items: Array = []
		for item in value:
			items.append(_render_value(item))
		return "[%s]" % ", ".join(items)
	return str(value)


func describe() -> String:
	if schema_version == 0:
		return "contracts: none declared"
	var summary := "contracts: schema %d, %d families, %d profiles, %d resources, %d abilities" % [
		schema_version, families.size(), generation_profiles.size(),
		resources.size(), abilities.size(),
	]
	if not attack_profiles.is_empty() or not defense_profiles.is_empty():
		summary += ", %d attack / %d defense profiles" % [attack_profiles.size(), defense_profiles.size()]
	if not issues.is_empty():
		summary += " (%d issue(s))" % issues.size()
	return summary