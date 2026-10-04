# tests/ruleset_story_settings_smoke.gd
#
# The rules the story slice leans on, each editable in the Ruleset dialog:
#
#   * who earns experience (and money) for a kill, how a blow is remembered
#     (`combat.experience_sharing`: mode, min_share, memory_seconds);
#   * what a level brings (`advancement.level_up`: stat_growth, health_base).
#
# Opening the dialog and saving writes nothing; a change lands in the ruleset as the engine reads it; and
# the engine's own validator accepts what was saved. the story fixture (a frozen copy of the FF4 slice) is the fixture.
#
#   godot --headless --path mud-world-editor --script tests/ruleset_story_settings_smoke.gd

extends SceneTree

const Rules = preload("res://scripts/ui/modals/RulesetEditorDialog.gd")

var failures := 0


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var fixture := repo.path_join("tmp/ruleset-story-%s/story_fixture" % Time.get_ticks_usec())
	_copy(repo.path_join("server/tests/sets/story_fixture"), fixture)
	DataRoot._resolved = fixture
	var rules_path := fixture.path_join("rules/ruleset.json")
	var original := FileAccess.get_file_as_string(rules_path)

	print("\n[opening writes nothing]")
	var rules = Rules.new(); root.add_child(rules); rules.setup(); rules.open_active()
	_assert(rules.sharing_mode.get_item_metadata(rules.sharing_mode.selected) == "proportional", "kill experience shows the engine's default mode")
	_assert(is_equal_approx(rules.sharing_min_share.value, 0.05) and int(rules.sharing_memory.value) == 300, "and its default minimum share and memory")
	_assert(is_equal_approx(rules.level_up_growth.value, 1.0) and int(rules.level_up_health.value) == 5 and rules.level_up_overrides.text == "", "a level shows the engine's default growth")
	_assert(rules.get_ok_button().disabled, "Save starts disabled")
	rules.confirmed.emit()
	_assert(FileAccess.get_file_as_string(rules_path) == original, "saving without a change leaves the file byte-identical")

	print("\n[kill experience]")
	rules.open_active()
	var equal := -1
	for i in range(rules.sharing_mode.item_count):
		if rules.sharing_mode.get_item_metadata(i) == "equal": equal = i
	rules.sharing_mode.select(equal); rules.sharing_mode.item_selected.emit(equal)
	rules.sharing_min_share.value = 0.2
	rules.sharing_memory.value = 60
	_assert(not rules.get_ok_button().disabled, "a change enables Save")
	rules.confirmed.emit()
	var saved: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	var sharing: Dictionary = saved["combat"]["experience_sharing"]
	_assert(sharing.get("mode") == "equal" and is_equal_approx(float(sharing.get("min_share", -1)), 0.2) and int(sharing.get("memory_seconds", -1)) == 60,
		"the three settings are written as chosen: %s" % JSON.stringify(sharing))
	_assert(not saved.has("advancement"), "and nothing about levels was invented")

	print("\n[what a level brings]")
	rules.open_active()
	_assert(rules.sharing_mode.get_item_metadata(rules.sharing_mode.selected) == "equal" and int(rules.sharing_memory.value) == 60, "reopening shows the saved kill rules")
	rules.level_up_growth.value = 2
	rules.level_up_health.value = 8
	rules.level_up_overrides.text = "strength=3, agility=0"; rules.level_up_overrides.text_changed.emit(rules.level_up_overrides.text)
	rules.confirmed.emit()
	saved = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	var level_up: Dictionary = saved["advancement"]["level_up"]
	var growth: Dictionary = level_up.get("stat_growth", {})
	var raw := FileAccess.get_file_as_string(rules_path)
	_assert(int(growth.get("default", -1)) == 2 and int(growth.get("strength", -1)) == 3 and int(growth.get("agility", -1)) == 0,
		"stat growth is written: %s" % JSON.stringify(growth))
	_assert(raw.contains("\"strength\": 3,") or raw.contains("\"strength\": 3
"), "whole numbers are written as whole numbers")
	_assert(int(level_up.get("health_base", -1)) == 8 and raw.contains("\"health_base\": 8"), "and so is the flat health")
	_assert(not saved["advancement"].has("curve"), "without inventing an XP curve")

	rules.open_active()
	var shown := Array(rules.level_up_overrides.text.split(",")).map(func(part): return str(part).strip_edges())
	shown.sort()
	_assert(is_equal_approx(rules.level_up_growth.value, 2.0) and shown == ["agility=0", "strength=3"], "reopening shows them (%s)" % rules.level_up_overrides.text)
	rules.level_up_overrides.text = "agility=0"; rules.level_up_overrides.text_changed.emit(rules.level_up_overrides.text)
	rules.confirmed.emit()
	saved = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	_assert(not saved["advancement"]["level_up"]["stat_growth"].has("strength") and saved["advancement"]["level_up"]["stat_growth"].has("agility"), "dropping a stat from the list removes it")
	rules.open_active()
	rules.level_up_growth.value = 1; rules.level_up_health.value = 5; rules.level_up_overrides.text = ""; rules.level_up_overrides.text_changed.emit("")
	rules.confirmed.emit()
	saved = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	_assert(not saved.get("advancement", {}).has("level_up"), "putting everything back to the defaults removes the section")

	print("\n[the engine's words]")
	rules.open_active()
	_assert(rules.message_fields.size() == RulesetDraft.MESSAGES.size(), "every message the engine says has a line (%d)" % rules.message_fields.size())
	var experience: LineEdit = rules.message_fields["kill_experience"]
	_assert(experience.text == "" and experience.placeholder_text == "You gain {amount} experience!", "a line shows the engine's words as its placeholder, and is empty")
	experience.text = "{amount} experience earned."; experience.text_changed.emit(experience.text)
	var before_bytes := FileAccess.get_file_as_string(rules_path)
	(rules.message_fields["defeated"] as LineEdit).text = "{amount}"; (rules.message_fields["defeated"] as LineEdit).text_changed.emit("{amount}")
	rules.confirmed.emit()
	_assert(FileAccess.get_file_as_string(rules_path) == before_bytes, "a line using a field it does not have is refused: nothing written")
	_assert("messages.defeated" in rules.status_label.text, "and the refusal says which: %s" % rules.status_label.text.left(140))
	(rules.message_fields["defeated"] as LineEdit).text = "Darkness takes you."; (rules.message_fields["defeated"] as LineEdit).text_changed.emit("Darkness takes you.")
	rules.confirmed.emit()
	saved = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	_assert(saved.get("messages", {}) == {"kill_experience": "{amount} experience earned.", "defeated": "Darkness takes you."}, "good lines are written as typed, and only those: %s" % JSON.stringify(saved.get("messages")))
	rules.open_active()
	_assert((rules.message_fields["defeated"] as LineEdit).text == "Darkness takes you.", "reopening shows them")
	(rules.message_fields["defeated"] as LineEdit).text = ""; (rules.message_fields["defeated"] as LineEdit).text_changed.emit("")
	(rules.message_fields["kill_experience"] as LineEdit).text = ""; (rules.message_fields["kill_experience"] as LineEdit).text_changed.emit("")
	rules.confirmed.emit()
	saved = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	_assert(not saved.has("messages"), "emptying the lines erases them, and the section with them")

	print("\n[the engine's verdict]")
	_the_engine_accepts(repo, fixture)

	if failures > 0: push_error("ruleset story settings smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _the_engine_accepts(repo: String, fixture: String) -> void:
	var python := repo.path_join(".venv/Scripts/python.exe")
	if not FileAccess.file_exists(python): python = repo.path_join(".venv/bin/python")
	if not FileAccess.file_exists(python):
		print("  skip  no project Python interpreter found")
		return
	var output: Array = []
	var code := OS.execute(python, [repo.path_join("toolkit/content_set_validator.py"), fixture], output, true)
	if code != 0: print("    validator: ", "\n".join(output).right(600))
	_assert(code == 0, "the engine's validator accepts the saved ruleset")


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
