# tests/affix_and_set_authoring_smoke.gd
#
# The two item files the editor never loaded, and the corruption that made it stop.
#
# `data/items/affixes.json` and `sets.json` are contracts, not templates: one holds
# two libraries of affixes (`prefixes`, `suffixes`) plus string keys the generator
# reads, the other holds item sets with per-count bonuses. The editor used to load
# them into the Items cache -- so `prefixes` and `suffixes` appeared in the library
# as if they were items, and saving any item rewrote affixes.json from that cache
# and deleted its string-valued keys.
#
# Excluding them from the items cache was the workaround; loading them as
# themselves is the fix. What this test defends:
#
#   * the string keys survive a save (the exact bytes that were lost);
#   * an edit changes only what it touched;
#   * a set that has neither file does not grow one;
#   * a no-op save rewrites them byte-identically, which is what the round-trip gate
#     compares.
#
# Run with:
#
#   godot --headless --path mud-world-editor --script tests/affix_and_set_authoring_smoke.gd -- --python <interp>

extends SceneTree

const DatabaseManagerScript = preload("res://scripts/data/DatabaseManager.gd")
const AffixInspectorScript = preload("res://scripts/ui/inspectors/sub_inspectors/AffixInspector.gd")
const ItemSetInspectorScript = preload("res://scripts/ui/inspectors/sub_inspectors/ItemSetInspector.gd")

var failures := 0
var fixture := ""
var db

func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/affix-set-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "affix and set smoke"
	db = DatabaseManagerScript.new()
	db.load_all()

	_check_the_two_files_load_as_what_they_are()
	_check_a_noop_save_is_byte_identical()
	_check_editing_an_affix_keeps_the_string_keys()
	_check_editing_a_set_keeps_its_bonuses()
	_check_a_set_without_them_does_not_grow_one()
	_check_the_inspectors_build()

	_remove_recursive(fixture)
	if failures > 0:
		push_error("affix and set authoring smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


# --- the checks ---------------------------------------------------------------

func _check_the_two_files_load_as_what_they_are() -> void:
	print("\n[they load as what they are]")
	_assert(db.affix_prefixes.size() > 3, "prefixes load: %d" % db.affix_prefixes.size())
	_assert(db.affix_suffixes.size() > 3, "suffixes load: %d" % db.affix_suffixes.size())
	_assert(db.affix_extras.has("generated_effect_name_pattern"),
		"and the pattern string beside them is kept: %s" % str(db.affix_extras.keys()))
	_assert(db.item_sets.has("gladiator_set"), "item sets load by id: %s" % str(db.item_sets.keys()))
	_assert(db.item_sets.has("mage_set"), "including the one whose members are still missing")
	# The workaround stays: the item cache must not carry the two files' own
	# top-level keys, which is precisely how `prefixes` and `suffixes` used to
	# appear in the library as if they were items.
	for key in ["prefixes", "suffixes"]:
		_assert(not db.items.has(key), "the items cache has no '%s' pseudo-entry" % key)


func _check_a_noop_save_is_byte_identical() -> void:
	print("\n[a no-op save is byte-identical]")
	var before_affixes := FileAccess.get_file_as_string(db.affixes_file())
	var before_sets := FileAccess.get_file_as_string(db.sets_file())
	var result: Dictionary = db.save_all()
	_assert(result.get("ok", true), "the save succeeds: %s" % str(result.get("errors", [])))
	_assert(FileAccess.get_file_as_string(db.affixes_file()) == before_affixes,
		"saving with nothing changed leaves affixes.json exactly as it was")
	_assert(FileAccess.get_file_as_string(db.sets_file()) == before_sets,
		"and sets.json too -- which is what the round-trip gate compares")


func _check_editing_an_affix_keeps_the_string_keys() -> void:
	print("\n[editing an affix keeps the string keys]")
	var prefix_id := str(db.affix_prefixes.keys()[0])
	db.affix_prefixes[prefix_id]["value_mult"] = 2.75
	db.affix_prefixes[prefix_id]["level_min"] = 7
	db.affix_prefixes[prefix_id]["modifiers"]["strength"] = 4
	db.mark_dirty("affix_prefix", prefix_id)
	var result: Dictionary = db.save_all()
	_assert(result.get("ok", true), "the save succeeds: %s" % str(result.get("errors", [])))
	var written = JSON.parse_string(FileAccess.get_file_as_string(db.affixes_file()))
	_assert(written is Dictionary, "the file is still a JSON object")
	_assert(written["prefixes"][prefix_id]["value_mult"] == 2.75, "the edited multiplier is written")
	_assert(int(written["prefixes"][prefix_id]["level_min"]) == 7, "and the level floor")
	_assert(int(written["prefixes"][prefix_id]["modifiers"]["strength"]) == 4, "and the new modifier")
	# The defect this whole file exists to remember.
	_assert(written.has("generated_effect_name_pattern"),
		"the generator's string key SURVIVED the save: %s" % str(written.keys()))
	var other := str(written["prefixes"].keys()[1])
	_assert(written["prefixes"][other] == JSON.parse_string(FileAccess.get_file_as_string(db.affixes_file()))["prefixes"][other],
		"and an untouched prefix is unchanged")
	_assert(db.affix_suffixes.size() > 0 and written["suffixes"].size() == db.affix_suffixes.size(),
		"the suffixes library is still there")


func _check_editing_a_set_keeps_its_bonuses() -> void:
	print("\n[editing a set keeps its bonuses]")
	var before: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(db.sets_file()))
	db.item_sets["gladiator_set"]["items"].append("item_starter_dagger")
	db.item_sets["gladiator_set"]["bonuses"]["4"] = {"type": "stat_mod", "modifiers": {"evasion": 3}}
	db.mark_dirty("item_set", "gladiator_set")
	var result: Dictionary = db.save_all()
	_assert(result.get("ok", true), "the save succeeds: %s" % str(result.get("errors", [])))
	var written: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(db.sets_file()))
	_assert(written["gladiator_set"]["items"].has("item_starter_dagger"), "the new member is written")
	_assert(written["gladiator_set"]["bonuses"].has("4"), "and the new bonus tier")
	_assert(int(written["gladiator_set"]["bonuses"]["4"]["modifiers"]["evasion"]) == 3, "with its modifier")
	_assert(written["gladiator_set"]["bonuses"].has("2"),
		"and the shipped tiers are still there: %s" % str(written["gladiator_set"]["bonuses"].keys()))
	_assert(written["mage_set"] == before["mage_set"], "an untouched set is unchanged")


