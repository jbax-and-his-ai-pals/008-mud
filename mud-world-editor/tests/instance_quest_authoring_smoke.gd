# tests/instance_quest_authoring_smoke.gd
#
# `quests/instances.json` (QuestGenerator.generate_instance_quest) was loaded
# into the Quests library but opened in the stage-based QuestInspector, which
# wrote `stages: []` into the template on open and offered kill/fetch editors
# that mean nothing here. Instance templates now have their own category and
# InstanceQuestInspector. fantasy_frontier's real `instance_generic_infestation`
# is the fixture. See docs/plan/editor-coverage-ledger.md family G.
#
#   godot --headless --path mud-world-editor --script tests/instance_quest_authoring_smoke.gd

extends SceneTree

const Library = preload("res://scripts/ui/modals/ContentLibraryDialog.gd")
const REAL_ID := "instance_generic_infestation"

var failures := 0
var fixture := ""


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/instance-quest-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "test fixture"
	var path := DataRoot.content_file("quests/instances.json")
	var original_bytes := FileAccess.get_file_as_string(path)

	var manager := DatabaseManager.new()
	_assert(manager.quests.has(REAL_ID), "the shipped instance template loads into quest storage")
	_check_the_library_separates_instance_templates(manager)

	print("\n[opening changes nothing]")
	var before := JSON.stringify(manager.quests[REAL_ID])
	var holder := _inspect(manager, REAL_ID)
	_assert(JSON.stringify(manager.quests[REAL_ID]) == before, "building the inspector wrote nothing into the template")
	_assert(not manager.quests[REAL_ID].has("stages"), "in particular, no empty stages list")
	manager.mark_dirty("quest", REAL_ID)
	var result: Dictionary = manager.save_all()
	_assert(result.get("ok", false), "saving reported ok: %s" % str(result.get("errors", [])))
	_assert(FileAccess.get_file_as_string(path) == original_bytes, "an opened-and-saved template is byte-identical on disk")
	_assert(_missing(holder).is_empty(), "every shipped reference resolves in its picker %s" % str(_missing(holder)))

	print("\n[editing]")
	manager = DatabaseManager.new()
	holder = _inspect(manager, REAL_ID)
	var data: Dictionary = manager.quests[REAL_ID]
	_edit(holder.find_child("RegionDescription", true, false), "A narrow house that smells of wet straw.")
	_assert(data["layout_generation_config"]["region_description"] == "A narrow house that smells of wet straw.", "the region description was written")
	var high: SpinBox = holder.find_child("TargetMax", true, false)
	high.value = 6
	_assert(data["layout_generation_config"]["target_count"] == [2, 6], "the target range was written as integers")
	_button(holder, "+ Creature").pressed.emit()
	var targets: Array = data["objective"]["possible_target_template_ids"]
	_assert(targets.size() == 3, "a creature row was added")
	var target_picker := _picker_with_metadata(holder, "")
	_pick(target_picker, "goblin")
	_assert(data["objective"]["possible_target_template_ids"][2] == "goblin", "the new creature was picked")
	_pick(holder.find_child("GiverNpcTemplateId", true, false), "")
	_assert(not data.has("giver_npc_template_id"), "choosing 'No giver' removes the key")
	result = manager.save_all()
	var saved: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))[REAL_ID]
	_assert(saved["objective"]["possible_target_template_ids"] == ["giant_rat", "giant_spider", "goblin"], "the targets were saved")
	_assert(not '6.0' in FileAccess.get_file_as_string(path), "the range is saved as integers on disk")
	_assert(saved["objective"]["type"] == "clear_region", "the objective type survives")

	print("\n[a template without optional sections]")
	manager.add_quest("bare_instance", {"_filename": "instances.json", "type": "instance", "objective": {"type": "clear_region", "possible_target_template_ids": ["giant_rat"]}})
	var bare_before := JSON.stringify(manager.quests["bare_instance"])
	holder = _inspect(manager, "bare_instance")
	_assert(JSON.stringify(manager.quests["bare_instance"]) == bare_before, "opening adds no empty rewards or layout")
	(holder.find_child("Xp", true, false) as SpinBox).value = 40
	_assert(manager.quests["bare_instance"].get("rewards", {}) == {"xp": 40}, "the first reward edit attaches the rewards section")

	_assert(_python_validator_accepts(repo), "the edited fixture passes the engine's content-set validation")

	if failures > 0:
		push_error("instance quest authoring failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _check_the_library_separates_instance_templates(manager: DatabaseManager):
	print("\n[library categories]")
	var library = Library.new()
	library.cached_quests = manager.quests
	library.category = "instance_quest"
	_assert(library._get_current_entries().keys() == [REAL_ID], "Instance Quests lists only the instance template")
	_assert(library._storage_type() == "quest", "and stores it as a quest")
	library.category = "quest"
	_assert(not library._get_current_entries().has(REAL_ID), "Quests no longer lists it")
	_assert(library._get_current_entries().size() == manager.quests.size() - 1, "but still lists every other quest")
	library.free()


func _python_validator_accepts(repo: String) -> bool:
	var output: Array = []
	var python := repo.path_join(".venv/Scripts/python.exe")
	if not FileAccess.file_exists(python): python = repo.path_join(".venv/bin/python")
	var code := OS.execute(python, [repo.path_join("toolkit/content_set_validator.py"), fixture], output, true)
	if code != 0: print("\n".join(output))
	return code == 0


func _inspect(manager: DatabaseManager, id: String) -> Node:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	InstanceQuestInspector.new(holder, manager).build(id, manager.quests[id])
	return holder


func _missing(node: Node) -> Array:
	var out: Array = []
	if node is OptionButton:
		for index in range(node.item_count):
			if str(node.get_item_text(index)).begins_with("Missing:"): out.append(node.get_item_text(index))
	for child in node.get_children(): out.append_array(_missing(child))
	return out


func _picker_with_metadata(node: Node, value: String) -> OptionButton:
	if node is OptionButton and node.selected >= 0 and str(node.get_item_metadata(node.selected)) == value and str(node.get_item_text(0)) == "Choose creature":
		return node
	for child in node.get_children():
		var found := _picker_with_metadata(child, value)
		if found != null: return found
	return null


func _pick(picker: OptionButton, value: String):
	for index in range(picker.item_count):
		if str(picker.get_item_metadata(index)) == value:
			picker.select(index); picker.item_selected.emit(index); return
	_assert(false, "picker offers '%s'" % value)


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
