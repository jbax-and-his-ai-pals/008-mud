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
	_build_dialogue_binding()
	_build_dialog_topics()
	_build_vendor_stock()
	_build_buy_orders()
	_build_stats()
	_build_gift_preferences()
	_build_loot_table()

## Made on the first write and not before -- shared by the vendor sections.
func _ensure_npc_properties() -> Dictionary:
	if not (cur_data.get("properties") is Dictionary):
		cur_data["properties"] = {}
	return cur_data["properties"]

func _npc_properties() -> Dictionary:
	var props = cur_data.get("properties", {})
	return props if props is Dictionary else {}

# `dialog` (`npc_factory.py:156`; `npc.py:85,124-125`): a flat topic -> reply
# map for `ask <npc> about <topic>`, independent of the graph above -- a hostile
# NPC with no dialogue graph can still answer a handful of topics. Had no
# editor control at all. The map is keyed by topic, so renaming one is a key
# rebuild (same shape as the loot table's item rename), refused on a collision
# rather than merging two topics' replies into one.
func _build_dialog_topics():
	container.add_child(HSeparator.new())
	var hb := HBoxContainer.new()
	hb.add_child(InspectorStyle.create_sub_header("Dialog Topics"))
	hb.tooltip_text = "Flat `ask <npc> about <topic>` replies -- independent of the dialogue graph above."
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; hb.add_child(spacer)
	var add := Button.new(); add.text = "+ Topic"; InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var dialog := _ensure_dialog()
		var key := "topic"; var n := 1
		while dialog.has(key): key = "topic_%d" % n; n += 1
		dialog[key] = ""
		database_modified.emit()
		_refresh_dialog_topics(container.get_node("DialogTopics")))
	hb.add_child(add); container.add_child(hb)
	var rows := VBoxContainer.new(); rows.name = "DialogTopics"; rows.add_theme_constant_override("separation", 4)
	container.add_child(rows)
	_refresh_dialog_topics(rows)

## Read-only: `dialog` as it stands, without creating it.
func _dialog() -> Dictionary:
	var d = cur_data.get("dialog", {})
	return d if d is Dictionary else {}

## Made on the first write and not before.
func _ensure_dialog() -> Dictionary:
	if not (cur_data.get("dialog") is Dictionary):
		cur_data["dialog"] = {}
	return cur_data["dialog"]

func _refresh_dialog_topics(rows: VBoxContainer):
	for child in rows.get_children(): child.queue_free()
	var dialog := _dialog()
	var topics := dialog.keys(); topics.sort()
	for topic_variant in topics:
		var current_topic: String = str(topic_variant)
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)

		var topic_field := LineEdit.new(); topic_field.text = current_topic; topic_field.custom_minimum_size.x = 120
		InspectorStyle.apply_input_style(topic_field)
		topic_field.text_submitted.connect(func(new_text: String):
			var live := _ensure_dialog()
			var new_key: String = new_text.strip_edges()
			if new_key == "" or new_key == current_topic or live.has(new_key):
				_refresh_dialog_topics(rows)
				return
			var value = live[current_topic]
			live.erase(current_topic)
			live[new_key] = value
			database_modified.emit()
			_refresh_dialog_topics(rows))
		row.add_child(topic_field)

		var text_field := LineEdit.new(); text_field.text = str(dialog[topic_variant]); text_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_input_style(text_field)
		text_field.text_changed.connect(func(new_text):
			var live := _ensure_dialog()
			if live.has(current_topic): live[current_topic] = new_text
			database_modified.emit())
		row.add_child(text_field)

		var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			var live := _ensure_dialog()
			live.erase(current_topic)
			if live.is_empty(): cur_data.erase("dialog")
			database_modified.emit()
			_refresh_dialog_topics(rows))
		row.add_child(remove)
		rows.add_child(row)
	if topics.is_empty(): rows.add_child(InspectorStyle.lbl("None.", InspectorStyle.COLOR_TEXT_DIM))

