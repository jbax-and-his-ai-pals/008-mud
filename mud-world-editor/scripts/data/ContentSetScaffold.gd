# scripts/data/ContentSetScaffold.gd
#
# Create a content set: the engine's manifest, a starter world, and the folders
# the engine requires.
#
# Why this exists
# ---------------
# `DataRoot.available_content_sets()` finds a set by testing for
# `content_set.manifest.json`, and nothing in the editor had ever written one. The
# documented way to get a new set was to hand-write the manifest and guess at the
# rest, so the editor's own tests did exactly that
# (`tests/contract_authoring_smoke.gd:212`).
#
# What it does, and what it refuses to do
# --------------------------------------
# * **Copies** `presentation/` and `opening/` from a set the author names, and its
#   `rules/` only if asked. Copied, never generated: a generated ruleset would be a
#   second opinion about game rules, and a set built on a guessed one is worse than
#   no set.
# * **Writes** the manifest from the engine's own field list, mirrored here as
#   constants that `tests/schema_parity_smoke.gd` holds equal to
#   `engine/server/content_set.py` through `toolkit/engine_vocabulary_dump.py`.
# * **Writes a starter region** with one room, classified the way the copied
#   ruleset's own policy requires (`world.regions.require_classification`,
#   `require_level_bands`). Nothing else: the first room is the author's, and a
#   scaffold that invented a village would be content, not a starting point.
# * **Reports what it could not satisfy.** A copied ruleset that requires hazard
#   coverage (`fantasy_frontier` does) demands every mapped hazard appear in some
#   room. Placing six hazards is world design, so the scaffold says so instead of
#   fabricating rooms to make a check go green.
#
# The capabilities in the new manifest are the *source set's*, validated against
# the engine's list. Copying them is the point of choosing a source: a new set
# starts from a shape someone checked.
#
# **Why rules are not copied by default.** A ruleset is a manifest of references
# into the world it came from: item templates, quests, NPCs, loot pools, salvage
# outputs. Measured across the shipped sets, `modern_capsule`'s names none and
# `fantasy_frontier`'s names ninety, so a set that copies rules without the world
# they describe opens and fails validation on every one of them. That is a
# legitimate way to start a clone, and it is a bad default for a new world, so
# `copy_rules` is a choice the dialog states the consequence of.

class_name ContentSetScaffold
extends RefCounted

const SaveIO = preload("res://scripts/data/SaveIO.gd")

# --- the engine's manifest shape ----------------------------------------------
# Every one of these is mirrored from `engine/server/content_set.py`, which is what
# refuses a set. `schema_parity_smoke.gd` compares them in both directions through
# `toolkit/engine_vocabulary_dump.py`, so a change on the engine side fails the
# gate rather than producing manifests the engine rejects.

const MANIFEST_FILENAME := "content_set.manifest.json"
const MANIFEST_SCHEMA_VERSION := "1"
const ENGINE_API_VERSION := "1.0"
const ID_PATTERN := "[a-z][a-z0-9_]*"
const REQUIRED_STRINGS := [
	"id", "title", "version", "manifest_schema_version", "engine_api_min", "engine_api_max",
]
const REQUIRED_PATHS := ["content_root", "ruleset", "presentation"]
const OPTIONAL_PATHS := ["feature_profile", "opening"]
const REQUIRED_START_FIELDS := ["scenario_id", "region_id", "room_id"]
const REQUIRED_DATA_DIRECTORIES := ["regions", "items", "npcs"]
# Two more the engine asks for when the `quests` capability is declared
# (`content_set.py`: campaigns are a quest-progression implementation). Not in the
# dump because it is a conditional rather than a list the manifest names, so this
# mirror is held honest by the smoke check validating a set copied from
# fantasy_frontier -- miss one and that set stops loading.
const QUEST_CAPABILITY_DIRECTORIES := ["quests", "campaigns"]
const CAPABILITIES := [
	"inventory", "dialogue", "combat", "abilities", "magic", "crafting",
	"gathering", "quests", "collections", "discoveries", "social",
]

