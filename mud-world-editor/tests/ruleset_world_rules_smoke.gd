# tests/ruleset_world_rules_smoke.gd
#
# economy, locksmithing, calendar, spawning, elites, npc_naming and
# player_defaults had no editor control; each now has a validator
# (content_set.py::_validate_simple_ruleset_sections) and a form in the Ruleset
# editor's World Rules section. fantasy_frontier authors all seven.
#
#   godot --headless --path mud-world-editor --script tests/ruleset_world_rules_smoke.gd

extends SceneTree

const Rules = preload("res://scripts/ui/modals/RulesetEditorDialog.gd")
const SECTIONS := ["economy", "locksmithing", "calendar", "spawning", "elites", "npc_naming", "player_defaults"]

var failures := 0


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var fixture := repo.path_join("tmp/ruleset-world-rules-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	var rules_path := fixture.path_join("rules/ruleset.json")
	var before: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rules_path))

	var rules = Rules.new(); root.add_child(rules); rules.setup(); rules.open_active()
	var section: WorldRulesSection = rules.world_rules_section
	var composed := section.compose()
	for name in SECTIONS:
		_assert(_same(composed.get(name), before.get(name)), "%s composes back unchanged" % name)
	_assert(not section.changed(), "opening is clean")
	_assert(rules.get_ok_button().disabled, "Save starts disabled")
	_assert(section.inventory_rows.get_child_count() == 3, "one row per starting item")

	_edit(section.controls["economy.currency_name"], "crowns")
	_assert(not rules.get_ok_button().disabled, "an edit enables Save")
	(section.controls["elites.chance"] as SpinBox).value = 0.1
	(section.controls["calendar.start_time.hour"] as SpinBox).value = 7
	_edit(section.controls["elites.prefixes"], "Alpha, Elder, Ancient, Dread, Savage, Greater, Feral, Grizzled, Hoary")
	var knife_row: Node = section.inventory_rows.get_child(1)
	(knife_row.get_node("Quantity") as SpinBox).value = 2

	_edit(section.controls["npc_naming.random_name_pattern"], "{first_name} of {village}")
	var bytes_before := FileAccess.get_file_as_string(rules_path)
	rules.confirmed.emit()
	_assert(FileAccess.get_file_as_string(rules_path) == bytes_before, "a name pattern that would raise is refused, nothing written")
	_assert("village" in rules.status_label.text, "and the refusal names it: %s" % rules.status_label.text)
	_edit(section.controls["npc_naming.random_name_pattern"], "{first_name} the {title}")

	rules.confirmed.emit()
	var after: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	_assert(after["economy"]["currency_name"] == "crowns", "the currency was saved")
	_assert(is_equal_approx(float(after["elites"]["chance"]), 0.1), "the elite chance was saved")
	_assert(int(after["calendar"]["start_time"]["hour"]) == 7 and int(after["calendar"]["start_time"]["minute"]) == 0, "the start hour was saved, minute untouched")
	_assert(after["elites"]["prefixes"].back() == "Hoary", "the prefix list was saved")
	_assert(_same(after["player_defaults"]["starting_inventory"][1], {"item_id": "item_foraging_knife", "quantity": 2}), "the quantity was saved")
	_assert(after["npc_naming"] == before["npc_naming"], "the corrected pattern left npc_naming as it was")
	_assert(after["calendar"]["day_names"] == before["calendar"]["day_names"], "untouched day names survive")
	_assert(_same(after["spawning"], before["spawning"]), "an untouched section survives exactly")
	_assert(after["elites"].keys() == before["elites"].keys(), "key order within a section is preserved")
	_assert(_same(after.get("quest_generation"), before.get("quest_generation")), "another ruleset section is untouched")
	_assert(not rules.visible, "a successful save closes the dialog")

	rules.open_active()
	_assert(not rules.world_rules_section.changed(), "reopen is clean")
	_edit(rules.world_rules_section.controls["economy.currency_name"], "")
	_assert(not rules.world_rules_section.compose().get("economy", {}).has("currency_name"), "clearing a field removes its key")

	rules._allow_close = true; rules.hide(); rules.queue_free()
	if failures > 0:
		push_error("ruleset world rules failed (%d)" % failures)
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
