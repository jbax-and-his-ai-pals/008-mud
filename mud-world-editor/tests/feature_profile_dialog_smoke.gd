# tests/feature_profile_dialog_smoke.gd
#
# The feature profile a set's manifest selects had no editor control at all.
# FeatureProfileDialog now edits its modes, provider ids and the party, shard
# and finite-adventure policies, saved through the staged engine check
# (content_set.py::_validate_feature_profile). fantasy_frontier (which selects
# creative_world.profile.json) and modern_capsule (which selects none) are the
# fixtures.
#
#   godot --headless --path mud-world-editor --script tests/feature_profile_dialog_smoke.gd

extends SceneTree

var failures := 0


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var fixture := repo.path_join("tmp/feature-profile-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	var path := fixture.path_join("data/profiles/creative_world.profile.json")
	var before: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))

	var dialog := FeatureProfileDialog.new(); root.add_child(dialog); dialog.setup(); dialog.open_active()
	print("\n[opening fantasy's profile]")
	_assert(dialog.body.visible and dialog.path.ends_with("creative_world.profile.json"), "it opens the profile the manifest selects")
	_assert(_picked(dialog.mode_pickers["combat"]) == "enabled" and _picked(dialog.mode_pickers["permadeath"]) == FeatureProfileDialog.DEFAULT, "authored modes are shown as authored, absent ones as the default")
	_assert(not (dialog.provider_fields["world_effects"] as LineEdit).editable, "a provider id is editable only in custom mode")
	_assert(_same(dialog.compose(), before), "the untouched form composes back to the file")
	_assert(dialog.get_ok_button().disabled, "Save starts disabled")

	print("\n[editing]")
	_choose(dialog.mode_pickers["combat"], "disabled")
	_choose(dialog.mode_pickers["world_effects"], "custom")
	(dialog.provider_fields["world_effects"] as LineEdit).text = "sample.effects.balance"
	_choose(dialog.mode_pickers["weather"], "disabled")
	(dialog.provider_fields["weather"] as LineEdit).text = "ignored.because.not.custom"
	_choose(dialog.policy_controls["party.loot_policy"], "finder_keep")
	_choose(dialog.policy_controls["finite_adventure.replay_supported"], false)
	var seconds: LineEdit = dialog.policy_controls["persistent_shard.disconnect_timeout_seconds"]
	seconds.text = "-3"; seconds.text_changed.emit("-3")
	_assert(not dialog.get_ok_button().disabled, "an edit enables Save")
	var bytes_before := FileAccess.get_file_as_string(path)
	dialog.confirmed.emit()
	_assert(FileAccess.get_file_as_string(path) == bytes_before and "seconds" in dialog.status.text, "negative seconds are refused before anything is written")
	seconds.text = "120"; seconds.text_changed.emit("120")
	dialog.confirmed.emit()
	var after: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	_assert(after["combat"]["mode"] == "disabled" and after["weather"] == {"mode": "disabled"}, "modes saved; a provider id outside custom mode is not written")
	_assert(after["world_effects"] == {"mode": "custom", "provider_id": "sample.effects.balance"}, "a custom mode saves its provider")
	_assert(after.get("party") == {"loot_policy": "finder_keep"} and after.get("finite_adventure") == {"replay_supported": false} and int(after.get("persistent_shard", {}).get("disconnect_timeout_seconds", 0)) == 120, "policies are written into their sections, only where set")
	_assert(not after.has("permadeath") and after["authoring"] == before["authoring"] and after["mods"] == before["mods"], "untouched sections stay as they were; no empty sections appear")

	print("\n[a value the list does not know]")
	after["shard"] = {"late_join_policy": "closed"}; after.erase("persistent_shard")
	var file := FileAccess.open(path, FileAccess.WRITE); file.store_string(JSON.stringify(after, "    ")); file.close()
	dialog.open_active()
	var late_join: OptionButton = dialog.policy_controls["persistent_shard.late_join_policy"]
	_assert(late_join.get_item_text(late_join.selected) == "Current: closed", "a synonym the reader accepts is shown as it is written")
	_choose(dialog.mode_pickers["mods"], "disabled")
	dialog.confirmed.emit()
	var kept: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	_assert(kept.get("shard") == {"late_join_policy": "closed"} and not kept.has("persistent_shard") and kept["mods"]["mode"] == "disabled", "and kept, in the `shard` section the file uses, when something else is saved")

	print("\n[a set with no profile]")
	var capsule := repo.path_join("tmp/feature-profile-%s/modern_capsule" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/modern_capsule"), capsule)
	DataRoot._resolved = capsule
	var none := FeatureProfileDialog.new(); root.add_child(none); none.setup(); none.open_active()
	_assert(not none.body.visible and "no feature profile" in none.status.text and none.get_ok_button().disabled, "says the server runs it with every default, and offers nothing to save")

	if failures > 0: push_error("feature profile dialog smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _picked(picker: OptionButton):
	return picker.get_item_metadata(picker.selected)


func _choose(picker: OptionButton, value) -> void:
	for index in picker.item_count:
		var meta = picker.get_item_metadata(index)
		if typeof(meta) == typeof(value) and meta == value:
			picker.select(index); picker.item_selected.emit(index); return
	failures += 1; print("  FAIL no option %s" % str(value))


func _same(a, b) -> bool:
	return JSON.stringify(SaveIO._normalize_numbers(a)) == JSON.stringify(SaveIO._normalize_numbers(b))


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
