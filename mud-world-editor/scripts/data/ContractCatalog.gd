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
# `work`: what a set lets an author declare as taking time. Indexed like the
# other list sections, and listed in the browser because a declaration an author
# cannot see is one they will not know they can make.
var work: Dictionary = {}
# The `stats` section: one mapping rather than a list of entries, and the
# vocabulary every attribute form in the editor is built from.
var stats: Dictionary = {}
# `ruleset.status.stats`, the older spelling of the same list. Read because the
# engine still reads it (`World.declared_status_stats`) and because a set may
# declare it without declaring contracts at all.
var ruleset_stats: Array = []


func load_contracts() -> bool:
	# Refresh must also remove deleted declarations and old validation findings.
	issues.clear()
	families.clear(); generation_profiles.clear(); resources.clear()
	attack_profiles.clear(); defense_profiles.clear(); abilities.clear()
	effect_packets.clear(); work.clear(); stats.clear()
	schema_version = 0
	source_path = DataRoot.root().path_join(RELATIVE_PATH)
	# The ruleset is read even when the contracts file is missing: a set may name
	# its stats in the older place and declare no contracts at all.
	_load_ruleset_stats()
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
	work = _index(payload.get("work", []))
	var declared_stats = payload.get("stats", {})
	stats = declared_stats if typeof(declared_stats) == TYPE_DICTIONARY else {}

	_check_references(payload)
	return issues.is_empty()


func _load_ruleset_stats() -> void:
	ruleset_stats = []
	var path := DataRoot.ruleset_path()
	if not FileAccess.file_exists(path):
		return
	var parsed := JSON.new()
	if parsed.parse(FileAccess.get_file_as_string(path)) != OK:
		return
	var payload = parsed.get_data()
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var status = payload.get("status", {})
	if typeof(status) != TYPE_DICTIONARY:
		return
	var declared = status.get("stats", [])
	if typeof(declared) != TYPE_ARRAY:
		return
	for stat in declared:
		var text := str(stat).strip_edges()
		if text != "":
			ruleset_stats.append(text)


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


# --- the stat vocabulary ------------------------------------------------------
# Which attribute rows a form offers. The precedence mirrors the engine's, because
# an editor whose vocabulary is not the engine's is how eight fantasy stats end up
# on a set that has six:
#
#   1. `stats.order` -- the general declaration, read by
#      `engine/contracts/stats.py` for the status line
#   2. `ruleset.status.stats` -- the older spelling, still read, and a set may
#      declare it with no contracts file at all (`World.declared_status_stats`
#      reads both, in exactly this order)
#   3. the stats `stats.roles` names -- a set that says which stat fills which
#      role has named its vocabulary even without a display list
#   4. the stats the set's own NPCs carry -- data rather than a declaration
#
# Nothing falls back to the engine's *default* stat names. For a set that has
# declared nothing and authored nothing the honest answer is no rows and a
# sentence saying so; inventing the defaults would put rows in front of an author
# whose set does not have those stats, which is the defect this replaced.

func contract_stat_order() -> Array:
	var order = stats.get("order", [])
	if typeof(order) != TYPE_ARRAY:
		return []
	return _clean_string_list(order)


func declared_stat_order() -> Array:
	var from_contract := contract_stat_order()
	if not from_contract.is_empty():
		return from_contract
	return ruleset_stats.duplicate()


func declared_stat_roles() -> Dictionary:
	var roles = stats.get("roles", {})
	var out := {}
	if typeof(roles) != TYPE_DICTIONARY:
		return out
	for role in roles:
		var stat := str(roles[role]).strip_edges()
		if stat != "":
			out[str(role)] = stat
	return out


## The distinct stats the declared roles name, in the order they are declared.
func role_stat_names() -> Array:
	var out: Array = []
	for stat in declared_stat_roles().values():
		var text := str(stat).strip_edges()
		if text != "" and not out.has(text):
			out.append(text)
	return out


func has_stats_declaration() -> bool:
	return not declared_stat_order().is_empty() or not declared_stat_roles().is_empty()


## The stats a form should offer, and where they came from. `observed` is what the
## set's own data carries, used only when nothing is declared.
func stat_vocabulary(observed: Array = []) -> Array:
	var declared := declared_stat_order()
	if not declared.is_empty():
		return declared
	var by_role := role_stat_names()
	if not by_role.is_empty():
		return by_role
	var carried := _clean_string_list(observed)
	carried.sort()
	return carried


## Where a form's attribute rows come from, as a phrase that reads after "comes
## from". Named so an author can tell a declaration from a fallback.
func stat_vocabulary_source(observed: Array = []) -> String:
	if not contract_stat_order().is_empty():
		return "the contracts' `stats.order`"
	if not ruleset_stats.is_empty():
		return "the ruleset's `status.stats`"
	if not role_stat_names().is_empty():
		return "the stats `stats.roles` names"
	if not _clean_string_list(observed).is_empty():
		return "the stats this set's NPCs carry"
	return "nothing: this set declares no stats"


## The label a content set gives one of its resources, by `kind`. The engine
## resolves the ability pool the same way -- first by id among the matching kind
## (`contracts/resources.py::ability_resource`) -- so a set that calls its pool
## Charge reads Charge here too.
func resource_label(kind: String, fallback: String) -> String:
	var matches: Array = []
	for resource_id in resources:
		if str(resources[resource_id].get("kind", "")) == kind:
			matches.append(resource_id)
	matches.sort()
	if matches.is_empty():
		return fallback
	var label := str(resources[matches[0]].get("label", "")).strip_edges()
	return label if label != "" else fallback


func _clean_string_list(values: Array) -> Array:
	var out: Array = []
	for value in values:
		var text := str(value).strip_edges()
		if text != "" and not out.has(text):
			out.append(text)
	return out


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
	out.append({"title": "Work that takes time (%d)" % work.size(), "entries": _simple_entries(
		work, ["duration_days", "station", "inputs", "outputs", "skill", "difficulty"])})
	# Last, and not a list of entries with ids: the stat vocabulary is what the
	# *other* sections' numbers are read against, and what every attribute form in
	# the editor is built from. Showing it is how an author sees where those rows
	# come from.
	out.append({"title": "Stats (%d)" % stat_vocabulary().size(), "entries": _stat_entries()})
	return out


func _stat_entries() -> Array:
	var roles := declared_stat_roles()
	var entries: Array = []
	for stat in stat_vocabulary():
		var fills: Array = []
		for role in roles:
			if str(roles[role]) == str(stat):
				fills.append(str(role))
		var detail := "no role: a flavour stat, or one a skill or resource names"
		if not fills.is_empty():
			detail = "fills: %s" % ", ".join(fills)
		entries.append({"id": str(stat), "detail": detail})
	return entries


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