# `properties.dialogue` (`dialogue/manager.py::NPC_GRAPH_KEY`): which authored
# conversation graph this NPC uses. A graph an NPC binds to that does not exist
# is an orphan the gate catches (`content_set.py:1545-1549`), so the picker only
# offers graphs the set actually has -- and still shows an already-authored id
# that no longer resolves, rather than silently dropping it on the next save.
func _build_dialogue_binding():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Dialogue"))
	var card = InspectorStyle.create_card(); var vbox: VBoxContainer = card.get_child(0).get_child(0)
	container.add_child(card)

	var graph_ids: Array = (db_manager.dialogues.keys() if db_manager != null else [])
	graph_ids.sort()
	var current_graph := ""
	var props = cur_data.get("properties", {})
	if props is Dictionary:
		current_graph = str(props.get("dialogue", ""))

	var row := HBoxContainer.new(); row.add_child(InspectorStyle.lbl("Graph", InspectorStyle.COLOR_TEXT_DIM))
	var picker := OptionButton.new(); picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	picker.add_item("(none)"); picker.set_item_metadata(0, "")
	var selected := 0
	for graph_id in graph_ids:
		picker.add_item(str(graph_id)); picker.set_item_metadata(picker.item_count - 1, str(graph_id))
		if str(graph_id) == current_graph: selected = picker.item_count - 1
	if current_graph != "" and not graph_ids.has(current_graph):
		picker.add_item("Missing: " + current_graph); picker.set_item_metadata(picker.item_count - 1, current_graph)
		selected = picker.item_count - 1
	picker.select(selected)
	InspectorStyle.apply_button_style(picker)
	picker.item_selected.connect(func(index):
		var chosen := str(picker.get_item_metadata(index))
		if chosen == "":
			if cur_data.get("properties") is Dictionary: cur_data["properties"].erase("dialogue")
		else:
			if not (cur_data.get("properties") is Dictionary): cur_data["properties"] = {}
			cur_data["properties"]["dialogue"] = chosen
		database_modified.emit())
	row.add_child(picker); vbox.add_child(row)

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

# `properties.sells_items` (`mercantile.py:81-122`) and `sell_rate_multiplier`
# (`mercantile.py:68-70`): what this vendor sells outright, at what markup, and
# how generously it buys from the player. Unlike a buy order, a sold item is
# read only by `item_id` -- `_display_vendor_inventory` never asks for a family
# or a capability -- so this stays a plain item picker rather than the generic
# reference editor.
func _build_vendor_stock():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Vendor Stock"))
	var card = InspectorStyle.create_card(); var vbox: VBoxContainer = card.get_child(0).get_child(0)
	container.add_child(card)

	var rate_row := HBoxContainer.new(); rate_row.add_child(InspectorStyle.lbl("Buys from player at", InspectorStyle.COLOR_TEXT_DIM))
	var rate := SpinBox.new(); rate.min_value = 0.0; rate.max_value = 5.0; rate.step = 0.05
	rate.value = float(_npc_properties().get("sell_rate_multiplier", 0.4))
	rate.tooltip_text = "fraction of an item's value paid when the player sells to this vendor (engine default 0.4)"
	rate.custom_minimum_size.x = 70
	InspectorStyle.apply_input_style(rate)
	rate.value_changed.connect(func(value):
		_ensure_npc_properties()["sell_rate_multiplier"] = float(value)
		database_modified.emit())
	rate_row.add_child(rate); vbox.add_child(rate_row)

	var header := HBoxContainer.new(); header.add_child(InspectorStyle.create_sub_header("Sells"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = "+ Item"; InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var list := _sells_items().duplicate(true); list.append({"item_id": ""})
		_ensure_npc_properties()["sells_items"] = list
		database_modified.emit()
		_refresh_sells_items(container.find_child("SellsItems", true, false)))
	header.add_child(add); vbox.add_child(header)
	var rows := VBoxContainer.new(); rows.name = "SellsItems"; rows.add_theme_constant_override("separation", 4); vbox.add_child(rows)
	_refresh_sells_items(rows)

func _sells_items() -> Array:
	var list = _npc_properties().get("sells_items", [])
	return list if list is Array else []

func _refresh_sells_items(rows: VBoxContainer):
	for child in rows.get_children(): child.queue_free()
	var list := _sells_items()
	for index in range(list.size()):
		if not (list[index] is Dictionary): continue
		var entry: Dictionary = list[index]
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)

		var picker := _item_id_picker(str(entry.get("item_id", "")))
		picker.item_selected.connect(func(selected):
			entry["item_id"] = str(picker.get_item_metadata(selected))
			database_modified.emit())
		row.add_child(picker)

		row.add_child(InspectorStyle.lbl("×", InspectorStyle.COLOR_TEXT_DIM))
		var mult := SpinBox.new(); mult.min_value = 0.1; mult.max_value = 20.0; mult.step = 0.1
		mult.value = float(entry.get("price_multiplier", 2.0)); mult.custom_minimum_size.x = 70
		mult.tooltip_text = "sell price = item value × this (engine default 2.0)"
		InspectorStyle.apply_input_style(mult)
		mult.value_changed.connect(func(value): entry["price_multiplier"] = float(value); database_modified.emit())
		row.add_child(mult)

		row.add_child(InspectorStyle.lbl("Friendship ≥", InspectorStyle.COLOR_TEXT_DIM))
		var rel := SpinBox.new(); rel.min_value = 0; rel.max_value = 100; rel.step = 1
		rel.value = int(entry.get("relationship_min", 0)); rel.custom_minimum_size.x = 60
		InspectorStyle.apply_input_style(rel)
		rel.value_changed.connect(func(value): entry["relationship_min"] = int(value); database_modified.emit())
		row.add_child(rel)

		var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			var live: Array = _ensure_npc_properties().get("sells_items", [])
			if index < live.size(): live.remove_at(index)
			if live.is_empty(): _ensure_npc_properties().erase("sells_items")
			database_modified.emit()
			_refresh_sells_items(rows))
		row.add_child(remove); rows.add_child(row)
	if list.is_empty(): rows.add_child(InspectorStyle.lbl("Nothing for sale.", InspectorStyle.COLOR_TEXT_DIM))

