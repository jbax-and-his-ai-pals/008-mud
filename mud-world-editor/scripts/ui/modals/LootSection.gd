# scripts/ui/modals/LootSection.gd
#
# The ruleset's `loot` section (utils.py `_loot_take_hint`,
# items/chest_loot_generator.py, npcs/npc.py ambient pools), validated by
# content_set.py::_validate_loot_settings and _validate_ambient_loot_references.
# Only what the author changed is written; unknown keys survive, including
# unknown keys inside an ambient pool.

class_name LootSection
extends RefCounted

const SELECTORS := [
	["npc_template_ids", "Only these NPC templates"], ["npc_tags_any", "NPCs with any of these tags"],
	["npc_tags_all", "NPCs with all of these tags"], ["npc_tags_none", "but none of these tags"],
]

var on_change: Callable
var database: DatabaseManager
var baseline = null
var hint_on: CheckBox
var hint_text: LineEdit
var currency: OptionButton
var chest_rows: VBoxContainer
var pool_rows: VBoxContainer
var loaded := {}


func build(box: VBoxContainer, changed: Callable) -> void:
	on_change = changed
	box.add_child(InspectorStyle.create_sub_header("Loot"))
	var hint_row := HBoxContainer.new(); box.add_child(hint_row)
	hint_on = CheckBox.new(); hint_on.name = "TakeHintOn"; hint_on.text = "After a kill, hint at taking the loot:"; hint_on.toggled.connect(func(_v): _changed()); hint_row.add_child(hint_on)
	hint_text = LineEdit.new(); hint_text.name = "TakeHint"; hint_text.placeholder_text = "You can 'take' it.   ({items} and {count} are filled)"
	hint_text.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(hint_text); hint_text.text_changed.connect(func(_t): _changed()); hint_row.add_child(hint_text)
	var currency_row := HBoxContainer.new(); box.add_child(currency_row)
	currency_row.add_child(InspectorStyle.lbl("Coin item placed in chests", InspectorStyle.COLOR_TEXT_DIM))
	currency = OptionButton.new(); currency.name = "Currency"; currency.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_button_style(currency); currency.item_selected.connect(func(_i): _changed()); currency_row.add_child(currency)

	var chest_header := HBoxContainer.new(); box.add_child(chest_header)
	chest_header.add_child(InspectorStyle.lbl("Chest containers, plainest first (none: any Container)", InspectorStyle.COLOR_TEXT_DIM))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; chest_header.add_child(spacer)
	var add_chest := Button.new(); add_chest.name = "AddChest"; add_chest.text = "+ Chest"; InspectorStyle.apply_button_style(add_chest, InspectorStyle.COLOR_SUCCESS)
	add_chest.pressed.connect(func(): _add_chest(""); _changed()); chest_header.add_child(add_chest)
	chest_rows = VBoxContainer.new(); chest_rows.name = "ChestMaterials"; chest_rows.add_theme_constant_override("separation", 4); box.add_child(chest_rows)

	var pool_header := HBoxContainer.new(); box.add_child(pool_header)
	pool_header.add_child(InspectorStyle.lbl("Ambient drops: a chance per kill, from a weighted list, for the NPCs a pool selects", InspectorStyle.COLOR_TEXT_DIM))
	var pool_spacer := Control.new(); pool_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; pool_header.add_child(pool_spacer)
	var add_pool := Button.new(); add_pool.name = "AddPool"; add_pool.text = "+ Pool"; InspectorStyle.apply_button_style(add_pool, InspectorStyle.COLOR_SUCCESS)
	add_pool.pressed.connect(func(): _add_pool({"chance": 0.1, "entries": []}); _changed()); pool_header.add_child(add_pool)
	pool_rows = VBoxContainer.new(); pool_rows.name = "AmbientPools"; pool_rows.add_theme_constant_override("separation", 8); box.add_child(pool_rows)


