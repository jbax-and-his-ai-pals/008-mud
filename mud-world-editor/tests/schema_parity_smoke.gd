# tests/schema_parity_smoke.gd
#
# The editor's vocabulary tables are copies of the engine's, and a copy drifts.
#
#   godot --headless --path mud-world-editor --script tests/schema_parity_smoke.gd
#
# `DialogueSchema` holds the condition kinds and effect keys; `QuestSchema` holds
# the objective types. They have to be copies -- the editor needs field *types* to
# choose widgets and cannot import Python -- but a kind the engine does not know is
# a gate that never fires, and the author's only clue is that nothing happened.
#
# So both directions are asserted against the engine's own sets, read through
# `toolkit/engine_vocabulary_dump.py` (which imports them, rather than listing them
# a third time). Both directions matter and for different reasons:
#
#   * in the editor, not in the engine -> the editor offers a kind that does nothing
#   * in the engine, not in the editor  -> authors hand-edit JSON to reach it
#
# The effect *shape hints* are checked too: a hint naming a field the engine does
# not read is worse than no hint, because the author trusts it. Two of them were
# wrong when this check was written (`adjust_relationship` said `{amount}` where the
# engine also needs `npc`; `move_npc` said `npc_id`/`region_id`/`room_id` where the
# engine reads `npc`/`region`/`room`).

extends SceneTree

var failure_count := 0
var repo_root: String = ""
var python_exe: String = ""