# `properties.buy_orders` (`mercantile.py:153-155`; `content_set.py::
# _validate_vendor_orders`): delivery orders the player fulfills for a reward,
# independent of what this vendor sells outright. An order wants an item the
# same way a recipe ingredient does -- an exact template, a family, or a
# capability, with an optional material-grade floor -- so this reuses
# `ReferenceEditor`, the same control the item panel's salvage output uses.
func _build_buy_orders():
	container.add_child(HSeparator.new())
	var header := HBoxContainer.new(); header.add_child(InspectorStyle.create_sub_header("Buy Orders"))
	header.tooltip_text = "Delivery orders the player fulfills for a reward."
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = "+ Order"; InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var list := _buy_orders().duplicate(true)
		var existing_ids := {}
		for order in list:
			if order is Dictionary: existing_ids[str(order.get("id", ""))] = true
		var order_id := "order"; var n := 1
		while existing_ids.has(order_id): order_id = "order_%d" % n; n += 1
		list.append({"id": order_id, "quantity": 1, "reward_gold": 0})
		_ensure_npc_properties()["buy_orders"] = list
		database_modified.emit()
		_refresh_buy_orders(container.find_child("BuyOrders", true, false)))
	header.add_child(add); container.add_child(header)
	var rows := VBoxContainer.new(); rows.name = "BuyOrders"; rows.add_theme_constant_override("separation", 6)
	container.add_child(rows)
	_refresh_buy_orders(rows)

func _buy_orders() -> Array:
	var list = _npc_properties().get("buy_orders", [])
	return list if list is Array else []

