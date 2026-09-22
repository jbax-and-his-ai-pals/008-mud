# scripts/ui/inspectors/sub_inspectors/ItemInspector.gd

class_name ItemInspector
extends RefCounted

signal database_modified

# The engine's item classes (ItemFactory.ITEM_CLASS_MAP). The list used to offer
# "Tool" and "Material", which are not classes: a template with one of those as
# its `type` names no engine class, so ItemFactory refuses to build it and the
# item cannot exist in the game at all.
const ITEM_CLASSES := [
	"Item", "Weapon", "Armor", "Consumable", "Container", "Key", "Treasure",
	"Junk", "Gem", "Lockpick", "ResourceNode", "Interactive",
]

var container: VBoxContainer
var cur_data: Dictionary
var props_box: VBoxContainer
var database_mgr: DatabaseManager
var catalog: ContractCatalog


func build(c: VBoxContainer, data: Dictionary, db_mgr: DatabaseManager = null):
	container = c
	cur_data = data
	database_mgr = db_mgr
	catalog = db_mgr.catalog if db_mgr != null else null
	_build_details()
	_build_container()
	_build_resource_node()
	_build_salvage()
	_build_resistances()
	_build_contract()
	_build_properties()

# `properties.resistances` (`contracts/equipment.py::armor_resistances`; schema
# `contracts/registry.py:129`): per-damage-type resistance this item grants
# when worn. Had no editor control -- it is a map, so the generic property
# table only ever showed it read-only (`PropertyTagRow.build_nested_row`),
# alongside a note that a dedicated editor did not exist yet. Damage types
# come from this set's own combat vocabulary (`data/combat/elements.json`),
# the same source `CombatVocabularyDialog` authors it from, so the picker
# cannot offer a type nothing in this set recognizes.
func _build_resistances():
	if database_mgr == null or database_mgr.combat_vocabulary.damage_types.is_empty():
		return
	container.add_child(HSeparator.new())
	var header := HBoxContainer.new(); header.add_child(InspectorStyle.create_sub_header("Resistances"))
	header.tooltip_text = "Per-damage-type resistance this item grants when worn."
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = "+ Resistance"; InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var res := _ensure_resistances()
		var candidate := ""
		for type_id in database_mgr.combat_vocabulary.damage_types:
			if not res.has(type_id): candidate = str(type_id); break
		if candidate == "": return
		res[candidate] = 0.0
		database_modified.emit()
		_refresh_resistances(container.find_child("Resistances", true, false)))
	header.add_child(add); container.add_child(header)
	var rows := VBoxContainer.new(); rows.name = "Resistances"; rows.add_theme_constant_override("separation", 4)
	container.add_child(rows)
	_refresh_resistances(rows)

## Read-only: `properties.resistances` as it stands, without creating it.
func _resistances() -> Dictionary:
	var props := _properties()
	var res = props.get("resistances", {})
	return res if res is Dictionary else {}

## Made on the first write and not before.
func _ensure_resistances() -> Dictionary:
	if not (cur_data.get("properties") is Dictionary): cur_data["properties"] = {}
	if not (cur_data["properties"].get("resistances") is Dictionary): cur_data["properties"]["resistances"] = {}
	return cur_data["properties"]["resistances"]

func _refresh_resistances(rows: VBoxContainer):
	for child in rows.get_children(): child.queue_free()
	var res := _resistances()
	var keys := res.keys(); keys.sort()
	for damage_type_variant in keys:
		var current_type: String = str(damage_type_variant)
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)

		var picker := OptionButton.new(); picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var selected := -1
		for type_id in database_mgr.combat_vocabulary.damage_types:
			picker.add_item(str(type_id)); picker.set_item_metadata(picker.item_count - 1, str(type_id))
			if str(type_id) == current_type: selected = picker.item_count - 1
		if selected == -1:
			picker.add_item("Unknown: " + current_type); picker.set_item_metadata(picker.item_count - 1, current_type)
			selected = picker.item_count - 1
		picker.select(selected)
		InspectorStyle.apply_button_style(picker)
		picker.item_selected.connect(func(index):
			var live := _ensure_resistances()
			var new_type := str(picker.get_item_metadata(index))
			# The map is keyed by damage type, so picking a type already in use
			# would merge two resistances into one; refuse rather than lose one.
			if new_type == current_type or live.has(new_type):
				_refresh_resistances(rows)
				return
			var value = live[current_type]
			live.erase(current_type)
			live[new_type] = value
			database_modified.emit()
			_refresh_resistances(rows))
		row.add_child(picker)

		var value_field := SpinBox.new(); value_field.min_value = 0.0; value_field.max_value = 1.0; value_field.step = 0.01
		value_field.value = float(res.get(damage_type_variant, 0.0)); value_field.custom_minimum_size.x = 70
		InspectorStyle.apply_input_style(value_field)
		value_field.value_changed.connect(func(value):
			var live := _ensure_resistances()
			if live.has(current_type): live[current_type] = float(value)
			database_modified.emit())
		row.add_child(value_field)

		var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			var live := _ensure_resistances()
			live.erase(current_type)
			if live.is_empty() and cur_data.get("properties") is Dictionary: cur_data["properties"].erase("resistances")
			database_modified.emit()
			_refresh_resistances(rows))
		row.add_child(remove); rows.add_child(row)
	if keys.is_empty(): rows.add_child(InspectorStyle.lbl("None.", InspectorStyle.COLOR_TEXT_DIM))

