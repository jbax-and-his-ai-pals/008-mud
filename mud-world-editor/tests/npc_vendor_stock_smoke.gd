# tests/npc_vendor_stock_smoke.gd
#
# `properties.sells_items`, `properties.sell_rate_multiplier` (`mercantile.py:
# 68-70, 81-122`) and `properties.buy_orders` (`mercantile.py:153-155`;
# `content_set.py::_validate_vendor_orders`) had no editor control at all -- an
# NPC could not be turned into a vendor without hand-editing JSON. See
# docs/plan/editor-coverage-ledger.md family C.
#
#   godot --headless --path mud-world-editor --script tests/npc_vendor_stock_smoke.gd
#
# `sells_items` is a plain item picker (the engine only ever reads `item_id` off
# it); `buy_orders` reuses `ReferenceEditor`, the same control the item panel's
# salvage output uses, since an order wants an item the way a recipe ingredient
# does -- template, family or capability.

extends SceneTree

var failure_count := 0
var scratch: String = ""


func _init() -> void:
	scratch = ProjectSettings.globalize_path("res://").path_join("../tmp/npc_vendor_stock")
	_rebuild_fixture()

	_check_opening_a_non_vendor_writes_nothing()
	_check_an_authored_vendor_shows_its_stock()
	_check_editing_the_sell_rate()
	_check_adding_a_sold_item()
	_check_removing_the_last_sold_item_erases_the_key()
	_check_adding_a_buy_order_defaults_to_valid_numbers()
	_check_the_buy_order_reference_editor_writes_a_family()
	_check_renaming_an_order_id_onto_an_existing_one_is_refused()
	_check_removing_the_last_order_erases_the_key()

	if failure_count > 0:
		push_error("npc vendor stock failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


func _check_opening_a_non_vendor_writes_nothing() -> void:
	print("\n[an NPC that is not a vendor]")
	var manager := _manager()
	_build_inspector_from("npc_plain", manager)
	var props: Dictionary = manager.npcs["npc_plain"].get("properties", {})
	_assert(not props.has("sells_items"), "opening the panel did not add sells_items")
	_assert(not props.has("sell_rate_multiplier"), "and did not add sell_rate_multiplier")
	_assert(not props.has("buy_orders"), "and did not add buy_orders")


func _check_an_authored_vendor_shows_its_stock() -> void:
	print("\n[an authored vendor]")
	var holder := _build_inspector("npc_vendor")
	var sells_rows := _rows(holder, "SellsItems")
	_assert(sells_rows.size() == 1, "one sold-item row (%d)" % sells_rows.size())
	var order_rows := _rows(holder, "BuyOrders")
	_assert(order_rows.size() == 1, "one buy-order row (%d)" % order_rows.size())


func _check_editing_the_sell_rate() -> void:
	print("\n[editing the sell rate]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_plain", manager)
	var rate := _first_spinbox_after(holder, "Buys from player at")
	_assert(rate != null, "the rate control was found")
	rate.value = 0.6
	rate.value_changed.emit(0.6)
	_assert(float(manager.npcs["npc_plain"]["properties"]["sell_rate_multiplier"]) == 0.6, "the rate was written")


func _check_adding_a_sold_item() -> void:
	print("\n[adding a sold item]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_plain", manager)
	var add := _button_after_rows(holder, "SellsItems", "+ Item")
	add.pressed.emit()
	var rows := _rows(holder, "SellsItems")
	_assert(rows.size() == 1, "one row after adding")
	var picker := _first_option_button(rows[0])
	var index := _index_for_id(picker, "item_potion")
	_assert(index != -1, "the picker offers item_potion")
	picker.item_selected.emit(index)
	var written: Array = manager.npcs["npc_plain"]["properties"]["sells_items"]
	_assert(str(written[0].get("item_id", "")) == "item_potion", "the item choice was written")


func _check_removing_the_last_sold_item_erases_the_key() -> void:
	print("\n[removing the only sold item]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_vendor", manager)
	var rows := _rows(holder, "SellsItems")
	var remove := _last_button(rows[0])
	remove.pressed.emit()
	_assert(not manager.npcs["npc_vendor"]["properties"].has("sells_items"), "the now-empty key was erased")


func _check_adding_a_buy_order_defaults_to_valid_numbers() -> void:
	print("\n[adding a buy order]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_plain", manager)
	var add := _button_after_rows(holder, "BuyOrders", "+ Order")
	add.pressed.emit()
	var written: Array = manager.npcs["npc_plain"]["properties"]["buy_orders"]
	_assert(written.size() == 1, "one order was created")
	var order: Dictionary = written[0]
	_assert(str(order.get("id", "")) != "", "it has a non-empty id")
	_assert(int(order.get("quantity", -1)) >= 1, "quantity is a valid positive int (content_set.py requires this)")
	_assert(int(order.get("reward_gold", -1)) >= 0, "reward_gold is a valid non-negative int")


func _check_the_buy_order_reference_editor_writes_a_family() -> void:
	print("\n[the order's reference editor]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_vendor", manager)
	var rows := _rows(holder, "BuyOrders")
	var kind_picker := _named_option_button(rows[0], "ReferenceKindPicker")
	_assert(kind_picker != null, "the reference kind picker was found (ReferenceEditor.gd is wired in)")
	var family_index := -1
	for index in range(kind_picker.item_count):
		if str(kind_picker.get_item_text(index)) == "item_family":
			family_index = index
	_assert(family_index != -1, "item_family is offered")
	kind_picker.item_selected.emit(family_index)
	var order: Dictionary = manager.npcs["npc_vendor"]["properties"]["buy_orders"][0]
	_assert(not order.has("item_id"), "switching kind cleared the old item_id")


func _check_renaming_an_order_id_onto_an_existing_one_is_refused() -> void:
	print("\n[renaming an order id onto another order's id]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_two_orders", manager)
	var rows := _rows(holder, "BuyOrders")
	var first_id_field := _first_line_edit(rows[0])
	first_id_field.text_submitted.emit("order_two")
	var written: Array = manager.npcs["npc_two_orders"]["properties"]["buy_orders"]
	var ids: Array = []
	for order in written:
		ids.append(str(order.get("id", "")))
	_assert(ids == ["order_one", "order_two"], "the collision left both ids alone (%s)" % str(ids))


func _check_removing_the_last_order_erases_the_key() -> void:
	print("\n[removing the only order]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_vendor", manager)
	var rows := _rows(holder, "BuyOrders")
	var remove := _button_labeled(rows[0], "Remove Order")
	remove.pressed.emit()
	_assert(not manager.npcs["npc_vendor"]["properties"].has("buy_orders"), "the now-empty key was erased")


# --- fixture ----------------------------------------------------------------

func _rebuild_fixture() -> void:
	_remove_recursive(scratch)
	_write("data/items/loot.json", {
		"item_potion": {"name": "Potion", "type": "Item", "weight": 1, "value": 5},
	})
	_write("data/npcs/probe.json", {
		"npc_plain": {"name": "Plain", "description": "", "level": 1, "health": 10, "friendly": true, "properties": {}},
		"npc_vendor": {
			"name": "Vendor", "description": "", "level": 1, "health": 10, "friendly": true,
			"properties": {
				"sells_items": [{"item_id": "item_potion", "price_multiplier": 2.0}],
				"buy_orders": [{"id": "order_one", "item_id": "item_potion", "quantity": 1, "reward_gold": 10}],
			},
		},
		"npc_two_orders": {
			"name": "Two Orders", "description": "", "level": 1, "health": 10, "friendly": true,
			"properties": {"buy_orders": [
				{"id": "order_one", "item_id": "item_potion", "quantity": 1, "reward_gold": 10},
				{"id": "order_two", "item_id": "item_potion", "quantity": 2, "reward_gold": 20},
			]},
		},
	})


func _write(relative: String, payload: Dictionary) -> void:
	var path := scratch.path_join(relative)
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(payload, "  "))
	file.close()


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			var child := path.path_join(name)
			if dir.current_is_dir():
				_remove_recursive(child)
			else:
				DirAccess.remove_absolute(child)
		name = dir.get_next()
	dir.list_dir_end()
	DirAccess.remove_absolute(path)


