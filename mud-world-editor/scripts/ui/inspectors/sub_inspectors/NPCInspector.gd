# scripts/ui/inspectors/sub_inspectors/NPCInspector.gd
#
# Track G item 5: the attribute rows come from the content set's own stat
# declaration, not from a list of eight fantasy names hard-coded here.
#
# The defect this replaced: `attr_keys` named strength, dexterity, constitution,
# agility, intelligence, wisdom, spell_power and magic_resist, always, for every
# content set. `orbital_salvage` declares six stats and `modern_capsule` declares
# none, so two of those rows offered to write a stat the set does not have --
# and the form built `cur_data["stats"] = {}` merely by being opened, which is a
# write nobody asked for. See `ContractCatalog`'s stat vocabulary for the
# precedence, which is the engine's.

class_name NPCInspector
extends RefCounted

signal database_modified

var container: VBoxContainer
var cur_data: Dictionary
var loot_box: VBoxContainer
# The catalog the manager already loaded, and the manager itself for the set's
# other NPCs -- which is where the vocabulary comes from when nothing is declared.
var catalog: ContractCatalog
var db_manager: DatabaseManager

func build(c: VBoxContainer, data: Dictionary, db_mgr: DatabaseManager = null):
	container = c
	cur_data = data
	db_manager = db_mgr
	catalog = db_mgr.catalog if db_mgr != null else ContractCatalog.new()
	_build_faction_and_behavior()
	_build_stats()
	_build_loot_table()

# Track G ledger, family C: `faction` and `behavior_type` were the two
# engine-owned vocabulary words on an NPC template with no editor control at
# all -- an NPC created here had no side and no AI routine, silently. Both are
# closed vocabularies (`NPCVocabulary.gd`, checked against the engine by
# `schema_parity_smoke.gd`), so both are pickers, not free text.
func _build_faction_and_behavior():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Faction & Behavior"))
	var card = InspectorStyle.create_card(); var vbox = card.get_child(0).get_child(0)
	container.add_child(card)

	var dispositions := NPCVocabulary.resolved_dispositions(NPCVocabulary.load_ruleset())
	var faction_ids := dispositions.keys(); faction_ids.sort()
	var current_faction := str(cur_data.get("faction", ""))

	var faction_row := HBoxContainer.new(); faction_row.add_child(InspectorStyle.lbl("Faction", InspectorStyle.COLOR_TEXT_DIM))
	var faction_picker := OptionButton.new(); faction_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	faction_picker.add_item("(none — bystander)"); faction_picker.set_item_metadata(0, "")
	var faction_selected := 0
	for faction_id in faction_ids:
		faction_picker.add_item("%s (%s)" % [faction_id, dispositions[faction_id]])
		faction_picker.set_item_metadata(faction_picker.item_count - 1, faction_id)
		if str(faction_id) == current_faction: faction_selected = faction_picker.item_count - 1
	if current_faction != "" and not dispositions.has(current_faction):
		faction_picker.add_item("Undeclared: " + current_faction); faction_picker.set_item_metadata(faction_picker.item_count - 1, current_faction)
		faction_selected = faction_picker.item_count - 1
	faction_picker.select(faction_selected)
	InspectorStyle.apply_button_style(faction_picker)
	faction_picker.item_selected.connect(func(index):
		var chosen := str(faction_picker.get_item_metadata(index))
		if chosen == "": cur_data.erase("faction")
		else: cur_data["faction"] = chosen
		database_modified.emit())
	faction_row.add_child(faction_picker); vbox.add_child(faction_row)

	var current_behavior := str(cur_data.get("behavior_type", ""))
	var behavior_row := HBoxContainer.new(); behavior_row.add_child(InspectorStyle.lbl("Behavior", InspectorStyle.COLOR_TEXT_DIM))
	var behavior_picker := OptionButton.new(); behavior_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	behavior_picker.add_item("(none — stands still)"); behavior_picker.set_item_metadata(0, "")
	var behavior_selected := 0
	for behavior in NPCVocabulary.BEHAVIOR_TYPES:
		behavior_picker.add_item(str(behavior).capitalize())
		behavior_picker.set_item_metadata(behavior_picker.item_count - 1, behavior)
		if str(behavior) == current_behavior: behavior_selected = behavior_picker.item_count - 1
	if current_behavior != "" and not NPCVocabulary.BEHAVIOR_TYPES.has(current_behavior):
		behavior_picker.add_item("Unknown: " + current_behavior); behavior_picker.set_item_metadata(behavior_picker.item_count - 1, current_behavior)
		behavior_selected = behavior_picker.item_count - 1
	behavior_picker.select(behavior_selected)
	InspectorStyle.apply_button_style(behavior_picker)
	behavior_picker.item_selected.connect(func(index):
		var chosen := str(behavior_picker.get_item_metadata(index))
		if chosen == "": cur_data.erase("behavior_type")
		else: cur_data["behavior_type"] = chosen
		database_modified.emit())
	behavior_row.add_child(behavior_picker); vbox.add_child(behavior_row)