func load(ruleset: Dictionary, db: DatabaseManager) -> void:
	database = db
	var loot = ruleset.get("loot", null)
	baseline = loot.duplicate(true) if loot is Dictionary else null
	var source: Dictionary = loot if loot is Dictionary else {}
	var hint = source.get("take_hint", null)
	# `false` switches the hint off; anything else (text, or absent) shows one.
	hint_on.set_pressed_no_signal(not (hint is bool and hint == false))
	hint_text.text = str(hint) if hint is String else ""
	var ids: Array = db.get_item_ids() if db != null else []
	QuestGenerationSection._fill_picker(currency, ids, {}, str(source.get("currency_item_id", "")) if source.get("currency_item_id") is String else "", "Automatic (an item typed as coin)")
	for child in chest_rows.get_children(): chest_rows.remove_child(child); child.queue_free()
	for material in (source.get("chest_materials", []) if source.get("chest_materials") is Array else []):
		_add_chest(str(material))
	for child in pool_rows.get_children(): pool_rows.remove_child(child); child.queue_free()
	for pool in (source.get("ambient_pools", []) if source.get("ambient_pools") is Array else []):
		if pool is Dictionary: _add_pool(pool)
	loaded = _parts()


## The whole `loot` section as it should be written, or {} for none.
func compose() -> Dictionary:
	var out: Dictionary = baseline.duplicate(true) if baseline is Dictionary else {}
	var now := _parts()
	if not _same(now["take_hint"], loaded["take_hint"]):
		if now["take_hint"] == null: out.erase("take_hint")
		else: out["take_hint"] = now["take_hint"]
	for key in ["currency_item_id", "chest_materials", "ambient_pools"]:
		if _same(now[key], loaded[key]): continue
		if now[key] == null or (now[key] is Array and now[key].is_empty()) or (now[key] is String and now[key] == ""): out.erase(key)
		else: out[key] = now[key]
	return out


func changed() -> bool:
	var before = baseline if baseline is Dictionary else {}
	return not _same(compose(), before)


func _parts() -> Dictionary:
	var hint = false
	if hint_on.button_pressed:
		hint = hint_text.text if hint_text.text.strip_edges() != "" else null
	var chests: Array = []
	for row in chest_rows.get_children():
		var picked := QuestGenerationSection._picked(row.get_node("Chest"))
		if picked != "": chests.append(picked)
	var pools: Array = []
	for card in pool_rows.get_children(): pools.append(_pool_of(card))
	return {"take_hint": hint, "currency_item_id": QuestGenerationSection._picked(currency), "chest_materials": chests, "ambient_pools": pools}


func _add_chest(item_id: String) -> void:
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
	var picker := OptionButton.new(); picker.name = "Chest"; picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	QuestGenerationSection._fill_picker(picker, _containers(), {}, item_id, "Choose a chest")
	InspectorStyle.apply_button_style(picker); picker.item_selected.connect(func(_i): _changed()); row.add_child(picker)
	for pair in [["^", -1], ["v", 1]]:
		var move := Button.new(); move.text = pair[0]; move.flat = true
		move.pressed.connect(func():
			var target := row.get_index() + int(pair[1])
			if target >= 0 and target < chest_rows.get_child_count(): chest_rows.move_child(row, target); _changed())
		row.add_child(move)
	var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
	remove.pressed.connect(func(): chest_rows.remove_child(row); row.queue_free(); _changed()); row.add_child(remove)
	chest_rows.add_child(row)


func _containers() -> Array:
	var out: Array = []
	if database == null: return out
	for item_id in database.items:
		if database.items[item_id] is Dictionary and str(database.items[item_id].get("type", "")) == "Container": out.append(str(item_id))
	out.sort()
	return out