func _init() -> void:
	repo_root = ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	python_exe = _python_from_args()
	if python_exe == "":
		python_exe = _probe_python()

	if python_exe == "":
		# Not a failure: no interpreter means this check cannot run, and saying so
		# is better than passing quietly.
		print("SKIP: no Python interpreter, so the engine's vocabularies cannot be read.")
		print("      Pass one with: -- --python <path>")
		quit(0)
		return

	var vocabulary := _engine_vocabulary()
	if vocabulary.is_empty() or vocabulary.has("error"):
		printerr("  FAIL the engine vocabulary could not be read: %s" % str(vocabulary.get("error", "no output")))
		push_error("schema parity failed (1)")
		quit(1)
		return

	print("engine vocabularies: %d conditions, %d effects, %d objective types" % [
		Array(vocabulary.get("condition_kinds", [])).size(),
		Array(vocabulary.get("effect_keys", [])).size(),
		Array(vocabulary.get("objective_types", [])).size(),
	])
	print("manifest: %d capabilities, %d required strings" % [
		Array(vocabulary.get("manifest", {}).get("capabilities", [])).size(),
		Array(vocabulary.get("manifest", {}).get("required_strings", [])).size(),
	])

	_check_no_extra_condition_kinds(vocabulary)
	_check_no_missing_condition_kinds(vocabulary)
	_check_effect_keys(vocabulary)
	_check_objective_types(vocabulary)
	_check_effect_shape_hints(vocabulary)
	_check_direction_reciprocals(vocabulary)
	_check_manifest_shape(vocabulary)

	if failure_count > 0:
		push_error("schema parity failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- the vocabularies ---------------------------------------------------------

func _check_no_extra_condition_kinds(vocabulary: Dictionary) -> void:
	print("\n[condition kinds: editor vs engine]")
	var engine := _as_set(vocabulary.get("condition_kinds", []))
	var editor := _as_set(DialogueSchema.condition_kinds())
	var extra: Array = _only_in(editor, engine)
	_assert(extra.is_empty(),
		"every condition kind the editor offers exists in the engine (offers %s)" % str(extra))


func _check_no_missing_condition_kinds(vocabulary: Dictionary) -> void:
	var engine := _as_set(vocabulary.get("condition_kinds", []))
	var editor := _as_set(DialogueSchema.condition_kinds())
	var missing: Array = _only_in(engine, editor)
	_assert(missing.is_empty(),
		"every condition kind the engine knows is offered by the editor (missing %s)" % str(missing))


func _check_effect_keys(vocabulary: Dictionary) -> void:
	print("\n[effect keys: editor vs engine]")
	var engine := _as_set(vocabulary.get("effect_keys", []))
	var editor := _as_set(DialogueSchema.effect_keys())
	_assert(_only_in(editor, engine).is_empty(),
		"every effect the editor offers exists in the engine (offers %s)" % str(_only_in(editor, engine)))
	_assert(_only_in(engine, editor).is_empty(),
		"every effect the engine knows is offered by the editor (missing %s)" % str(_only_in(engine, editor)))


func _check_objective_types(vocabulary: Dictionary) -> void:
	print("\n[objective types: editor vs engine]")
	var engine := _as_set(vocabulary.get("objective_types", []))
	var editor := _as_set(QuestSchema.TYPES.keys())
	# A type the engine routes but the editor does not model forces an author into
	# hand-edited JSON for a quest the game fully supports.
	var missing: Array = _only_in(engine, editor)
	var extra: Array = _only_in(editor, engine)
	_assert(missing.is_empty(),
		"every objective type the engine routes is offered by the editor (missing %s)" % str(missing))
	_assert(extra.is_empty(),
		"and every type the editor offers is routed by the engine (offers %s)" % str(extra))


# --- the shape hints ----------------------------------------------------------

func _check_effect_shape_hints(vocabulary: Dictionary) -> void:
	print("\n[effect shape hints name real fields]")
	var fields: Dictionary = vocabulary.get("effect_fields", {})
	_assert(not fields.is_empty(), "the engine's effect readers were scanned")

	for effect in fields.keys():
		var reads := _as_set(fields[effect])
		var shape := DialogueSchema.effect_shape(str(effect))
		# Every field name the engine reads must appear in the hint, or an author
		# following the hint writes an object the engine half-understands. Two
		# exceptions, both recorded rather than quietly skipped:
		#
		#   `delta`                an accepted alias for `amount`, so naming either
		#                          is enough
		#   `generated_item_data`  a *pre-rolled* item instance, written by the
		#                          procedural-loot path rather than by an author --
		#                          hinting it would invite hand-written instance
		#                          dicts, which is the opposite of the point
		var aliases := {"delta": "amount"}
		var not_authored := {"generated_item_data": true}
		var unnamed: Array = []
		for field_name in _sorted(reads):
			if not_authored.has(field_name):
				continue
			if aliases.has(field_name) and shape.contains(str(aliases[field_name])):
				continue
			if not shape.contains(str(field_name)):
				unnamed.append(field_name)
		_assert(unnamed.is_empty(),
			"the `" + str(effect) + "` hint names the fields the engine reads (missing from hint: " + str(unnamed) + " in " + shape + ")")

	# And the reverse for the two that were wrong: a hint must not send an author
	# to a key no reader looks at.
	var move_hint := DialogueSchema.effect_shape("move_npc")
	_assert(not move_hint.contains("npc_id") and not move_hint.contains("region_id") and not move_hint.contains("room_id"),
		"the `move_npc` hint does not name the `_id`-suffixed keys the engine never reads (" + move_hint + ")")
	var trust_hint := DialogueSchema.effect_shape("adjust_relationship")
	_assert(trust_hint.contains("npc"),
		"the `adjust_relationship` hint names `npc`, which the engine requires (" + trust_hint + ")")


## The editor draws and offers exits, so a wrong reciprocal here is not cosmetic:
## it can create a two-way link that disagrees with engine navigation.  In
## particular, `climb` <-> `descend` and `surface` <-> `dive` are distinct pairs.
func _check_direction_reciprocals(vocabulary: Dictionary) -> void:
	print("\n[exit reciprocals: editor vs engine]")
	var engine: Dictionary = vocabulary.get("direction_opposites", {})
	_assert(not engine.is_empty(), "the engine's exit reciprocal vocabulary was read")
	_assert(Constants.INV_DIR_MAP == engine,
		"every editor reciprocal exactly matches the engine's (%s)" % str(Constants.INV_DIR_MAP))
	var offered := _as_set(Constants.AUTHORABLE_DIRECTIONS)
	var engine_directions := _as_set(engine.keys())
	_assert(_only_in(offered, engine_directions).is_empty(),
		"every exit the editor offers is recognized by the engine (extra %s)" % str(_only_in(offered, engine_directions)))
	_assert(_only_in(engine_directions, offered).is_empty(),
		"every engine exit is reachable from the editor (missing %s)" % str(_only_in(engine_directions, offered)))


# --- the manifest -------------------------------------------------------------

## `ContentSetScaffold` writes the manifest a new content set starts with, and the
## engine (`engine/server/content_set.py`) is what refuses one. Every name in the
## scaffold's table is therefore a copy, and this is what keeps it equal.
##
## The failure this prevents is specific: a manifest missing one required string,
## or naming a capability the engine does not have, is a set the editor creates and
## then cannot open -- and the author's only clue would be the editor failing to
## list it.
func _check_manifest_shape(vocabulary: Dictionary) -> void:
	print("\n[manifest shape: editor vs engine]")
	var engine: Dictionary = vocabulary.get("manifest", {})
	_assert(not engine.is_empty(), "the engine's manifest shape was read")
	if engine.is_empty():
		return

	_assert(ContentSetScaffold.MANIFEST_FILENAME == str(engine.get("filename", "")),
		"the manifest file name matches (%s)" % ContentSetScaffold.MANIFEST_FILENAME)
	_assert(ContentSetScaffold.MANIFEST_SCHEMA_VERSION == str(engine.get("schema_version", "")),
		"the manifest schema version matches (%s)" % ContentSetScaffold.MANIFEST_SCHEMA_VERSION)
	_assert(ContentSetScaffold.ENGINE_API_VERSION == str(engine.get("runtime_api_version", "")),
		"the engine API version matches (%s)" % ContentSetScaffold.ENGINE_API_VERSION)
	_assert(ContentSetScaffold.ID_PATTERN == str(engine.get("id_pattern", "")),
		"the id pattern is the engine's own (%s)" % ContentSetScaffold.ID_PATTERN)

	# Every list, both directions: a name the editor writes that the engine does not
	# know is a manifest it refuses, and a name it never writes is a feature an
	# author cannot reach.
	var lists := {
		"required_strings": ContentSetScaffold.REQUIRED_STRINGS,
		"required_paths": ContentSetScaffold.REQUIRED_PATHS,
		"optional_paths": ContentSetScaffold.OPTIONAL_PATHS,
		"required_start_fields": ContentSetScaffold.REQUIRED_START_FIELDS,
		"required_data_directories": ContentSetScaffold.REQUIRED_DATA_DIRECTORIES,
		"capabilities": ContentSetScaffold.CAPABILITIES,
	}
	for key in lists.keys():
		var from_engine := _as_set(engine.get(key, []))
		var from_editor := _as_set(lists[key])
		_assert(_only_in(from_editor, from_engine).is_empty(),
			"every %s the editor writes is one the engine knows (extra %s)"
				% [key, str(_only_in(from_editor, from_engine))])
		_assert(_only_in(from_engine, from_editor).is_empty(),
			"and every %s the engine knows is one the editor writes (missing %s)"
				% [key, str(_only_in(from_engine, from_editor))])

	# The pattern has to be applied the way the engine applies it: a full match.
	_assert(ContentSetScaffold.matches_id_pattern("new_frontier"), "an id like `new_frontier` is accepted")
	_assert(not ContentSetScaffold.matches_id_pattern("New_Frontier"), "a capital is not")
	_assert(not ContentSetScaffold.matches_id_pattern("1st_world"), "a leading digit is not")
	_assert(not ContentSetScaffold.matches_id_pattern("new-frontier"), "a hyphen is not")
	_assert(not ContentSetScaffold.matches_id_pattern("new_frontier "), "trailing space is not")
	_assert(not ContentSetScaffold.matches_id_pattern(""), "an empty id is not")


# --- helpers ------------------------------------------------------------------

func _python_from_args() -> String:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--python="):
			return argument.trim_prefix("--python=")
	var args := OS.get_cmdline_user_args()
	for index in range(args.size() - 1):
		if args[index] == "--python":
			return args[index + 1]
	return ""


## The interpreter `run_editor_checks.py` passes through, or a guess.
func _probe_python() -> String:
	for candidate in ["python3", "python", "py"]:
		var output: Array = []
		var code := OS.execute(candidate, ["--version"], output, true)
		if code == 0:
			return candidate
	return ""


func _engine_vocabulary() -> Dictionary:
	var script := repo_root.path_join("toolkit/engine_vocabulary_dump.py")
	if not FileAccess.file_exists(script):
		return {"error": "missing %s" % script}
	var output: Array = []
	var code := OS.execute(python_exe, [script], output, true)
	var raw: String = str(output[0]) if output.size() > 0 else ""
	if raw.strip_edges() == "":
		return {"error": "no output (exit %d)" % code}
	var parsed = JSON.parse_string(raw)
	if typeof(parsed) != TYPE_DICTIONARY:
		return {"error": "output was not a JSON object"}
	return parsed


func _as_set(values: Variant) -> Dictionary:
	var out := {}
	if values is Array:
		for value in values:
			out[str(value)] = true
	return out


## Keys in `left` that are not in `right`. GDScript's Dictionary has no set
## difference, and the sets are small enough that spelling it out is cheaper than
## a clever alternative.
func _only_in(left: Dictionary, right: Dictionary) -> Array:
	var out: Array = []
	for key in left.keys():
		if not right.has(key):
			out.append(key)
	out.sort()
	return out


func _sorted(keys: Variant) -> Array:
	var out: Array = []
	if keys is Dictionary:
		out = keys.keys()
	elif keys is Array:
		out = keys.duplicate()
	out.sort()
	return out


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		printerr("  FAIL ", message)