func _build_stats():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Combat Stats"))
	
	var card = InspectorStyle.create_card(); var vbox = card.get_child(0).get_child(0)
	container.add_child(card)
	
	# Basic. `level`, authored starting `health`, and `max_mana` are engine keys.
	# The factory clamps starting health to the max derived from level/stats, so
	# this is not a misleading max-health override. Only labels come from content:
	# a set whose ability pool is Charge says Charge here.
	var hb_basic = HBoxContainer.new()
	vbox.add_child(hb_basic)
	_add_spin_field(hb_basic, "Level", "level", 1)
	_add_spin_field(hb_basic, "Starting " + _pool_label("vital", "Health"), "health", 10)
	_add_spin_field(hb_basic, _pool_label("ability", "Ability"), "max_mana", 0)
	
	# Attributes Grid: this content set's stats, and only those.
	var observed := _observed_stats()
	var vocabulary := catalog.stat_vocabulary(observed)
	if vocabulary.is_empty():
		# Better a sentence than rows the set does not speak. The author's next
		# step is the declaration, and this names the file it lives in.
		vbox.add_child(InspectorStyle.lbl(
			"This content set declares no stats, and none of its NPCs carry any yet. "
			+ "Declare `stats` in data/contracts/world_contracts.json to choose them.",
			InspectorStyle.COLOR_TEXT_DIM))
		return
	
	var header := InspectorStyle.lbl("Attributes:", InspectorStyle.COLOR_TEXT_DIM)
	header.tooltip_text = "Attribute rows come from %s." % catalog.stat_vocabulary_source(observed)
	vbox.add_child(header)

	var grid = GridContainer.new(); grid.columns = 2
	grid.add_theme_constant_override("h_separation", 20)
	vbox.add_child(grid)

	for stat in vocabulary:
		_add_stat_row(grid, str(stat).capitalize(), str(stat))

## The pool label this content set gives a resource kind, from its declaration.
func _pool_label(kind: String, fallback: String) -> String:
	return catalog.resource_label(kind, fallback)

## Every stat any NPC in this content set carries. Used only when the set declares
## no vocabulary: the rows then come from the set's own data rather than from an
## engine default nobody checked. The question belongs to the manager, which is
## what holds the NPCs.
func _observed_stats() -> Array:
	if db_manager == null:
		return []
	return db_manager.carried_stats()

## The stats dictionary as it stands, without creating one.
func _carried_stats() -> Dictionary:
	var carried = cur_data.get("stats", {})
	return carried if typeof(carried) == TYPE_DICTIONARY else {}


## The stats dictionary, made on the first write and not before.
func _ensure_stats() -> Dictionary:
	if typeof(cur_data.get("stats")) != TYPE_DICTIONARY:
		cur_data["stats"] = {}
	return cur_data["stats"]

func _add_spin_field(parent, label, key, default):
	var vb = VBoxContainer.new(); vb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vb.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var sb = SpinBox.new(); sb.value = cur_data.get(key, default)
	# `int()` because these are integer fields: a SpinBox emits a float, and a
	# float written into `level` is the int-to-float defect the number gate exists
	# to catch. Coercing here is cheaper than explaining it in a diff.
	sb.value_changed.connect(func(v): cur_data[key] = int(v); database_modified.emit())
	InspectorStyle.apply_input_style(sb)
	vb.add_child(sb); parent.add_child(vb)

