# scripts/ui/inspectors/panels/RoomEnvironmentPanel.gd
#
# Environmental atmosphere is a room field in its own right.  It used to be
# visible only as a nested read-only property tag, which meant a new content set
# could declare hazards but could not place one without hand-writing JSON.

class_name RoomEnvironmentPanel
extends RefCounted

signal data_modified

var room: Dictionary
var database_mgr: DatabaseManager
var weather_rows: VBoxContainer
var hazard_value_controls: Array[Control] = []
var weather_add_button: Button


func build(parent: VBoxContainer, room_data: Dictionary, db_mgr: DatabaseManager) -> void:
	room = room_data
	database_mgr = db_mgr
	parent.add_child(InspectorStyle.create_section_header("ENVIRONMENT & HAZARDS", InspectorStyle.COLOR_ACCENT))
	var card := InspectorStyle.create_card()
	var box: VBoxContainer = card.get_child(0).get_child(0)
	box.add_theme_constant_override("separation", 7)
	parent.add_child(card)
	_build_atmosphere(box)
	box.add_child(HSeparator.new())
	_build_time_descriptions(box)
	box.add_child(HSeparator.new())
	_build_hazard(box)


func _build_atmosphere(parent: VBoxContainer) -> void:
	parent.add_child(InspectorStyle.create_sub_header("Atmosphere"))
	var env := _env()
	var toggles := HBoxContainer.new(); toggles.add_theme_constant_override("separation", 8)
	for pair in [["Dark", "dark"], ["Outdoors", "outdoors"], ["Windows", "has_windows"], ["Noisy", "noisy"]]:
		var check := CheckBox.new(); check.name = "Environment" + str(pair[1]).capitalize(); check.text = pair[0]
		check.button_pressed = bool(env.get(pair[1], false))
		check.toggled.connect(func(value): _set_env(str(pair[1]), value, false))
		toggles.add_child(check)
	parent.add_child(toggles)
	var details := HBoxContainer.new(); details.add_theme_constant_override("separation", 6)
	var smell := LineEdit.new(); smell.name = "EnvironmentSmell"; smell.text = str(env.get("smell", "")); smell.placeholder_text = "Smell (optional)"; smell.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(smell); smell.text_changed.connect(func(value): _set_env("smell", str(value).strip_edges(), ""))
	details.add_child(smell)
	var temperature := OptionButton.new(); temperature.name = "EnvironmentTemperature"; temperature.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for value in ["normal", "cold", "hot"]: temperature.add_item(value.capitalize()); temperature.set_item_metadata(temperature.item_count - 1, value)
	var current_temperature := str(env.get("temperature", "normal")); var selected := ["normal", "cold", "hot"].find(current_temperature)
	if selected < 0: temperature.add_item(current_temperature.capitalize()); temperature.set_item_metadata(temperature.item_count - 1, current_temperature); selected = temperature.item_count - 1
	temperature.select(selected); InspectorStyle.apply_button_style(temperature)
	temperature.item_selected.connect(func(index): _set_env("temperature", str(temperature.get_item_metadata(index)), "normal"))
	details.add_child(temperature); parent.add_child(details)


func _build_time_descriptions(parent: VBoxContainer) -> void:
	parent.add_child(InspectorStyle.create_sub_header("Time descriptions"))
	var descriptions := _time_descriptions()
	var grid := GridContainer.new(); grid.columns = 2; grid.add_theme_constant_override("h_separation", 8); grid.add_theme_constant_override("v_separation", 6)
	for period in ["dawn", "day", "dusk", "night"]:
		var field := VBoxContainer.new(); field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		field.add_child(InspectorStyle.lbl(period.capitalize(), InspectorStyle.COLOR_TEXT_DIM))
		var text := TextEdit.new(); text.name = "TimeDescription" + period.capitalize(); text.text = str(descriptions.get(period, "")); text.placeholder_text = "Optional description"; text.custom_minimum_size.y = 52; text.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
		InspectorStyle.apply_input_style(text)
		text.text_changed.connect(func(): _set_time_description(period, text.text.strip_edges()))
		field.add_child(text); grid.add_child(field)
	parent.add_child(grid)


