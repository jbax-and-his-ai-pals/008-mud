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
	_check_character_effect_vocabulary(vocabulary)
	_check_passage_keys(vocabulary)
	_check_trigger_vocabulary(vocabulary)
	_check_direction_reciprocals(vocabulary)
	_check_manifest_shape(vocabulary)
	_check_npc_vocabulary(vocabulary)
	_check_knowledge_conditions(vocabulary)
	_check_affix_item_classes(vocabulary)
	_check_item_type_names(vocabulary)
	_check_room_property_kinds(vocabulary)
	_check_holder_kinds(vocabulary, "region_property_kinds", RegionInspector.REGION_PROPERTY_KINDS)
	_check_holder_kinds(vocabulary, "district_property_kinds", DistrictInspector.DISTRICT_PROPERTY_KINDS)
	_check_campaign_vocabulary(vocabulary)
	_check_ability_vocabulary(vocabulary)
	_check_pace_vocabulary(vocabulary)
	_check_sharing_vocabulary(vocabulary)
	_check_level_up_vocabulary(vocabulary)
	_check_scene_vocabulary(vocabulary)
	_check_attack_mode_vocabulary(vocabulary)
	_check_messages_vocabulary(vocabulary)
	_check_weather_vocabulary(vocabulary)
	_check_feature_profile_vocabulary(vocabulary)

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