func _refresh_buy_orders(rows: VBoxContainer):
	for child in rows.get_children(): child.queue_free()
	var list := _buy_orders()
	for index in range(list.size()):
		if not (list[index] is Dictionary): continue
		var order: Dictionary = list[index]
		var card := InspectorStyle.create_card(); var vbox: VBoxContainer = card.get_child(0).get_child(0)
		rows.add_child(card)

		var id_row := HBoxContainer.new(); id_row.add_theme_constant_override("separation", 6)
		id_row.add_child(InspectorStyle.lbl("ID", InspectorStyle.COLOR_TEXT_DIM))
		var id_field := LineEdit.new(); id_field.text = str(order.get("id", "")); id_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_input_style(id_field)
		id_field.text_submitted.connect(func(new_text: String):
			var live: Array = _ensure_npc_properties().get("buy_orders", [])
			var new_id: String = new_text.strip_edges()
			var collision := false
			for other_index in range(live.size()):
				if other_index != index and live[other_index] is Dictionary and str(live[other_index].get("id", "")) == new_id:
					collision = true
			if new_id == "" or collision:
				_refresh_buy_orders(rows)
				return
			if index < live.size() and live[index] is Dictionary: live[index]["id"] = new_id
			database_modified.emit()
			_refresh_buy_orders(rows))
		id_row.add_child(id_field)

		var remove := Button.new(); remove.text = "Remove Order"; InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			var live: Array = _ensure_npc_properties().get("buy_orders", [])
			if index < live.size(): live.remove_at(index)
			if live.is_empty(): _ensure_npc_properties().erase("buy_orders")
			database_modified.emit()
			_refresh_buy_orders(rows))
		id_row.add_child(remove)
		vbox.add_child(id_row)

		var ref_row := HBoxContainer.new(); ref_row.add_theme_constant_override("separation", 6)
		ref_row.add_child(InspectorStyle.lbl("Wants:", InspectorStyle.COLOR_TEXT_DIM))
		vbox.add_child(ref_row)
		var reference_editor := ReferenceEditor.new()
		var _reference_row := reference_editor.build(ref_row, order, Callable(self, "_buy_order_suggestions"))
		reference_editor.changed.connect(func(): database_modified.emit())

		var numbers := HBoxContainer.new(); numbers.add_theme_constant_override("separation", 12)
		vbox.add_child(numbers)

		numbers.add_child(InspectorStyle.lbl("Quantity", InspectorStyle.COLOR_TEXT_DIM))
		var qty := SpinBox.new(); qty.min_value = 1; qty.max_value = 999; qty.step = 1
		qty.value = int(order.get("quantity", 1)); qty.custom_minimum_size.x = 60
		InspectorStyle.apply_input_style(qty)
		qty.value_changed.connect(func(value): order["quantity"] = int(value); database_modified.emit())
		numbers.add_child(qty)

		numbers.add_child(InspectorStyle.lbl("Reward gold", InspectorStyle.COLOR_TEXT_DIM))
		var reward := SpinBox.new(); reward.min_value = 0; reward.max_value = 100000; reward.step = 1
		reward.value = int(order.get("reward_gold", 0)); reward.custom_minimum_size.x = 80
		InspectorStyle.apply_input_style(reward)
		reward.value_changed.connect(func(value): order["reward_gold"] = int(value); database_modified.emit())
		numbers.add_child(reward)

		var repeatable := CheckBox.new(); repeatable.text = "Repeatable"
		repeatable.button_pressed = bool(order.get("repeatable", false))
		repeatable.toggled.connect(func(pressed):
			if pressed: order["repeatable"] = true
			else: order.erase("repeatable")
			database_modified.emit())
		numbers.add_child(repeatable)

		var crafted_only := CheckBox.new(); crafted_only.text = "Crafted only"
		crafted_only.button_pressed = bool(order.get("crafted_only", false))
		crafted_only.toggled.connect(func(pressed):
			if pressed: order["crafted_only"] = true
			else: order.erase("crafted_only")
			database_modified.emit())
		numbers.add_child(crafted_only)
	if list.is_empty(): rows.add_child(InspectorStyle.lbl("No buy orders.", InspectorStyle.COLOR_TEXT_DIM))

func _buy_order_suggestions(kind: String) -> Array:
	match kind:
		"item_family": return catalog.family_ids() if catalog != null else []
		"capability": return catalog.capability_ids() if catalog != null else []
		_: return db_manager.get_item_ids() if db_manager != null else []

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

# `properties.gift_preferences` (`use_give.py::_gift_affinity`): five lists
# nothing authored before this -- an NPC could be given anything and never show
# a preference, because the shape existed only in the reader. Two are item-id
# lists (reuses the loot table's picker), three are free-text tag lists (item
# `category` and `gift_tags` are open vocabularies, not engine-closed ones, so
# these stay text fields rather than pickers).
const _GIFT_ITEM_LISTS := [["preferred_item_ids", "Preferred items"], ["disliked_item_ids", "Disliked items"]]
const _GIFT_TEXT_LISTS := [
	["preferred_categories", "Preferred categories", "matches an item's `category` property"],
	["preferred_gift_tags", "Preferred gift tags", "matches a tag in an item's `gift_tags`"],
	["disliked_gift_tags", "Disliked gift tags", "matches a tag in an item's `gift_tags`"],
]

