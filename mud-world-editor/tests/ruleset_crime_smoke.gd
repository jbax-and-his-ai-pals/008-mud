# tests/ruleset_crime_smoke.gd
#
# The ruleset's `crime` section had no editor control; it now has a validator
# (content_set.py::_validate_crime_and_debug_rules) and the Ruleset editor's
# Crime section. fantasy_frontier's real section is the fixture.
#
#   godot --headless --path mud-world-editor --script tests/ruleset_crime_smoke.gd

extends SceneTree

const Rules = preload("res://scripts/ui/modals/RulesetEditorDialog.gd")

var failures := 0


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var fixture := repo.path_join("tmp/ruleset-crime-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	var rules_path := fixture.path_join("rules/ruleset.json")
	var before: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rules_path))

	var rules = Rules.new(); root.add_child(rules); rules.setup(); rules.open_active()
	var crime: CrimeSection = rules.crime_section
	_assert(_same(crime.compose(), before["crime"]), "the real section composes back unchanged")
	_assert(not crime.changed(), "opening is clean")
	_assert(rules.get_ok_button().disabled, "Save starts disabled")
	_assert(crime.requirement_rows.get_child_count() == 2, "one row per concealed-tool requirement")
	_assert((crime.controls["enabled"] as CheckBox).button_pressed, "crime shows as enabled")
	_assert(QuestGenerationSection._picked(crime.controls["custody.emergency_tool_item_id"]) == "item_lockpick_shiv", "the emergency tool resolves in its picker")

	(crime.controls["consequences.fine_rate"] as SpinBox).value = 3.5
	_assert(not rules.get_ok_button().disabled, "an edit enables Save")
	_edit(crime.controls["witness.excluded_factions"], "hostile, player_minion, wildlife")
	var lockpicking: Node = crime.requirement_rows.get_child(1)
	(lockpicking.get_node("Minimum") as SpinBox).value = 25

	# The jail room is a cross-file fact: only the staged engine check knows
	# which rooms carry the property, and it must refuse before anything is written.
	_edit(crime.controls["custody.room_property"], "is_dungeon")
	var bytes_before := FileAccess.get_file_as_string(rules_path)
	rules.confirmed.emit()
	_assert(FileAccess.get_file_as_string(rules_path) == bytes_before, "a jail property no room carries is refused, nothing written")
	_assert("is_dungeon" in rules.status_label.text, "and the refusal names it")
	_edit(crime.controls["custody.room_property"], "is_jail_cell")

	rules.confirmed.emit()
	var after: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	var saved: Dictionary = after["crime"]
	_assert(is_equal_approx(float(saved["consequences"]["fine_rate"]), 3.5), "the fine rate was saved")
	_assert(saved["witness"]["excluded_factions"] == ["hostile", "player_minion", "wildlife"], "the excluded factions were saved")
	_assert(int(saved["custody"]["concealed_tool_requirements"][1]["minimum"]) == 25, "the requirement was saved")
	_assert(saved["custody"]["room_property"] == "is_jail_cell", "the restored jail property was saved")
	_assert(_same(saved["witness"]["base_difficulty"], before["crime"]["witness"]["base_difficulty"]), "an untouched number survives")
	_assert(saved["custody"].keys() == before["crime"]["custody"].keys(), "key order within custody is preserved")
	_assert(_same(after.get("elites"), before.get("elites")), "another ruleset section is untouched")
	_assert(not rules.visible, "a successful save closes the dialog")

	rules.open_active()
	_assert(not rules.crime_section.changed(), "reopen is clean")
	(rules.crime_section.controls["enabled"] as CheckBox).button_pressed = false
	_assert(rules.crime_section.compose()["enabled"] == false, "turning crime off writes false, not a missing key")

	rules._allow_close = true; rules.hide(); rules.queue_free()
	if failures > 0:
		push_error("ruleset crime failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _same(a, b) -> bool:
	return JSON.stringify(SaveIO._normalize_numbers(a)) == JSON.stringify(SaveIO._normalize_numbers(b))


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _edit(field: LineEdit, value: String):
	field.text = value; field.text_changed.emit(value)


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