func _check_trigger_vocabulary(vocabulary: Dictionary) -> void:
	print("
[triggers: editor vs engine]")
	var schema = load("res://scripts/data/TriggerSchema.gd")
	var engine: Dictionary = vocabulary.get("triggers", {})
	_assert(not engine.is_empty(), "the engine's trigger vocabulary was read")
	_assert(_as_set(engine.get("events", [])) == _as_set(schema.EVENTS),
		"the events match (engine %s, editor %s)" % [str(engine.get("events")), str(schema.EVENTS)])
	_assert(_as_set(engine.get("keys", [])) == _as_set(schema.KEYS),
		"the keys match (engine %s, editor %s)" % [str(engine.get("keys")), str(schema.KEYS)])
	for key in ["event_fields", "event_required"]:
		var editor_table: Dictionary = schema.EVENT_FIELDS if key == "event_fields" else schema.EVENT_REQUIRED
		var engine_table: Dictionary = engine.get(key, {})
		_assert(_as_set(engine_table.keys()) == _as_set(editor_table.keys()), "the events in %s match" % key)
		for event in engine_table:
			_assert(_as_set(engine_table[event]) == _as_set(editor_table.get(event, [])),
				"%s for %s matches (engine %s, editor %s)" % [key, event, str(engine_table[event]), str(editor_table.get(event))])
	_assert(_as_set(engine.get("once_modes", [])) == _as_set(schema.ONCE_MODES),
		"the once modes match (engine %s, editor %s)" % [str(engine.get("once_modes")), str(schema.ONCE_MODES)])
	_assert(str(engine.get("default_once", "")) == schema.DEFAULT_ONCE, "and so does the default")


func _check_passage_keys(vocabulary: Dictionary) -> void:
	print("\n[exit requirement and reaction keys: editor vs engine]")
	var requirements: Dictionary = vocabulary.get("exit_requirement_keys", {})
	_assert(not requirements.is_empty(), "the engine's exit requirement keys were read")
	_assert(_as_set(requirements.keys()) == _as_set(RoomPassagesPanel.REQUIREMENT_TYPES),
		"the requirement types match (engine %s, editor %s)" % [str(requirements.keys()), str(RoomPassagesPanel.REQUIREMENT_TYPES)])
	for kind in requirements:
		_assert(_as_set(requirements[kind]) == _as_set(RoomPassagesPanel.REQUIREMENT_KEYS.get(kind, [])),
			"a '%s' requirement's keys match (engine %s, editor %s)" % [kind, str(requirements[kind]), str(RoomPassagesPanel.REQUIREMENT_KEYS.get(kind))])
	var reactions: Dictionary = vocabulary.get("env_interaction_keys", {})
	_assert(_as_set(reactions.keys()) == _as_set(RoomPassagesPanel.REACTION_TYPES),
		"the reaction types match (engine %s, editor %s)" % [str(reactions.keys()), str(RoomPassagesPanel.REACTION_TYPES)])
	for kind in reactions:
		_assert(_as_set(reactions[kind]) == _as_set(RoomPassagesPanel.REACTION_KEYS.get(kind, [])),
			"a '%s' reaction's keys match (engine %s, editor %s)" % [kind, str(reactions[kind]), str(RoomPassagesPanel.REACTION_KEYS.get(kind))])


func _check_character_effect_vocabulary(vocabulary: Dictionary) -> void:
	print("\n[restore resources and consumable effect types: editor vs engine]")
	_assert(Array(vocabulary.get("restore_resources", [])) == DialogueSchema.RESTORE_RESOURCES,
		"`restore` offers the resources the engine refills (engine %s, editor %s)" % [
			str(vocabulary.get("restore_resources")), str(DialogueSchema.RESTORE_RESOURCES)])
	var engine := _as_set(vocabulary.get("consumable_effect_types", []))
	var editor := _as_set(ItemInspector.CONSUMABLE_EFFECT_TYPES)
	_assert(not engine.is_empty(), "the engine's consumable effect types were read")
	_assert(engine == editor,
		"a consumable's effect types match exactly (engine only %s, editor only %s)" % [
			str(_only_in(engine, editor)), str(_only_in(editor, engine))])


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
## engine (`engine/server/content_set/`) is what refuses one. Every name in the
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


## `NPCVocabulary.gd` copies the engine's faction and behaviour vocabularies for
## the NPC inspector's pickers (see its own header for why a copy at all).
func _check_npc_vocabulary(vocabulary: Dictionary) -> void:
	print("\n[NPC vocabulary: editor vs engine]")
	var factions: Dictionary = vocabulary.get("factions", {})
	_assert(not factions.is_empty(), "the engine's faction vocabulary was read")

	var engine_built_in := _as_set(factions.get("built_in", []))
	var editor_built_in := _as_set(NPCVocabulary.BUILT_IN_FACTIONS)
	_assert(engine_built_in == editor_built_in,
		"the built-in factions match exactly (engine %s, editor %s)" % [str(_sorted(engine_built_in)), str(_sorted(editor_built_in))])

	var engine_dispositions := _as_set(factions.get("dispositions", []))
	var editor_dispositions := _as_set(NPCVocabulary.FACTION_DISPOSITIONS)
	_assert(engine_dispositions == editor_dispositions,
		"the disposition vocabulary matches exactly (engine %s, editor %s)" % [str(_sorted(engine_dispositions)), str(_sorted(editor_dispositions))])

	var engine_defaults: Dictionary = factions.get("default_dispositions", {})
	_assert(engine_defaults == NPCVocabulary.FACTION_DEFAULT_DISPOSITIONS,
		"the default disposition per built-in faction matches exactly (engine %s, editor %s)" % [str(engine_defaults), str(NPCVocabulary.FACTION_DEFAULT_DISPOSITIONS)])

	var engine_behaviors := _as_set(vocabulary.get("npc_behavior_types", []))
	var editor_behaviors := _as_set(NPCVocabulary.BEHAVIOR_TYPES)
	_assert(engine_behaviors == editor_behaviors,
		"the behaviour vocabulary matches exactly (engine %s, editor %s)" % [str(_sorted(engine_behaviors)), str(_sorted(editor_behaviors))])

	var engine_slots: Array = vocabulary.get("equipment_slots", [])
	_assert(engine_slots == NPCVocabulary.EQUIPMENT_SLOTS,
		"the equipment slots match, in order (engine %s, editor %s)" % [str(engine_slots), str(NPCVocabulary.EQUIPMENT_SLOTS)])


## `KnowledgeInspector.gd` copies a topic response's condition vocabulary for its
## kind and state pickers. The engine's constants sit beside the reader and are
## tied to it by test_knowledge_condition_vocabulary.py; this ties the copy to them.
func _check_knowledge_conditions(vocabulary: Dictionary) -> void:
	print("\n[knowledge conditions: editor vs engine]")
	var knowledge: Dictionary = vocabulary.get("knowledge_conditions", {})
	_assert(not knowledge.is_empty(), "the engine's knowledge-condition vocabulary was read")
	for pair in [["kinds", KnowledgeInspector.CONDITION_KINDS], ["knowledge_states", KnowledgeInspector.KNOWLEDGE_STATES],
			["campaign_states", KnowledgeInspector.CAMPAIGN_STATES], ["quest_states", KnowledgeInspector.QUEST_STATES]]:
		var engine := _as_set(knowledge.get(pair[0], []))
		var editor := _as_set(pair[1])
		_assert(engine == editor, "%s match exactly (engine %s, editor %s)" % [pair[0], str(_sorted(engine)), str(_sorted(editor))])


## `AffixInspector.ITEM_CLASSES` is what an affix's `allowed_types` may name:
## the engine's item classes plus "All".
func _check_affix_item_classes(vocabulary: Dictionary) -> void:
	print("\n[affix item classes: editor vs engine]")
	var engine := _as_set(vocabulary.get("item_classes", []))
	_assert(not engine.is_empty(), "the engine's item classes were read")
	var editor := _as_set(AffixInspector.ITEM_CLASSES)
	editor.erase("All")
	_assert(engine == editor, "the affix type list matches the engine's classes (engine %s, editor %s)" % [str(_sorted(engine)), str(_sorted(editor))])


## `ItemInspector.ITEM_CLASSES` is what a template's `type` picker offers: every
## name ITEM_CLASS_MAP accepts (a type outside it is refused by the engine).
func _check_item_type_names(vocabulary: Dictionary) -> void:
	print("\n[item type names: editor vs engine]")
	var engine := _as_set(vocabulary.get("item_type_names", []))
	_assert(not engine.is_empty(), "the engine's item type names were read")
	var editor := _as_set(ItemInspector.ITEM_CLASSES)
	_assert(engine == editor, "the item type picker matches the factory's names (engine %s, editor %s)" % [str(_sorted(engine)), str(_sorted(editor))])


func _check_room_property_kinds(vocabulary: Dictionary) -> void:
	print("\n[room property vocabulary: editor vs engine]")
	var engine: Dictionary = vocabulary.get("room_property_kinds", {})
	_assert(not engine.is_empty(), "the engine's room property vocabulary was read")
	_assert(_as_set(engine.keys()) == _as_set(RoomPropertiesPanel.ROOM_PROPERTY_KINDS.keys()), "the room property keys match (engine %s, editor %s)" % [str(_sorted(_as_set(engine.keys()))), str(_sorted(_as_set(RoomPropertiesPanel.ROOM_PROPERTY_KINDS.keys())))])
	for key in engine:
		_assert(str(RoomPropertiesPanel.ROOM_PROPERTY_KINDS.get(key, "")) == str(engine[key]), "room property %s is a %s in both" % [key, engine[key]])


func _check_holder_kinds(vocabulary: Dictionary, name: String, editor: Dictionary) -> void:
	print("\n[%s: editor vs engine]" % name)
	var engine: Dictionary = vocabulary.get(name, {})
	_assert(not engine.is_empty(), "the engine's %s were read" % name)
	_assert(_as_set(engine.keys()) == _as_set(editor.keys()), "%s keys match (engine %s, editor %s)" % [name, str(_sorted(_as_set(engine.keys()))), str(_sorted(_as_set(editor.keys())))])
	for key in engine:
		_assert(str(editor.get(key, "")) == str(engine[key]), "%s.%s is a %s in both" % [name, key, engine[key]])


func _check_feature_profile_vocabulary(vocabulary: Dictionary) -> void:
	print("
[feature profile: editor vs engine]")
	var profile: Dictionary = vocabulary.get("feature_profile", {})
	_assert(not profile.is_empty(), "the engine's feature profile vocabulary was read")
	var modes: Dictionary = profile.get("modes", {})
	_assert(_as_set(modes.keys()) == _as_set(FeatureProfileDialog.MODES.keys()), "the same mode categories (engine %s)" % str(_sorted(_as_set(modes.keys()))))
	for category in modes:
		_assert(Array(modes[category]) == Array(FeatureProfileDialog.MODES.get(category, [])), "%s modes match, default first (engine %s)" % [category, str(modes[category])])
	_assert(Array(profile.get("provider_categories", [])) == FeatureProfileDialog.PROVIDER_CATEGORIES, "the categories that take a provider id match")
	_assert(JSON.stringify(profile.get("policies", {})) == JSON.stringify(FeatureProfileDialog.POLICIES), "the policy sections, keys and values match the readers'")


func _check_weather_vocabulary(vocabulary: Dictionary) -> void:
	print("
[weather: editor vs engine]")
	var weather: Dictionary = vocabulary.get("weather", {})
	_assert(Array(weather.get("seasons", [])) == WeatherChancesSection.SEASONS, "the seasons match, in calendar order (engine %s)" % str(weather.get("seasons")))
	_assert(JSON.stringify(SaveIO._normalize_numbers(weather.get("default_chances", {}))) == JSON.stringify(SaveIO._normalize_numbers(_sorted_table(WeatherChancesSection.DEFAULT_CHANCES))), "the engine's default seasonal table matches the one the editor shows")


func _sorted_table(table: Dictionary) -> Dictionary:
	var out := {}
	var seasons := table.keys(); seasons.sort()
	for season in seasons:
		var entries: Dictionary = table[season]; var types := entries.keys(); types.sort()
		out[season] = {}
		for weather_type in types: out[season][weather_type] = entries[weather_type]
	return out


func _check_campaign_vocabulary(vocabulary: Dictionary) -> void:
	print("\n[campaign vocabulary: editor vs engine]")
	var campaigns: Dictionary = vocabulary.get("campaigns", {})
	_assert(not campaigns.is_empty(), "the engine's campaign vocabulary was read")
	for pair in [["node_types", CampaignInspector.NODE_TYPES], ["triggers", CampaignInspector.TRIGGERS]]:
		var engine := _as_set(campaigns.get(pair[0], []))
		var editor := _as_set(pair[1])
		_assert(engine == editor, "campaign %s match exactly (engine %s, editor %s)" % [pair[0], str(_sorted(engine)), str(_sorted(editor))])


func _check_sharing_vocabulary(vocabulary: Dictionary) -> void:
	print("\n[experience sharing vocabulary: editor vs engine]")
	var engine: Dictionary = vocabulary.get("experience_sharing", {})
	_assert(not engine.is_empty(), "the engine's experience-sharing vocabulary was read")
	_assert(_as_set(engine.get("modes", [])) == _as_set(RulesetDraft.SHARING_MODES), "sharing modes match exactly (engine %s, editor %s)" % [str(_sorted(_as_set(engine.get("modes", [])))), str(_sorted(_as_set(RulesetDraft.SHARING_MODES)))])
	_assert(is_equal_approx(float(engine.get("default_min_share", -1.0)), RulesetDraft.SHARING_DEFAULT_MIN_SHARE), "the default minimum share is the same in both")
	_assert(is_equal_approx(float(engine.get("default_memory_seconds", -1.0)), float(RulesetDraft.SHARING_DEFAULT_MEMORY_SECONDS)), "the default memory is the same in both")


func _check_attack_mode_vocabulary(vocabulary: Dictionary) -> void:
	print("\n[attack modes: editor vs engine]")
	var engine: Dictionary = vocabulary.get("attack_modes", {})
	_assert(not engine.is_empty(), "the engine's attack-mode vocabulary was read")
	_assert(engine.get("keys", []) == ItemInspector.ATTACK_MODE_KEYS, "mode keys match, in order (engine %s, editor %s)" % [str(engine.get("keys", [])), str(ItemInspector.ATTACK_MODE_KEYS)])
	_assert(engine.get("text_fields", []) == ItemInspector.ATTACK_MODE_TEXT_FIELDS, "sentence fields match (engine %s, editor %s)" % [str(engine.get("text_fields", [])), str(ItemInspector.ATTACK_MODE_TEXT_FIELDS)])
	_assert(engine.get("damage_types", []) == ItemInspector.WEAPON_DAMAGE_TYPES, "weapon damage types match (engine %s, editor %s)" % [str(engine.get("damage_types", [])), str(ItemInspector.WEAPON_DAMAGE_TYPES)])


func _check_scene_vocabulary(vocabulary: Dictionary) -> void:
	print("\n[scenes: editor vs engine]")
	var schema = load("res://scripts/data/SceneSchema.gd")
	var engine: Dictionary = vocabulary.get("scenes", {})
	_assert(not engine.is_empty(), "the engine's scene vocabulary was read")
	_assert(_as_set(engine.get("keys", [])) == _as_set(schema.KEYS), "scene keys match exactly (engine %s, editor %s)" % [str(_sorted(_as_set(engine.get("keys", [])))), str(_sorted(_as_set(schema.KEYS)))])
	_assert(_as_set(engine.get("beat_keys", [])) == _as_set(schema.BEAT_KEYS), "beat keys match exactly (engine %s, editor %s)" % [str(_sorted(_as_set(engine.get("beat_keys", [])))), str(_sorted(_as_set(schema.BEAT_KEYS)))])
	_assert(is_equal_approx(float(engine.get("default_first_wait", -1.0)), schema.DEFAULT_FIRST_WAIT) and is_equal_approx(float(engine.get("default_wait", -1.0)), schema.DEFAULT_WAIT), "the default waits are the same in both")
	_assert(int(engine.get("max_wait", -1)) == schema.MAX_WAIT, "the longest wait is the same in both")


func _check_level_up_vocabulary(vocabulary: Dictionary) -> void:
	print("\n[level-up growth vocabulary: editor vs engine]")
	var engine: Dictionary = vocabulary.get("level_up", {})
	_assert(not engine.is_empty(), "the engine's level-up vocabulary was read")
	_assert(is_equal_approx(float(engine.get("default_stat_growth", -1.0)), float(RulesetDraft.LEVEL_UP_DEFAULT_STAT_GROWTH)), "the default stat growth is the same in both")
	_assert(int(engine.get("default_health_base", -1)) == RulesetDraft.LEVEL_UP_DEFAULT_HEALTH_BASE, "the default flat health per level is the same in both")


func _check_messages_vocabulary(vocabulary: Dictionary) -> void:
	print("\n[the engine's words: editor vs engine]")
	var engine: Dictionary = vocabulary.get("messages", {})
	_assert(not engine.is_empty(), "the engine's messages were read")
	_assert(_as_set(engine.keys()) == _as_set(RulesetDraft.MESSAGES.keys()), "the same messages are named (engine %s, editor %s)" % [str(_sorted(_as_set(engine.keys()))), str(_sorted(_as_set(RulesetDraft.MESSAGES.keys())))])
	for key in engine:
		if not RulesetDraft.MESSAGES.has(key): continue
		_assert(str(engine[key].get("default", "")) == str(RulesetDraft.MESSAGES[key][0]), "%s: the engine's words are the same in both" % key)
		_assert(_as_set(engine[key].get("fields", [])) == _as_set(RulesetDraft.MESSAGES[key][1]), "%s: the fields it may use are the same in both" % key)


func _check_pace_vocabulary(vocabulary: Dictionary) -> void:
	print("\n[text pace vocabulary: editor vs engine]")
	var engine_paces: Dictionary = vocabulary.get("text_paces", {}).get("paces", {})
	_assert(not engine_paces.is_empty(), "the engine's text paces were read")
	var editor_paces: Dictionary = DialogueInspector.TEXT_PACES
	_assert(_as_set(engine_paces.keys()) == _as_set(editor_paces.keys()), "pace names match exactly (engine %s, editor %s)" % [str(_sorted(_as_set(engine_paces.keys()))), str(_sorted(_as_set(editor_paces.keys())))])
	for pace_name in engine_paces:
		_assert(editor_paces.has(pace_name) and int(editor_paces[pace_name]) == int(engine_paces[pace_name]), "pace %s is %s characters a second in both" % [pace_name, str(engine_paces[pace_name])])


func _check_ability_vocabulary(vocabulary: Dictionary) -> void:
	print("\n[ability vocabulary: editor vs engine]")
	var abilities: Dictionary = vocabulary.get("abilities", {})
	_assert(not abilities.is_empty(), "the engine's ability vocabulary was read")
	var engine_targets := _as_set(abilities.get("target_types", []))
	_assert(engine_targets == _as_set(MagicInspector.TARGET_TYPES), "ability target types match exactly (engine %s, editor %s)" % [str(_sorted(engine_targets)), str(_sorted(_as_set(MagicInspector.TARGET_TYPES)))])
	var engine_fields: Dictionary = abilities.get("effect_fields", {})
	_assert(_as_set(engine_fields.keys()) == _as_set(MagicInspector.EFFECT_FIELDS.keys()), "effect types match exactly (engine %s, editor %s)" % [str(_sorted(_as_set(engine_fields.keys()))), str(_sorted(_as_set(MagicInspector.EFFECT_FIELDS.keys())))])
	for effect_type in engine_fields:
		var editor: Array = MagicInspector.EFFECT_FIELDS.get(effect_type, [])
		_assert(_as_set(engine_fields[effect_type]) == _as_set(editor), "a %s effect's fields match (engine %s, editor %s)" % [effect_type, str(engine_fields[effect_type]), str(editor)])
	var engine_messages: Dictionary = abilities.get("message_placeholders", {})
	for key in engine_messages:
		var editor_names: Array = MagicInspector.MESSAGE_PLACEHOLDERS.get(key, [])
		_assert(_as_set(engine_messages[key]) == _as_set(editor_names), "%s placeholders match (engine %s, editor %s)" % [key, str(engine_messages[key]), str(editor_names)])
	_assert(_as_set(engine_messages.keys()) == _as_set(MagicInspector.MESSAGE_PLACEHOLDERS.keys()), "the editor offers every message the engine formats")


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