func _build_details():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Details"))
	
	var card = InspectorStyle.create_card(); var vbox = card.get_child(0).get_child(0)
	container.add_child(card)
	
	# Type
	var hb = HBoxContainer.new()
	hb.add_child(InspectorStyle.lbl("Type:", InspectorStyle.COLOR_TEXT_DIM))
	var type_opt = OptionButton.new()
	var item_types := ITEM_CLASSES.duplicate()
	for t in item_types: type_opt.add_item(t)
	var current_type = str(cur_data.get("type", "Item"))
	var idx = item_types.find(current_type)
	if idx != -1: type_opt.selected = idx
	else:
		type_opt.add_item(current_type)
		type_opt.select(type_opt.item_count - 1)
	type_opt.item_selected.connect(func(i): cur_data["type"] = type_opt.get_item_text(i); database_modified.emit())
	# A template with a family resolves to the *family's* class
	# (item_class_for_template), so `type` is only the legacy fallback once a
	# family is named. Say that rather than letting an author edit a field that
	# no longer decides anything.
	if str(cur_data.get("item_family", "")) != "":
		type_opt.disabled = true
		type_opt.tooltip_text = "This template names a family, so the engine builds the family's class. Clear the family to edit this."
	else:
		type_opt.disabled = str(cur_data.get("type", "")) == "Gem"
	type_opt.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_button_style(type_opt)
	hb.add_child(type_opt)
	vbox.add_child(hb)
	
	# Weight & Value
	var hb2 = HBoxContainer.new()
	_add_spin_field(hb2, "Weight", "weight", 0.0)
	_add_spin_field(hb2, "Value", "value", 0)
	vbox.add_child(hb2)
	
	# Stackable
	var chk = CheckBox.new(); chk.text = "Stackable"
	chk.button_pressed = cur_data.get("stackable", false)
	chk.toggled.connect(func(b): cur_data["stackable"] = b; database_modified.emit())
	vbox.add_child(chk)


# Containers and resource nodes are both ordinary item templates at load time,
# but their nested properties are gameplay contracts.  Keeping them out of the
# generic property table means an author can create a usable chest or harvest
# point without knowing its JSON shape.
func _build_container():
	if _engine_item_class() != "Container":
		return
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Container"))
	var card := InspectorStyle.create_card()
	var vbox: VBoxContainer = card.get_child(0).get_child(0)
	container.add_child(card)
	var properties := _properties()
	var capacity_row := HBoxContainer.new(); capacity_row.add_child(InspectorStyle.lbl("Capacity", InspectorStyle.COLOR_TEXT_DIM))
	var capacity := SpinBox.new(); capacity.min_value = 0; capacity.max_value = 100000; capacity.step = 0.5; capacity.value = float(properties.get("capacity", 50.0)); capacity.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(capacity)
	capacity.value_changed.connect(func(value): properties["capacity"] = float(value); database_modified.emit())
	capacity_row.add_child(capacity); vbox.add_child(capacity_row)
	var state_row := HBoxContainer.new()
	var locked := CheckBox.new(); locked.text = "Locked"; locked.button_pressed = bool(properties.get("locked", false))
	locked.toggled.connect(func(pressed): properties["locked"] = pressed; database_modified.emit())
	state_row.add_child(locked)
	var open := CheckBox.new(); open.text = "Starts open"; open.button_pressed = bool(properties.get("is_open", false))
	open.toggled.connect(func(pressed): properties["is_open"] = pressed; database_modified.emit())
	state_row.add_child(open); vbox.add_child(state_row)
	var key_row := HBoxContainer.new(); key_row.add_child(InspectorStyle.lbl("Key template", InspectorStyle.COLOR_TEXT_DIM))
	var key_picker := _item_picker(str(properties.get("key_id", "")), "no key required")
	key_picker.item_selected.connect(func(index):
		var chosen := str(key_picker.get_item_metadata(index))
		if chosen == "": properties.erase("key_id")
		else: properties["key_id"] = chosen
		database_modified.emit()
	)
	key_row.add_child(key_picker); vbox.add_child(key_row)
	var contains: Array = properties.get("contains", []) if properties.get("contains", []) is Array else []
	var header := HBoxContainer.new(); header.add_child(InspectorStyle.create_sub_header("Starting contents"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = "+ Item"; InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func(): contains.append({"item_id": "", "quantity": 1}); properties["contains"] = contains; database_modified.emit(); _refresh_container_contents(vbox, properties))
	header.add_child(add); vbox.add_child(header)
	var rows := VBoxContainer.new(); rows.name = "ContainerContents"; rows.add_theme_constant_override("separation", 4); vbox.add_child(rows)
	_refresh_container_contents(vbox, properties)


func _refresh_container_contents(vbox: VBoxContainer, properties: Dictionary):
	var rows := vbox.get_node_or_null("ContainerContents")
	if rows == null: return
	for child in rows.get_children(): child.queue_free()
	var contains: Array = properties.get("contains", []) if properties.get("contains", []) is Array else []
	for index in range(contains.size()):
		if not (contains[index] is Dictionary): continue
		var entry: Dictionary = contains[index]
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
		var item_picker := _item_picker(str(entry.get("item_id", "")), "choose contained item")
		item_picker.item_selected.connect(func(selected): entry["item_id"] = str(item_picker.get_item_metadata(selected)); database_modified.emit())
		row.add_child(item_picker)
		var quantity := SpinBox.new(); quantity.min_value = 1; quantity.max_value = 999; quantity.step = 1; quantity.value = int(entry.get("quantity", 1)); quantity.custom_minimum_size.x = 72
		InspectorStyle.apply_input_style(quantity); quantity.value_changed.connect(func(value): entry["quantity"] = int(value); database_modified.emit())
		row.add_child(quantity)
		var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func(): contains.remove_at(index); if contains.is_empty(): properties.erase("contains") else: properties["contains"] = contains; database_modified.emit(); _refresh_container_contents(vbox, properties))
		row.add_child(remove); rows.add_child(row)
	if contains.is_empty(): rows.add_child(InspectorStyle.lbl("Empty when placed.", InspectorStyle.COLOR_TEXT_DIM))