func _build_hazard(parent: VBoxContainer) -> void:
	parent.add_child(InspectorStyle.create_sub_header("Hazard"))
	var props := _properties()
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
	var picker := OptionButton.new(); picker.name = "HazardPicker"; picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	picker.add_item("No hazard"); picker.set_item_metadata(0, "")
	var hazard_ids: Array = database_mgr.combat_vocabulary.hazard_ids() if database_mgr != null else []
	var current := str(props.get("hazard_type", "")); var selected := 0
	for hazard_id in hazard_ids:
		picker.add_item(str(hazard_id).replace("_", " ").capitalize()); picker.set_item_metadata(picker.item_count - 1, hazard_id)
		if str(hazard_id) == current: selected = picker.item_count - 1
	if current != "" and not hazard_ids.has(current):
		picker.add_item("Missing: " + current); picker.set_item_metadata(picker.item_count - 1, current); selected = picker.item_count - 1
	if hazard_ids.is_empty() and current == "": picker.tooltip_text = "Declare hazards in Combat Vocabulary before placing one."
	picker.select(selected); InspectorStyle.apply_button_style(picker)
	picker.item_selected.connect(func(index): _set_hazard(str(picker.get_item_metadata(index))))
	row.add_child(picker)
	var damage := SpinBox.new(); damage.name = "HazardDamage"; damage.min_value = 0.1; damage.max_value = 9999; damage.step = 0.5; damage.value = float(props.get("hazard_damage", 1.0)); damage.custom_minimum_size.x = 86; damage.tooltip_text = "Optional room-specific damage override"
	damage.editable = current != ""; InspectorStyle.apply_input_style(damage); damage.value_changed.connect(func(value): _set_hazard_number("hazard_damage", float(value)))
	row.add_child(damage)
	var tick := SpinBox.new(); tick.name = "HazardTickInterval"; tick.min_value = 0.1; tick.max_value = 9999; tick.step = 0.5; tick.value = float(props.get("hazard_tick_interval", 1.0)); tick.custom_minimum_size.x = 86; tick.tooltip_text = "Optional room-specific tick interval override"
	tick.editable = current != ""; InspectorStyle.apply_input_style(tick); tick.value_changed.connect(func(value): _set_hazard_number("hazard_tick_interval", float(value)))
	row.add_child(tick); parent.add_child(row)
	hazard_value_controls = [damage, tick]
	var hint := InspectorStyle.lbl("Choose a declared hazard. Damage and interval are optional per-room overrides.", InspectorStyle.COLOR_TEXT_DIM)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; parent.add_child(hint)
	var header := HBoxContainer.new(); header.add_child(InspectorStyle.create_sub_header("Weather multiplier"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	weather_add_button = Button.new(); weather_add_button.text = "+ Weather"; InspectorStyle.apply_button_style(weather_add_button, Color(0.18, 0.31, 0.39)); weather_add_button.disabled = current == ""
	weather_add_button.pressed.connect(func(): _add_weather_multiplier())
	header.add_child(weather_add_button); parent.add_child(header)
	weather_rows = VBoxContainer.new(); weather_rows.name = "HazardWeatherRows"; weather_rows.add_theme_constant_override("separation", 4); parent.add_child(weather_rows)
	_refresh_weather_rows()


func _refresh_weather_rows() -> void:
	if weather_rows == null: return
	for child in weather_rows.get_children(): child.queue_free()
	var multipliers = _properties().get("weather_hazard_multipliers", {})
	if not (multipliers is Dictionary) or multipliers.is_empty():
		weather_rows.add_child(InspectorStyle.lbl("No weather-specific adjustment.", InspectorStyle.COLOR_TEXT_DIM))
		return
	for weather in multipliers.keys():
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
		var name := LineEdit.new(); name.text = str(weather); name.placeholder_text = "Weather"; name.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(name)
		name.text_submitted.connect(func(value): _rename_weather_multiplier(str(weather), str(value).strip_edges()))
		row.add_child(name)
		var multiplier := SpinBox.new(); multiplier.min_value = 0.1; multiplier.max_value = 99; multiplier.step = 0.1; multiplier.value = float(multipliers[weather]); multiplier.custom_minimum_size.x = 82; InspectorStyle.apply_input_style(multiplier)
		multiplier.value_changed.connect(func(value): _set_weather_multiplier(str(weather), float(value)))
		row.add_child(multiplier)
		var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, Color(0.34, 0.18, 0.18))
		remove.pressed.connect(func(): _remove_weather_multiplier(str(weather)))
		row.add_child(remove); weather_rows.add_child(row)


func _env() -> Dictionary:
	var value = room.get("env_properties", {})
	return value if value is Dictionary else {}


func _properties() -> Dictionary:
	var value = room.get("properties", {})
	if not (value is Dictionary): room["properties"] = {}
	return room["properties"]


func _time_descriptions() -> Dictionary:
	var value = room.get("time_descriptions", {})
	return value if value is Dictionary else {}


func _set_time_description(period: String, value: String) -> void:
	var descriptions := _time_descriptions()
	if value == "": descriptions.erase(period)
	else: descriptions[period] = value
	if descriptions.is_empty(): room.erase("time_descriptions")
	else: room["time_descriptions"] = descriptions
	data_modified.emit()


func _set_env(key: String, value, default) -> void:
	var env := _env()
	if value == default: env.erase(key)
	else: env[key] = value
	if env.is_empty(): room.erase("env_properties")
	else: room["env_properties"] = env
	data_modified.emit()


func _set_hazard(hazard_id: String) -> void:
	var props := _properties()
	if hazard_id == "":
		for key in ["hazard_type", "hazard_damage", "hazard_tick_interval", "weather_hazard_multipliers"]: props.erase(key)
	else: props["hazard_type"] = hazard_id
	data_modified.emit()
	for control in hazard_value_controls: control.editable = hazard_id != ""
	if weather_add_button != null: weather_add_button.disabled = hazard_id == ""
	_refresh_weather_rows()


func _set_hazard_number(key: String, value: float) -> void:
	if str(_properties().get("hazard_type", "")) == "": return
	_properties()[key] = value
	data_modified.emit()


func _add_weather_multiplier() -> void:
	if str(_properties().get("hazard_type", "")) == "": return
	var multipliers: Dictionary = _properties().get("weather_hazard_multipliers", {}) if _properties().get("weather_hazard_multipliers", {}) is Dictionary else {}
	var key := "weather"
	var suffix := 2
	while multipliers.has(key): key = "weather_%d" % suffix; suffix += 1
	multipliers[key] = 1.0; _properties()["weather_hazard_multipliers"] = multipliers
	data_modified.emit(); _refresh_weather_rows()


func _set_weather_multiplier(weather: String, value: float) -> void:
	var multipliers: Dictionary = _properties().get("weather_hazard_multipliers", {}) if _properties().get("weather_hazard_multipliers", {}) is Dictionary else {}
	multipliers[weather] = value; _properties()["weather_hazard_multipliers"] = multipliers
	data_modified.emit()


func _rename_weather_multiplier(old: String, new: String) -> void:
	if new == "" or new == old: return
	var multipliers: Dictionary = _properties().get("weather_hazard_multipliers", {}) if _properties().get("weather_hazard_multipliers", {}) is Dictionary else {}
	if multipliers.has(new): return
	var value = multipliers.get(old); multipliers.erase(old); multipliers[new] = value
	_properties()["weather_hazard_multipliers"] = multipliers
	data_modified.emit(); _refresh_weather_rows()


func _remove_weather_multiplier(weather: String) -> void:
	var multipliers: Dictionary = _properties().get("weather_hazard_multipliers", {}) if _properties().get("weather_hazard_multipliers", {}) is Dictionary else {}
	multipliers.erase(weather)
	if multipliers.is_empty(): _properties().erase("weather_hazard_multipliers")
	else: _properties()["weather_hazard_multipliers"] = multipliers
	data_modified.emit(); _refresh_weather_rows()
