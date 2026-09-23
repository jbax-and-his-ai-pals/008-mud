# tests/field_interactions_authoring_smoke.gd
#
# `data/world/field_interactions.json` (headless/field_fx.py) had no editor
# control and no validator. fantasy_frontier's real file is the fixture for
# editing; modern_capsule, which ships none, proves that saving creates one.
# Saves go through ConfigurationSave, so the engine's own check runs on each.
# See docs/plan/editor-coverage-ledger.md family G.
#
#   godot --headless --path mud-world-editor --script tests/field_interactions_authoring_smoke.gd

extends SceneTree

var failures := 0


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var stamp := Time.get_ticks_usec()
	_edits_a_real_file(repo.path_join("tmp/field-interactions-%s/fantasy_frontier" % stamp), repo.path_join("content_sets/fantasy_frontier"))
	_creates_a_missing_file(repo.path_join("tmp/field-interactions-%s/modern_capsule" % stamp), repo.path_join("content_sets/modern_capsule"))
	if failures > 0:
		push_error("field interactions authoring failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _edits_a_real_file(fixture: String, source: String):
	print("\n[editing fantasy_frontier's file]")
	_copy(source, fixture)
	DataRoot._resolved = fixture
	var path := FieldInteractionsDraft.config_path()
	var before: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	var dialog := _dialog()
	_assert(_same(dialog.compose(), before), "the real file composes back unchanged")
	_assert(dialog.get_ok_button().disabled, "Save starts disabled")
	_assert(dialog.polarity_rows.get_child_count() == 8, "one row per declared field")
	_assert(dialog.rule_rows.get_child_count() == 2, "one row per pairwise rule")

	var fog := _row(dialog.polarity_rows, "FieldId", "fog")
	var picker: OptionButton = fog.get_node("Polarity")
	picker.select(0); picker.item_selected.emit(0)
	_assert(not dialog.get_ok_button().disabled, "an edit enables Save")
	_button(dialog, "+ Rule").pressed.emit()
	var rule: Node = dialog.rule_rows.get_child(dialog.rule_rows.get_child_count() - 1)
	_edit(rule.get_node("Source"), "hope")
	_edit(rule.get_node("Target"), "fog")
	(rule.get_node("Coefficient") as SpinBox).value = 0.25

	var bad := _row(dialog.polarity_rows, "FieldId", "wild")
	_edit(bad.get_node("FieldId"), "Wild")
	var bytes_before := FileAccess.get_file_as_string(path)
	dialog.confirmed.emit()
	_assert(FileAccess.get_file_as_string(path) == bytes_before, "an upper-case field id is refused, nothing written")
	_assert("lower-case" in dialog.status.text, "and the refusal says why: %s" % dialog.status.text)
	_edit(bad.get_node("FieldId"), "wild")

	dialog.confirmed.emit()
	var after: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	_assert(after["polarities"]["fog"] == "positive", "the polarity change was saved")
	_assert(is_equal_approx(float(after["pairwise_rules"]["hope"]["fog"]), 0.25), "the new rule was saved")
	_assert(_same(after["pairwise_rules"]["sanctity"], before["pairwise_rules"]["sanctity"]), "an untouched rule survives")
	_assert(is_equal_approx(float(after["fallback_positive_suppresses_negative"]), 0.6), "the untouched fallback survives")
	_assert(after["default_field_id"] == "blight", "the untouched default survives")
	_assert(after.keys() == before.keys(), "top-level key order is preserved")
	_assert(not dialog.visible, "a successful save closes the dialog")
	dialog._allow_close = true; dialog.queue_free()


func _creates_a_missing_file(fixture: String, source: String):
	print("\n[creating one for modern_capsule]")
	_copy(source, fixture)
	DataRoot._resolved = fixture
	var path := FieldInteractionsDraft.config_path()
	_assert(not FileAccess.file_exists(path), "modern_capsule ships no field interactions")
	var dialog := _dialog()
	_assert("no ambient fields" in dialog.status.text, "the dialog says the system is off")
	_button(dialog, "+ Rule").pressed.emit()
	var rule: Node = dialog.rule_rows.get_child(0)
	_edit(rule.get_node("Source"), "calm"); _edit(rule.get_node("Target"), "static")
	dialog.confirmed.emit()
	_assert(not FileAccess.file_exists(path), "a new file with no fields is refused")
	_assert("at least one field" in dialog.status.text, "and the refusal says why: %s" % dialog.status.text)

	for spec in [["static", 2], ["calm", 0]]:
		_button(dialog, "+ Field").pressed.emit()
		var row: Node = dialog.polarity_rows.get_child(dialog.polarity_rows.get_child_count() - 1)
		_edit(row.get_node("FieldId"), spec[0])
		var polarity: OptionButton = row.get_node("Polarity")
		polarity.select(spec[1]); polarity.item_selected.emit(spec[1])
	_edit(dialog.default_field, "static")
	dialog.confirmed.emit()
	_assert(FileAccess.file_exists(path), "saving created the file (%s)" % dialog.status.text)
	var created: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else {}
	_assert(created.get("polarities", {}) == {"static": "negative", "calm": "positive"}, "with the declared fields: %s" % str(created))
	_assert(created.get("default_field_id", "") == "static", "and the default field")
	_assert(created.get("pairwise_rules", {}).has("calm"), "and the rule")
	dialog._allow_close = true; dialog.queue_free()


func _dialog() -> FieldInteractionsDialog:
	var dialog := FieldInteractionsDialog.new()
	root.add_child(dialog); dialog.setup(); dialog.open_active()
	return dialog


func _same(a, b) -> bool:
	return JSON.stringify(SaveIO._normalize_numbers(a)) == JSON.stringify(SaveIO._normalize_numbers(b))


func _row(rows: Node, field: String, value: String) -> Node:
	for row in rows.get_children():
		if str((row.get_node(field) as LineEdit).text) == value: return row
	_assert(false, "a row with %s '%s'" % [field, value])
	return null


func _button(node: Node, text: String) -> Button:
	if node is Button and str(node.text) == text: return node
	for child in node.get_children():
		var found := _button(child, text)
		if found != null: return found
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