func _build_resource_node():
	if _engine_item_class() != "ResourceNode":
		return
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Gathering resource"))
	var card := InspectorStyle.create_card()
	var vbox: VBoxContainer = card.get_child(0).get_child(0)
	container.add_child(card)
	var properties := _properties()
	var item_row := HBoxContainer.new(); item_row.add_child(InspectorStyle.lbl("Primary yield", InspectorStyle.COLOR_TEXT_DIM))
	var yield_picker := _item_picker(str(properties.get("resource_item_id", "")), "choose resource item")
	yield_picker.item_selected.connect(func(index): properties["resource_item_id"] = str(yield_picker.get_item_metadata(index)); database_modified.emit())
	item_row.add_child(yield_picker); vbox.add_child(item_row)
	var tool_row := HBoxContainer.new(); tool_row.add_child(InspectorStyle.lbl("Tool type", InspectorStyle.COLOR_TEXT_DIM))
	var tool := LineEdit.new(); tool.text = str(properties.get("tool_required", "")); tool.placeholder_text = "empty = no tool"; tool.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(tool)
	tool.text_changed.connect(func(text): var value := str(text).strip_edges(); if value == "": properties.erase("tool_required") else: properties["tool_required"] = value; database_modified.emit())
	tool_row.add_child(tool); vbox.add_child(tool_row)
	var numbers := HBoxContainer.new()
	for pair in [["Charges", "charges", 3], ["Respawn days", "respawn_days", 0]]:
		var field := VBoxContainer.new(); field.size_flags_horizontal = Control.SIZE_EXPAND_FILL; field.add_child(InspectorStyle.lbl(pair[0], InspectorStyle.COLOR_TEXT_DIM))
		var spin := SpinBox.new(); spin.min_value = 0; spin.max_value = 999; spin.step = 1; spin.value = int(properties.get(pair[1], pair[2])); InspectorStyle.apply_input_style(spin)
		spin.value_changed.connect(func(value): properties[pair[1]] = int(value); database_modified.emit())
		field.add_child(spin); numbers.add_child(field)
	vbox.add_child(numbers)
	var availability := HBoxContainer.new()
	var season_picker := MenuButton.new(); season_picker.text = _season_button_text(properties.get("seasons", [])); season_picker.tooltip_text = "Leave every season unchecked to make the node available year-round."
	InspectorStyle.apply_button_style(season_picker)
	var seasons := ["winter", "spring", "summer", "fall"]
	var selected_seasons: Array = properties.get("seasons", []) if properties.get("seasons", []) is Array else []
	var season_menu := season_picker.get_popup(); season_menu.hide_on_checkable_item_selection = false
	for season in seasons:
		season_menu.add_check_item(season.capitalize())
		season_menu.set_item_checked(season_menu.item_count - 1, selected_seasons.has(season))
	season_menu.index_pressed.connect(func(index):
		var season := str(seasons[index])
		if selected_seasons.has(season): selected_seasons.erase(season)
		else: selected_seasons.append(season)
		season_menu.set_item_checked(index, selected_seasons.has(season))
		if selected_seasons.is_empty(): properties.erase("seasons")
		else: properties["seasons"] = selected_seasons
		season_picker.text = _season_button_text(selected_seasons)
		database_modified.emit()
	)
	availability.add_child(InspectorStyle.lbl("Available", InspectorStyle.COLOR_TEXT_DIM)); availability.add_child(season_picker)
	var weather := LineEdit.new(); weather.text = ", ".join(_string_list(properties.get("weather_blocked_by", []))); weather.placeholder_text = "blocked weather, comma separated"; weather.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(weather)
	weather.text_changed.connect(func(text):
		var values := _split_csv(text)
		if values.is_empty(): properties.erase("weather_blocked_by")
		else: properties["weather_blocked_by"] = values
		database_modified.emit()
	)
	availability.add_child(weather); vbox.add_child(availability)
	var quality_header := HBoxContainer.new(); quality_header.add_child(InspectorStyle.create_sub_header("Material grade"))
	var quality_spacer := Control.new(); quality_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; quality_header.add_child(quality_spacer)
	var has_quality := CheckBox.new(); has_quality.text = "apply a grade"; has_quality.button_pressed = properties.get("material_quality") is Dictionary
	quality_header.add_child(has_quality); vbox.add_child(quality_header)
	var quality: Dictionary = properties.get("material_quality", {}) if properties.get("material_quality") is Dictionary else {}
	var quality_row := HBoxContainer.new(); quality_row.add_child(InspectorStyle.lbl("ID / label / score", InspectorStyle.COLOR_TEXT_DIM))
	var quality_id := LineEdit.new(); quality_id.text = str(quality.get("id", "")); quality_id.placeholder_text = "refined"; quality_id.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(quality_id)
	var quality_label := LineEdit.new(); quality_label.text = str(quality.get("label", "")); quality_label.placeholder_text = "Refined"; quality_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(quality_label)
	var quality_score := SpinBox.new(); quality_score.min_value = 1; quality_score.max_value = 99; quality_score.step = 1; quality_score.value = int(quality.get("score", 1)); quality_score.custom_minimum_size.x = 72; InspectorStyle.apply_input_style(quality_score)
	for control in [quality_id, quality_label, quality_score]: control.editable = has_quality.button_pressed
	quality_id.text_changed.connect(func(text): quality["id"] = str(text).strip_edges(); if has_quality.button_pressed: properties["material_quality"] = quality; database_modified.emit())
	quality_label.text_changed.connect(func(text): quality["label"] = str(text).strip_edges(); if has_quality.button_pressed: properties["material_quality"] = quality; database_modified.emit())
	quality_score.value_changed.connect(func(value): quality["score"] = int(value); if has_quality.button_pressed: properties["material_quality"] = quality; database_modified.emit())
	has_quality.toggled.connect(func(pressed):
		for control in [quality_id, quality_label, quality_score]: control.editable = pressed
		if pressed:
			if str(quality.get("id", "")) == "": quality["id"] = "refined"
			if str(quality.get("label", "")) == "": quality["label"] = "Refined"
			if int(quality.get("score", 0)) < 1: quality["score"] = 1
			properties["material_quality"] = quality
		else: properties.erase("material_quality")
		database_modified.emit()
	)
	quality_row.add_child(quality_id); quality_row.add_child(quality_label); quality_row.add_child(quality_score); vbox.add_child(quality_row)
	var substitute_header := HBoxContainer.new(); substitute_header.add_child(InspectorStyle.create_sub_header("Substitute resources"))
	var substitute_spacer := Control.new(); substitute_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; substitute_header.add_child(substitute_spacer)
	var add_substitute := Button.new(); add_substitute.text = "+ Substitute"; InspectorStyle.apply_button_style(add_substitute, Color(0.2, 0.3, 0.4))
	add_substitute.pressed.connect(func(): var values: Array = properties.get("substitute_resource_ids", []) if properties.get("substitute_resource_ids", []) is Array else []; values.append(""); properties["substitute_resource_ids"] = values; database_modified.emit(); _refresh_resource_references(vbox, properties))
	substitute_header.add_child(add_substitute); vbox.add_child(substitute_header)
	var substitute_rows := VBoxContainer.new(); substitute_rows.name = "ResourceSubstituteRows"; substitute_rows.add_theme_constant_override("separation", 4); vbox.add_child(substitute_rows)
	_refresh_resource_references(vbox, properties)
	var yield_header := HBoxContainer.new(); yield_header.add_child(InspectorStyle.create_sub_header("Alternate yields"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; yield_header.add_child(spacer)
	var add := Button.new(); add.text = "+ Yield"; InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func(): var yields: Array = properties.get("yield_table", []) if properties.get("yield_table", []) is Array else []; yields.append({"item_id": "", "chance": 0.1}); properties["yield_table"] = yields; database_modified.emit(); _refresh_yield_rows(vbox, properties))
	yield_header.add_child(add); vbox.add_child(yield_header)
	var rows := VBoxContainer.new(); rows.name = "ResourceYieldRows"; rows.add_theme_constant_override("separation", 4); vbox.add_child(rows)
	_refresh_yield_rows(vbox, properties)


func _refresh_yield_rows(vbox: VBoxContainer, properties: Dictionary):
	var rows := vbox.get_node_or_null("ResourceYieldRows")
	if rows == null: return
	for child in rows.get_children(): child.queue_free()
	var yields: Array = properties.get("yield_table", []) if properties.get("yield_table", []) is Array else []
	for index in range(yields.size()):
		if not (yields[index] is Dictionary): continue
		var entry: Dictionary = yields[index]
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
		var item_picker := _item_picker(str(entry.get("item_id", "")), "choose alternate item")
		item_picker.item_selected.connect(func(selected): entry["item_id"] = str(item_picker.get_item_metadata(selected)); database_modified.emit())
		row.add_child(item_picker)
		var chance := SpinBox.new(); chance.min_value = 0; chance.max_value = 1; chance.step = 0.05; chance.value = float(entry.get("chance", 0.1)); chance.custom_minimum_size.x = 90; chance.tooltip_text = "chance from 0 to 1"
		InspectorStyle.apply_input_style(chance); chance.value_changed.connect(func(value): entry["chance"] = float(value); database_modified.emit())
		row.add_child(chance)
		var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func(): yields.remove_at(index); if yields.is_empty(): properties.erase("yield_table") else: properties["yield_table"] = yields; database_modified.emit(); _refresh_yield_rows(vbox, properties))
		row.add_child(remove); rows.add_child(row)
	if yields.is_empty(): rows.add_child(InspectorStyle.lbl("The primary yield is guaranteed.", InspectorStyle.COLOR_TEXT_DIM))


