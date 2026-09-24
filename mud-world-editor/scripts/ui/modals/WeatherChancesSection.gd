# scripts/ui/modals/WeatherChancesSection.gd
#
# The ruleset's `weather.chances` (weather_manager.py `_update_weather`),
# validated by content_set.py::_validate_weather_chances: per season, the
# weather types a weather change can roll and their weights. A set without its
# own table plays the engine's, shown here (read-only) so the author sees what
# play uses; ticking "own table" starts from it. Only a change is written, and
# keys this section does not own survive.

class_name WeatherChancesSection
extends RefCounted

# time_manager.py SEASONS and weather_manager.py DEFAULT_WEATHER_CHANCES;
# schema_parity_smoke.gd checks both against the engine.
const SEASONS := ["winter", "spring", "summer", "fall"]
const DEFAULT_CHANCES := {
	"spring": {"clear": 0.4, "cloudy": 0.3, "rain": 0.3, "storm": 0.1},
	"summer": {"clear": 0.6, "cloudy": 0.2, "rain": 0.1, "storm": 0.1},
	"fall": {"clear": 0.3, "cloudy": 0.4, "rain": 0.2, "storm": 0.1},
	"winter": {"clear": 0.5, "cloudy": 0.3, "snow": 0.2},
}

var on_change: Callable
var baseline = null
var own_table: CheckBox
var season_rows: Dictionary = {}
var add_buttons: Array = []


func build(box: VBoxContainer, changed: Callable) -> void:
	on_change = changed
	box.add_child(InspectorStyle.create_sub_header("Seasonal Weather"))
	var hint := InspectorStyle.lbl("Each weather change rolls a type from the season's table, by weight. A season left empty uses summer's, so summer is required. Weather types are this set's own words; give new ones a description above.", InspectorStyle.COLOR_TEXT_DIM)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(hint)
	own_table = CheckBox.new(); own_table.name = "OwnWeatherTable"; own_table.text = "This set has its own seasonal table (off: the engine's, shown below)"
	own_table.toggled.connect(func(_pressed): _set_editable(); _changed()); box.add_child(own_table)
	var grid := GridContainer.new(); grid.columns = 2; grid.add_theme_constant_override("h_separation", 16); box.add_child(grid)
	for season in SEASONS:
		var card := VBoxContainer.new(); card.name = "Season_" + season; card.size_flags_horizontal = Control.SIZE_EXPAND_FILL; grid.add_child(card)
		var head := HBoxContainer.new(); card.add_child(head)
		head.add_child(InspectorStyle.lbl(season.capitalize(), InspectorStyle.COLOR_ACCENT))
		var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; head.add_child(spacer)
		var rows := VBoxContainer.new(); rows.name = "Rows"; rows.add_theme_constant_override("separation", 3)
		var add := Button.new(); add.name = "AddWeather"; add.text = "+ Weather"; add.flat = true
		add.pressed.connect(func(): _add_row(rows, "", 1.0); _changed()); head.add_child(add); add_buttons.append(add)
		card.add_child(rows); season_rows[season] = rows


func load(ruleset: Dictionary) -> void:
	var weather = ruleset.get("weather", {})
	var chances = weather.get("chances", null) if weather is Dictionary else null
	baseline = chances.duplicate(true) if chances is Dictionary else null
	var own: bool = chances is Dictionary and not chances.is_empty()
	own_table.set_block_signals(true); own_table.button_pressed = own; own_table.set_block_signals(false)
	var table: Dictionary = chances if own else DEFAULT_CHANCES
	for season in SEASONS:
		var rows: VBoxContainer = season_rows[season]
		for child in rows.get_children(): rows.remove_child(child); child.queue_free()
		var entries = table.get(season, {})
		if entries is Dictionary:
			for weather_type in entries: _add_row(rows, str(weather_type), entries[weather_type])
	_set_editable()


# The table to write, or null for "use the engine's". Seasons and keys this
# section does not show (a misnamed season, a `_note`) are carried from the
# file as they were, so the engine check can name them rather than the editor
# dropping them unseen.
func compose():
	if not own_table.button_pressed: return null
	var out: Dictionary = {}
	if baseline is Dictionary:
		for key in baseline:
			if not SEASONS.has(str(key)): out[key] = baseline[key]
	for season in SEASONS:
		var entries: Dictionary = {}
		for row in season_rows[season].get_children():
			var weather_type := (row.get_node("Type") as LineEdit).text.strip_edges()
			if weather_type != "": entries[weather_type] = snappedf((row.get_node("Weight") as SpinBox).value, 0.01)
		if not entries.is_empty(): out[season] = entries
	return out


func changed() -> bool:
	var composed = compose()
	# An authored `{}` plays the engine's table, the same as no key at all.
	var had_own: bool = baseline is Dictionary and not baseline.is_empty()
	if composed == null: return had_own
	if baseline == null: return true
	return not _same(composed, baseline)


func _add_row(rows: VBoxContainer, weather_type: String, weight) -> void:
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 4)
	var field := LineEdit.new(); field.name = "Type"; field.text = weather_type; field.placeholder_text = "weather type"; field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(field); field.text_changed.connect(func(_t): _changed()); row.add_child(field)
	# A minimum of 0 keeps the 0.01 step grid on round values.
	var spin := SpinBox.new(); spin.name = "Weight"; spin.min_value = 0; spin.max_value = 1000; spin.step = 0.01
	spin.value = float(weight) if (weight is float or weight is int) else 0.0; spin.custom_minimum_size.x = 70
	InspectorStyle.apply_input_style(spin); spin.value_changed.connect(func(_v): _changed()); row.add_child(spin)
	var remove := Button.new(); remove.name = "Remove"; remove.text = "×"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
	remove.pressed.connect(func(): rows.remove_child(row); row.queue_free(); _changed()); row.add_child(remove)
	rows.add_child(row)
	_set_row_editable(row, own_table == null or own_table.button_pressed)


func _set_editable() -> void:
	var own := own_table.button_pressed
	for season in SEASONS:
		for row in season_rows[season].get_children(): _set_row_editable(row, own)
	for button in add_buttons: button.disabled = not own


func _set_row_editable(row: Node, editable: bool) -> void:
	(row.get_node("Type") as LineEdit).editable = editable
	(row.get_node("Weight") as SpinBox).editable = editable
	(row.get_node("Remove") as Button).disabled = not editable


static func _same(a, b) -> bool:
	return JSON.stringify(SaveIO._normalize_numbers(a)) == JSON.stringify(SaveIO._normalize_numbers(b))


func _changed() -> void:
	if on_change.is_valid(): on_change.call()
