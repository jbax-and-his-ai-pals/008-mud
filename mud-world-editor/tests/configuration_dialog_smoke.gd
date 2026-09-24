extends SceneTree

const Contracts = preload("res://scripts/ui/modals/ContractEditorDialog.gd")
const Rules = preload("res://scripts/ui/modals/RulesetEditorDialog.gd")
const Combat = preload("res://scripts/ui/modals/CombatVocabularyDialog.gd")
const SaveIO = preload("res://scripts/data/SaveIO.gd")
var failures := 0
var fixture := ""

func _init(): _run.call_deferred()

func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/configuration-dialog-%s/orbital_salvage" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/orbital_salvage"), fixture)
	DataRoot._resolved = fixture
	# Give the schedule form a compact setting-owned grammar to render.  The
	# orbital fixture intentionally has no auto-schedule section of its own.
	var seeded_rules_path := fixture.path_join("rules/ruleset.json")
	var seeded_rules: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(seeded_rules_path))
	seeded_rules["npc_schedules"] = {
		"excluded_name_keywords": ["guard"],
		"room_categories": {"quarters": ["bunk", "quarters"]},
		"roles": [{
			"id": "crew", "template_keywords": ["crew", "worker"],
			"location_slots": {
				"home": {"type": "self"},
				"work": {"type": "property_or_self", "property": "work_location"},
				"rest": {"type": "category", "categories": ["quarters"], "exclude": "work", "fallback": "home"},
			},
			"schedule": {"8": {"activity": "on shift", "slot": "work"}, "20": {"activity": "off shift", "slot": "rest"}},
		}],
	}
	seeded_rules["advancement"] = {
		"curve": {"base": 120, "multiplier": 1.2},
		"grants": [{"id": "first_dock", "match": {"kind": "region"}, "xp": 40, "message": "A new berth."}],
	}
	SaveIO.write_json(seeded_rules_path, seeded_rules)
	var dialog = Contracts.new(); root.add_child(dialog); dialog.setup(); dialog.open_active()
	var path := fixture.path_join("data/contracts/world_contracts.json")
	var before := FileAccess.get_file_as_string(path)
	var original: Dictionary = JSON.parse_string(before)
	_assert(not dialog._form_changed(), "opening a contract is clean")
	dialog.confirmed.emit()
	_assert(FileAccess.get_file_as_string(path) == before, "no-op dialog save is byte-identical")
	dialog.open_active()
	var count: int = dialog.resource_rows.get_child_count()
	dialog.hide(); dialog.open_active()
	_assert(dialog.resource_rows.get_child_count() == count, "immediate reopen does not duplicate rows")
	var label: LineEdit = _field(dialog.resource_rows.get_child(0), "Label")
	var initial := label.text
	_edit(label, initial + " edited")
	_assert(not dialog.get_ok_button().disabled, "a field edit enables Save")
	_edit(label, initial)
	_assert(dialog.get_ok_button().disabled, "reverting a field disables Save")
	_edit(label, initial + " edited")
	dialog.confirmed.emit()
	var expected := original.duplicate(true)
	expected["resources"][0]["label"] = initial + " edited"
	_assert(JSON.parse_string(FileAccess.get_file_as_string(path)) == expected, "actual dialog save changes only the resource label: " + dialog.status_label.text)
	_assert(not dialog.visible, "successful save closes the dialog")
	_assert(FileAccess.get_file_as_string(path + ".bak") == before, "configuration backup retains prior bytes")
	dialog.open_active()
	_assert(dialog.draft.original == expected, "reopen reads the saved contract")
	var short_before: String = dialog.stats_short.text
	_edit(dialog.stats_short, "strength=STR, constitution=CON")
	_assert(dialog._stats_value().get("short", {}) == {"strength":"STR", "constitution":"CON"}, "stats controls serialize textual labels, not a numeric map")
	_edit(dialog.stats_short, short_before)
	var parsed: Dictionary = dialog._parse_field("inputs", "item_flux_box x 2", {"inputs": [{"item_id": "item_flux_box", "quantity": 1, "extra": {"keep": true}}]})
	_assert(parsed.get("value", [])[0] == {"item_id": "item_flux_box", "quantity": 2, "extra": {"keep": true}}, "work IDs containing x and nested metadata survive quantity edits")
	_assert(dialog._parse_field("inputs", "item_flux_box x nope").has("error"), "invalid quantities are not defaulted")
	_assert(dialog._parse_field("damage", "nope").has("error"), "invalid numbers are not zeroed")
	parsed = dialog._parse_field("payload", '{"enabled":true,"amount":2,"nested":{"values":[1,2]}}')
	_assert(parsed.get("value", {}).get("enabled") == true and parsed["value"]["nested"]["values"][1] == 2, "typed payload keeps booleans, numbers and nested collections")
	_assert(dialog._parse_field("payload", '{bad').has("error"), "malformed JSON is reported")
	parsed = dialog._parse_map("strength=STR, constitution=CON", false)
	_assert(parsed.get("value", {}) == {"strength":"STR", "constitution":"CON"}, "stat short labels stay strings")
	_assert(dialog._parse_map("a=1,a=2", true).has("error"), "duplicate map keys are rejected")
	var tier_rows := VBoxContainer.new(); root.add_child(tier_rows)
	var profile := {}
	dialog._add_tier_row(tier_rows, profile, "rarity_tiers", {}, ["ID", "Rank", "Weight"])
	_edit(tier_rows.get_child(0).get_child(0), "new_grade")
	_edit(tier_rows.get_child(0).get_child(1), "2")
	_edit(tier_rows.get_child(0).get_child(2), "15")
	_assert(profile.get("rarity_tiers", [])[0] == {"id":"new_grade", "rank":2, "weight":15.0}, "new tier edits immediately reach the draft")
	tier_rows.get_child(0).get_child(3).pressed.emit()
	_assert(profile["rarity_tiers"].is_empty(), "tier removal updates the draft immediately")
	tier_rows.queue_free()
	var resources: Array = dialog.draft.data.get("resources", []).duplicate(true)
	resources.append({"id":"", "label":"unfinished"}); dialog.draft.set_resources(resources)
	_assert(dialog.draft.data["resources"].size() == resources.size() and not dialog.draft.validate().is_empty(), "blank entries remain visible to validation")
	# A close with edits must keep the draft until discard is explicitly confirmed.
	label = _field(dialog.resource_rows.get_child(0), "Label")
	_edit(label, "pending discard")
	dialog.hide()
	await process_frame
	await process_frame
	_assert(dialog.visible and dialog._discard_prompt.visible, "closing a dirty form asks before discarding")
	dialog._discard_prompt.hide(); dialog._discard_prompt.canceled.emit()
	_assert(dialog.visible and label.text == "pending discard", "cancel discard retains draft")
	dialog._discard_prompt.confirmed.emit()
	_assert(not dialog.visible, "confirmed discard closes the form")
	dialog.open_active()
	_assert(_field(dialog.resource_rows.get_child(0), "Label").text == initial + " edited", "discarded edits do not reappear")
	# External changes: save must keep both the disk version and the visible draft.
	label = _field(dialog.resource_rows.get_child(0), "Label"); _edit(label, "conflicting edit")
	var current := FileAccess.get_file_as_string(path)
	var file := FileAccess.open(path, FileAccess.WRITE); file.store_string(current + "\n"); file.close()
	dialog.confirmed.emit()
	_assert(dialog.visible and not dialog.get_ok_button().disabled and FileAccess.get_file_as_string(path) == current + "\n", "external edits are not overwritten and draft stays open")
	dialog._allow_close = true; dialog.hide(); dialog.queue_free()
	await process_frame
	var rules = Rules.new(); root.add_child(rules); rules.setup(); rules.open_active()
	var rules_path := fixture.path_join("rules/ruleset.json")
	var rules_before: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	_assert(rules.retreat_skill.text == "evasion" and int(rules.retreat_base.value) == 8 and int(rules.retreat_per_level.value) == 2, "combat retreat controls render the authored policy")
	_assert(rules._salvage_rules() == rules_before.get("crafting", {}).get("salvage_rules", {}), "ruleset salvage rows preserve authored comments and family rules")
	_assert(rules._npc_schedules() == rules_before.get("npc_schedules", {}), "schedule roles render without rewriting their runtime grammar")
	var role_card: VBoxContainer = rules.npc_schedule_roles.get_child(0)
	var activity_row: HBoxContainer = role_card.get_node("Activities").get_child(0)
	_edit(activity_row.get_node("Activity"), "starting shift")
	_assert(not rules.get_ok_button().disabled, "schedule activity edits mark the ruleset dirty")
	_assert(rules._advancement() == rules_before.get("advancement", {}), "advancement curve and grants render without changing their runtime shape")
	var grant_card: VBoxContainer = rules.advancement_grant_rows.get_child(0)
	_edit(grant_card.get_node("Message"), "A familiar berth.")
	var fallback_index := _metadata_index(rules.salvage_default, "item_patch_kit")
	_assert(fallback_index >= 0, "salvage fallback offers authored item templates")
	if fallback_index >= 0:
		rules.salvage_default.item_selected.emit(fallback_index)
	rules.confirmed.emit()
	var rules_expected := rules_before.duplicate(true); rules_expected["crafting"]["salvage_rules"]["default_item_id"] = "item_patch_kit"; rules_expected["npc_schedules"]["roles"][0]["schedule"]["8"]["activity"] = "starting shift"; rules_expected["advancement"]["grants"][0]["message"] = "A familiar berth."
	_assert(JSON.parse_string(FileAccess.get_file_as_string(rules_path)) == rules_expected, "ruleset save preserves untouched salvage details while changing its chosen fallback: " + rules.status_label.text)
	rules.open_active()
	var rows_before: int = rules.faction_rows.get_child_count(); rules.hide(); rules.open_active()
	_assert(rules.faction_rows.get_child_count() == rows_before, "faction rows do not duplicate on reopen")
	rules._allow_close = true; rules.hide(); rules.queue_free()
	await process_frame
	var combat = Combat.new(); root.add_child(combat); combat.setup(); combat.open_active()
	var combat_path := fixture.path_join("data/combat/elements.json")
	var combat_before := FileAccess.get_file_as_string(combat_path)
	var initial_types: String = combat.types.text
	_edit(combat.types, initial_types + ", " + initial_types.split(",")[0])
	combat.confirmed.emit()
	_assert(combat.visible and FileAccess.get_file_as_string(combat_path) == combat_before, "duplicate channels cannot be saved")
	_edit(combat.types, initial_types)
	_assert(combat.get_ok_button().disabled, "combat revert returns to clean state")
	combat._add_hazard("", {}); combat._mark_dirty(); combat.confirmed.emit()
	_assert(combat.visible and FileAccess.get_file_as_string(combat_path) == combat_before, "blank hazard does not silently disappear")
	combat._remove_row(combat.hazard_rows.get_child(combat.hazard_rows.get_child_count() - 1)); combat._mark_dirty()
	_edit(combat.types, initial_types + ", test_channel")
	combat.confirmed.emit()
	var combat_expected: Dictionary = JSON.parse_string(combat_before); combat_expected["valid_damage_types"].append("test_channel")
	_assert(JSON.parse_string(FileAccess.get_file_as_string(combat_path)) == combat_expected, "combat save changes only requested channels: " + combat.status.text)
	combat._allow_close = true; combat.hide(); combat.queue_free()
	await process_frame
	var malformed_path := fixture.path_join("malformed.json")
	SaveIO.write_json(malformed_path, {"resources": ["cannot render this"]})
	_assert(not ContractDraft.load(malformed_path).get("ok", true), "unrenderable contract entries fail closed instead of being dropped")
	SaveIO.write_json(malformed_path, {"world": 7})
	_assert(not RulesetDraft.load(malformed_path).get("ok", true), "malformed ruleset sections fail without a type crash")
	SaveIO.write_json(malformed_path, {"advancement": []})
	_assert(not RulesetDraft.load(malformed_path).get("ok", true), "malformed advancement refuses to open instead of risking an empty rewrite")
	SaveIO.write_json(malformed_path, {"hazards": {"bad": false}})
	_assert(not CombatVocabularyDraft.load(malformed_path).get("ok", true), "unrenderable hazards cannot be shortened on save")
	# Full application signal route, not just a standalone draft or dialog.
	var app = load("res://scenes/Main.tscn").instantiate()
	root.add_child(app)
	await process_frame
	app.ui_mgr.side_panel.request_edit_ruleset.emit()
	var live_rules = app.ui_mgr.ruleset_editor
	_assert(live_rules.visible, "Ruleset request reaches the dialog through the actual UI manager")
	_edit(live_rules.progression_model, live_rules.progression_model.text + " ")
	_assert(app.ui_mgr.has_configuration_drafts() and app._has_unsaved_work(), "application quit/switch sees pending configuration")
	live_rules.confirmed.emit()
	_assert(not live_rules.visible and not app.ui_mgr.has_configuration_drafts(), "save refresh callbacks work in the full application")
	app.ui_mgr.side_panel.request_edit_ruleset.emit()
	_edit(live_rules.progression_model, live_rules.progression_model.text + " ")
	app._reset_per_set_state()
	_assert(not live_rules.visible and live_rules.draft == null and not app.ui_mgr.has_configuration_drafts(), "set reset discards only after the application chooses that path")
	app.queue_free()
	await process_frame
	print("Configuration dialog checks: %s failure(s)." % failures)
	quit(1 if failures else 0)

func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))

func _field(node: Node, caption: String) -> LineEdit:
	if node is GridContainer:
		var children := node.get_children()
		for i in range(children.size() - 1):
			if children[i] is Label and children[i].text == caption and children[i + 1] is LineEdit: return children[i + 1]
	for child in node.get_children():
		var found := _field(child, caption)
		if found != null: return found
	return null

func _edit(field: LineEdit, value: String):
	field.text = value; field.text_changed.emit(value)

func _metadata_index(picker: OptionButton, wanted: String) -> int:
	for index in range(picker.item_count):
		if str(picker.get_item_metadata(index)) == wanted: return index
	return -1

func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
