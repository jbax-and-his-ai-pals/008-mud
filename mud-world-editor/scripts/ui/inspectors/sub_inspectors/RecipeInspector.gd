# scripts/ui/inspectors/sub_inspectors/RecipeInspector.gd
#
# Recipe authoring: `data/crafting/*.json`, the content behind every crafting
# bench, station and skill check in the game.
#
# It had no surface at all before this -- the editor could edit the items a recipe
# consumes and produces but not the recipe itself, so the one system that connects
# them had to be hand-written in JSON.
#
# The field list is the engine's (`engine/crafting/recipe.py` plus
# `engine/crafting/crafting_manager.py`): ingredients, quality tiers gated on
# crafts *and* material grade, familiarity milestones, station, and
# `requires_discovery`. Keys this inspector does not model are shown and kept, the
# same rule as everywhere else in the editor.

class_name RecipeInspector
extends RefCounted

signal database_modified

const ROW_LABEL_WIDTH := 150

# The tier fields with their own widgets; anything else on a tier is kept and
# shown as JSON.
const TIER_FIELDS := ["id", "label", "min_crafts", "value_multiplier"]

var container: VBoxContainer
var cur_data: Dictionary
var database_mgr: DatabaseManager
var ingredients_box: VBoxContainer
var tiers_box: VBoxContainer
var milestones_box: VBoxContainer
# Reference suggestions per kind, built once per build rather than per button
# press: `capability_ids()` walks every family, and a recipe may hold a dozen
# ingredients.
var cached_suggestions: Dictionary = {}


func _init(c: VBoxContainer, db_mgr: DatabaseManager):
	container = c
	database_mgr = db_mgr


func build(id: String, data: Dictionary):
	cur_data = data
	cached_suggestions.clear()
	container.add_child(InspectorStyle.create_section_header("RECIPE: %s" % id.to_upper(), Color(0.7, 0.85, 0.5)))

	_build_identity()
	_build_result()
	_build_ingredients()
	_build_quality_tiers()
	_build_milestones()
	_build_extras()


func _build_identity():
	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)

	vbox.add_child(InspectorStyle.lbl("Name (what the player sees):", InspectorStyle.COLOR_TEXT_DIM))
	var name_ed := LineEdit.new(); name_ed.text = str(cur_data.get("name", ""))
	InspectorStyle.apply_input_style(name_ed)
	name_ed.text_changed.connect(func(text): cur_data["name"] = text; database_modified.emit())
	vbox.add_child(name_ed)

	vbox.add_child(InspectorStyle.lbl("Aliases (what a player might type, comma separated):", InspectorStyle.COLOR_TEXT_DIM))
	var alias_ed := LineEdit.new()
	alias_ed.text = ", ".join(_as_string_list(cur_data.get("aliases", [])))
	alias_ed.placeholder_text = "posy, flowers, bouquet"
	InspectorStyle.apply_input_style(alias_ed)
	alias_ed.text_changed.connect(func(text):
		var aliases: Array = []
		for part in text.split(","):
			var trimmed: String = str(part).strip_edges()
			if trimmed != "": aliases.append(trimmed)
		if aliases.is_empty(): cur_data.erase("aliases")
		else: cur_data["aliases"] = aliases
		database_modified.emit()
	)
	vbox.add_child(alias_ed)

	vbox.add_child(InspectorStyle.lbl("Description:", InspectorStyle.COLOR_TEXT_DIM))
	var desc_ed := TextEdit.new(); desc_ed.custom_minimum_size.y = 54
	desc_ed.text = str(cur_data.get("description", ""))
	InspectorStyle.apply_input_style(desc_ed)
	desc_ed.text_changed.connect(func(): cur_data["description"] = desc_ed.text; database_modified.emit())
	vbox.add_child(desc_ed)


