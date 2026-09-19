# scripts/ui/inspectors/sub_inspectors/BackgroundInspector.gd
#
# Background authoring: `player/backgrounds.json` (`engine/core/backgrounds.py`),
# where a character begins -- a stat spread, a starting kit, and zero or more
# starting skills/recipes/spells. It replaced the class system and had no
# editor surface at all.
#
# Convention the engine's own docstring states and this inspector does not
# enforce (an author's call, not a structural rule): weapons start in the
# pack, armour is worn, so a new player's first `inventory` shows the weapon
# they own.

class_name BackgroundInspector
extends RefCounted

signal database_modified

const STAT_NAMES := ["strength", "dexterity", "constitution", "agility", "intelligence", "wisdom", "spell_power", "magic_resist"]

var container: VBoxContainer
var cur_data: Dictionary
var cur_id: String
var database_mgr: DatabaseManager
var equipment_box: VBoxContainer
var inventory_box: VBoxContainer
var skills_box: VBoxContainer
var recipes_box: VBoxContainer


func _init(c: VBoxContainer, db_mgr: DatabaseManager):
	container = c
	database_mgr = db_mgr


func build(id: String, data: Dictionary):
	cur_data = data
	cur_id = id
	container.add_child(InspectorStyle.create_section_header("BACKGROUND: %s" % id.to_upper(), Color(0.8, 0.7, 0.95)))
	_build_default_marker()
	_build_identity()
	_build_stats()
	_build_equipment()
	_build_inventory()
	_build_spells()
	_build_skills()
	_build_recipes()
	_build_gold()
	_build_extras()


func _rebuild():
	for child in container.get_children(): child.queue_free()
	build(cur_id, cur_data)


func _build_default_marker():
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 8)
	var is_default := database_mgr.backgrounds_default == cur_id
	var label := InspectorStyle.lbl("Default for new characters" if is_default else "Not the default", InspectorStyle.COLOR_TEXT_DIM if not is_default else Color(0.6, 0.9, 0.6))
	row.add_child(label)
	if not is_default:
		var make_default := Button.new(); make_default.text = "Make default"
		InspectorStyle.apply_button_style(make_default, Color(0.2, 0.3, 0.4))
		make_default.pressed.connect(func():
			database_mgr.set_default_background(cur_id)
			database_modified.emit()
			_rebuild()
		)
		row.add_child(make_default)
	container.add_child(row)


func _build_identity():
	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)

	vbox.add_child(InspectorStyle.lbl("Name:", InspectorStyle.COLOR_TEXT_DIM))
	var name_ed := LineEdit.new(); name_ed.text = str(cur_data.get("name", ""))
	InspectorStyle.apply_input_style(name_ed)
	name_ed.text_changed.connect(func(text): cur_data["name"] = text; database_modified.emit())
	vbox.add_child(name_ed)

	vbox.add_child(InspectorStyle.lbl("Description:", InspectorStyle.COLOR_TEXT_DIM))
	var desc_ed := TextEdit.new(); desc_ed.custom_minimum_size.y = 54
	desc_ed.text = str(cur_data.get("description", ""))
	InspectorStyle.apply_input_style(desc_ed)
	desc_ed.text_changed.connect(func(): cur_data["description"] = desc_ed.text; database_modified.emit())
	vbox.add_child(desc_ed)


func _build_stats():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Starting stats"))
	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)

	var stats = cur_data.get("stats")
	if not (stats is Dictionary):
		stats = {}
		cur_data["stats"] = stats

	var grid := GridContainer.new(); grid.columns = 2
	grid.add_theme_constant_override("h_separation", 10)
	grid.add_theme_constant_override("v_separation", 4)
	vbox.add_child(grid)
	for stat_name in STAT_NAMES:
		grid.add_child(InspectorStyle.lbl(stat_name.replace("_", " "), InspectorStyle.COLOR_TEXT_DIM))
		var spin := SpinBox.new(); spin.min_value = 0; spin.max_value = 100; spin.step = 1
		spin.value = int(stats.get(stat_name, 0))
		spin.custom_minimum_size.x = 90
		InspectorStyle.apply_input_style(spin)
		spin.value_changed.connect(func(value): stats[stat_name] = int(value); database_modified.emit())
		grid.add_child(spin)


func _build_equipment():
	container.add_child(HSeparator.new())
	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.create_sub_header("Worn equipment"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var add := Button.new(); add.text = "+ Slot"
	InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var equipment = cur_data.get("equipment")
		if not (equipment is Dictionary): equipment = {}
		# A blank key would collide with a second blank row (dictionaries have
		# one entry per key), so a fresh row gets a placeholder slot name an
		# author overwrites -- not the empty string every "+ Slot" click would
		# otherwise share.
		var key := "slot"; var n := 1
		while equipment.has(key): key = "slot_%d" % n; n += 1
		equipment[key] = ""
		cur_data["equipment"] = equipment
		database_modified.emit()
		_refresh_equipment()
	)
	header.add_child(add)
	container.add_child(header)

	equipment_box = VBoxContainer.new()
	equipment_box.add_theme_constant_override("separation", 4)
	container.add_child(equipment_box)
	_refresh_equipment()