func _refresh_resource_references(vbox: VBoxContainer, properties: Dictionary):
	var rows := vbox.get_node_or_null("ResourceSubstituteRows")
	if rows == null: return
	for child in rows.get_children(): child.queue_free()
	var values: Array = properties.get("substitute_resource_ids", []) if properties.get("substitute_resource_ids", []) is Array else []
	for index in range(values.size()):
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
		var picker := _item_picker(str(values[index]), "choose substitute item")
		picker.item_selected.connect(func(selected): values[index] = str(picker.get_item_metadata(selected)); properties["substitute_resource_ids"] = values; database_modified.emit())
		row.add_child(picker)
		var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func(): values.remove_at(index); if values.is_empty(): properties.erase("substitute_resource_ids") else: properties["substitute_resource_ids"] = values; database_modified.emit(); _refresh_resource_references(vbox, properties))
		row.add_child(remove); rows.add_child(row)
	if values.is_empty(): rows.add_child(InspectorStyle.lbl("No alternate source is suggested when this node is depleted.", InspectorStyle.COLOR_TEXT_DIM))


func _split_csv(text: String) -> Array:
	var values: Array = []
	for raw in text.split(","):
		var value := str(raw).strip_edges()
		if value != "" and not values.has(value): values.append(value)
	return values