func _build_result():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Result"))
	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)

	var result_row := _row(vbox, "Creates item")
	var result_ed := LineEdit.new(); result_ed.text = str(cur_data.get("result_item_id", ""))
	result_ed.placeholder_text = "item template id this recipe makes"
	result_ed.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(result_ed)
	result_ed.text_changed.connect(func(text): _set_or_erase("result_item_id", text.strip_edges()))
	result_row.add_child(result_ed)
	InspectorStyle.add_suggestion_button(result_row, result_ed, func(): return database_mgr.get_item_ids())

	var quantity_row := _row(vbox, "Quantity")
	_add_spin(quantity_row, "result_quantity", 1, 1, 999)

	var station_row := _row(vbox, "Station required")
	var station_picker := _station_picker()
	station_picker.item_selected.connect(func(index):
		var selected := str(station_picker.get_item_metadata(index))
		cur_data["station_required"] = null if selected == "" else selected
		database_modified.emit()
	)
	station_row.add_child(station_picker)
	var station_hint := InspectorStyle.lbl("Choose a station type supplied by an item template; leave empty for handcrafting.", InspectorStyle.COLOR_TEXT_DIM)
	station_hint.add_theme_font_size_override("font_size", 11)
	vbox.add_child(station_hint)

	# `difficulty` has no default in the engine: absent means "derive it from the
	# result's value", which is what most recipes do. So it gets a switch rather
	# than a spin box that would write 0 on every recipe it touched.
	var difficulty_row := _row(vbox, "Skill check")
	var explicit := CheckBox.new()
	explicit.text = "authored difficulty"
	explicit.button_pressed = cur_data.has("difficulty") and cur_data.get("difficulty") != null
	var difficulty := SpinBox.new()
	difficulty.min_value = 0; difficulty.max_value = 100; difficulty.step = 1
	# `difficulty` may be absent, or present with no value; `int(x or 0)` would be
	# `int(true)` — GDScript's `or` is a bool, not Python's fallback.
	var authored_difficulty = cur_data.get("difficulty")
	difficulty.value = int(authored_difficulty) if (authored_difficulty is int or authored_difficulty is float) else 0
	difficulty.editable = explicit.button_pressed
	InspectorStyle.apply_input_style(difficulty)
	explicit.toggled.connect(func(pressed):
		difficulty.editable = pressed
		if pressed: cur_data["difficulty"] = int(difficulty.value)
		else: cur_data.erase("difficulty")
		database_modified.emit()
	)
	difficulty.value_changed.connect(func(value):
		if explicit.button_pressed: cur_data["difficulty"] = int(value); database_modified.emit()
	)
	difficulty_row.add_child(explicit)
	difficulty_row.add_child(difficulty)

	var discovery_row := _row(vbox, "Taught or found")
	var discovery := CheckBox.new()
	discovery.text = "requires discovery before it can be crafted"
	discovery.button_pressed = bool(cur_data.get("requires_discovery", false))
	discovery.toggled.connect(func(pressed):
		if pressed: cur_data["requires_discovery"] = true
		else: cur_data.erase("requires_discovery")
		database_modified.emit()
	)
	discovery_row.add_child(discovery)


func _build_ingredients():
	container.add_child(HSeparator.new())
	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.create_sub_header("Ingredients"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var add := Button.new(); add.text = "+ Ingredient"
	InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var list: Array = cur_data.get("ingredients", []) if cur_data.get("ingredients") is Array else []
		list.append({"item_id": "", "quantity": 1})
		cur_data["ingredients"] = list
		database_modified.emit()
		_refresh_ingredients()
	)
	header.add_child(add)
	container.add_child(header)

	ingredients_box = VBoxContainer.new()
	ingredients_box.add_theme_constant_override("separation", 4)
	container.add_child(ingredients_box)
	_refresh_ingredients()