func _refresh_equipment():
	for child in equipment_box.get_children(): child.queue_free()
	var equipment = cur_data.get("equipment")
	if not (equipment is Dictionary) or equipment.is_empty():
		equipment_box.add_child(InspectorStyle.lbl("None -- worn armour skips the lesson of drawing a weapon from inventory.", InspectorStyle.COLOR_TEXT_DIM))
		return
	for slot in equipment.keys():
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
		var slot_ed := LineEdit.new(); slot_ed.text = str(slot)
		slot_ed.placeholder_text = "slot (e.g. body)"
		slot_ed.custom_minimum_size.x = 100
		InspectorStyle.apply_input_style(slot_ed)
		var captured_slot := str(slot)
		var item_ed := LineEdit.new(); item_ed.text = str(equipment[slot])
		item_ed.placeholder_text = "item template id"
		item_ed.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_input_style(item_ed)
		slot_ed.text_submitted.connect(func(text):
			var new_slot := str(text).strip_edges()
			if new_slot == captured_slot: return
			var value = equipment[captured_slot]
			equipment.erase(captured_slot)
			equipment[new_slot] = value
			database_modified.emit()
			_refresh_equipment()
		)
		item_ed.text_changed.connect(func(text): equipment[captured_slot] = str(text).strip_edges(); database_modified.emit())
		row.add_child(slot_ed)
		row.add_child(item_ed)
		InspectorStyle.add_suggestion_button(row, item_ed, func(): return database_mgr.get_item_ids())
		var remove := Button.new(); remove.text = "×"
		InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			equipment.erase(captured_slot)
			if equipment.is_empty(): cur_data.erase("equipment")
			database_modified.emit()
			_refresh_equipment()
		)
		row.add_child(remove)
		equipment_box.add_child(row)


func _build_inventory():
	container.add_child(HSeparator.new())
	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.create_sub_header("Carried inventory"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var add := Button.new(); add.text = "+ Item"
	InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var list: Array = cur_data.get("inventory", []) if cur_data.get("inventory") is Array else []
		list.append({"item_id": "", "quantity": 1})
		cur_data["inventory"] = list
		database_modified.emit()
		_refresh_inventory()
	)
	header.add_child(add)
	container.add_child(header)

	inventory_box = VBoxContainer.new()
	inventory_box.add_theme_constant_override("separation", 4)
	container.add_child(inventory_box)
	_refresh_inventory()


func _refresh_inventory():
	for child in inventory_box.get_children(): child.queue_free()
	var inventory: Array = cur_data.get("inventory", []) if cur_data.get("inventory") is Array else []
	if inventory.is_empty():
		inventory_box.add_child(InspectorStyle.lbl("Nothing carried yet.", InspectorStyle.COLOR_TEXT_DIM))
		return
	for index in range(inventory.size()):
		if not (inventory[index] is Dictionary): continue
		var entry: Dictionary = inventory[index]
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
		var item_ed := LineEdit.new(); item_ed.text = str(entry.get("item_id", ""))
		item_ed.placeholder_text = "item template id"
		item_ed.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_input_style(item_ed)
		item_ed.text_changed.connect(func(text): entry["item_id"] = str(text).strip_edges(); database_modified.emit())
		row.add_child(item_ed)
		InspectorStyle.add_suggestion_button(row, item_ed, func(): return database_mgr.get_item_ids())

		var qty := SpinBox.new(); qty.min_value = 1; qty.max_value = 999; qty.step = 1
		qty.value = int(entry.get("quantity", 1))
		qty.custom_minimum_size.x = 70
		InspectorStyle.apply_input_style(qty)
		qty.value_changed.connect(func(value): entry["quantity"] = int(value); database_modified.emit())
		row.add_child(qty)

		var captured_index := index
		var remove := Button.new(); remove.text = "×"
		InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			inventory.remove_at(captured_index)
			if inventory.is_empty(): cur_data.erase("inventory")
			database_modified.emit()
			_refresh_inventory()
		)
		row.add_child(remove)
		inventory_box.add_child(row)


func _build_spells():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Starting abilities"))
	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)
	vbox.add_child(InspectorStyle.lbl("Ability ids, comma separated:", InspectorStyle.COLOR_TEXT_DIM))
	var spells_ed := LineEdit.new()
	spells_ed.text = ", ".join(_as_string_list(cur_data.get("spells", [])))
	spells_ed.placeholder_text = "magic_missile, minor_heal"
	InspectorStyle.apply_input_style(spells_ed)
	spells_ed.text_changed.connect(func(text):
		var spells := _split_list(text)
		if spells.is_empty(): cur_data.erase("spells")
		else: cur_data["spells"] = spells
		database_modified.emit()
	)
	vbox.add_child(spells_ed)
	InspectorStyle.add_suggestion_button(vbox, spells_ed, func(): return database_mgr.get_ids("magic"))


