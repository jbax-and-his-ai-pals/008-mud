# tests/encounter_authoring_smoke.gd
#
# Encounter zones (`data/encounters/*.json`, `engine/world/encounters.py`) are authorable: somewhere walking is dangerous.
# The Content Library lists them, the inspector edits the region and rooms, what may come with its weight, the chance, how
# many and the line said; opening one writes nothing, a cleared field is erased rather than written, and the engine's own
# validator accepts what was saved.
#
#   godot --headless --path mud-world-editor --script tests/encounter_authoring_smoke.gd

extends SceneTree

const EncounterInspector = preload("res://scripts/ui/inspectors/sub_inspectors/EncounterInspector.gd")
const ZONE := "near_the_gate"

var failures := 0
var fixture := ""


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/encounter-authoring-%s/story_fixture" % Time.get_ticks_usec())
	_copy(repo.path_join("server/tests/sets/story_fixture"), fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "test fixture"

	print("\n[text and rows]")
	_assert(EncounterInspector.monsters_text(["slime", {"npc": "drakee", "weight": 3}]) == "slime, drakee:3", "monsters are read as 'id, id:weight'")
	_assert(EncounterInspector.monsters_from_text("slime, drakee:3, ghost:1") == ["slime", {"npc": "drakee", "weight": 3}, "ghost"], "and written back, a weight of 1 left off")

	print("\n[a new zone is valid before anything is typed]")
	var manager := DatabaseManager.new()
	_assert(manager.get_encounter_ids().is_empty(), "a set with no zones starts with none")
	var some_region := ""
	var refs := preload("res://scripts/ui/inspectors/sub_inspectors/TriggerInspector.gd").room_refs()
	some_region = str(refs[0]).split(":")[0] if not refs.is_empty() else ""
	var some_monster := ""
	for npc_id in manager.npcs: some_monster = str(npc_id); break
	manager.add_encounter(ZONE, EncounterInspector.data_defaults(some_region, some_monster))
	_assert(manager.encounters.has(ZONE) and manager.dirty_flags["encounter"].has(ZONE), "adding one marks it dirty")
	_assert(manager.save_all().get("ok", false), "it saves")
	var path := DataRoot.content_dir("encounters").path_join("custom.json")
	_assert(FileAccess.file_exists(path), "into data/encounters/custom.json, where a new entry goes")
	var original := FileAccess.get_file_as_string(path)

	print("\n[opening writes nothing]")
	manager = DatabaseManager.new()
	_assert(manager.get_encounter_ids() == [ZONE], "the saved zone is loaded by its id")
	var before := JSON.stringify(manager.encounters[ZONE])
	var holder := _open(manager)
	_assert(JSON.stringify(manager.encounters[ZONE]) == before, "building the inspector changes nothing")
	manager.mark_dirty("encounter", ZONE)
	manager.save_all()
	_assert(FileAccess.get_file_as_string(path) == original, "an unedited save is byte-identical")

	print("\n[editing]")
	manager = DatabaseManager.new()
	var zone: Dictionary = manager.encounters[ZONE]
	holder = _open(manager)
	_edit(holder, "EncounterRooms", "gate, road")
	_assert(zone["rooms"] == ["gate", "road"], "rooms are a list")
	_edit(holder, "EncounterRooms", "")
	_assert(not zone.has("rooms"), "and empty, erased: the whole region")
	_edit(holder, "EncounterMonsters", "%s:3, %s" % [some_monster, some_monster])
	_assert(zone["monsters"].size() == 2 and zone["monsters"][0] == {"npc": some_monster, "weight": 3}, "monsters are written with their weights")
	_spin(holder, "EncounterChance", 0.35)
	_assert(is_equal_approx(float(zone["chance"]), 0.35), "the chance is written")
	_spin(holder, "EncounterLeast", 1)
	_spin(holder, "EncounterMost", 3)
	_assert(zone["count"] == [1, 3], "how many is [least, most]")
	_spin(holder, "EncounterMost", 1)
	_assert(not zone.has("count"), "one is the default, so the key is erased")
	_spin(holder, "EncounterCooldown", 20)
	_assert(int(zone["cooldown"]) == 20, "a cooldown is written")
	_spin(holder, "EncounterCooldown", 0)
	_assert(not zone.has("cooldown"), "and 0 erased")
	_edit(holder, "EncounterMessage", "{name} springs out!")
	_assert(zone["message"] == "{name} springs out!", "the words said are written")
	var gate := holder.find_child("EncounterWhen", true, false)
	_assert(gate != null and not zone.has("when"), "a zone with no condition is always live")
	var picker := gate.find_child("ConditionPicker", true, false) as OptionButton
	for index in range(picker.item_count):
		if picker.get_item_text(index) == "flag": picker.select(index); picker.item_selected.emit(index)
	_assert(zone.get("when") == {"kind": "flag"}, "a condition can be set: %s" % str(zone.get("when")))
	zone["when"] = {"not": {"kind": "flag", "flag": "won"}}
	manager.mark_dirty("encounter", ZONE)
	_assert(manager.save_all().get("ok", false), "the edited zone saves")

	print("\n[keys it does not model survive]")
	zone["wind"] = "north"
	holder = _open(manager)
	_assert(zone["wind"] == "north", "an unknown key stays")

	print("\n[the engine's verdict]")
	zone.erase("wind")
	manager.mark_dirty("encounter", ZONE)
	manager.save_all()
	_the_engine_accepts(repo)

	if failures > 0: push_error("encounter authoring failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _open(manager: DatabaseManager) -> Node:
	var holder := VBoxContainer.new(); root.add_child(holder)
	var inspector := EncounterInspector.new(holder, manager)
	inspector.build(ZONE, manager.encounters[ZONE])
	return holder


func _edit(holder: Node, field_name: String, text: String) -> void:
	var field: LineEdit = holder.find_child(field_name, true, false)
	field.text = text; field.text_changed.emit(text)


func _spin(holder: Node, field_name: String, value: float) -> void:
	var field: SpinBox = holder.find_child(field_name, true, false)
	field.value = value
	field.value_changed.emit(value)


func _the_engine_accepts(repo: String) -> void:
	var python := repo.path_join(".venv/Scripts/python.exe")
	if not FileAccess.file_exists(python): python = repo.path_join(".venv/bin/python")
	if not FileAccess.file_exists(python):
		print("  skip  no project Python interpreter found")
		return
	var output: Array = []
	var code := OS.execute(python, [repo.path_join("toolkit/content_set_validator.py"), fixture], output, true)
	if code != 0: print("    validator: ", "\n".join(output).right(800))
	_assert(code == 0, "the engine's validator accepts the saved zone")


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