func _build_gift_preferences():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Gift Preferences"))
	var card = InspectorStyle.create_card(); var vbox: VBoxContainer = card.get_child(0).get_child(0)
	container.add_child(card)
	for spec in _GIFT_ITEM_LISTS:
		_build_gift_item_list(vbox, str(spec[0]), str(spec[1]))
	for spec in _GIFT_TEXT_LISTS:
		_build_gift_text_list(vbox, str(spec[0]), str(spec[1]), str(spec[2]))

## Read-only: `properties.gift_preferences` as it stands, without creating
## `properties` or `gift_preferences` merely by looking at them.
func _gift_preferences() -> Dictionary:
	var props = cur_data.get("properties", {})
	if not (props is Dictionary):
		return {}
	var prefs = props.get("gift_preferences", {})
	return prefs if prefs is Dictionary else {}

## Made on the first write and not before -- the same rule `_ensure_stats()`
## follows, so opening an NPC with no gift preferences writes none.
func _ensure_gift_preferences() -> Dictionary:
	if not (cur_data.get("properties") is Dictionary):
		cur_data["properties"] = {}
	if not (cur_data["properties"].get("gift_preferences") is Dictionary):
		cur_data["properties"]["gift_preferences"] = {}
	return cur_data["properties"]["gift_preferences"]

func _gift_list(key: String) -> Array:
	var list = _gift_preferences().get(key, [])
	return list if list is Array else []

func _build_gift_item_list(vbox: VBoxContainer, key: String, title: String):
	var header := HBoxContainer.new(); header.add_child(InspectorStyle.create_sub_header(title))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = "+ Item"; InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var list := _gift_list(key).duplicate(); list.append("")
		_ensure_gift_preferences()[key] = list
		database_modified.emit()
		_refresh_gift_item_list(vbox, key))
	header.add_child(add); vbox.add_child(header)
	var rows := VBoxContainer.new(); rows.name = "GiftItems_" + key; rows.add_theme_constant_override("separation", 4); vbox.add_child(rows)
	_refresh_gift_item_list(vbox, key)

func _refresh_gift_item_list(vbox: VBoxContainer, key: String):
	var rows := vbox.get_node_or_null("GiftItems_" + key)
	if rows == null: return
	for child in rows.get_children(): child.queue_free()
	var list := _gift_list(key)
	for index in range(list.size()):
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
		var picker := _item_id_picker(str(list[index]))
		picker.item_selected.connect(func(selected):
			var live: Array = _ensure_gift_preferences().get(key, [])
			var chosen := str(picker.get_item_metadata(selected))
			if index < live.size(): live[index] = chosen
			database_modified.emit())
		row.add_child(picker)
		var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			var live: Array = _ensure_gift_preferences().get(key, [])
			if index < live.size(): live.remove_at(index)
			if live.is_empty(): _ensure_gift_preferences().erase(key)
			database_modified.emit()
			_refresh_gift_item_list(vbox, key))
		row.add_child(remove); rows.add_child(row)
	if list.is_empty(): rows.add_child(InspectorStyle.lbl("None.", InspectorStyle.COLOR_TEXT_DIM))

func _build_gift_text_list(vbox: VBoxContainer, key: String, title: String, note: String):
	var header := HBoxContainer.new(); header.add_child(InspectorStyle.create_sub_header(title))
	header.tooltip_text = note
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = "+ Tag"; InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var list := _gift_list(key).duplicate(); list.append("")
		_ensure_gift_preferences()[key] = list
		database_modified.emit()
		_refresh_gift_text_list(vbox, key))
	header.add_child(add); vbox.add_child(header)
	var rows := VBoxContainer.new(); rows.name = "GiftTags_" + key; rows.add_theme_constant_override("separation", 4); vbox.add_child(rows)
	_refresh_gift_text_list(vbox, key)

