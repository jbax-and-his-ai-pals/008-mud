# tests/scene_authoring_smoke.gd
#
# Scenes (`data/scenes/*.json`, `engine/world/scenes.py`) are authorable: something the player watches, a few beats
# told a moment apart with things happening between them. The Content Library lists them, the inspector edits each
# beat's text, wait, pace and effects, opening one writes nothing, a default is erased rather than written, and
# the engine's own validator accepts what was saved.
#
#   godot --headless --path mud-world-editor --script tests/scene_authoring_smoke.gd

extends SceneTree

const SceneInspector = preload("res://scripts/ui/inspectors/sub_inspectors/SceneInspector.gd")
const SCENE := "the_watch"

var failures := 0
var fixture := ""


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/scene-authoring-%s/story_fixture" % Time.get_ticks_usec())
	_copy(repo.path_join("server/tests/sets/story_fixture"), fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "test fixture"

	print("\n[a new scene is valid before anything is typed]")
	var manager := DatabaseManager.new()
	_assert(manager.get_scene_ids().is_empty(), "a set with no scenes starts with none")
	manager.add_scene(SCENE, SceneInspector.data_defaults())
	_assert(manager.scenes.has(SCENE) and manager.dirty_flags["scene"].has(SCENE), "adding one marks it dirty")
	_assert(manager.save_all().get("ok", false), "it saves")
	var path := DataRoot.content_dir("scenes").path_join("custom.json")
	_assert(FileAccess.file_exists(path), "into data/scenes/custom.json, where a new entry goes")
	var original := FileAccess.get_file_as_string(path)

	print("\n[opening writes nothing]")
	manager = DatabaseManager.new()
	_assert(manager.get_scene_ids() == [SCENE], "the saved scene is loaded by its id")
	var before := JSON.stringify(manager.scenes[SCENE])
	var holder := _open(manager)
	_assert(JSON.stringify(manager.scenes[SCENE]) == before, "building the inspector changes nothing")
	_assert(holder.find_child("Beat0", true, false) != null, "the beat has a card")
	manager.mark_dirty("scene", SCENE)
	manager.save_all()
	_assert(FileAccess.get_file_as_string(path) == original, "an unedited save is byte-identical")

	print("\n[editing]")
	manager = DatabaseManager.new()
	var scene: Dictionary = manager.scenes[SCENE]
	holder = _open(manager)
	var first: Node = holder.find_child("Beat0", true, false)
	var text: TextEdit = first.find_child("Text", true, false)
	_assert(text.text == "Something happens." and (first.find_child("After", true, false) as SpinBox).value == 0.0, "the beat shows its text and the default first wait (0)")
	text.text = "The bell tolls once."; text.text_changed.emit()
	_assert(scene["beats"][0]["text"] == "The bell tolls once.", "editing the words is written")
	_assert(not scene["beats"][0].has("after"), "and the untouched wait is not")

	holder.find_child("AddBeat", true, false).pressed.emit()
	_assert((scene["beats"] as Array).size() == 2 and scene["beats"][1] == {"text": ""}, "adding a beat appends an empty one")
	var second: Node = holder.find_child("Beat1", true, false)
	_assert(second != null and (second.find_child("After", true, false) as SpinBox).value == 2.0, "it shows the default wait between beats (2)")
	(second.find_child("Text", true, false) as TextEdit).text = "A second bell."; (second.find_child("Text", true, false) as TextEdit).text_changed.emit()
	var after: SpinBox = second.find_child("After", true, false)
	after.value = 4; after.value_changed.emit(4.0)
	_assert(scene["beats"][1]["after"] == 4 and typeof(scene["beats"][1]["after"]) == TYPE_INT, "a whole wait is written as a whole number: %s" % str(scene["beats"][1]["after"]))
	var pace: OptionButton = second.find_child("Pace", true, false)
	var slow := -1
	for i in range(pace.item_count):
		if str(pace.get_item_metadata(i)) == "slow": slow = i
	pace.select(slow); pace.item_selected.emit(slow)
	_assert(scene["beats"][1]["pace"] == "slow", "a pace is written by name")
	pace.select(0); pace.item_selected.emit(0)
	_assert(not scene["beats"][1].has("pace"), "and Instant erases it")
	pace.select(slow); pace.item_selected.emit(slow)

	_button(second, "AddEffect").pressed.emit()
	_assert(scene["beats"][1].get("effects") is Dictionary and not (scene["beats"][1]["effects"] as Dictionary).is_empty(), "a beat's effects use the same rows a conversation does: %s" % JSON.stringify(scene["beats"][1].get("effects")))

	_button(holder.find_child("Beat0", true, false), "MoveDown").pressed.emit()
	_assert(scene["beats"][0]["text"] == "A second bell." and scene["beats"][1]["text"] == "The bell tolls once.", "beats can be reordered")
	_button(holder.find_child("Beat0", true, false), "RemoveBeat").pressed.emit()
	_assert((scene["beats"] as Array).size() == 1 and scene["beats"][0]["text"] == "The bell tolls once.", "and removed")
	holder.find_child("AddBeat", true, false).pressed.emit()
	(holder.find_child("Beat1", true, false).find_child("Text", true, false) as TextEdit).text = "A third."
	(holder.find_child("Beat1", true, false).find_child("Text", true, false) as TextEdit).text_changed.emit()

	var lock: CheckBox = holder.find_child("SceneLock", true, false)
	_assert(lock.button_pressed and not scene.has("lock"), "a scene locks its player by default, and says nothing")
	lock.button_pressed = false; lock.toggled.emit(false)
	_assert(scene.get("lock") == false, "unticking it writes lock: false")
	lock.button_pressed = true; lock.toggled.emit(true)
	_assert(not scene.has("lock"), "and ticking it again erases the key")
	var note: LineEdit = holder.find_child("SceneNote", true, false)
	note.text = "the opening bells"; note.text_changed.emit(note.text)
	_assert(scene.get("note") == "the opening bells", "a note is written")

	manager.mark_dirty("scene", SCENE)
	_assert(manager.save_all().get("ok", false), "the edited scene saves")
	var saved = JSON.parse_string(FileAccess.get_file_as_string(path))
	_assert(saved[SCENE]["beats"].size() == 2 and saved[SCENE]["note"] == "the opening bells", "and the file carries it")

	print("\n[the engine's verdict]")
	_the_engine_accepts(repo)

	if failures > 0: push_error("scene authoring failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _open(manager: DatabaseManager) -> Node:
	var holder := VBoxContainer.new(); root.add_child(holder)
	var inspector := SceneInspector.new(holder, manager)
	inspector.build(SCENE, manager.scenes[SCENE])
	return holder


func _button(node: Node, button_name: String) -> Button:
	return node.find_child(button_name, true, false) as Button


func _the_engine_accepts(repo: String) -> void:
	var python := repo.path_join(".venv/Scripts/python.exe")
	if not FileAccess.file_exists(python): python = repo.path_join(".venv/bin/python")
	if not FileAccess.file_exists(python):
		print("  skip  no project Python interpreter found")
		return
	var output: Array = []
	var code := OS.execute(python, [repo.path_join("toolkit/content_set_validator.py"), fixture], output, true)
	if code != 0: print("    validator: ", "\n".join(output).right(800))
	_assert(code == 0, "the engine's validator accepts the saved scene")


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