func _build_skills():
	container.add_child(HSeparator.new())
	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.create_sub_header("Starting skills"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var add := Button.new(); add.text = "+ Skill"
	InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var skills = cur_data.get("skills")
		if not (skills is Dictionary): skills = {}
		var key := "skill"; var n := 1
		while skills.has(key): key = "skill_%d" % n; n += 1
		skills[key] = 0
		cur_data["skills"] = skills
		database_modified.emit()
		_refresh_skills()
	)
	header.add_child(add)
	container.add_child(header)

	skills_box = VBoxContainer.new()
	skills_box.add_theme_constant_override("separation", 4)
	container.add_child(skills_box)
	_refresh_skills()


func _refresh_skills():
	for child in skills_box.get_children(): child.queue_free()
	var skills = cur_data.get("skills")
	if not (skills is Dictionary) or skills.is_empty():
		skills_box.add_child(InspectorStyle.lbl("None -- practising in play is enough to start any skill.", InspectorStyle.COLOR_TEXT_DIM))
		return
	for skill_name in skills.keys():
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
		var name_ed := LineEdit.new(); name_ed.text = str(skill_name)
		name_ed.placeholder_text = "skill name"
		name_ed.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_input_style(name_ed)
		var captured_name := str(skill_name)
		name_ed.text_submitted.connect(func(text):
			var new_name := str(text).strip_edges()
			if new_name == captured_name or new_name == "": return
			var value = skills[captured_name]
			skills.erase(captured_name)
			skills[new_name] = value
			database_modified.emit()
			_refresh_skills()
		)
		row.add_child(name_ed)

		var level := SpinBox.new(); level.min_value = 0; level.max_value = 20; level.step = 1
		level.value = int(skills[skill_name])
		level.custom_minimum_size.x = 70
		InspectorStyle.apply_input_style(level)
		level.value_changed.connect(func(value): skills[captured_name] = int(value); database_modified.emit())
		row.add_child(level)

		var remove := Button.new(); remove.text = "×"
		InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			skills.erase(captured_name)
			if skills.is_empty(): cur_data.erase("skills")
			database_modified.emit()
			_refresh_skills()
		)
		row.add_child(remove)
		skills_box.add_child(row)


func _build_recipes():
	container.add_child(HSeparator.new())
	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.create_sub_header("Starting recipes"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var add := Button.new(); add.text = "+ Recipe"
	InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var list: Array = _as_string_list(cur_data.get("recipes", []))
		list.append("")
		cur_data["recipes"] = list
		database_modified.emit()
		_refresh_recipes()
	)
	header.add_child(add)
	container.add_child(header)

	recipes_box = VBoxContainer.new()
	recipes_box.add_theme_constant_override("separation", 4)
	container.add_child(recipes_box)
	_refresh_recipes()


func _refresh_recipes():
	for child in recipes_box.get_children(): child.queue_free()
	var recipes: Array = _as_string_list(cur_data.get("recipes", []))
	if recipes.is_empty():
		recipes_box.add_child(InspectorStyle.lbl("None yet.", InspectorStyle.COLOR_TEXT_DIM))
		return
	for index in range(recipes.size()):
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
		var line := LineEdit.new(); line.text = str(recipes[index])
		line.placeholder_text = "recipe id"
		line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_input_style(line)
		var captured_index := index
		line.text_changed.connect(func(text):
			recipes[captured_index] = str(text).strip_edges()
			cur_data["recipes"] = recipes
			database_modified.emit()
		)
		row.add_child(line)
		InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_recipe_ids())
		var remove := Button.new(); remove.text = "×"
		InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			recipes.remove_at(captured_index)
			if recipes.is_empty(): cur_data.erase("recipes")
			else: cur_data["recipes"] = recipes
			database_modified.emit()
			_refresh_recipes()
		)
		row.add_child(remove)
		recipes_box.add_child(row)


func _build_gold():
	container.add_child(HSeparator.new())
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
	row.add_child(InspectorStyle.lbl("Starting gold", InspectorStyle.COLOR_TEXT_DIM))
	var gold := SpinBox.new(); gold.min_value = 0; gold.max_value = 100000; gold.step = 1
	gold.value = int(cur_data.get("starting_gold", 0))
	InspectorStyle.apply_input_style(gold)
	gold.value_changed.connect(func(value): cur_data["starting_gold"] = int(value); database_modified.emit())
	row.add_child(gold)
	container.add_child(row)


func _build_extras():
	var known := ["name", "description", "stats", "equipment", "inventory", "spells", "skills", "recipes", "starting_gold"]
	var extras: Array = []
	for key in cur_data:
		if not known.has(str(key)): extras.append(key)
	extras.sort()
	if extras.is_empty(): return
	var note := Label.new()
	note.text = "Other background fields (kept as authored): %s" % ", ".join(extras)
	note.add_theme_font_size_override("font_size", 11)
	note.modulate = Color(0.7, 0.72, 0.6)
	container.add_child(note)


func _as_string_list(value) -> Array:
	if value is Array:
		var out: Array = []
		for entry in value: out.append(str(entry))
		return out
	return []


func _split_list(text: String) -> Array:
	var out: Array = []
	for part in text.split(","):
		var trimmed: String = str(part).strip_edges()
		if trimmed != "": out.append(trimmed)
	return out