func _add_stat_row(parent, label, key):
	var hb = HBoxContainer.new(); hb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var l = Label.new(); l.text = label; l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	hb.add_child(l)
	var carried = _carried_stats()
	var sb = SpinBox.new(); sb.value = carried.get(key, 0); sb.custom_minimum_size.x = 70
	sb.value_changed.connect(func(v):
		_ensure_stats()[key] = int(v)
		database_modified.emit())
	InspectorStyle.apply_input_style(sb)
	hb.add_child(sb)
	parent.add_child(hb)

func _build_loot_table():
	container.add_child(HSeparator.new())
	var hb = HBoxContainer.new()
	hb.add_child(InspectorStyle.create_sub_header("Loot Table"))
	var spacer = Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; hb.add_child(spacer)
	var btn_add = Button.new(); btn_add.text = "+ Drop"; InspectorStyle.apply_button_style(btn_add)
	btn_add.pressed.connect(_add_loot_entry)
	hb.add_child(btn_add); container.add_child(hb)
	
	loot_box = VBoxContainer.new(); loot_box.add_theme_constant_override("separation", 6)
	container.add_child(loot_box)
	
	if not cur_data.has("loot_table"): cur_data["loot_table"] = {}
	_refresh_loot_table()

func _refresh_loot_table():
	for c in loot_box.get_children(): c.queue_free()
	var table = cur_data.loot_table
	
	for item_id in table:
		var entry = table[item_id]
		var pc = PanelContainer.new()
		var style = StyleBoxFlat.new(); style.bg_color = Color(0.15, 0.15, 0.17); style.set_corner_radius_all(4)
		pc.add_theme_stylebox_override("panel", style)
		
		var m = MarginContainer.new(); m.add_theme_constant_override("margin_left", 5); m.add_theme_constant_override("margin_right", 5)
		pc.add_child(m)
		var hb = HBoxContainer.new(); m.add_child(hb)
		
		# Item ID / Gold
		var lbl_id = Label.new(); lbl_id.text = item_id
		if item_id == "gold_value": lbl_id.modulate = Color.GOLD
		lbl_id.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		hb.add_child(lbl_id)
		
		# Chance
		hb.add_child(InspectorStyle.lbl("Chance:", Color.GRAY))
		var sb_c = SpinBox.new(); sb_c.step = 0.05; sb_c.max_value = 1.0
		sb_c.value = entry.get("chance", 0.0)
		sb_c.custom_minimum_size.x = 60
		InspectorStyle.apply_input_style(sb_c)
		sb_c.value_changed.connect(func(v): entry["chance"] = v; database_modified.emit())
		hb.add_child(sb_c)
		
		# Qty (Range)
		var qty = entry.get("quantity", [1, 1])
		if typeof(qty) != TYPE_ARRAY: qty = [qty, qty]
		
		hb.add_child(InspectorStyle.lbl("Qty:", Color.GRAY))
		var sb_min = SpinBox.new(); sb_min.value = qty[0]; sb_min.custom_minimum_size.x = 50
		InspectorStyle.apply_input_style(sb_min)
		var sb_max = SpinBox.new(); sb_max.value = qty[1]; sb_max.custom_minimum_size.x = 50
		InspectorStyle.apply_input_style(sb_max)
		
		var update_qty = func(_v): entry["quantity"] = [sb_min.value, sb_max.value]; database_modified.emit()
		sb_min.value_changed.connect(update_qty)
		sb_max.value_changed.connect(update_qty)
		
		# Delete
		var btn_del = Button.new(); btn_del.text = "X"; btn_del.flat = true
		btn_del.pressed.connect(func(): table.erase(item_id); database_modified.emit(); _refresh_loot_table())
		hb.add_child(btn_del)
		
		loot_box.add_child(pc)

func _add_loot_entry():
	var popup = PopupMenu.new()
	popup.add_item("Item from DB")
	popup.add_item("Gold Value")
	popup.id_pressed.connect(func(id):
		if id == 1:
			cur_data.loot_table["gold_value"] = {"chance": 0.5, "quantity": [1, 10]}
		else:
			var k = "new_item_" + str(randi() % 100)
			cur_data.loot_table[k] = {"chance": 0.1, "quantity": [1, 1]}
		_refresh_loot_table()
		database_modified.emit()
	)
	container.add_child(popup)
	popup.position = Vector2i(container.get_global_mouse_position())
	popup.popup()