func _string_list(value) -> Array:
	var values: Array = []
	if value is Array:
		for raw in value:
			var text := str(raw).strip_edges()
			if text != "": values.append(text)
	return values


func _season_button_text(value) -> String:
	var seasons := _string_list(value)
	return "Year-round" if seasons.is_empty() else ", ".join(seasons)


func _properties() -> Dictionary:
	if not cur_data.has("properties") or not (cur_data["properties"] is Dictionary): cur_data["properties"] = {}
	return cur_data["properties"]


func _engine_item_class() -> String:
	var family_id := str(cur_data.get("item_family", ""))
	if catalog != null and family_id != "" and catalog.has_family(family_id):
		return catalog.item_class_for_family(family_id)
	return str(cur_data.get("type", "Item"))


func _item_picker(current: String, placeholder: String) -> OptionButton:
	var picker := OptionButton.new(); picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	picker.add_item(placeholder); picker.set_item_metadata(0, "")
	var ids: Array = database_mgr.get_item_ids() if database_mgr != null else []
	for item_id in ids:
		var label := str(item_id)
		if database_mgr != null and database_mgr.items.get(item_id) is Dictionary:
			label = "%s — %s" % [str(database_mgr.items[item_id].get("name", item_id)), item_id]
		picker.add_item(label); picker.set_item_metadata(picker.item_count - 1, str(item_id))
		if str(item_id) == current: picker.select(picker.item_count - 1)
	if current != "" and picker.selected == 0:
		picker.add_item("Missing: " + current); picker.set_item_metadata(picker.item_count - 1, current); picker.select(picker.item_count - 1)
	InspectorStyle.apply_button_style(picker)
	return picker


# What this template *is*, to the contract system: the family the engine resolves
# its class and behaviour from, and the roll tables if it generates instances.
# These are the fields content validation checks and the loader reads, and until
# now the editor had no control for either of them.
# What this template breaks down into.
#
# Salvage is asked in three places, most specific first, and this is the most
# specific: the item's own answer beats the family rule in the ruleset, which
# beats the engine class rule. The property is a nested object, and the property
# editor below only offers string/number/bool/equip-slot rows -- so this was
# hand-written JSON, which is why eleven templates in the fantasy set were the
# only ones that could say "this is leather, not iron".
func _build_salvage():
	container.add_child(HSeparator.new())
	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.create_sub_header("Salvage"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var toggle := CheckBox.new()
	toggle.text = "declare its own output"
	InspectorStyle.apply_button_style(toggle)
	header.add_child(toggle)
	container.add_child(header)

	var hint := Label.new()
	hint.add_theme_font_size_override("font_size", 11)
	hint.modulate = Color(0.65, 0.68, 0.74)
	hint.text = "Leave this off and the ruleset's family rule answers instead."
	container.add_child(hint)

	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)

	if not cur_data.has("properties"): cur_data["properties"] = {}
	var properties: Dictionary = cur_data["properties"]
	var authored = properties.get("salvage_output")
	toggle.button_pressed = authored is Dictionary

	var row_holder := HBoxContainer.new()
	row_holder.add_theme_constant_override("separation", 6)
	row_holder.add_child(InspectorStyle.lbl("Breaks into:", InspectorStyle.COLOR_TEXT_DIM))
	vbox.add_child(row_holder)

	var rate_holder := HBoxContainer.new()
	rate_holder.add_theme_constant_override("separation", 6)
	rate_holder.add_child(InspectorStyle.lbl("Per unit of weight:", InspectorStyle.COLOR_TEXT_DIM))
	vbox.add_child(rate_holder)

	# The switch is what writes the property; the controls below edit the dict
	# that would be written, so turning it on is never a surprise.
	if not (authored is Dictionary):
		authored = {}
	var editor := ReferenceEditor.new()
	var _reference_row := editor.build(row_holder, authored, Callable(self, "_salvage_suggestions"))

	var rate := SpinBox.new()
	rate.min_value = 0.0; rate.max_value = 20.0; rate.step = 0.1
	rate.value = float(authored.get("quantity_per_weight", 1.0))
	rate.tooltip_text = "how much comes back per unit of the item's weight"
	rate.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(rate)
	rate.value_changed.connect(func(value):
		authored["quantity_per_weight"] = float(value)
		if toggle.button_pressed:
			properties["salvage_output"] = authored
		database_modified.emit()
	)
	rate_holder.add_child(rate)

	# Typing in either control is itself the decision; the switch only says
	# whether the template answers at all.
	editor.changed.connect(func():
		if toggle.button_pressed:
			properties["salvage_output"] = authored
		database_modified.emit()
	)
	toggle.toggled.connect(func(pressed):
		if pressed: properties["salvage_output"] = authored
		else: properties.erase("salvage_output")
		database_modified.emit()
	)