# The folders copied from the source set. `rules/` and `presentation/` must exist
# -- the manifest has to point at a ruleset and a presentation -- while `opening/`
# is optional in the engine and optional here.
const COPIED_FOLDERS := ["rules", "presentation", "opening"]
const REQUIRED_SOURCE_FOLDERS := ["rules", "presentation"]

# What "version" means in a new manifest. The engine only requires a non-empty
# string; starting at 0.1.0 says nothing has been released from it yet.
const NEW_SET_VERSION := "0.1.0"


## Why an id cannot be used, or "" when it can. The pattern is the engine's: an id
## it refuses is a set the editor would have created and then failed to open.
static func id_problem(content_set_id: String, sets_root: String = "") -> String:
	var text := content_set_id.strip_edges()
	if text == "":
		return "An id is required."
	if text.length() > 64:
		return "Keep the id under 64 characters."
	if not matches_id_pattern(text):
		return "Ids are lower-case letters, digits and underscores, starting with a letter (like `new_frontier`)."
	if sets_root != "" and DirAccess.dir_exists_absolute(sets_root.path_join(text)):
		return "A content set called `%s` is already there." % text
	return ""


## The engine's pattern, applied the way the engine applies it: a full match, not
## a substring. `RegEx` rather than a hand-rolled loop so the two agree by
## construction, since `ID_PATTERN` is the engine's own string.
static func matches_id_pattern(text: String) -> bool:
	var regex := RegEx.new()
	if regex.compile("^" + ID_PATTERN + "$") != OK:
		return false
	return regex.search(text) != null


## The directory new sets are created in: `content_sets/` beside this checkout, so
## the engine, the gates and `available_content_sets()` all find them.
static func sets_root() -> String:
	return ProjectSettings.globalize_path("res://").path_join("../content_sets").simplify_path()