# --- harness ------------------------------------------------------------------

func _manager() -> DatabaseManager:
	DataRoot._resolved = scratch
	DataRoot._source = "test fixture"
	return DatabaseManager.new()


func _build_inspector(npc_id: String) -> Node:
	return _build_inspector_from(npc_id, _manager())


func _build_inspector_from(npc_id: String, manager: DatabaseManager) -> Node:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	var inspector := DatabaseInspector.new(holder)
	inspector.set_db_manager(manager)
	inspector.build("npc", npc_id, manager.npcs[npc_id])
	return holder


func _find_named(node: Node, wanted_name: String) -> Node:
	if str(node.name) == wanted_name:
		return node
	for child in node.get_children():
		var found := _find_named(child, wanted_name)
		if found != null:
			return found
	return null


## Filtered to HBoxContainer/PanelContainer rows only: a freed placeholder
## label (e.g. "Nothing for sale.") is queued, not removed, so it can still
## appear in get_children() the instant a refresh runs synchronously.
func _rows(node: Node, container_name: String) -> Array:
	var holder := _find_named(node, container_name)
	if holder == null:
		return []
	var out: Array = []
	for child in holder.get_children():
		if child is HBoxContainer or child is PanelContainer:
			out.append(child)
	return out


func _button_after_rows(node: Node, rows_container_name: String, text: String) -> Button:
	var rows := _find_named(node, rows_container_name)
	if rows == null:
		return null
	var header := rows.get_parent().get_child(rows.get_index() - 1)
	return _button_labeled(header, text)