## Every `crafting_station_type` any item in this set already declares --
## the same scan `RecipeInspector._station_picker` does over `database_mgr.items`,
## so a recipe's station picker and this suggestion list can never name two
## different sets of stations.
func _station_type_suggestions() -> Array:
	var stations := {}
	if database_mgr != null:
		for item_id in database_mgr.items:
			var item = database_mgr.items[item_id]
			if not (item is Dictionary): continue
			var properties = item.get("properties", {})
			if not (properties is Dictionary): continue
			var station_id := str(properties.get("crafting_station_type", "")).strip_edges()
			if station_id != "": stations[station_id] = true
	var ids: Array = stations.keys(); ids.sort(); return ids


func _salvage_suggestions(kind: String) -> Array:
	match kind:
		"item_family":
			return catalog.family_ids() if catalog != null else []
		"capability":
			return catalog.capability_ids() if catalog != null else []
		_:
			return database_mgr.get_item_ids() if database_mgr != null else []


func _build_contract():
	if catalog == null or catalog.family_ids().is_empty():
		return
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Contract"))
	var card = InspectorStyle.create_card(); var vbox = card.get_child(0).get_child(0)
	container.add_child(card)

	var family_id := str(cur_data.get("item_family", ""))

	var family_row := HBoxContainer.new()
	family_row.add_child(InspectorStyle.lbl("Family:", InspectorStyle.COLOR_TEXT_DIM))
	var family_picker := OptionButton.new()
	family_picker.name = "FamilyPicker"
	family_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var family_ids: Array = ["(no family)"] + catalog.family_ids()
	for id in family_ids:
		family_picker.add_item(str(id))
		if str(id) == family_id:
			family_picker.select(family_picker.item_count - 1)
	if family_id == "":
		family_picker.select(0)
	InspectorStyle.apply_button_style(family_picker)
	family_picker.item_selected.connect(func(index):
		var chosen := str(family_ids[index])
		if chosen == "(no family)":
			cur_data.erase("item_family")
		else:
			cur_data["item_family"] = chosen
		database_modified.emit()
		_refresh_contract_summary()
	)
	family_row.add_child(family_picker)
	vbox.add_child(family_row)

	# Every generation profile in the set, plus the option of following the
	# family's own -- a template may override which tables it rolls on.
	var profile_row := HBoxContainer.new()
	profile_row.add_child(InspectorStyle.lbl("Roll tables:", InspectorStyle.COLOR_TEXT_DIM))
	var profile_picker := OptionButton.new()
	profile_picker.name = "ProfilePicker"
	profile_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var authored_profile := str(cur_data.get("generation_profile", ""))
	var profile_ids: Array = ["(family default)"] + catalog.profile_ids()
	for id in profile_ids:
		profile_picker.add_item(str(id))
		if str(id) == authored_profile:
			profile_picker.select(profile_picker.item_count - 1)
	if authored_profile == "":
		profile_picker.select(0)
	InspectorStyle.apply_button_style(profile_picker)
	profile_picker.item_selected.connect(func(index):
		var chosen := str(profile_ids[index])
		if chosen == "(family default)":
			cur_data.erase("generation_profile")
		else:
			cur_data["generation_profile"] = chosen
		database_modified.emit()
		_refresh_contract_summary()
	)
	profile_row.add_child(profile_picker)
	vbox.add_child(profile_row)

	var summary := Label.new()
	summary.name = "ContractSummary"
	summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	summary.add_theme_font_size_override("font_size", 11)
	vbox.add_child(summary)
	_refresh_contract_summary()

	if _rolls_instances():
		_build_generation_definition(vbox)


func _refresh_contract_summary():
	var summary := container.find_child("ContractSummary", true, false)
	if summary == null or not (summary is Label):
		return
	var lines: Array = []
	var family_id := str(cur_data.get("item_family", ""))
	if family_id == "":
		lines.append("No family: the engine builds this template's `type` and nothing else.")
	elif not catalog.has_family(family_id):
		lines.append("Family '%s' is not declared in this content set -- the loader will refuse it." % family_id)
	else:
		var engine_class := catalog.item_class_for_family(family_id)
		lines.append("Family makes the engine build: %s" % engine_class)
		if engine_class != str(cur_data.get("type", "")):
			lines.append("(its legacy `type` says %s; the family decides)" % str(cur_data.get("type", "")))
		var capabilities := catalog.family_capabilities(family_id)
		if not capabilities.is_empty():
			lines.append("capabilities: %s" % ", ".join(capabilities))
		var trailing: Array = []
		var icon := catalog.family_icon_style(family_id)
		if icon != "": trailing.append("icon: %s" % icon)
		var profile := _effective_profile()
		if profile != "": trailing.append("rolls on: %s" % profile)
		if not trailing.is_empty():
			lines.append("  |  ".join(trailing))
	summary.text = "\n".join(lines)