func _refresh_gift_text_list(vbox: VBoxContainer, key: String):
	var rows := vbox.get_node_or_null("GiftTags_" + key)
	if rows == null: return
	for child in rows.get_children(): child.queue_free()
	var list := _gift_list(key)
	for index in range(list.size()):
		var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
		var field := LineEdit.new(); field.text = str(list[index]); field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_input_style(field)
		field.text_changed.connect(func(new_text):
			var live: Array = _ensure_gift_preferences().get(key, [])
			if index < live.size(): live[index] = new_text
			database_modified.emit())
		row.add_child(field)
		var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			var live: Array = _ensure_gift_preferences().get(key, [])
			if index < live.size(): live.remove_at(index)
			if live.is_empty(): _ensure_gift_preferences().erase(key)
			database_modified.emit()
			_refresh_gift_text_list(vbox, key))
		row.add_child(remove); rows.add_child(row)
	if list.is_empty(): rows.add_child(InspectorStyle.lbl("None.", InspectorStyle.COLOR_TEXT_DIM))

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

	_refresh_loot_table()

## Reads `cur_data.loot_table` without creating it: opening an NPC that has none
## must not add an empty `"loot_table": {}` merely by being viewed. The key is
## only created by `_add_loot_entry`, when the author actually adds a drop.
func _refresh_loot_table():
	for c in loot_box.get_children(): c.queue_free()
	var table: Dictionary = cur_data.get("loot_table", {}) if cur_data.get("loot_table", {}) is Dictionary else {}

	for item_id in table:
		var entry = table[item_id]
		var pc = PanelContainer.new()
		var style = StyleBoxFlat.new(); style.bg_color = Color(0.15, 0.15, 0.17); style.set_corner_radius_all(4)
		pc.add_theme_stylebox_override("panel", style)
		
		var m = MarginContainer.new(); m.add_theme_constant_override("margin_left", 5); m.add_theme_constant_override("margin_right", 5)
		pc.add_child(m)
		var hb = HBoxContainer.new(); m.add_child(hb)
		
		# Item ID / Gold. `gold_value` is not a real item -- there is nothing to
		# pick -- but every other key names an item template, and until now that
		# name was a Label: an author could add a drop but never say which item it
		# was, short of hand-editing the JSON afterward.
		if item_id == "gold_value":
			var lbl_id = Label.new(); lbl_id.text = "Gold"; lbl_id.modulate = Color.GOLD
			lbl_id.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			hb.add_child(lbl_id)
		else:
			var current_item_id: String = item_id
			var item_picker := _item_id_picker(current_item_id)
			item_picker.item_selected.connect(func(index):
				var chosen := str(item_picker.get_item_metadata(index))
				# The table is keyed by item id, so choosing an id already in use
				# would silently merge two drops into one; refuse rather than lose
				# an entry, and let the picker snap back on the next refresh.
				if chosen == "" or chosen == current_item_id or table.has(chosen):
					_refresh_loot_table()
					return
				var moved = entry
				table.erase(current_item_id)
				table[chosen] = moved
				database_modified.emit()
				_refresh_loot_table())
			hb.add_child(item_picker)
		
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

## Mirrors `ItemInspector._item_picker`: every known item id, labelled with its
## name, plus the current id even if nothing declares it any more (a stale
## reference is a fact to show, not to silently swap out from under the author).
func _item_id_picker(current: String) -> OptionButton:
	var picker := OptionButton.new(); picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	picker.add_item("choose item"); picker.set_item_metadata(0, "")
	var ids: Array = db_manager.get_item_ids() if db_manager != null else []
	for item_id in ids:
		var label := str(item_id)
		if db_manager != null and db_manager.items.get(item_id) is Dictionary:
			label = "%s — %s" % [str(db_manager.items[item_id].get("name", item_id)), item_id]
		picker.add_item(label); picker.set_item_metadata(picker.item_count - 1, str(item_id))
		if str(item_id) == current: picker.select(picker.item_count - 1)
	if current != "" and picker.selected == 0:
		picker.add_item("Missing: " + current); picker.set_item_metadata(picker.item_count - 1, current); picker.select(picker.item_count - 1)
	InspectorStyle.apply_button_style(picker)
	return picker


func _add_loot_entry():
	var popup = PopupMenu.new()
	popup.add_item("Item from DB")
	popup.add_item("Gold Value")
	popup.id_pressed.connect(func(id):
		if typeof(cur_data.get("loot_table")) != TYPE_DICTIONARY: cur_data["loot_table"] = {}
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
