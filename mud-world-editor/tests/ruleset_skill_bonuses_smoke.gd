# tests/ruleset_skill_bonuses_smoke.gd
#
# `skills.stat_bonuses` (`skill_system.py:43-49`; `content_set.py::
# _validate_skills_rules`): which stat backs a skill check, and how much each
# point above 10 adds. Had no editor control at all -- orbital_salvage already
# declares two (evasion/agility, fabrication/intelligence), and until now the
# only way to add, edit or remove one was hand-editing ruleset.json. See
# docs/plan/editor-coverage-ledger.md family E.
#
#   godot --headless --path mud-world-editor --script tests/ruleset_skill_bonuses_smoke.gd

extends SceneTree

const Rules = preload("res://scripts/ui/modals/RulesetEditorDialog.gd")

var failures := 0
var fixture := ""

func _init(): _run.call_deferred()

func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/ruleset-skill-bonuses-%s/orbital_salvage" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/orbital_salvage"), fixture)
	DataRoot._resolved = fixture
	var rules_path := fixture.path_join("rules/ruleset.json")
	var before: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rules_path))

	var rules = Rules.new(); root.add_child(rules); rules.setup(); rules.open_active()

	_assert(rules._skill_bonuses() == rules._normalized_bonuses(before["skills"]["stat_bonuses"]), "the two authored bonuses load unchanged")
	_assert(rules.skill_bonus_rows.get_child_count() == 2, "one row per authored bonus (%d)" % rules.skill_bonus_rows.get_child_count())
	_assert(not rules._skill_bonuses_changed(), "opening is clean")
	_assert(rules.get_ok_button().disabled, "Save starts disabled")

	# Edit an existing bonus's per_point in place.
	var evasion_row := _row_with_id(rules, "evasion")
	_assert(evasion_row != null, "the evasion row was found")
	var per_point: SpinBox = evasion_row.get_child(3)
	per_point.value = 3; per_point.value_changed.emit(3.0)
	_assert(rules._skill_bonuses()["evasion"]["per_point"] == 3, "the edit reached the draft immediately")
	_assert(not rules.get_ok_button().disabled, "an edit enables Save")

	# Add a third bonus.
	rules._add_skill_bonus_row("", {}); rules._mark_dirty()
	var new_row: Node = rules.skill_bonus_rows.get_child(rules.skill_bonus_rows.get_child_count() - 1)
	_edit(new_row.get_child(0), "lockpicking")
	_edit(new_row.get_child(1), "dexterity")
	var new_per_point: SpinBox = new_row.get_child(3)
	new_per_point.value = 2; new_per_point.value_changed.emit(2.0)
	_assert(rules._skill_bonuses().get("lockpicking", {}) == {"stat": "dexterity", "per_point": 2}, "the new bonus reached the draft")

	rules.confirmed.emit()
	var after: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	# JSON.parse_string always returns a float for a number, whatever the file
	# spells -- both sides here are read that way, so both use float literals.
	_assert(after["skills"]["stat_bonuses"]["evasion"] == {"stat": "agility", "per_point": 3.0}, "the edit was saved")
	_assert(after["skills"]["stat_bonuses"]["lockpicking"] == {"stat": "dexterity", "per_point": 2.0}, "the addition was saved")
	_assert(after["skills"]["stat_bonuses"]["fabrication"] == before["skills"]["stat_bonuses"]["fabrication"], "the untouched bonus survives byte-for-byte")
	_assert(after.get("social", {}) == before.get("social", {}), "an unrelated ruleset section is untouched")
	_assert(not rules.visible, "successful save closes the dialog")

	rules.open_active()
	_assert(rules.skill_bonus_rows.get_child_count() == 3, "reopen shows all three, no duplication")
	_assert(_row_with_id(rules, "lockpicking") != null, "the saved addition reopens correctly")

	# Blanking a stat clears it rather than saving an empty string.
	var lockpicking_row := _row_with_id(rules, "lockpicking")
	_edit(lockpicking_row.get_child(1), "")
	_assert(not rules._skill_bonuses()["lockpicking"].has("stat"), "a blanked stat field is erased, not saved as ''")

	# Removing the only remaining edit's row takes it out of the draft.
	var remove_button: Button = lockpicking_row.get_child(4)
	remove_button.pressed.emit()
	_assert(not rules._skill_bonuses().has("lockpicking"), "the removed row's bonus is gone from the draft")
	rules.confirmed.emit()
	var final: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	_assert(not final["skills"]["stat_bonuses"].has("lockpicking"), "the removal was saved")
	_assert(final["skills"]["stat_bonuses"].size() == 2, "back to two bonuses")

	rules._allow_close = true; rules.hide(); rules.queue_free()
	if failures > 0:
		push_error("ruleset skill bonuses failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _row_with_id(rules, skill_id: String) -> Node:
	for row in rules.skill_bonus_rows.get_children():
		if row is HBoxContainer and row.get_child_count() > 0 and row.get_child(0) is LineEdit and str(row.get_child(0).text) == skill_id:
			return row
	return null


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
