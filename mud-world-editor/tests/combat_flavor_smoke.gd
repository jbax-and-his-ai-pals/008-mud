# tests/combat_flavor_smoke.gd
#
# `combat/elements.json`'s `flavor_text` (what a spell hit says about a
# weakness or resistance) had no editor control; the Combat Vocabulary dialog
# now edits it, saved through the staged engine check
# (content_set.py::_validate_combat_flavor). fantasy_frontier is the fixture.
#
#   godot --headless --path mud-world-editor --script tests/combat_flavor_smoke.gd

extends SceneTree

const Dialog = preload("res://scripts/ui/modals/CombatVocabularyDialog.gd")

var failures := 0


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var fixture := repo.path_join("tmp/combat-flavor-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	var path := fixture.path_join("data/combat/elements.json")
	var original := FileAccess.get_file_as_string(path)
	var before: Dictionary = JSON.parse_string(original)

	var dialog = Dialog.new(); root.add_child(dialog); dialog.setup(); dialog.open_active()
	print("\n[opening]")
	_assert(dialog.flavor_rows.get_child_count() == before["flavor_text"].size(), "one row per flavored channel, default included")
	_assert(JSON.stringify(dialog._flavor_text()) == JSON.stringify(before["flavor_text"]), "the rows compose back to the file's table")
	_assert(dialog.get_ok_button().disabled, "Save starts disabled")
	var default_row: Node = dialog.flavor_rows.find_child("Flavor_default", true, false)
	_assert(default_row != null and not (default_row.find_child("Channel", true, false) as LineEdit).editable and _button(default_row, "Remove") == null, "the default row cannot be renamed or removed")

	print("\n[editing]")
	var fire: Node = dialog.flavor_rows.find_child("Flavor_fire", true, false)
	_edit(fire.find_child("weakness", true, false), "{target_name} goes up like tinder!")
	dialog._add_flavor("acid", {})
	var acid: Node = dialog.flavor_rows.get_child(dialog.flavor_rows.get_child_count() - 1)
	_edit(acid.find_child("resistance", true, false), "{target_name}'s hide shrugs off the acid.")
	_assert(not dialog.get_ok_button().disabled, "an edit enables Save")

	_edit(acid.find_child("weakness", true, false), "{attacker} melts {target_name}!")
	dialog.confirmed.emit()
	_assert(FileAccess.get_file_as_string(path) == original, "a line using a placeholder the engine does not fill is refused, nothing written")
	_assert("attacker" in dialog.status.text, "and the refusal names it: %s" % dialog.status.text.left(160))
	_edit(acid.find_child("weakness", true, false), "")

	dialog.confirmed.emit()
	var after: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	_assert(after["flavor_text"]["fire"]["weakness"] == "{target_name} goes up like tinder!", "the edited fire line was saved")
	_assert(after["flavor_text"]["fire"]["resistance"] == before["flavor_text"]["fire"]["resistance"], "its other lines are untouched")
	_assert(after["flavor_text"]["acid"] == {"resistance": "{target_name}'s hide shrugs off the acid."}, "the new channel was saved with only its filled line")
	_assert(JSON.stringify(after["hazards"]) == JSON.stringify(before["hazards"]) and after["valid_damage_types"] == before["valid_damage_types"], "hazards and channels are untouched")

	if failures > 0: push_error("combat flavor smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _edit(field: LineEdit, text: String):
	field.text = text; field.text_changed.emit(text)


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


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
