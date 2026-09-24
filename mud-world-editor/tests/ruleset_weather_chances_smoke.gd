# tests/ruleset_weather_chances_smoke.gd
#
# `weather.chances` (weather_manager.py `_update_weather`) had no editor
# control and no engine check; the Ruleset dialog's Seasonal Weather section
# now edits it, saved through the staged engine check
# (content_set.py::_validate_weather_chances). fantasy_frontier, which plays
# the engine's own table, is the fixture.
#
#   godot --headless --path mud-world-editor --script tests/ruleset_weather_chances_smoke.gd

extends SceneTree

const Rules = preload("res://scripts/ui/modals/RulesetEditorDialog.gd")

var failures := 0


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var fixture := repo.path_join("tmp/ruleset-weather-chances-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	var rules_path := fixture.path_join("rules/ruleset.json")
	var before: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rules_path))

	var rules = Rules.new(); root.add_child(rules); rules.setup(); rules.open_active()
	var section: WeatherChancesSection = rules.weather_chances_section

	print("\n[opening a set that plays the engine's table]")
	_assert(not section.own_table.button_pressed and section.compose() == null and not section.changed(), "no table of its own: the switch is off and nothing would be written")
	_assert(_types(section, "summer") == ["clear", "cloudy", "rain", "storm"], "the engine's summer table is shown (%s)" % str(_types(section, "summer")))
	_assert(not (_rows(section, "summer")[0].get_node("Type") as LineEdit).editable, "read-only while the switch is off")
	_assert(rules.get_ok_button().disabled, "Save starts disabled")

	print("\n[a table of its own]")
	section.own_table.button_pressed = true
	_assert((_rows(section, "summer")[0].get_node("Type") as LineEdit).editable and not rules.get_ok_button().disabled, "ticking it makes the rows editable and enables Save")
	# Summer becomes clear or a heatwave; winter loses its snow.
	for row in _rows(section, "summer"):
		var weather_type := (row.get_node("Type") as LineEdit).text
		if weather_type in ["cloudy", "rain", "storm"]: (row.get_node("Remove") as Button).pressed.emit()
	section._add_row(section.season_rows["summer"], "heatwave", 3)
	(_row(section, "summer", "clear").get_node("Weight") as SpinBox).value = 1
	(_row(section, "winter", "snow").get_node("Remove") as Button).pressed.emit()

	# Emptying summer entirely is what the engine cannot survive: refused.
	var summer_rows := _rows(section, "summer")
	for row in summer_rows: (row.get_node("Type") as LineEdit).text = ""
	var bytes_before := FileAccess.get_file_as_string(rules_path)
	rules.confirmed.emit()
	_assert(FileAccess.get_file_as_string(rules_path) == bytes_before, "a table without summer is refused, nothing written")
	_assert("summer" in rules.status_label.text, "and the refusal says why: %s" % rules.status_label.text.left(160))
	(summer_rows[0].get_node("Type") as LineEdit).text = "clear"
	(summer_rows[1].get_node("Type") as LineEdit).text = "heatwave"

	rules.confirmed.emit()
	var after: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	var chances: Dictionary = after["weather"].get("chances", {})
	_assert(_same(chances.get("summer"), {"clear": 1, "heatwave": 3}), "summer is saved as authored (%s)" % JSON.stringify(chances.get("summer")))
	_assert(_same(chances.get("winter"), {"clear": 0.5, "cloudy": 0.3}) and _same(chances.get("spring"), WeatherChancesSection.DEFAULT_CHANCES["spring"]), "winter without snow; the untouched seasons keep the table they started from")
	_assert(_same(after["weather"]["profiles"], before["weather"]["profiles"]) and _same(after["weather"]["descriptions"], before["weather"]["descriptions"]), "profiles and descriptions are untouched")

	print("\n[back to the engine's]")
	rules.open_active()
	_assert(rules.weather_chances_section.own_table.button_pressed and _types(rules.weather_chances_section, "summer") == ["clear", "heatwave"], "reopening shows the saved table")
	rules.weather_chances_section.own_table.button_pressed = false
	rules.confirmed.emit()
	after = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	_assert(not after["weather"].has("chances"), "switching it off removes the table, so the engine's plays again")

	if failures > 0: push_error("ruleset weather chances smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _rows(section: WeatherChancesSection, season: String) -> Array:
	return section.season_rows[season].get_children()


func _row(section: WeatherChancesSection, season: String, weather_type: String) -> Node:
	for row in _rows(section, season):
		if (row.get_node("Type") as LineEdit).text == weather_type: return row
	return null


func _types(section: WeatherChancesSection, season: String) -> Array:
	var out: Array = []
	for row in _rows(section, season): out.append((row.get_node("Type") as LineEdit).text)
	return out


func _same(a, b) -> bool:
	return JSON.stringify(SaveIO._normalize_numbers(a)) == JSON.stringify(SaveIO._normalize_numbers(b))


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
