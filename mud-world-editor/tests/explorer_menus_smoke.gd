# tests/explorer_menus_smoke.gd
#
# The Explorer's controls under the region tree: fifteen full-width buttons
# became one row of map toggles and four menus (Map, Check, Game Rules,
# Content Sets). Every item must still reach the action its button did, and
# the running states a long check shows must land on the menu.
#
#   godot --headless --path mud-world-editor --script tests/explorer_menus_smoke.gd

extends SceneTree

var failures := 0


func _initialize() -> void:
	var panel := ExplorerPanel.new()
	root.add_child(panel)
	panel.setup()

	print("\n[every menu item reaches its action]")
	var expected := {
		"MapMenu": {"New Region…": "request_create_modal_open", "New District…": "request_district_modal_open", "Auto-Arrange Rooms": "request_auto_layout"},
		"CheckMenu": {"Validate Region": "request_validate", "Validate Region Policy": "request_validate_region_policy", "Validate Open Set": "request_validate_content", "Run Release Gate": "request_run_release_gate"},
		"RulesMenu": {"Ruleset…": "request_edit_ruleset", "Manifest…": "request_edit_manifest", "Combat Vocabulary…": "request_edit_combat_vocabulary", "Feature Profile…": "request_edit_feature_profile", "Ambient Fields…": "request_edit_field_interactions", "Browse Contracts": "request_show_contracts", "Edit Contracts…": "request_edit_contracts"},
	}
	for menu_name in expected:
		var menu: MenuButton = panel.find_child(menu_name, true, false)
		_assert(menu != null, "%s exists" % menu_name)
		if menu == null: continue
		var popup := menu.get_popup()
		for label in expected[menu_name]:
			var fired := [false]
			var signal_name: String = expected[menu_name][label]
			var hear := func(): fired[0] = true
			panel.connect(signal_name, hear)
			var index := -1
			for i in popup.item_count:
				if popup.get_item_text(i) == label: index = i
			if index >= 0:
				popup.id_pressed.emit(popup.get_item_id(index))
				_assert(popup.get_item_tooltip(index) != "", "%s › %s says what it does" % [menu_name, label])
			_assert(fired[0], "%s › %s emits %s" % [menu_name, label, signal_name])
			panel.disconnect(signal_name, hear)
	var sets_fired := [false]
	panel.request_choose_content_set.connect(func(): sets_fired[0] = true)
	var sets: Button = panel.find_child("ContentSetsButton", true, false)
	if sets: sets.pressed.emit()
	_assert(sets_fired[0], "Content Sets… opens the chooser")

	print("\n[running states show on the menu]")
	panel.set_content_validation_running(true)
	var check: MenuButton = panel.check_menu
	_assert(check.text.begins_with("Checking"), "the Check menu says a check is running")
	var open_set := panel._menu_index(check, "Validating Open Set")
	_assert(open_set >= 0 and check.get_popup().is_item_disabled(open_set), "and that item cannot be started twice")
	panel.set_content_validation_running(false)
	_assert(check.text.begins_with("Check ") and panel._menu_index(check, "Validate Open Set") >= 0, "and goes back when it finishes")
	panel.update_layout_btn_text(true)
	_assert(panel._menu_index(panel.map_menu, "Auto-Arrange World") >= 0, "on the world map, the Map menu arranges the world")

	panel.free()
	if failures > 0: push_error("explorer menus smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _assert(condition: bool, message: String) -> void:
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