## Create `id` by copying `source_set`'s shape. Returns
## `{ok, path, wrote: [], copied: [], errors: [], notes: []}`, where `wrote` and
## `copied` are absolute paths.
##
## `copy_rules` decides what the new set's `rules/ruleset.json` is:
##
## * **false** (the default) writes a placeholder ruleset that declares nothing, so
##   the engine's own defaults apply and the set validates immediately.
## * **true** copies the source's rules verbatim -- and a ruleset is a manifest of
##   references into the world it came from. It names that world's item templates,
##   quests, NPCs, loot pools and salvage outputs, and this set has none of them, so
##   Validate will report every one of them until they are authored. Measured on the
##   shipped sets: `modern_capsule`'s ruleset names nothing, `night_shift`'s names
##   three items, `orbital_salvage`'s five, and `fantasy_frontier`'s ninety. That is
##   a real choice an author may want; it is not a working set, and the dialog says
##   so before the button is pressed.
static func create(
	content_set_id: String,
	title: String,
	source_set: String,
	target_root: String = "",
	copy_rules: bool = false,
) -> Dictionary:
	var result := {"ok": false, "path": "", "wrote": [], "copied": [], "errors": [], "notes": []}
	var identity := content_set_id.strip_edges()
	var root := target_root if target_root != "" else sets_root()
	source_set = source_set.simplify_path()

	var problem := id_problem(identity, root)
	if problem != "":
		result["errors"].append(problem)
		return result
	if not DirAccess.dir_exists_absolute(source_set):
		result["errors"].append("The set to copy (%s) is not there." % source_set)
		return result

	var source_manifest := _read_json(source_set.path_join(MANIFEST_FILENAME))
	if source_manifest.is_empty():
		result["errors"].append("%s is not a content set: no readable %s." % [source_set, MANIFEST_FILENAME])
		return result

	var missing := _missing_copied_folders(source_set)
	if not missing.is_empty():
		result["errors"].append("%s has no %s to copy." % [source_set, ", ".join(missing)])
		return result

	var target := root.path_join(identity)
	if DirAccess.dir_exists_absolute(target):
		result["errors"].append("A directory already exists at %s." % target)
		return result

	DirAccess.make_dir_recursive_absolute(target)
	result["path"] = target

	# The three directories the engine requires must exist before anything is
	# written into them: `SaveIO` reports a failed write rather than creating a
	# directory, which is the point of it.
	for directory in REQUIRED_DATA_DIRECTORIES:
		DirAccess.make_dir_recursive_absolute(target.path_join("data").path_join(directory))

	# Mirroring `content_set.py`'s own rule: a set that declares the `quests`
	# capability must also carry the quest and campaign directories. Copying the
	# capability without the directories it implies is how a scaffold produces a set
	# the engine refuses for a reason the author cannot act on.
	var capabilities := _copied_capabilities(source_manifest)
	# A fresh scaffold intentionally does not copy a source world's content. A
	# capability whose sole useful definition is an authored ability would then
	# advertise a system that loads nothing -- a world that passes file validation
	# but fails the first runtime play check. Preserve those capabilities only for
	# the explicit clone path, where copying rules is the author's signal that the
	# source's content shape is wanted too.
	if not copy_rules:
		for content_backed in ["abilities", "magic"]:
			capabilities.erase(content_backed)
	if capabilities.has("quests"):
		for directory in QUEST_CAPABILITY_DIRECTORIES:
			DirAccess.make_dir_recursive_absolute(target.path_join("data").path_join(directory))

	_copy_folders(source_set, target, result, copy_rules)
	if not copy_rules:
		# The placeholder goes where the manifest will point, which is the source's
		# own answer rather than an assumed `rules/ruleset.json`. Nothing was copied
		# into that directory, so it is the scaffold's to make: `SaveIO` refuses to
		# invent a parent directory, on purpose.
		var ruleset_path := target.path_join(_ruleset_relative(source_manifest))
		DirAccess.make_dir_recursive_absolute(ruleset_path.get_base_dir())
		var placeholder := SaveIO.write_json(ruleset_path, {
			"label": "%s rules" % (title.strip_edges() if title.strip_edges() != "" else identity.capitalize()),
		})
		if not placeholder.get("ok", false):
			result["errors"].append("Could not write the placeholder ruleset: %s" % str(placeholder.get("error", "")))
			return result
		result["wrote"].append(ruleset_path)

	# The starter region replaces the source's start: a copied world's starting
	# room belongs to the world it was copied from. It is classified from *this*
	# set's ruleset -- the copied one, or the placeholder -- because that is what
	# will validate it. Reading the source's instead would copy a vocabulary this
	# set's own ruleset never asked for.
	var start_region := identity
	var start_room := "start"
	result["wrote"].append_array(_write_starter_region(target, start_region, start_room, result))

	var opening := _copied_opening(target, source_manifest)
	# With no opening, the scenario id is the new set's own id rather than the
	# source's: pointing at a scenario this set does not contain is a dangling
	# reference, and an author who writes `opening/<id>.json` later will match.
	var scenario_id := str(opening["scenario_id"]) if opening["path"] != "" else identity
	var payload := _manifest_payload(
		identity, title, source_manifest, start_region, start_room, str(opening["path"]), scenario_id, capabilities
	)
	var written := SaveIO.write_json(target.path_join(MANIFEST_FILENAME), payload)
	if not written.get("ok", false):
		result["errors"].append("Could not write the manifest: %s" % str(written.get("error", "")))
		return result
	result["wrote"].append(target.path_join(MANIFEST_FILENAME))

	_append_policy_notes(target, source_set, result)
	result["ok"] = result["errors"].is_empty()
	return result


## Where a set's ruleset lives, relative to its root: the source manifest's own
## answer, so a set that keeps its rules somewhere else gets a placeholder there
## rather than one the manifest does not point at.
static func _ruleset_relative(source_manifest: Dictionary) -> String:
	var source_paths: Dictionary = source_manifest.get("paths", {}) if typeof(source_manifest.get("paths")) == TYPE_DICTIONARY else {}
	var declared := str(source_paths.get("ruleset", "")).strip_edges()
	return declared if declared != "" else "rules/ruleset.json"