# The profile that will actually be used: the template's own if it names one,
# else the family's.
func _effective_profile() -> String:
	var authored := str(cur_data.get("generation_profile", ""))
	if authored != "": return authored
	return catalog.generation_profile_for_family(str(cur_data.get("item_family", "")))


func _rolls_instances() -> bool:
	var profile := _effective_profile()
	if profile == "": return false
	return catalog.family_capabilities(str(cur_data.get("item_family", ""))).has("generated_instance")


func _build_generation_definition(parent: VBoxContainer):
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Generated instances"))
	var card = InspectorStyle.create_card(); var vbox = card.get_child(0).get_child(0)
	container.add_child(card)
	var profile := _effective_profile()
	vbox.add_child(InspectorStyle.lbl(
		"This family rolls instances on '%s': each found one rolls its own bands." % profile,
		InspectorStyle.COLOR_TEXT_DIM))

	# Intrinsic rarity, from the profile's own bands. The list used to be the four
	# fantasy rarity names, which a set that names its bands differently could not
	# express at all.
	var rarity_ids := catalog.tier_ids(profile, "rarity_tiers")
	if not rarity_ids.is_empty():
		var rarity_row := HBoxContainer.new()
		rarity_row.add_child(InspectorStyle.lbl("Intrinsic rarity", InspectorStyle.COLOR_TEXT_DIM))
		var rarity := OptionButton.new(); rarity.name = "RarityPicker"; rarity.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var options: Array = ["(infer from value)"] + rarity_ids
		for rarity_id in options: rarity.add_item(str(rarity_id))
		var current_rarity := str(cur_data.get("rarity", "")).to_lower()
		var rarity_index := options.find(current_rarity)
		rarity.select(rarity_index if rarity_index >= 0 else 0)
		rarity.item_selected.connect(func(index):
			if index == 0: cur_data.erase("rarity")
			else: cur_data["rarity"] = str(options[index])
			database_modified.emit()
		)
		InspectorStyle.apply_button_style(rarity)
		rarity_row.add_child(rarity); vbox.add_child(rarity_row)

	var biases: Dictionary = cur_data.get("gem_generation", {})
	if not (biases is Dictionary):
		biases = {}
	if biases.is_empty():
		biases = {"size_bias": 0.0, "quality_bias": 0.0}
	_add_gem_bias(vbox, "Size tendency (this template)", "size_bias", biases, "Smaller ← → larger")
	_add_gem_bias(vbox, "Quality tendency (this template)", "quality_bias", biases, "Flawed ← → perfect")

func _add_gem_bias(parent: VBoxContainer, label: String, key: String, profile: Dictionary, hint: String):
	var group := VBoxContainer.new()
	var heading := HBoxContainer.new()
	heading.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var value_label := Label.new(); value_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT; value_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	heading.add_child(value_label); group.add_child(heading)
	var slider := HSlider.new(); slider.min_value = -2.0; slider.max_value = 2.0; slider.step = 0.5
	slider.value = float(profile.get(key, 0.0)); slider.tooltip_text = hint
	value_label.text = "%+.1f  %s" % [slider.value, hint]
	slider.value_changed.connect(func(value):
		profile[key] = value
		cur_data["gem_generation"] = profile
		value_label.text = "%+.1f  %s" % [value, hint]
		database_modified.emit()
	)
	group.add_child(slider); parent.add_child(group)

func _add_spin_field(parent, label, key, default):
	var vb = VBoxContainer.new(); vb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vb.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var sb = SpinBox.new(); sb.value = cur_data.get(key, default)
	sb.value_changed.connect(func(v): cur_data[key] = v; database_modified.emit())
	InspectorStyle.apply_input_style(sb)
	vb.add_child(sb); parent.add_child(vb)

func _build_properties():
	container.add_child(HSeparator.new())
	var hb = HBoxContainer.new()
	hb.add_child(InspectorStyle.create_sub_header("Item Properties"))
	var spacer = Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; hb.add_child(spacer)
	var btn_add = Button.new(); btn_add.text = "+ Prop"; InspectorStyle.apply_button_style(btn_add)
	
	var pp = PopupMenu.new()
	pp.add_item("String"); pp.add_item("Number"); pp.add_item("Bool"); pp.add_item("Equip Slot")
	pp.id_pressed.connect(_add_item_prop)
	btn_add.pressed.connect(func(): pp.position = Vector2i(btn_add.get_screen_position()) + Vector2i(0, 30); pp.popup())
	container.add_child(pp)
	
	hb.add_child(btn_add); container.add_child(hb)
	
	props_box = VBoxContainer.new(); props_box.add_theme_constant_override("separation", 6)
	container.add_child(props_box)
	
	if not cur_data.has("properties"): cur_data["properties"] = {}
	_refresh_props()

func _add_item_prop(id):
	var k = "new_prop"
	var v = ""
	if id == 1: v = 0
	elif id == 2: v = false
	elif id == 3: k = "equip_slot"; v = []
	cur_data.properties[k] = v
	database_modified.emit()
	_refresh_props()

