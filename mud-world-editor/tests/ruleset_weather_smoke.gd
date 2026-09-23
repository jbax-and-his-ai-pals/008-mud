# tests/ruleset_weather_smoke.gd
#
# `weather.descriptions` (information.py's `weather` command) and
# `weather.profiles.<id>.map`/`.travel_notes` (weather_manager.py::
# effective_weather/travel_note) had no editor control at all -- a region
# could already pick a declared profile (RegionInspector.gd), but nothing
# authored what a profile actually meant, or what a weather type's flavor
# text said. See docs/plan/editor-coverage-ledger.md, region B and ruleset
# H.1.
#
# fantasy_frontier already declares six descriptions and eight profiles by
# hand, which makes it the fixture: this proves a real, populated weather
# section round-trips, not just an empty one.
#
#   godot --headless --path mud-world-editor --script tests/ruleset_weather_smoke.gd

extends SceneTree

const Rules = preload("res://scripts/ui/modals/RulesetEditorDialog.gd")

var failures := 0
var fixture := ""

func _init(): _run.call_deferred()

func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/ruleset-weather-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	var rules_path := fixture.path_join("rules/ruleset.json")
	var before: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	var before_weather: Dictionary = before["weather"]
	_assert(before_weather.get("descriptions", {}).size() == 6, "the fixture starts with six authored descriptions")
	_assert(before_weather.get("profiles", {}).size() == 8, "and eight authored profiles")

	var rules = Rules.new(); root.add_child(rules); rules.setup(); rules.open_active()
	_assert(rules._weather_descriptions() == before_weather["descriptions"], "descriptions load unchanged")
	_assert(rules._weather_profiles() == before_weather["profiles"], "profiles load unchanged")
	_assert(not rules._weather_descriptions_changed() and not rules._weather_profiles_changed(), "opening is clean")
	_assert(rules.get_ok_button().disabled, "Save starts disabled")
	_assert(rules.weather_profile_rows.get_child_count() == 8, "one card per authored profile")

	# Edit one existing description in place.
	var rain_row := _row_with_key(rules.weather_description_rows, "windy")
	_assert(rain_row != null, "the 'windy' description row was found")
	_edit(rain_row.get_child(1), "A gale strips leaves from the roadside trees.")
	_assert(rules._weather_descriptions()["windy"] == "A gale strips leaves from the roadside trees.", "the edit reached the draft")
	_assert(not rules.get_ok_button().disabled, "the edit enables Save")

	# Add a mapping to the existing "underground" profile (which starts empty).
	var underground_card := _profile_card(rules, "underground")
	_assert(underground_card != null, "the 'underground' profile card was found")
	var underground_map: Node = underground_card.find_child("MapRows", true, false)
	var add_map := _button_labeled(underground_card, "+ Mapping")
	add_map.pressed.emit()
	var new_map_row: Node = underground_map.get_child(underground_map.get_child_count() - 1)
	_edit(new_map_row.get_child(0), "clear")
	_edit(new_map_row.get_child(1), "still air")
	_assert(rules._weather_profiles()["underground"]["map"] == {"clear": "still air"}, "the new mapping reached the draft")

	# Add a brand new profile.
	var add_profile := _button_labeled(rules, "+ Profile")
	add_profile.pressed.emit()
	var new_card: Node = rules.weather_profile_rows.get_child(rules.weather_profile_rows.get_child_count() - 1)
	_edit(new_card.find_child("ProfileId", true, false), "volcanic")
	var add_note := _button_labeled(new_card, "+ Travel Note")
	add_note.pressed.emit()
	var note_rows: Node = new_card.find_child("TravelNoteRows", true, false)
	var note_row: Node = note_rows.get_child(0)
	_edit(note_row.get_child(0), "clear")
	_edit(note_row.get_child(1), "Ash drifts even on a clear day.")
	_assert(rules._weather_profiles().get("volcanic", {}) == {"travel_notes": {"clear": "Ash drifts even on a clear day."}}, "the new profile reached the draft")

	rules.confirmed.emit()
	var after: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	var after_weather: Dictionary = after["weather"]
	_assert(after_weather["descriptions"]["windy"] == "A gale strips leaves from the roadside trees.", "the edited description was saved")
	_assert(after_weather["descriptions"]["mist"] == before_weather["descriptions"]["mist"], "an untouched description survives byte-for-byte")
	_assert(after_weather["profiles"]["underground"]["map"] == {"clear": "still air"}, "the new mapping was saved")
	_assert(after_weather["profiles"]["volcanic"]["travel_notes"] == {"clear": "Ash drifts even on a clear day."}, "the new profile was saved")
	_assert(after_weather["profiles"]["alpine"] == before_weather["profiles"]["alpine"], "an untouched profile survives byte-for-byte")
	_assert(after_weather["profiles"].size() == 9, "eight original profiles plus the new one")
	_assert(not rules.visible, "successful save closes the dialog")

	rules.open_active()
	_assert(rules.weather_profile_rows.get_child_count() == 9, "reopen shows all nine profiles, no duplication")

	rules._allow_close = true; rules.hide(); rules.queue_free()
	if failures > 0:
		push_error("ruleset weather failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _row_with_key(rows: Node, key: String) -> Node:
	for row in rows.get_children():
		if row is HBoxContainer and row.get_child_count() > 0 and row.get_child(0) is LineEdit and str(row.get_child(0).text) == key:
			return row
	return null


func _profile_card(rules, profile_id: String) -> Node:
	for card in rules.weather_profile_rows.get_children():
		var id_field: LineEdit = card.find_child("ProfileId", true, false)
		if id_field != null and str(id_field.text) == profile_id:
			return card
	return null


func _button_labeled(node: Node, text: String) -> Button:
	if node is Button and str(node.text) == text:
		return node
	for child in node.get_children():
		var found := _button_labeled(child, text)
		if found != null:
			return found
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
