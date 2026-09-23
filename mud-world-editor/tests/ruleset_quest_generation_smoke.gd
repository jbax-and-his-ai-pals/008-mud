# tests/ruleset_quest_generation_smoke.gd
#
# The ruleset's `quest_generation` section (board rooms, authored notices,
# NPC interests, procedural naming, instance and generated-quest wording) had
# no editor control. fantasy_frontier authors every key by hand, so it is the
# fixture: a real, populated section must open clean, keep what it is not
# asked to change, and refuse a pattern that would crash quest generation.
# See docs/plan/editor-coverage-ledger.md, family G and ruleset H.
#
#   godot --headless --path mud-world-editor --script tests/ruleset_quest_generation_smoke.gd

extends SceneTree

const Rules = preload("res://scripts/ui/modals/RulesetEditorDialog.gd")

var failures := 0
var fixture := ""


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/ruleset-quest-generation-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	var rules_path := fixture.path_join("rules/ruleset.json")
	var before: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	var before_qg: Dictionary = before["quest_generation"]

	var rules = Rules.new(); root.add_child(rules); rules.setup(); rules.open_active()
	var section: QuestGenerationSection = rules.quest_generation_section
	_assert(_same(section.compose(), before_qg), "the real section composes back unchanged")
	_assert(not section.changed(), "opening is clean")
	_assert(rules.get_ok_button().disabled, "Save starts disabled")
	_assert(section.location_rows.get_child_count() == 5, "one row per board location")
	_assert(section.authored_rows.get_child_count() == 10, "one card per authored notice")
	_assert(section.interest_rows.get_child_count() == 7, "one row per NPC interest")
	_assert(_missing_labels(rules).is_empty(), "every shipped reference resolves in its picker %s" % str(_missing_labels(rules)))

	_edit(section.board_name, "Notice Board")
	_assert(not rules.get_ok_button().disabled, "an edit enables Save")
	_edit(section.text_fields["kill.title"], "Wanted: {target_name_plural}")

	var add_location := _button_labeled(rules, "+ Location")
	add_location.pressed.emit()
	var location_row: Node = section.location_rows.get_child(section.location_rows.get_child_count() - 1)
	_pick(location_row.get_node("Room"), "town:west_lane")

	var add_interest := _button_labeled(rules, "+ Interest")
	add_interest.pressed.emit()
	var interest_row: Node = section.interest_rows.get_child(section.interest_rows.get_child_count() - 1)
	_pick(interest_row.get_node("Npc"), "healer")
	_edit(interest_row.get_node("Tags"), "fetch, fetch_ingredients")

	var first_notice: Node = section.authored_rows.get_child(0)
	var repeatable: CheckBox = first_notice.get_node("Repeat/Repeatable")
	repeatable.button_pressed = false

	var composed := section.compose()
	_assert(composed["board_display_name"] == "Notice Board", "the board name reached the draft")
	_assert(composed["quest_board_locations"].back() == "town:west_lane", "the new location reached the draft")
	_assert(composed["npc_quest_interests"]["healer"] == ["fetch", "fetch_ingredients"], "the new interest reached the draft")
	_assert(not composed["authored_board_templates"][0].has("repeatable"), "unticking repeatable removes the policy")

	# `generate_instance_quest` formats this with only creature_name and no
	# try/except -- the one quest pattern that crashes rather than degrades.
	_edit(section.instance_fields["title_pattern"], "Clear {region_name}")
	var bytes_before_refusal := FileAccess.get_file_as_string(rules_path)
	rules.confirmed.emit()
	_assert(FileAccess.get_file_as_string(rules_path) == bytes_before_refusal, "a crashing instance placeholder is refused, nothing written")
	_assert("region_name" in rules.status_label.text, "and the refusal names the placeholder: %s" % rules.status_label.text)
	_edit(section.instance_fields["title_pattern"], "Bounty: {creature_name} Nest")

	rules.confirmed.emit()
	var after: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	var after_qg: Dictionary = after["quest_generation"]
	_assert(after_qg["board_display_name"] == "Notice Board", "the board name was saved")
	_assert(after_qg["text_templates"]["kill"]["title"] == "Wanted: {target_name_plural}", "the kill title was saved")
	_assert(after_qg["text_templates"]["kill"]["description"] == before_qg["text_templates"]["kill"]["description"], "the untouched kill description survives")
	_assert(after_qg["instance_quest"]["title_pattern"] == "Bounty: {creature_name} Nest", "the corrected instance title was saved")
	_assert(after_qg["quest_board_locations"].size() == 6, "five locations plus the new one")
	_assert(_same(after_qg["authored_board_templates"][1], before_qg["authored_board_templates"][1]), "an untouched notice survives exactly")
	_assert(_same(after_qg["procedural_naming"], before_qg["procedural_naming"]), "untouched procedural naming survives exactly")
	_assert(after_qg.keys().slice(0, before_qg.size()) == before_qg.keys(), "section key order is preserved")
	var float_delay := RegEx.create_from_string("\"delay_seconds\":\\s*\\d+\\.0")
	_assert(float_delay.search(FileAccess.get_file_as_string(rules_path)) == null, "delays are written as integers on disk, not 900.0")
	_assert(_same(after.get("weather"), before.get("weather")), "an unrelated ruleset section is untouched")
	_assert(not rules.visible, "a successful save closes the dialog")

	rules.open_active()
	section = rules.quest_generation_section
	_assert(section.location_rows.get_child_count() == 6, "reopen shows six locations, no duplication")
	_assert(not section.changed(), "reopen is clean")
	_edit(section.board_name, "")
	_assert(not section.compose().has("board_display_name"), "clearing an optional field removes the key")

	rules._allow_close = true; rules.hide(); rules.queue_free()
	if failures > 0:
		push_error("ruleset quest generation failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _same(a, b) -> bool:
	return JSON.stringify(SaveIO._normalize_numbers(a)) == JSON.stringify(SaveIO._normalize_numbers(b))


func _missing_labels(node: Node) -> Array:
	var out: Array = []
	if node is OptionButton:
		for index in range(node.item_count):
			if str(node.get_item_text(index)).begins_with("Missing:"): out.append(node.get_item_text(index))
	for child in node.get_children(): out.append_array(_missing_labels(child))
	return out


func _pick(picker: OptionButton, value: String):
	for index in range(picker.item_count):
		if str(picker.get_item_metadata(index)) == value:
			picker.select(index); picker.item_selected.emit(index); return
	_assert(false, "picker offers '%s'" % value)


func _button_labeled(node: Node, text: String) -> Button:
	if node is Button and str(node.text) == text:
		return node
	for child in node.get_children():
		var found := _button_labeled(child, text)
		if found != null:
			return found
	return null


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _edit(field: LineEdit, value: String):
	field.text = value; field.text_changed.emit(value)


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