func _refresh_props():
	for c in props_box.get_children(): c.queue_free()
	var props = cur_data.properties
	# These fields have a dedicated, lossless authoring surface above. Showing
	# them again as generic rows invites two conflicting edits and makes the
	# useful controls look like decoration.
	var specialized := ["salvage_output", "resistances"]
	if _engine_item_class() == "Container":
		specialized.append_array(["capacity", "locked", "key_id", "is_open", "contains"])
	if _engine_item_class() == "ResourceNode":
		specialized.append_array(["resource_item_id", "tool_required", "charges", "respawn_days", "yield_table", "substitute_resource_ids", "weather_blocked_by", "seasons", "material_quality"])
	for key in props:
		var val = props[key]
		if specialized.has(str(key)):
			continue
		# Objects and arrays cannot make a lossless trip through a LineEdit:
		# `str(value)` is GDScript debug syntax, not editable JSON. Keep them
		# visible but read-only until their dedicated item-property controls exist.
		# `equip_slot` is the one structured property this inspector owns.
		if key != "equip_slot" and not PropertyTagRow.is_inline_editable(val):
			props_box.add_child(PropertyTagRow.build_nested_row(
				str(key), val, "a dedicated item-property editor (not available here yet)"
			))
			continue
		var panel = PanelContainer.new()
		var style = StyleBoxFlat.new(); style.bg_color = Color(0.25, 0.25, 0.28); style.set_corner_radius_all(6)
		style.content_margin_left = 10; style.content_margin_right = 10; style.content_margin_top = 4; style.content_margin_bottom = 4
		panel.add_theme_stylebox_override("panel", style)
		
		var hb = HBoxContainer.new(); panel.add_child(hb)
		
		if key == "equip_slot":
			var l = Label.new(); l.text = "Equip Slots"; l.modulate = Color.CYAN; hb.add_child(l)
		else:
			var ed_k = LineEdit.new(); ed_k.text = key; ed_k.custom_minimum_size.x = 120
			InspectorStyle.apply_input_style(ed_k)
			ed_k.text_submitted.connect(func(t): 
				if t != key and not props.has(t):
					props[t] = val; props.erase(key); database_modified.emit(); _refresh_props()
			)
			hb.add_child(ed_k)
		
		var spacer = Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; hb.add_child(spacer)
		
		if key == "equip_slot" and typeof(val) == TYPE_ARRAY:
			var btn_slots = MenuButton.new(); btn_slots.text = "Select Slots..."
			if not val.is_empty(): btn_slots.text = ",".join(val)
			InspectorStyle.apply_button_style(btn_slots)
			var popup = btn_slots.get_popup()
			popup.hide_on_checkable_item_selection = false
			var slots = ["head", "body", "legs", "feet", "main_hand", "off_hand", "neck", "hands", "ring"]
			for s in slots:
				popup.add_check_item(s)
				popup.set_item_checked(popup.item_count-1, val.has(s))
			popup.index_pressed.connect(func(idx):
				var s_name = slots[idx]
				if val.has(s_name): val.erase(s_name)
				else: val.append(s_name)
				popup.set_item_checked(idx, val.has(s_name))
				btn_slots.text = ",".join(val) if not val.is_empty() else "Select Slots..."
				database_modified.emit()
			)
			hb.add_child(btn_slots)
		elif typeof(val) == TYPE_BOOL:
			var chk = CheckBox.new(); chk.button_pressed = val; chk.text = "True" if val else "False"
			chk.toggled.connect(func(b): props[key] = b; chk.text = "True" if b else "False"; database_modified.emit())
			hb.add_child(chk)
		elif typeof(val) == TYPE_FLOAT or typeof(val) == TYPE_INT:
			var sb = SpinBox.new(); sb.step = 0.1; sb.allow_greater = true; sb.allow_lesser = true
			sb.value = val; sb.custom_minimum_size.x = 80
			# SpinBox emits floats. Preserve authored integer fields so the number
			# gate does not later reject an editor-produced `2.0` for `2`.
			InspectorStyle.apply_input_style(sb); sb.value_changed.connect(func(v):
				props[key] = int(v) if typeof(val) == TYPE_INT else v
				database_modified.emit()
			)
			hb.add_child(sb)
		else:
			var ed_v = LineEdit.new(); ed_v.text = str(val); ed_v.custom_minimum_size.x = 150
			InspectorStyle.apply_input_style(ed_v); ed_v.text_changed.connect(func(t): props[key] = t; database_modified.emit())
			hb.add_child(ed_v)
			# `crafting_station_type` is the name a recipe's own station
			# picker matches against (`RecipeInspector._station_picker`) --
			# still free text (an author can name a station type nothing has
			# used yet), but offering the ones already in use catches the
			# typo that would otherwise silently make a station unreachable.
			if key == "crafting_station_type":
				InspectorStyle.add_suggestion_button(hb, ed_v, Callable(self, "_station_type_suggestions"))
			
		var btn_x = Button.new(); btn_x.text = "×"; btn_x.flat = true
		btn_x.add_theme_color_override("font_color", Color(0.6, 0.6, 0.6))
		btn_x.add_theme_color_override("font_hover_color", Color.RED)
		btn_x.pressed.connect(func(): props.erase(key); database_modified.emit(); _refresh_props())
		hb.add_child(btn_x)
		
		props_box.add_child(panel)
