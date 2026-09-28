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
var hazard_list: VBoxContainer
var hazard_add_button: Button


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


static func _number(value) -> String:
	if (value is float or value is int) and float(value) == floor(float(value)): return str(int(value))
	return str(value)


func _build_hazard(parent: VBoxContainer) -> void:
	# A room may carry several hazards (engine/world/environment.py reads a
	# `hazards` list, each on its own clock). One hazard is still written with the
	# flat keys every existing room uses, so opening and saving a one-hazard room
	# changes nothing; a second one moves them all into the list.
	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.create_sub_header("Hazards"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	hazard_add_button = Button.new(); hazard_add_button.name = "AddHazard"; hazard_add_button.text = "+ Hazard"
	InspectorStyle.apply_button_style(hazard_add_button, Color(0.18, 0.31, 0.39))
	hazard_add_button.pressed.connect(_add_hazard)
	header.add_child(hazard_add_button); parent.add_child(header)
	hazard_list = VBoxContainer.new(); hazard_list.name = "HazardList"; hazard_list.add_theme_constant_override("separation", 8)
	parent.add_child(hazard_list)
	var hint := InspectorStyle.lbl("Damage and interval are optional overrides for this room; leave them at 0 to use the hazard's own values. Each hazard ticks on its own; defense (physical) or resistance (other channels) comes off each tick.", InspectorStyle.COLOR_TEXT_DIM)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; parent.add_child(hint)
	_refresh_hazards()


func _declared_hazard_ids() -> Array:
	return database_mgr.combat_vocabulary.hazard_ids() if database_mgr != null else []


## The room's hazards as a list of entries, whichever way the room wrote them.
func _hazard_entries() -> Array:
	var props := _properties()
	if props.get("hazards") is Array:
		var out: Array = []
		for entry in props["hazards"]:
			if entry is Dictionary: out.append(entry.duplicate(true))
		return out
	if str(props.get("hazard_type", "")) == "": return []
	var entry := {"type": str(props["hazard_type"])}
	if props.has("hazard_damage"): entry["damage"] = props["hazard_damage"]
	if props.has("hazard_tick_interval"): entry["tick_interval"] = props["hazard_tick_interval"]
	if props.get("weather_hazard_multipliers") is Dictionary: entry["weather_multipliers"] = props["weather_hazard_multipliers"].duplicate()
	return [entry]


func _write_hazards(entries: Array) -> void:
	var props := _properties()
	for key in ["hazards", "hazard_type", "hazard_damage", "hazard_tick_interval", "weather_hazard_multipliers"]: props.erase(key)
	if entries.size() == 1:
		var entry: Dictionary = entries[0]
		props["hazard_type"] = entry["type"]
		if entry.has("damage"): props["hazard_damage"] = entry["damage"]
		if entry.has("tick_interval"): props["hazard_tick_interval"] = entry["tick_interval"]
		if entry.get("weather_multipliers") is Dictionary and not entry["weather_multipliers"].is_empty(): props["weather_hazard_multipliers"] = entry["weather_multipliers"]
	elif entries.size() > 1:
		props["hazards"] = entries
	data_modified.emit()


func _refresh_hazards() -> void:
	if hazard_list == null: return
	for child in hazard_list.get_children(): hazard_list.remove_child(child); child.queue_free()
	var entries := _hazard_entries()
	var declared := _declared_hazard_ids()
	var used: Array = entries.map(func(e): return str(e.get("type", "")))
	hazard_add_button.disabled = declared.filter(func(id): return not used.has(str(id))).is_empty()
	hazard_add_button.tooltip_text = "Declare hazards in Combat Vocabulary before placing one." if declared.is_empty() else ("Every declared hazard is already here." if hazard_add_button.disabled else "Add another hazard to this room.")
	if entries.is_empty():
		hazard_list.add_child(InspectorStyle.lbl("No hazards.", InspectorStyle.COLOR_TEXT_DIM))
		return
	for index in entries.size():
		hazard_list.add_child(_hazard_card(index, entries[index], declared, used))


func _hazard_card(index: int, entry: Dictionary, declared: Array, used: Array) -> Control:
	var panel := PanelContainer.new(); panel.name = "HazardEntry%d" % index
	var style := StyleBoxFlat.new(); style.bg_color = Color(0.13, 0.13, 0.15); style.set_corner_radius_all(4)
	style.content_margin_left = 8; style.content_margin_right = 8; style.content_margin_top = 6; style.content_margin_bottom = 8
	panel.add_theme_stylebox_override("panel", style)
	var box := VBoxContainer.new(); box.add_theme_constant_override("separation", 6); panel.add_child(box)
	var current := str(entry.get("type", ""))

	var top := HBoxContainer.new(); top.add_theme_constant_override("separation", 6)
	var picker := OptionButton.new(); picker.name = "HazardPicker"; picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var selected := -1
	for hazard_id in declared:
		picker.add_item(str(hazard_id).replace("_", " ").capitalize()); picker.set_item_metadata(picker.item_count - 1, str(hazard_id))
		# One entry per hazard: a hazard already in the room is not offered twice.
		if str(hazard_id) != current and used.has(str(hazard_id)): picker.set_item_disabled(picker.item_count - 1, true)
		if str(hazard_id) == current: selected = picker.item_count - 1
	if selected < 0:
		picker.add_item("Missing: " + current); picker.set_item_metadata(picker.item_count - 1, current); selected = picker.item_count - 1
	picker.select(selected); InspectorStyle.apply_button_style(picker)
	picker.item_selected.connect(func(i): _update_hazard(index, func(e): e["type"] = str(picker.get_item_metadata(i)), true))
	top.add_child(picker)
	var remove := Button.new(); remove.name = "RemoveHazard"; remove.text = "×"; remove.tooltip_text = "Remove this hazard from the room"
	InspectorStyle.apply_button_style(remove, Color(0.34, 0.18, 0.18))
	remove.pressed.connect(func():
		var entries := _hazard_entries(); entries.remove_at(index); _write_hazards(entries); _refresh_hazards())
	top.add_child(remove); box.add_child(top)

	# 0 is "no override": environment.py::_override ignores a value of 0 or less
	# and uses the declared one. Damage is a whole number (the engine casts it);
	# a minimum of 0 keeps the step grid on whole values.
	var numbers := HBoxContainer.new(); numbers.name = "HazardOverrides"; numbers.add_theme_constant_override("separation", 6)
	numbers.add_child(InspectorStyle.lbl("Damage per tick", InspectorStyle.COLOR_TEXT_DIM))
	var damage := SpinBox.new(); damage.name = "HazardDamage"; damage.min_value = 0; damage.max_value = 9999; damage.step = 1; damage.value = float(entry.get("damage", 0)); damage.custom_minimum_size.x = 86; damage.tooltip_text = "Room-specific damage per tick (0: the hazard's own)"
	InspectorStyle.apply_input_style(damage)
	damage.value_changed.connect(func(value): _update_hazard(index, func(e): _set_override(e, "damage", int(value)), false))
	numbers.add_child(damage)
	numbers.add_child(InspectorStyle.lbl("  every", InspectorStyle.COLOR_TEXT_DIM))
	var tick := SpinBox.new(); tick.name = "HazardTickInterval"; tick.min_value = 0; tick.max_value = 9999; tick.step = 0.5; tick.value = float(entry.get("tick_interval", 0)); tick.custom_minimum_size.x = 86; tick.suffix = "s"; tick.tooltip_text = "Room-specific seconds between ticks (0: the hazard's own)"
	InspectorStyle.apply_input_style(tick)
	tick.value_changed.connect(func(value): _update_hazard(index, func(e): _set_override(e, "tick_interval", float(value)), false))
	numbers.add_child(tick); box.add_child(numbers)

	var defaults := InspectorStyle.lbl(_hazard_defaults_text(current), InspectorStyle.COLOR_TEXT_DIM); defaults.name = "HazardDefaults"
	box.add_child(defaults)

	var weather_header := HBoxContainer.new()
	weather_header.add_child(InspectorStyle.lbl("Weather multiplier", InspectorStyle.COLOR_TEXT_DIM))
	var weather_spacer := Control.new(); weather_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; weather_header.add_child(weather_spacer)
	var add_weather := Button.new(); add_weather.text = "+ Weather"; InspectorStyle.apply_button_style(add_weather, Color(0.18, 0.31, 0.39))
	add_weather.pressed.connect(func():
		_update_hazard(index, func(e):
			var multipliers: Dictionary = e.get("weather_multipliers", {}) if e.get("weather_multipliers") is Dictionary else {}
			var key := "weather"; var suffix := 2
			while multipliers.has(key): key = "weather_%d" % suffix; suffix += 1
			multipliers[key] = 1.0; e["weather_multipliers"] = multipliers, true))
	weather_header.add_child(add_weather); box.add_child(weather_header)
	var multipliers = entry.get("weather_multipliers", {})
	var weather_rows := VBoxContainer.new(); weather_rows.name = "HazardWeatherRows"; weather_rows.add_theme_constant_override("separation", 4)
	if not (multipliers is Dictionary) or multipliers.is_empty():
		weather_rows.add_child(InspectorStyle.lbl("No weather-specific adjustment.", InspectorStyle.COLOR_TEXT_DIM))
	else:
		for weather in multipliers.keys():
			var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
			var name_edit := LineEdit.new(); name_edit.text = str(weather); name_edit.placeholder_text = "Weather"; name_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(name_edit)
			name_edit.text_submitted.connect(func(value):
				var renamed := str(value).strip_edges()
				if renamed == "" or renamed == str(weather) or multipliers.has(renamed): return
				_update_hazard(index, func(e):
					var m: Dictionary = e["weather_multipliers"]; var v = m[weather]; m.erase(weather); m[renamed] = v, true))
			row.add_child(name_edit)
			var factor := SpinBox.new(); factor.min_value = 0.1; factor.max_value = 99; factor.step = 0.1; factor.value = float(multipliers[weather]); factor.custom_minimum_size.x = 82; InspectorStyle.apply_input_style(factor)
			factor.value_changed.connect(func(value): _update_hazard(index, func(e): e["weather_multipliers"][weather] = float(value), false))
			row.add_child(factor)
			var drop := Button.new(); drop.text = "×"; InspectorStyle.apply_button_style(drop, Color(0.34, 0.18, 0.18))
			drop.pressed.connect(func():
				_update_hazard(index, func(e):
					e["weather_multipliers"].erase(weather)
					if e["weather_multipliers"].is_empty(): e.erase("weather_multipliers"), true))
			row.add_child(drop); weather_rows.add_child(row)
	box.add_child(weather_rows)
	return panel


## Change one entry through `change`, write the list back, and redraw the cards
## when the change alters what they show (not for typed numbers, which would
## take the focus away mid-edit).
func _update_hazard(index: int, change: Callable, redraw: bool) -> void:
	var entries := _hazard_entries()
	if index < 0 or index >= entries.size(): return
	change.call(entries[index])
	_write_hazards(entries)
	if redraw: _refresh_hazards()


func _add_hazard() -> void:
	var entries := _hazard_entries()
	var used: Array = entries.map(func(e): return str(e.get("type", "")))
	for hazard_id in _declared_hazard_ids():
		if not used.has(str(hazard_id)):
			entries.append({"type": str(hazard_id)})
			_write_hazards(entries); _refresh_hazards()
			return


static func _set_override(entry: Dictionary, key: String, value) -> void:
	if float(value) <= 0: entry.erase(key)
	else: entry[key] = value


# What 0 means for this hazard: its declaration in combat/elements.json.
func _hazard_defaults_text(hazard_id: String) -> String:
	var record = database_mgr.combat_vocabulary.hazards.get(hazard_id) if database_mgr != null and hazard_id != "" else null
	if not record is Dictionary: return ""
	return "The hazard's own: %s %s damage every %s s." % [_number(record.get("damage", "?")), str(record.get("channel", "")), _number(record.get("tick_interval", "?"))]
