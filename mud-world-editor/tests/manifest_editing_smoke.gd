# tests/manifest_editing_smoke.gd
#
# Changing a content set's start and capabilities after it exists.
#
# This is batch 6B's gate in one test: until now the manifest was written once by
# the scaffold and never again, so an author who wanted a different start room, or
# to turn a system on, edited JSON by hand. Three things have to hold, and each has
# a way of going wrong that this checks:
#
#   * the form writes only what it owns -- an unrelated edit must not reorder,
#     renumber or drop the fields it does not show;
#   * the engine decides, not the form -- a capability that contradicts the
#     ruleset must be refused, with the engine's message and nothing written;
#   * the id and the paths are not editable here, and a draft cannot smuggle them.
#
# Run with:
#
#   godot --headless --path mud-world-editor --script tests/manifest_editing_smoke.gd -- --python <interp>

extends SceneTree

const DraftScript = preload("res://scripts/data/ManifestDraft.gd")
const DialogScript = preload("res://scripts/ui/modals/ManifestEditorDialog.gd")

var failures := 0
var fixture := ""
var manifest_path := ""

func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	fixture = repo.path_join("tmp/manifest-editing-%s/orbital_salvage" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/orbital_salvage"), fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "manifest editing smoke"
	manifest_path = fixture.path_join("content_set.manifest.json")

	_check_the_draft_owns_only_what_it_shows()
	_check_an_unrelated_edit_preserves_everything_else()
	_check_the_engine_refuses_a_contradictory_capability()
	_check_the_id_and_paths_cannot_be_smuggled()
	_check_the_dialog_writes_through_the_form()

	_remove_recursive(fixture)
	if failures > 0:
		push_error("manifest editing smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


# --- the checks ---------------------------------------------------------------

func _check_the_draft_owns_only_what_it_shows() -> void:
	print("\n[the draft owns only what it shows]")
	var draft = DraftScript.new()
	var loaded: Dictionary = draft.open(manifest_path)
	_assert(loaded.get("ok", false), "the manifest loads: %s" % loaded.get("error", ""))
	_assert(draft.capabilities().has("combat"), "the shipped capabilities are read")
	_assert(draft.start_field("room_id") == "dock_ring", "and the start room: %s" % draft.start_field("room_id"))
	_assert(draft.title_value() == "Orbital Salvage", "and the title")


func _check_an_unrelated_edit_preserves_everything_else() -> void:
	print("\n[an unrelated edit preserves everything else]")
	var before := _read_raw(manifest_path)
	var draft = _open_draft()
	draft.set_title("Orbital Salvage (edited)")
	var result: Dictionary = draft.save()
	_assert(result.get("ok", false), "the title saves: %s" % result.get("error", ""))
	var after := _read_json(manifest_path)
	var original: Dictionary = JSON.parse_string(before)
	_assert(after["title"] == "Orbital Salvage (edited)", "the title changed")
	_assert(after["id"] == original["id"], "the id did not")
	_assert(after["paths"] == original["paths"], "the paths did not")
	_assert(after["start"] == original["start"], "the start did not")
	_assert(after["capabilities"] == original["capabilities"], "the capabilities did not, and kept their order")
	_assert(after["manifest_schema_version"] == original["manifest_schema_version"]
		and after["engine_api_min"] == original["engine_api_min"], "the version fields did not")
	_assert(FileAccess.file_exists(manifest_path + ".bak"), "the previous manifest is kept as .bak")

	var reopened = _open_draft()
	_assert(not reopened.is_dirty(), "reopening a saved manifest is clean")


func _check_the_engine_refuses_a_contradictory_capability() -> void:
	print("\n[the engine refuses a contradictory capability]")
	var before := _read_raw(manifest_path)
	var draft = _open_draft()
	var without_combat: Array = []
	for capability in draft.capabilities():
		if str(capability) != "combat":
			without_combat.append(capability)
	draft.set_capabilities(without_combat)
	var result: Dictionary = draft.save()
	_assert(not result.get("ok", true), "dropping a capability the ruleset enables is refused")
	_assert(str(result.get("error", "")).contains("combat"),
		"and the refusal names it: %s" % str(result.get("error", "")).left(160))
	_assert(_read_raw(manifest_path) == before, "and nothing was written")

	var form_errors: Array = draft.validate()
	_assert(form_errors.is_empty(),
		"the form itself had no objection -- the refusal came from the engine: %s" % str(form_errors))


func _check_the_id_and_paths_cannot_be_smuggled() -> void:
	print("\n[the id and paths cannot be smuggled through the draft]")
	var draft = _open_draft()
	draft.data["id"] = "renamed_identity"
	var errors: Array = draft.validate()
	_assert(not errors.is_empty(), "a changed id is refused by the draft")
	_assert(str(errors).contains("directory name"), "and says why: %s" % str(errors))

	var empty_start = _open_draft()
	empty_start.set_start("first_watch", "station", "")
	_assert(not empty_start.validate().is_empty(), "an empty start room is refused before saving")

	var unknown_capability = _open_draft()
	unknown_capability.set_capabilities(["inventory", "telepathy"])
	_assert(str(unknown_capability.validate()).contains("telepathy"),
		"a capability the engine does not know is refused: %s" % str(unknown_capability.validate()))


func _check_the_dialog_writes_through_the_form() -> void:
	# The dialog is where an author actually is, so the last check drives it: the
	# same guarantees must hold when the edit arrives through a control.
	print("\n[the dialog writes through the form]")
	var dialog = DialogScript.new()
	root.add_child(dialog)
	dialog.setup()
	dialog.open_active()
	_assert(dialog.draft != null, "the dialog loads the manifest")
	_assert(dialog.get_ok_button().disabled, "and opens clean: Save starts disabled")

	var before := _read_raw(manifest_path)
	dialog.region_field.text = "station"
	dialog.room_field.text = "workshop"
	dialog._mark_dirty()
	_assert(not dialog.get_ok_button().disabled, "editing the start enables Save")
	dialog._save()
	var after := _read_json(manifest_path)
	_assert(after["start"]["room_id"] == "workshop",
		"the start room is written: %s" % str(after["start"]))
	_assert(after["title"] == JSON.parse_string(before)["title"], "and nothing else moved")
	_assert(dialog.get_ok_button().disabled, "after a save the form is clean again")

	# A start the engine cannot place is refused and the draft is kept: the whole
	# point of routing this form through the staged verdict is that a form which
	# looks fine can still be wrong.
	dialog.room_field.text = "no_such_room"
	dialog._mark_dirty()
	dialog._save()
	_assert(_read_json(manifest_path)["start"]["room_id"] == "workshop",
		"a start room the set does not have is refused, and the saved file is unchanged")
	_assert(not dialog.get_ok_button().disabled, "the draft is kept so it can be fixed")
	dialog.room_field.text = "workshop"
	dialog._mark_dirty()

	var keep := _read_raw(manifest_path)
	dialog.room_field.text = ""
	dialog._mark_dirty()
	dialog._save()
	_assert(_read_raw(manifest_path) == keep, "an empty start room writes nothing")


# --- helpers ------------------------------------------------------------------

## A draft over the fixture's manifest. An instance, not a static factory: a new
## `class_name` cannot name itself until the project has scanned it.
func _open_draft():
	var draft = DraftScript.new()
	draft.open(manifest_path)
	return draft

func _read_raw(path: String) -> String:
	return FileAccess.get_file_as_string(path)


func _read_json(path: String) -> Dictionary:
	var parsed = JSON.parse_string(_read_raw(path))
	return parsed if parsed is Dictionary else {}


func _assert(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error("FAIL: " + message)
	else:
		print("  ok: " + message)


func _copy(from: String, to: String) -> void:
	DirAccess.make_dir_recursive_absolute(to)
	var dir := DirAccess.open(from)
	if dir == null:
		push_error("could not open %s" % from)
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			if dir.current_is_dir():
				_copy(from.path_join(name), to.path_join(name))
			else:
				DirAccess.copy_absolute(from.path_join(name), to.path_join(name))
		name = dir.get_next()
	dir.list_dir_end()


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null: return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			if dir.current_is_dir():
				_remove_recursive(path.path_join(name))
			else:
				DirAccess.remove_absolute(path.path_join(name))
		name = dir.get_next()
	dir.list_dir_end()
	DirAccess.remove_absolute(path)