func _check_a_set_without_them_does_not_grow_one() -> void:
	print("\n[a set without them does not grow one]")
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var other := repo.path_join("tmp/affix-set-%s/orbital_salvage" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/orbital_salvage"), other)
	DataRoot._resolved = other
	var fresh = DatabaseManagerScript.new()
	fresh.load_all()
	_assert(not FileAccess.file_exists(fresh.affixes_file()), "this set has no affixes.json")
	var result: Dictionary = fresh.save_all()
	_assert(result.get("ok", true), "and it saves: %s" % str(result.get("errors", [])))
	_assert(not FileAccess.file_exists(fresh.affixes_file()),
		"the editor did not invent one merely by being opened and saved")
	_assert(not FileAccess.file_exists(fresh.sets_file()), "and not sets.json either")
	_remove_recursive(other.get_base_dir())


func _check_the_inspectors_build() -> void:
	# Cheap wiring check: the library hands these a container and real data, so a
	# mistake in either builder would otherwise only show up as a blank panel.
	print("\n[the inspectors build]")
	DataRoot._resolved = fixture
	var box := VBoxContainer.new()
	root.add_child(box)
	var prefix_id := str(db.affix_prefixes.keys()[0])
	var affix_inspector = AffixInspectorScript.new(box, db)
	affix_inspector.build(prefix_id, db.affix_prefixes[prefix_id], "prefix")
	_assert(box.get_child_count() > 0, "the affix inspector renders: %d sections" % box.get_child_count())
	var set_box := VBoxContainer.new()
	root.add_child(set_box)
	var set_inspector = ItemSetInspectorScript.new(set_box, db)
	set_inspector.build("gladiator_set", db.item_sets["gladiator_set"])
	_assert(set_box.get_child_count() > 0, "and the item-set inspector: %d sections" % set_box.get_child_count())


# --- helpers ------------------------------------------------------------------

func _assert(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("  ok: " + message)


func _copy(from: String, to: String) -> void:
	DirAccess.make_dir_recursive_absolute(to)
	var dir := DirAccess.open(from)
	if dir == null:
		push_error("could not open %s" % from)
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			if dir.current_is_dir():
				_copy(from.path_join(name), to.path_join(name))
			else:
				DirAccess.copy_absolute(from.path_join(name), to.path_join(name))
		name = dir.get_next()
	dir.list_dir_end()


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null: return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			if dir.current_is_dir():
				_remove_recursive(path.path_join(name))
			else:
				DirAccess.remove_absolute(path.path_join(name))
		name = dir.get_next()
	dir.list_dir_end()
	DirAccess.remove_absolute(path)
