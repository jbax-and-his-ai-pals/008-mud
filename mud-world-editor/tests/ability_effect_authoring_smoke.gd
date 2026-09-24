# tests/ability_effect_authoring_smoke.gd
#
# An ability's effect card covered type, amount, damage type and duration; the
# keys most effects actually run on (a DoT's name and tick, an applied effect's
# payload, a summon's creature and cap, a cleanse's tags) had no control, and the
# target picker could not show `item`. MagicInspector now edits what each effect
# type reads (magic/spell.py ABILITY_EFFECT_FIELDS). fantasy_frontier is the
# fixture; the edited set is run through the engine's validator.
#
#   godot --headless --path mud-world-editor --script tests/ability_effect_authoring_smoke.gd

extends SceneTree

var failures := 0
var fixture := ""
var inspectors: Array = []


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/ability-effects-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "test fixture"
	var magic_dir := fixture.path_join("data/magic")
	var originals := {}
	for name in DirAccess.get_files_at(magic_dir): originals[name] = FileAccess.get_file_as_string(magic_dir.path_join(name))

	print("\n[opening every ability]")
	var manager := DatabaseManager.new()
	var before := JSON.stringify(manager.magic)
	for ability_id in manager.magic: _inspect(manager, ability_id)
	_assert(JSON.stringify(manager.magic) == before, "building every ability's inspector writes nothing")
	for ability_id in manager.magic: manager.mark_dirty("magic", ability_id)
	manager.save_all()
	var identical := true
	for name in originals:
		if FileAccess.get_file_as_string(magic_dir.path_join(name)) != originals[name]:
			identical = false; print("    changed: ", name)
	_assert(identical, "an unedited save of every ability file is byte-identical")

	var knock := _inspect(manager, "knock")
	var target: OptionButton = knock.find_child("TargetType", true, false)
	_assert(str(target.get_item_metadata(target.selected)) == "item", "an item ability shows its Item target (the picker had no such option)")

	print("\n[editing each effect type's own fields]")
	manager = DatabaseManager.new()
	var fireball := _inspect(manager, "fireball")
	var dot: Node = fireball.find_child("Effect_1", true, false)
	_assert((dot.find_child("dot_name", true, false) as LineEdit).text == "Ignite", "a DoT shows its name")
	_spin(dot.find_child("dot_damage_per_tick", true, false), 7)
	_spin(dot.find_child("dot_tick_interval", true, false), 2)
	var effect: Dictionary = manager.magic["fireball"]["effects"][1]
	_assert(effect["dot_damage_per_tick"] == 7.0 and effect["dot_tick_interval"] == 2.0, "its damage per tick and tick interval are written")

	var weaken := _inspect(manager, "weaken_strength")
	var applied: Node = weaken.find_child("Effect_0", true, false)
	_assert((applied.find_child("EffectName", true, false) as LineEdit).text == "Weaken", "an applied effect shows its payload's name")
	var stat: LineEdit = applied.find_child("Modifier_0", true, false).find_child("Stat", true, false)
	stat.text = "agility"; stat.text_submitted.emit("agility")
	await process_frame
	var payload: Dictionary = manager.magic["weaken_strength"]["effects"][0]["effect_data"]
	_assert(SaveIO._normalize_numbers(payload["modifiers"]) == {"agility": -5}, "a stat modifier can be renamed, keeping its amount")
	_button(weaken, "+ Modifier").pressed.emit()
	applied = weaken.find_child("Effect_0", true, false)
	_spin(applied.find_child("Modifier_1", true, false).find_child("Amount", true, false), -2)
	_edit(applied.find_child("Modifier_1", true, false).find_child("Stat", true, false), "strength", true)
	await process_frame
	_assert(SaveIO._normalize_numbers(payload["modifiers"]) == {"agility": -5, "strength": -2}, "and one can be added")
	_assert(manager.magic["weaken_strength"]["effects"][0]["dot_duration"] == 20, "the duration it already authored is left where it is")

	var skeleton := _inspect(manager, "raise_skeleton")
	var summon: Node = skeleton.find_child("Effect_0", true, false)
	_spin(summon.find_child("max_summons", true, false), 0)
	_assert(not manager.magic["raise_skeleton"]["effects"][0].has("max_summons"), "clearing the summon cap removes it")
	_pick(summon.find_child("summon_template_id", true, false), "spirit_wolf_minion")
	_assert(manager.magic["raise_skeleton"]["effects"][0]["summon_template_id"] == "spirit_wolf_minion", "the creature is picked from the minion templates")
	var offered := _options(summon.find_child("summon_template_id", true, false))
	_assert(not offered.is_empty() and offered.all(func(id): return str(manager.npcs[id].get("behavior_type", "")) == "minion"), "only minions are offered (nothing else follows its summoner)")

	var missile := _inspect(manager, "magic_missile")
	_pick(missile.find_child("Effect_0", true, false).find_child("EffectType", true, false), "cleanse")
	var cleanse: Dictionary = manager.magic["magic_missile"]["effects"][0]
	_assert(cleanse == {"type": "cleanse", "effect_data": {"tags": ["poison", "disease", "curse"]}}, "retyping keeps only what the new type reads, with working defaults")
	_edit(missile.find_child("Effect_0", true, false).find_child("Tags", true, false), "poison, curse")
	_assert(cleanse["effect_data"]["tags"] == ["poison", "curse"], "a cleanse's tags are written")
	_pick(missile.find_child("TargetType", true, false), "friendly")
	_edit(missile.find_child("cast_message", true, false), "")
	_assert(not manager.magic["magic_missile"].has("cast_message"), "clearing a message removes it (the engine's default applies)")
	_edit(missile.find_child("hit_message", true, false), "{caster_name} purges {target_name}.")

	for ability_id in ["fireball", "weaken_strength", "raise_skeleton", "magic_missile"]: manager.mark_dirty("magic", ability_id)
	_assert(manager.save_all().get("ok", false), "the edited abilities save")
	_assert(_engine_accepts(repo), "and the engine's validator accepts them")

	print("\n[what the engine refuses]")
	var zap := _inspect(manager, "zap")
	_pick(zap.find_child("Effect_0", true, false).find_child("EffectType", true, false), "apply_effect")
	_assert(zap.find_child("Effect_0", true, false).find_child("EffectName", true, false) != null, "an applied effect's fields appear once it is retyped")
	manager.mark_dirty("magic", "zap")
	manager.save_all()
	_assert(not _engine_accepts(repo), "an applied effect left with no name or modifiers is refused until it is filled in")

	if failures > 0: push_error("ability effect authoring failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _engine_accepts(repo: String) -> bool:
	var output: Array = []
	var python := repo.path_join(".venv/Scripts/python.exe")
	if not FileAccess.file_exists(python): python = repo.path_join(".venv/bin/python")
	var code := OS.execute(python, [repo.path_join("toolkit/content_set_validator.py"), fixture], output, true)
	if code != 0: print("    validator: ", "\n".join(output).right(500))
	return code == 0


func _inspect(manager: DatabaseManager, ability_id: String) -> Node:
	var holder := VBoxContainer.new(); root.add_child(holder)
	var inspector := MagicInspector.new(); inspectors.append(inspector)
	inspector.build(holder, manager.magic[ability_id], manager.magic_groups, ability_id, manager)
	return holder


func _options(picker: OptionButton) -> Array:
	var out: Array = []
	for index in range(picker.item_count):
		var value := str(picker.get_item_metadata(index))
		if not value.is_empty(): out.append(value)
	return out


func _pick(picker: OptionButton, value: String):
	for index in range(picker.item_count):
		if str(picker.get_item_metadata(index)) == value:
			picker.select(index); picker.item_selected.emit(index); return
	_assert(false, "picker offers '%s'" % value)


func _spin(field: SpinBox, value: float):
	field.value = value


func _edit(field: LineEdit, value: String, submit: bool = false):
	field.text = value
	if submit: field.text_submitted.emit(value)
	else: field.text_changed.emit(value)


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
