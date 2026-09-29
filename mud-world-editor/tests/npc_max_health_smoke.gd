# tests/npc_max_health_smoke.gd
#
# A template's `max_health` (`engine/npcs/npc_factory.py`) is the creature's maximum; the
# NPC panel now offers it beside the starting health. 0 is "not authored": it erases the
# key, so opening or leaving the field alone never writes anything.
#
#   godot --headless --path mud-world-editor --script tests/npc_max_health_smoke.gd

extends SceneTree

const NPC := "slime_blob"

var failures := 0


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var fixture := repo.path_join("tmp/npc-max-health-%s/zelda_slice" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/zelda_slice"), fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "test fixture"
	var path := DataRoot.content_dir("npcs").path_join("hostiles.json")
	var original := FileAccess.get_file_as_string(path)

	print("\n[opening writes nothing]")
	var manager := DatabaseManager.new()
	var before := JSON.stringify(manager.npcs[NPC])
	var holder := _open(manager)
	_assert(JSON.stringify(manager.npcs[NPC]) == before, "building the panel changes nothing")
	var field: SpinBox = holder.find_child("MaxHealth", true, false)
	_assert(field != null, "there is a Max Health field")
	_assert(int(field.value) == int(manager.npcs[NPC].get("max_health", 0)), "it shows what the file holds")
	manager.mark_dirty("npc", NPC)
	manager.save_all()
	_assert(FileAccess.get_file_as_string(path) == original, "an unedited save is byte-identical")

	print("\n[editing]")
	manager = DatabaseManager.new()
	holder = _open(manager)
	field = holder.find_child("MaxHealth", true, false)
	field.value = 64
	field.value_changed.emit(64.0)
	_assert(manager.npcs[NPC].get("max_health") == 64 and typeof(manager.npcs[NPC]["max_health"]) == TYPE_INT,
		"a value is written as a whole number: %s" % str(manager.npcs[NPC].get("max_health")))
	field.value = 0
	field.value_changed.emit(0.0)
	_assert(not manager.npcs[NPC].has("max_health"), "0 erases the key (the derived figure applies)")
	field.value = 40
	field.value_changed.emit(40.0)
	manager.mark_dirty("npc", NPC)
	_assert(manager.save_all().get("ok", false), "the edited template saves")
	var saved = JSON.parse_string(FileAccess.get_file_as_string(path))
	_assert(saved[NPC]["max_health"] == 40, "and the file carries it")

	if failures > 0: push_error("npc max health failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _open(manager: DatabaseManager) -> Node:
	var holder := VBoxContainer.new(); root.add_child(holder)
	var inspector := DatabaseInspector.new(holder)
	inspector.set_db_manager(manager)
	inspector.build("npc", NPC, manager.npcs[NPC])
	return holder


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
