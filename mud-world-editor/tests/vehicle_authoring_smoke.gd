# tests/vehicle_authoring_smoke.gd
#
# Vehicles (`data/vehicles/*.json`, `engine/world/vehicles.py`) are authorable: something the player boards to go where
# they cannot go on foot. The Content Library lists them, the inspector edits the name, the words, where it waits at the
# start and the biomes it may be set down in, opening one writes nothing, a cleared field is erased rather than written,
# and the engine's own validator accepts what was saved.
#
#   godot --headless --path mud-world-editor --script tests/vehicle_authoring_smoke.gd

extends SceneTree

const VehicleInspector = preload("res://scripts/ui/inspectors/sub_inspectors/VehicleInspector.gd")
const VEHICLE := "skimmer"

var failures := 0
var fixture := ""


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/vehicle-authoring-%s/story_fixture" % Time.get_ticks_usec())
	_copy(repo.path_join("server/tests/sets/story_fixture"), fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "test fixture"

	print("\n[a new vehicle is valid before anything is typed]")
	var manager := DatabaseManager.new()
	_assert(manager.get_vehicle_ids().is_empty(), "a set with no vehicles starts with none")
	manager.add_vehicle(VEHICLE, VehicleInspector.data_defaults())
	_assert(manager.vehicles.has(VEHICLE) and manager.dirty_flags["vehicle"].has(VEHICLE), "adding one marks it dirty")
	_assert(manager.save_all().get("ok", false), "it saves")
	var path := DataRoot.content_dir("vehicles").path_join("custom.json")
	_assert(FileAccess.file_exists(path), "into data/vehicles/custom.json, where a new entry goes")
	var original := FileAccess.get_file_as_string(path)

	print("\n[opening writes nothing]")
	manager = DatabaseManager.new()
	_assert(manager.get_vehicle_ids() == [VEHICLE], "the saved vehicle is loaded by its id")
	var before := JSON.stringify(manager.vehicles[VEHICLE])
	var holder := _open(manager)
	_assert(JSON.stringify(manager.vehicles[VEHICLE]) == before, "building the inspector changes nothing")
	manager.mark_dirty("vehicle", VEHICLE)
	manager.save_all()
	_assert(FileAccess.get_file_as_string(path) == original, "an unedited save is byte-identical")

	print("\n[editing]")
	manager = DatabaseManager.new()
	var vehicle: Dictionary = manager.vehicles[VEHICLE]
	holder = _open(manager)
	_edit(holder, "VehicleName", "the skimmer")
	_assert(vehicle["name"] == "the skimmer", "the name is written")
	_edit(holder, "VehicleDescription", "A flat craft that rides the sand.")
	_assert(vehicle["description"] == "A flat craft that rides the sand.", "a description is written")
	_edit(holder, "VehicleDescription", "")
	_assert(not vehicle.has("description"), "and cleared, erased")
	_edit(holder, "VehicleBoardText", "You climb aboard.")
	_edit(holder, "VehicleDisembarkText", "You climb down.")
	_assert(vehicle["board_text"] == "You climb aboard." and vehicle["disembark_text"] == "You climb down.", "the words said aboard and ashore are written")
	_edit(holder, "VehicleStartRegion", "hazevale")
	_edit(holder, "VehicleStartRoom", "shrine")
	_assert(vehicle["start"] == {"region": "hazevale", "room": "shrine"}, "where it waits is written as a pair")
	_edit(holder, "VehicleBiomes", "desert, plain")
	_assert(vehicle["lands_in_biomes"] == ["desert", "plain"], "the biomes it may be set down in are a list")
	_edit(holder, "VehicleNote", "for the desert crossing")
	_assert(vehicle["note"] == "for the desert crossing", "a note is written")
	manager.mark_dirty("vehicle", VEHICLE)
	_assert(manager.save_all().get("ok", false), "the edited vehicle saves")
	var saved = JSON.parse_string(FileAccess.get_file_as_string(path))
	_assert(saved[VEHICLE]["start"]["room"] == "shrine" and saved[VEHICLE]["lands_in_biomes"].size() == 2, "and the file carries it")

	print("\n[clearing]")
	_edit(holder, "VehicleBiomes", "")
	_edit(holder, "VehicleStartRegion", "")
	_edit(holder, "VehicleStartRoom", "")
	_assert(not vehicle.has("lands_in_biomes") and not vehicle.has("start"), "empty biomes and an empty start are erased, so it lands anywhere and starts nowhere")
	vehicle["wheels"] = 4
	holder = _open(manager)
	_assert(vehicle["wheels"] == 4, "a key the inspector does not model survives")

	print("\n[the engine's verdict]")
	_edit(holder, "VehicleStartRegion", "hazevale")
	_edit(holder, "VehicleStartRoom", "shrine")
	vehicle.erase("wheels")
	manager.mark_dirty("vehicle", VEHICLE)
	manager.save_all()
	_the_engine_accepts(repo)

	if failures > 0: push_error("vehicle authoring failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _open(manager: DatabaseManager) -> Node:
	var holder := VBoxContainer.new(); root.add_child(holder)
	var inspector := VehicleInspector.new(holder, manager)
	inspector.build(VEHICLE, manager.vehicles[VEHICLE])
	return holder


func _edit(holder: Node, field_name: String, text: String) -> void:
	var field: LineEdit = holder.find_child(field_name, true, false)
	field.text = text; field.text_changed.emit(text)


func _the_engine_accepts(repo: String) -> void:
	var python := repo.path_join(".venv/Scripts/python.exe")
	if not FileAccess.file_exists(python): python = repo.path_join(".venv/bin/python")
	if not FileAccess.file_exists(python):
		print("  skip  no project Python interpreter found")
		return
	var output: Array = []
	var code := OS.execute(python, [repo.path_join("toolkit/content_set_validator.py"), fixture], output, true)
	if code != 0: print("    validator: ", "\n".join(output).right(800))
	_assert(code == 0, "the engine's validator accepts the saved vehicle")


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