func _refresh_ingredients():
	for child in ingredients_box.get_children(): child.queue_free()
	var ingredients: Array = cur_data.get("ingredients", []) if cur_data.get("ingredients") is Array else []
	if ingredients.is_empty():
		ingredients_box.add_child(InspectorStyle.lbl("Nothing yet -- a recipe with no ingredients cannot be crafted.", InspectorStyle.COLOR_TEXT_DIM))
		return
	for index in range(ingredients.size()):
		if not (ingredients[index] is Dictionary):
			continue
		var ingredient: Dictionary = ingredients[index]
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 6)

		# What this ingredient names -- an exact template, a family, or a
		# capability -- and the material-grade floor that goes with the rule
		# kinds. `ReferenceEditor` is the same control the item inspector's
		# salvage output uses, because it is the same authored shape.
		var editor := ReferenceEditor.new()
		editor.changed.connect(func(): database_modified.emit())
		editor.build(row, ingredient, Callable(self, "_suggestions_for"))

		var quantity := SpinBox.new()
		quantity.min_value = 1; quantity.max_value = 999; quantity.step = 1
		quantity.value = int(ingredient.get("quantity", 1))
		quantity.custom_minimum_size.x = 70
		InspectorStyle.apply_input_style(quantity)
		quantity.value_changed.connect(func(value): ingredient["quantity"] = int(value); database_modified.emit())
		row.add_child(quantity)

		# `quality_contributes` and `alternatives` are authored on a few recipes;
		# they are kept and editable as JSON rather than dropped.
		var extras: Array = []
		for key in ingredient:
			if key not in ["item_id", "item_family", "capability", "min_material_quality", "quantity"]:
				extras.append(key)
		if not extras.is_empty():
			var extras_ed := LineEdit.new()
			extras_ed.custom_minimum_size.x = 150
			extras_ed.tooltip_text = "extra fields: %s" % ", ".join(extras)
			var extra_values := {}
			for key in extras: extra_values[key] = ingredient[key]
			extras_ed.text = JSON.stringify(extra_values)
			InspectorStyle.apply_input_style(extras_ed)
			extras_ed.text_changed.connect(func(text):
				var parsed = JSON.parse_string(str(text).strip_edges())
				if typeof(parsed) != TYPE_DICTIONARY:
					extras_ed.modulate = Color(1.0, 0.6, 0.6)
					return
				extras_ed.modulate = Color.WHITE
				for key in extras: ingredient.erase(key)
				for key in parsed: ingredient[key] = parsed[key]
				database_modified.emit()
			)
			row.add_child(extras_ed)

		var remove := Button.new(); remove.text = "×"
		InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			ingredients.remove_at(index)
			if ingredients.is_empty(): cur_data.erase("ingredients")
			database_modified.emit()
			_refresh_ingredients()
		)
		row.add_child(remove)
		ingredients_box.add_child(row)


# Quality tiers are what the crafting command shows as a quality preview, and
# `craft_quality` quest objectives validate their ids against this list.
func _build_quality_tiers():
	container.add_child(HSeparator.new())
	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.create_sub_header("Quality tiers"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var add := Button.new(); add.text = "+ Tier"
	InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var tiers: Array = cur_data.get("quality_tiers", []) if cur_data.get("quality_tiers") is Array else []
		tiers.append({"id": "tier_%d" % (tiers.size() + 1), "label": "", "min_crafts": 1, "value_multiplier": 1.0})
		cur_data["quality_tiers"] = tiers
		database_modified.emit()
		_refresh_tiers()
	)
	header.add_child(add)
	container.add_child(header)

	var hint := Label.new()
	hint.text = "Reached after `min_crafts` crafts, or at a material grade if one is set."
	hint.add_theme_font_size_override("font_size", 11)
	hint.modulate = Color(0.65, 0.68, 0.74)
	container.add_child(hint)

	tiers_box = VBoxContainer.new()
	tiers_box.add_theme_constant_override("separation", 4)
	container.add_child(tiers_box)
	_refresh_tiers()