## The manifest, built from the engine's field names rather than from a template
## string. A template would be a second place the shape is written down.
static func _manifest_payload(
	content_set_id: String,
	title: String,
	source_manifest: Dictionary,
	start_region: String,
	start_room: String,
	opening: String,
	scenario_id: String,
	capabilities: Array,
) -> Dictionary:
	var source_paths: Dictionary = source_manifest.get("paths", {}) if typeof(source_manifest.get("paths")) == TYPE_DICTIONARY else {}
	var paths := {
		"content_root": "data",
		"ruleset": str(source_paths.get("ruleset", "rules/ruleset.json")),
		"presentation": str(source_paths.get("presentation", "presentation/default.json")),
	}
	if opening != "":
		paths["opening"] = opening

	var clean_title := title.strip_edges()
	return {
		"id": content_set_id,
		"title": clean_title if clean_title != "" else content_set_id.capitalize(),
		"version": NEW_SET_VERSION,
		"manifest_schema_version": MANIFEST_SCHEMA_VERSION,
		"engine_api_min": ENGINE_API_VERSION,
		"engine_api_max": ENGINE_API_VERSION,
		"paths": paths,
		"start": {
			"scenario_id": scenario_id,
			"region_id": start_region,
			"room_id": start_room,
		},
		"capabilities": capabilities,
	}


## The source's own capabilities, kept in the engine's order. A capability the
## engine does not know is dropped rather than copied: the manifest would be
## refused, and the copy is where an unknown name would come from.
static func _copied_capabilities(source_manifest: Dictionary) -> Array:
	var declared = source_manifest.get("capabilities", [])
	var out: Array = []
	if typeof(declared) != TYPE_ARRAY:
		return out
	for capability in declared:
		var text := str(capability).strip_edges()
		if CAPABILITIES.has(text) and not out.has(text):
			out.append(text)
	return out


## The source's opening scenario, kept only when the copied file is there *and*
## usable. `paths.opening` is optional, and the engine refuses both a pointer to
## nothing and an opening whose `scenario_id` cannot match `start`. Returns
## `{path, scenario_id}`, both empty when there is no usable opening.
static func _copied_opening(target: String, source_manifest: Dictionary) -> Dictionary:
	var source_paths: Dictionary = source_manifest.get("paths", {}) if typeof(source_manifest.get("paths")) == TYPE_DICTIONARY else {}
	var declared := str(source_paths.get("opening", "")).strip_edges()
	if declared == "" or not FileAccess.file_exists(target.path_join(declared)):
		return {"path": "", "scenario_id": ""}
	var scenario_id := str(_read_json(target.path_join(declared)).get("scenario_id", "")).strip_edges()
	if scenario_id == "":
		return {"path": "", "scenario_id": ""}
	return {"path": declared, "scenario_id": scenario_id}


static func _missing_copied_folders(source_set: String) -> Array:
	var missing: Array = []
	for folder in REQUIRED_SOURCE_FOLDERS:
		if not DirAccess.dir_exists_absolute(source_set.path_join(folder)):
			missing.append(folder + "/")
	return missing


static func _copy_folders(source_set: String, target: String, result: Dictionary, copy_rules: bool) -> void:
	for folder in COPIED_FOLDERS:
		if folder == "rules" and not copy_rules:
			continue
		var written: Array = []
		_copy_tree(source_set.path_join(folder), target.path_join(folder), written)
		result["copied"].append_array(written)


static func _copy_tree(source: String, target: String, written: Array) -> void:
	var directory := DirAccess.open(source)
	if directory == null:
		return
	if not DirAccess.dir_exists_absolute(target):
		DirAccess.make_dir_recursive_absolute(target)
	directory.list_dir_begin()
	var name := directory.get_next()
	while name != "":
		if name.begins_with("."):
			name = directory.get_next()
			continue
		var from := source.path_join(name)
		var to := target.path_join(name)
		if directory.current_is_dir():
			_copy_tree(from, to, written)
		else:
			var bytes := FileAccess.get_file_as_bytes(from)
			var file := FileAccess.open(to, FileAccess.WRITE)
			if file != null:
				file.store_buffer(bytes)
				file.close()
				written.append(to)
		name = directory.get_next()
	directory.list_dir_end()


