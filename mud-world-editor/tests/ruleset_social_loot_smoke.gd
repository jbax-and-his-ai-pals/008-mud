# tests/ruleset_social_loot_smoke.gd
#
# The ruleset's `social` and `loot` sections had no editor control. They now
# have the Ruleset editor's Relationships and Loot sections, saved through the
# staged engine check (content_set.py::_validate_social_rules,
# _validate_loot_settings, _validate_ambient_loot_references).
# fantasy_frontier's real sections are the fixture.
#
#   godot --headless --path mud-world-editor --script tests/ruleset_social_loot_smoke.gd

extends SceneTree

const Rules = preload("res://scripts/ui/modals/RulesetEditorDialog.gd")

var failures := 0


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var fixture := repo.path_join("tmp/ruleset-social-loot-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	var rules_path := fixture.path_join("rules/ruleset.json")
	var before: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rules_path))

	var rules = Rules.new(); root.add_child(rules); rules.setup(); rules.open_active()
	var social: SocialSection = rules.social_section
	var loot: LootSection = rules.loot_section

	print("\n[opening]")
	_assert(_same(social.compose(), before["social"]) and not social.changed(), "the real social section composes back unchanged")
	_assert(_same(loot.compose(), before["loot"]) and not loot.changed(), "the real loot section composes back unchanged")
	_assert(rules.get_ok_button().disabled, "Save starts disabled")
	_assert(social.tier_rows.get_child_count() == 4 and loot.pool_rows.get_child_count() == before["loot"]["ambient_pools"].size(), "one row per tier and one card per ambient pool")
	_assert(int((social.gift_spins["crafted"] as SpinBox).value) == 5 and int((social.gift_spins["preferred_tag"] as SpinBox).value) == 3, "gift values show what the file says")
	_assert(QuestGenerationSection._picked(loot.currency) == "item_gold_coin", "the currency resolves in its picker")

	print("\n[editing relationships]")
	var friend: Node = social.tier_rows.get_child(1)
	(friend.get_node("Discount") as SpinBox).value = 0.12
	_assert(not rules.get_ok_button().disabled, "an edit enables Save")
	(social.gift_spins["crafted"] as SpinBox).value = 7
	social._add_tier({"min": 90, "label": "Sworn", "vendor_discount": 0.2})
	social._add_tag("heirloom", 2)

	print("\n[editing loot]")
	loot.hint_text.text = "Take {items} while you can."; loot.hint_text.text_changed.emit(loot.hint_text.text)
	var first_chest: Node = loot.chest_rows.get_child(0)
	for button in first_chest.get_children():
		if button is Button and button.text == "v": button.pressed.emit(); break
	var pool: Node = loot.pool_rows.get_child(0)
	(pool.find_child("Chance", true, false) as SpinBox).value = 0.25

	# A pool entry naming an item that does not exist is a cross-file fact the
	# staged engine check owns: refused, nothing written.
	var entries: Node = pool.get_node("Entries")
	loot._add_entry(entries, {"item_id": "item_moonstone_nowhere", "weight": 3})
	var bytes_before := FileAccess.get_file_as_string(rules_path)
	rules.confirmed.emit()
	_assert(FileAccess.get_file_as_string(rules_path) == bytes_before, "a drop naming a missing item is refused, nothing written")
	_assert("item_moonstone_nowhere" in rules.status_label.text, "and the refusal names it")
	var bad: Node = entries.get_child(entries.get_child_count() - 1)
	entries.remove_child(bad); bad.queue_free()

	rules.confirmed.emit()
	var after: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	var saved_social: Dictionary = after["social"]
	var saved_loot: Dictionary = after["loot"]
	_assert(is_equal_approx(float(saved_social["tiers"][1]["vendor_discount"]), 0.12), "the Friend discount was saved")
	_assert(saved_social["tiers"].size() == 5 and saved_social["tiers"][4]["label"] == "Sworn", "the added tier was saved")
	_assert(int(saved_social["gift_values"]["crafted"]) == 7 and _same(saved_social["gift_values"]["disliked_item"], before["social"]["gift_values"]["disliked_item"]), "the crafted gift value was saved; the others untouched")
	_assert(int(saved_social["gift_tag_values"].get("heirloom", 0)) == 2 and int(saved_social["gift_tag_values"]["gem"]) == 1, "the gift tag was added beside the existing one")
	_assert(saved_loot["take_hint"] == "Take {items} while you can.", "the take hint was saved")
	var chests: Array = before["loot"]["chest_materials"]
	_assert(saved_loot["chest_materials"] == [chests[1], chests[0], chests[2]], "the chest order was saved")
	_assert(is_equal_approx(float(saved_loot["ambient_pools"][0]["chance"]), 0.25) and _same(saved_loot["ambient_pools"][0]["entries"], before["loot"]["ambient_pools"][0]["entries"]), "the pool chance was saved; its drops untouched")
	_assert(_same(saved_loot["ambient_pools"].slice(1), before["loot"]["ambient_pools"].slice(1)), "the other pools are untouched")
	_assert(_same(after.get("crime"), before.get("crime")) and _same(after.get("advancement"), before.get("advancement")), "other ruleset sections are untouched")

	print("\n[switching the hint off]")
	rules.open_active()
	rules.loot_section.hint_on.button_pressed = false
	rules.confirmed.emit()
	after = JSON.parse_string(FileAccess.get_file_as_string(rules_path))
	_assert(after["loot"]["take_hint"] == false, "an unticked hint is saved as false (no hint), not deleted")

	if failures > 0: push_error("ruleset social/loot smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


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