func _refresh_tiers():
	for child in tiers_box.get_children(): child.queue_free()
	var tiers: Array = cur_data.get("quality_tiers", []) if cur_data.get("quality_tiers") is Array else []
	for index in range(tiers.size()):
		if not (tiers[index] is Dictionary):
			continue
		var tier: Dictionary = tiers[index]
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 6)

		for field in ["id", "label"]:
			var line := LineEdit.new()
			line.text = str(tier.get(field, ""))
			line.placeholder_text = field
			line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			InspectorStyle.apply_input_style(line)
			line.text_changed.connect(func(text): tier[field] = str(text).strip_edges(); database_modified.emit())
			row.add_child(line)

		var crafts := SpinBox.new()
		crafts.min_value = 1; crafts.max_value = 9999; crafts.step = 1
		crafts.value = int(tier.get("min_crafts", 1))
		crafts.tooltip_text = "crafts needed"
		crafts.custom_minimum_size.x = 70
		InspectorStyle.apply_input_style(crafts)
		crafts.value_changed.connect(func(value): tier["min_crafts"] = int(value); database_modified.emit())
		row.add_child(crafts)

		var multiplier := SpinBox.new()
		multiplier.min_value = 0.0; multiplier.max_value = 100.0; multiplier.step = 0.05
		multiplier.value = float(tier.get("value_multiplier", 1.0))
		multiplier.tooltip_text = "value multiplier"
		multiplier.custom_minimum_size.x = 80
		InspectorStyle.apply_input_style(multiplier)
		multiplier.value_changed.connect(func(value): tier["value_multiplier"] = float(value); database_modified.emit())
		row.add_child(multiplier)

		var extras: Array = []
		for key in tier:
			if not TIER_FIELDS.has(str(key)):
				extras.append(key)
		if not extras.is_empty():
			var extras_ed := LineEdit.new()
			extras_ed.custom_minimum_size.x = 150
			extras_ed.tooltip_text = "extra fields: %s" % ", ".join(extras)
			var extra_values := {}
			for key in extras: extra_values[key] = tier[key]
			extras_ed.text = JSON.stringify(extra_values)
			InspectorStyle.apply_input_style(extras_ed)
			extras_ed.text_changed.connect(func(text):
				var parsed = JSON.parse_string(str(text).strip_edges())
				if typeof(parsed) != TYPE_DICTIONARY:
					extras_ed.modulate = Color(1.0, 0.6, 0.6)
					return
				extras_ed.modulate = Color.WHITE
				for key in extras: tier.erase(key)
				for key in parsed: tier[key] = parsed[key]
				database_modified.emit()
			)
			row.add_child(extras_ed)

		var remove := Button.new(); remove.text = "×"
		InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			tiers.remove_at(index)
			if tiers.is_empty(): cur_data.erase("quality_tiers")
			database_modified.emit()
			_refresh_tiers()
		)
		row.add_child(remove)
		tiers_box.add_child(row)


func _build_milestones():
	container.add_child(HSeparator.new())
	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.create_sub_header("Familiarity milestones"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var add := Button.new(); add.text = "+ Milestone"
	InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var list: Array = cur_data.get("familiarity_milestones", []) if cur_data.get("familiarity_milestones") is Array else []
		list.append({"count": 1, "label": "", "message": ""})
		cur_data["familiarity_milestones"] = list
		database_modified.emit()
		_refresh_milestones()
	)
	header.add_child(add)
	container.add_child(header)

	milestones_box = VBoxContainer.new()
	milestones_box.add_theme_constant_override("separation", 4)
	container.add_child(milestones_box)
	_refresh_milestones()


func _refresh_milestones():
	for child in milestones_box.get_children(): child.queue_free()
	var milestones: Array = cur_data.get("familiarity_milestones", []) if cur_data.get("familiarity_milestones") is Array else []
	for index in range(milestones.size()):
		if not (milestones[index] is Dictionary):
			continue
		var milestone: Dictionary = milestones[index]
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 6)

		var count := SpinBox.new()
		count.min_value = 1; count.max_value = 9999; count.step = 1
		count.value = int(milestone.get("count", 1))
		count.custom_minimum_size.x = 70
		count.tooltip_text = "crafts"
		InspectorStyle.apply_input_style(count)
		count.value_changed.connect(func(value): milestone["count"] = int(value); database_modified.emit())
		row.add_child(count)

		for field in ["label", "message"]:
			var line := LineEdit.new()
			line.text = str(milestone.get(field, ""))
			line.placeholder_text = field
			line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			InspectorStyle.apply_input_style(line)
			line.text_changed.connect(func(text): milestone[field] = text; database_modified.emit())
			row.add_child(line)

		var remove := Button.new(); remove.text = "×"
		InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			milestones.remove_at(index)
			if milestones.is_empty(): cur_data.erase("familiarity_milestones")
			database_modified.emit()
			_refresh_milestones()
		)
		row.add_child(remove)
		milestones_box.add_child(row)