## A one-room region that satisfies *this* set's region policy -- the ruleset the
## manifest points at, whether it was copied or is the placeholder.
static func _write_starter_region(
	target: String, region_id: String, room_id: String, result: Dictionary
) -> Array:
	var properties := {}
	var regions_config := _regions_config(_read_json(target.path_join("rules").path_join("ruleset.json")))
	if bool(regions_config.get("require_classification", false)):
		properties["biome"] = _first_vocabulary(regions_config, "biomes")
		properties["region_type"] = _first_vocabulary(regions_config, "region_types")
	if bool(regions_config.get("require_level_bands", false)):
		properties["level_band"] = {"min": 1, "max": 1}

	var region := {
		"region_id": region_id,
		"name": region_id.capitalize(),
		"description": "A new region. Its first room is empty on purpose: what this world is belongs to whoever builds it.",
		"properties": properties,
		"rooms": {
			room_id: {
				"name": "Start",
				"description": "The first room of %s. Nothing has happened here yet." % region_id,
				"exits": {},
			},
		},
	}
	var path := target.path_join("data").path_join("regions").path_join(region_id + ".json")
	var written := SaveIO.write_json(path, region)
	if not written.get("ok", false):
		result["errors"].append("Could not write the starter region: %s" % str(written.get("error", "")))
		return []
	return [path]


static func _regions_config(ruleset: Dictionary) -> Dictionary:
	var world_config = ruleset.get("world", {})
	if typeof(world_config) != TYPE_DICTIONARY:
		return {}
	var regions_config = world_config.get("regions", {})
	return regions_config if typeof(regions_config) == TYPE_DICTIONARY else {}


static func _first_vocabulary(regions_config: Dictionary, key: String) -> String:
	var declared = regions_config.get(key, [])
	if typeof(declared) == TYPE_ARRAY and not declared.is_empty():
		return str(declared[0])
	return ""


## What the copied ruleset still demands that a scaffold cannot invent. Returned as
## notes rather than errors: the set opens, and this is the author's to-do list.
##
## The source set is read as well as the new one, and only for *names*. A ruleset
## that requires hazard coverage wants one room per hazard, and the hazards are
## defined in `data/combat/elements.json`, which is not copied -- a world's damage
## types are its own. Naming the source's hazards turns "place every hazard" into a
## list an author can act on, without copying a single one of them.
static func _append_policy_notes(target: String, source_set: String, result: Dictionary) -> void:
	var regions_config := _regions_config(_read_json(target.path_join("rules").path_join("ruleset.json")))
	if not bool(regions_config.get("require_hazard_coverage", false)):
		return
	var requirement := "The copied ruleset requires every mapped hazard to appear in some room"
	var own := _mapped_hazards(target)
	if not own.is_empty():
		result["notes"].append(
			"%s. This world has %d to place (as a room's properties.hazard_type): %s."
			% [requirement, own.size(), ", ".join(own)]
		)
		return
	var inherited := _mapped_hazards(source_set)
	if not inherited.is_empty():
		result["notes"].append(
			"%s, and the combat data (`data/combat/elements.json`) was not copied -- a world's "
			% requirement
			+ "damage types are its own. The set this came from defines %d, as a starting point: %s."
			% [inherited.size(), ", ".join(inherited)]
		)
		return
	result["notes"].append(
		"%s, and this set has no data/combat/elements.json yet, so the engine will ask for one."
		% requirement
	)


static func _mapped_hazards(target: String) -> Array:
	"""The hazard ids a set declares, for the "you still have to place these" note.

	A hazard is one record keyed by the id a room names; `_`-prefixed keys are
	authoring comments and non-objects are not records, so neither is mistaken for
	a hazard. This read is the second consumer of that shape after the engine's own
	validator, and it is how the shape change was caught here.
	"""
	var elements := _read_json(target.path_join("data").path_join("combat").path_join("elements.json"))
	var hazards = elements.get("hazards", {})
	if typeof(hazards) != TYPE_DICTIONARY:
		return []
	var names: Array = []
	for name in hazards:
		var hazard_id := str(name)
		if hazard_id.begins_with("_"):
			continue
		if typeof(hazards[name]) == TYPE_DICTIONARY:
			names.append(hazard_id)
	names.sort()
	return names


static func _read_json(path: String) -> Dictionary:
	if path == "" or not FileAccess.file_exists(path):
		return {}
	var parsed := JSON.new()
	if parsed.parse(FileAccess.get_file_as_string(path)) != OK:
		return {}
	var payload = parsed.get_data()
	return payload if typeof(payload) == TYPE_DICTIONARY else {}