func _button_labeled(node: Node, text: String) -> Button:
	for child in _all_buttons(node):
		if str(child.text) == text:
			return child
	return null


func _all_buttons(node: Node) -> Array:
	var out: Array = []
	if node is Button:
		out.append(node)
	for child in node.get_children():
		out.append_array(_all_buttons(child))
	return out


func _last_button(node: Node) -> Button:
	var buttons := _all_buttons(node)
	return buttons[buttons.size() - 1] if not buttons.is_empty() else null


func _first_option_button(node: Node) -> OptionButton:
	if node is OptionButton:
		return node
	for child in node.get_children():
		var found := _first_option_button(child)
		if found != null:
			return found
	return null


func _named_option_button(node: Node, wanted_name: String) -> OptionButton:
	if node is OptionButton and str(node.name) == wanted_name:
		return node
	for child in node.get_children():
		var found := _named_option_button(child, wanted_name)
		if found != null:
			return found
	return null


func _first_line_edit(node: Node) -> LineEdit:
	if node is LineEdit:
		return node
	for child in node.get_children():
		var found := _first_line_edit(child)
		if found != null:
			return found
	return null


## Each row is an HBoxContainer whose first child is the dim label and whose
## second child is the control -- the shape every row in this file builds.
func _first_spinbox_after(node: Node, label_text: String) -> SpinBox:
	if node is HBoxContainer and node.get_child_count() >= 2:
		var first := node.get_child(0)
		if first is Label and str(first.text) == label_text and node.get_child(1) is SpinBox:
			return node.get_child(1)
	for child in node.get_children():
		var found := _first_spinbox_after(child, label_text)
		if found != null:
			return found
	return null


func _index_for_id(picker: OptionButton, id: String) -> int:
	for index in range(picker.item_count):
		if str(picker.get_item_metadata(index)) == id:
			return index
	return -1


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		printerr("  FAIL ", message)