func _build_extras():
	var known := ["name", "aliases", "description", "result_item_id", "result_quantity",
		"station_required", "difficulty", "requires_discovery", "ingredients",
		"quality_tiers", "familiarity_milestones"]
	var extras: Array = []
	for key in cur_data:
		if not known.has(str(key)):
			extras.append(key)
	extras.sort()
	if extras.is_empty():
		return
	var note := Label.new()
	note.text = "Other recipe fields (kept as authored): %s" % ", ".join(extras)
	note.add_theme_font_size_override("font_size", 11)
	note.modulate = Color(0.7, 0.72, 0.6)
	container.add_child(note)


# --- helpers ------------------------------------------------------------------

# Which reference-able values this recipe's content set knows, per kind. The
# families and capabilities come from the same contracts the engine reads, so a
# recipe cannot be offered a family the validator will then reject.
func _suggestions_for(kind: String) -> Array:
	if cached_suggestions.has(kind):
		return cached_suggestions[kind]
	var values: Array = []
	match kind:
		"item_family":
			values = database_mgr.catalog.family_ids()
		"capability":
			values = database_mgr.catalog.capability_ids()
		_:
			values = database_mgr.get_item_ids()
	cached_suggestions[kind] = values
	return values


# Stations are capabilities exposed by placed item templates, not recipe ids.
# Present the actual authored values so a recipe cannot quietly ask for a bench
# no item in the set can ever provide. An existing unknown value remains visible
# for repair instead of being silently erased.
func _station_picker() -> OptionButton:
	var picker := OptionButton.new()
	picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	picker.add_item("Handcrafting (no station)")
	picker.set_item_metadata(0, "")
	var stations := {}
	if database_mgr != null:
		for item_id in database_mgr.items:
			var item = database_mgr.items[item_id]
			if not (item is Dictionary): continue
			var properties = item.get("properties", {})
			if not (properties is Dictionary): continue
			var station_id := str(properties.get("crafting_station_type", "")).strip_edges()
			if station_id != "":
				stations[station_id] = str(item.get("name", item_id))
	var station_ids: Array = stations.keys(); station_ids.sort()
	var current := str(cur_data.get("station_required", "") if cur_data.get("station_required") != null else "")
	for station_id in station_ids:
		picker.add_item("%s — %s" % [str(stations[station_id]), str(station_id)])
		picker.set_item_metadata(picker.item_count - 1, station_id)
		if station_id == current: picker.select(picker.item_count - 1)
	if current != "" and picker.selected == 0:
		picker.add_item("Missing station: " + current)
		picker.set_item_metadata(picker.item_count - 1, current)
		picker.select(picker.item_count - 1)
	InspectorStyle.apply_button_style(picker)
	return picker


func _row(parent: VBoxContainer, label_text: String) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var label := InspectorStyle.lbl(label_text, InspectorStyle.COLOR_TEXT_DIM)
	label.custom_minimum_size.x = ROW_LABEL_WIDTH
	row.add_child(label)
	parent.add_child(row)
	return row


func _add_spin(row: HBoxContainer, key: String, default: int, minimum: int, maximum: int):
	var spin := SpinBox.new()
	spin.min_value = minimum; spin.max_value = maximum; spin.step = 1
	spin.value = int(cur_data.get(key, default))
	spin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(spin)
	spin.value_changed.connect(func(value): cur_data[key] = int(value); database_modified.emit())
	row.add_child(spin)


func _set_or_erase(key: String, value: String):
	if value == "": cur_data.erase(key)
	else: cur_data[key] = value
	database_modified.emit()


func _as_string_list(value) -> Array:
	if value is Array:
		var out: Array = []
		for entry in value:
			out.append(str(entry))
		return out
	return []