func _add_pool(source: Dictionary) -> void:
	var card := VBoxContainer.new(); card.add_theme_constant_override("separation", 4); card.set_meta("source", source.duplicate(true))
	card.set_meta("row_kind", "AmbientPool")
	var head := HBoxContainer.new(); card.add_child(head)
	head.add_child(InspectorStyle.lbl("Chance per kill", InspectorStyle.COLOR_TEXT_DIM))
	var chance := SpinBox.new(); chance.name = "Chance"; chance.min_value = 0; chance.max_value = 1; chance.step = 0.01; chance.value = float(source.get("chance", 0.0))
	chance.custom_minimum_size.x = 80; InspectorStyle.apply_input_style(chance); chance.value_changed.connect(func(_v): _changed()); head.add_child(chance)
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; head.add_child(spacer)
	var remove := Button.new(); remove.text = "Remove Pool"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
	remove.pressed.connect(func(): pool_rows.remove_child(card); card.queue_free(); _changed()); head.add_child(remove)
	for spec in SELECTORS:
		var row := HBoxContainer.new(); card.add_child(row)
		row.add_child(InspectorStyle.lbl(str(spec[1]), InspectorStyle.COLOR_TEXT_DIM))
		var field := LineEdit.new(); field.name = str(spec[0]); field.placeholder_text = "comma-separated"; field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		field.text = QuestGenerationSection._joined(source.get(spec[0], [])); InspectorStyle.apply_input_style(field); field.text_changed.connect(func(_t): _changed()); row.add_child(field)
	var entries := VBoxContainer.new(); entries.name = "Entries"; card.add_child(entries)
	var add := Button.new(); add.name = "AddEntry"; add.text = "+ Drop"; add.flat = true
	add.pressed.connect(func(): _add_entry(entries, {"item_id": "", "weight": 1}); _changed()); card.add_child(add)
	for entry in (source.get("entries", []) if source.get("entries") is Array else []):
		if entry is Dictionary: _add_entry(entries, entry)
	card.add_child(HSeparator.new())
	pool_rows.add_child(card)


func _add_entry(entries: VBoxContainer, source: Dictionary) -> void:
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6); row.set_meta("source", source.duplicate(true))
	var id_field := LineEdit.new(); id_field.name = "Item"; id_field.text = str(source.get("item_id", "")); id_field.placeholder_text = "item id"; id_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(id_field); id_field.text_changed.connect(func(_t): _changed()); row.add_child(id_field)
	if database != null: InspectorStyle.add_suggestion_button(row, id_field, func(): return database.get_item_ids())
	row.add_child(InspectorStyle.lbl("weight", InspectorStyle.COLOR_TEXT_DIM))
	var spin := SpinBox.new(); spin.name = "Weight"; spin.min_value = 0; spin.max_value = 100000; spin.step = 0.01; spin.value = float(source.get("weight", 1))
	spin.custom_minimum_size.x = 70; InspectorStyle.apply_input_style(spin); spin.value_changed.connect(func(_v): _changed()); row.add_child(spin)
	var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
	remove.pressed.connect(func(): entries.remove_child(row); row.queue_free(); _changed()); row.add_child(remove)
	entries.add_child(row)


func _pool_of(card: Node) -> Dictionary:
	var pool: Dictionary = card.get_meta("source", {}).duplicate(true)
	pool["chance"] = snappedf((card.find_child("Chance", true, false) as SpinBox).value, 0.01)
	for spec in SELECTORS:
		var values := QuestGenerationSection._split((card.find_child(str(spec[0]), true, false) as LineEdit).text)
		if values.is_empty(): pool.erase(spec[0])
		else: pool[spec[0]] = values
	var entries: Array = []
	for row in card.get_node("Entries").get_children():
		var item_id := (row.get_node("Item") as LineEdit).text.strip_edges()
		if item_id == "": continue
		var entry: Dictionary = row.get_meta("source", {}).duplicate(true)
		entry["item_id"] = item_id; entry["weight"] = (row.get_node("Weight") as SpinBox).value
		entries.append(entry)
	pool["entries"] = entries
	return pool


static func _same(a, b) -> bool:
	return JSON.stringify(SaveIO._normalize_numbers(a)) == JSON.stringify(SaveIO._normalize_numbers(b))


func _changed() -> void:
	if on_change.is_valid(): on_change.call()
