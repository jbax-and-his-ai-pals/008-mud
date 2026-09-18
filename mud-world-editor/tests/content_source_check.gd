# tests/content_source_check.gd
#
# Headless verification that the editor reads the shared content set and keeps
# its own bookkeeping out of it. Run with:
#
#   godot --headless --path mud-world-editor --script tests/content_source_check.gd
#
# Exits non-zero on failure, so it can gate a change the way the Python suite
# does. Touches no real content file for writing: the save path is exercised
# through a scratch region id whose sidecar is removed afterwards.

extends SceneTree

var failure_count := 0
var catalog: ContractCatalog

func _init() -> void:
	print("content root : ", DataRoot.describe())

	_check_resolution()
	_check_region_round_trip()
	_check_split_does_not_touch_content()
	_check_quest_positions()
	_check_contracts()

	if failure_count > 0:
		push_error("content source check failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)

func _check_contracts() -> void:
	print("\n[contracts]")
	catalog = ContractCatalog.new()
	var loaded := catalog.load_contracts()
	_assert(loaded, "contracts load through the shared content set: " + catalog.source_path)
	_assert(catalog.issues.is_empty(), "no contract problems: %s" % ", ".join(catalog.issues))
	_assert(catalog.schema_version == ContractCatalog.KNOWN_SCHEMA_VERSION,
		"content schema version matches the editor's (%d)" % catalog.schema_version)
	_assert(catalog.family_ids().size() > 0,
		"families are enumerable for inspectors (%d)" % catalog.family_ids().size())
	_assert(catalog.profile_ids().size() > 0,
		"generation profiles are enumerable (%d)" % catalog.profile_ids().size())

	# The editor resolves a family to engine behaviour exactly as the registry
	# does; if these disagreed, an inspector would offer a class the runtime
	# would not build.
	var stone_class := catalog.item_class_for_family("collectible_stone")
	_assert(stone_class == "Gem", "family resolves to its engine class ('%s')" % stone_class)
	_assert(catalog.generation_profile_for_family("collectible_stone") == "faceted_stone",
		"family resolves to its generation profile")
	print("  note: %s" % catalog.describe())


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		push_error("FAIL: " + message)

func _check_resolution() -> void:
	print("\n[resolution]")
	var root := DataRoot.root()
	_assert(root.contains("content_sets"), "resolves inside a content set: " + root)
	_assert(DirAccess.dir_exists_absolute(DataRoot.data_dir()), "content data directory exists")
	_assert(FileAccess.file_exists(DataRoot.ruleset_path()), "ruleset resolves: " + DataRoot.ruleset_path())
	_assert(DataRoot.content_dir("items").ends_with("items"), "content folders resolve under data/")
	_assert(DataRoot.region_editor_file("town").contains("editor"), "editor state resolves under editor/")

func _check_region_round_trip() -> void:
	print("\n[region round trip]")
	var manager := RegionManager.new()
	_assert(manager.load_region("town.json"), "town.json loads through the resolver")

	var rooms: Dictionary = manager.data.get("rooms", {})
	_assert(rooms.size() > 0, "region has rooms (%d)" % rooms.size())

	var positioned := 0
	for room_id in rooms:
		if rooms[room_id] is Dictionary and rooms[room_id].has("_editor_pos"):
			positioned += 1
	_assert(positioned == rooms.size(), "every room has a position after load (%d/%d)" % [positioned, rooms.size()])

	# The file the game reads must stay clean.
	var raw := FileAccess.get_file_as_string(DataRoot.content_dir("regions").path_join("town.json"))
	_assert(not raw.contains("\"_editor_"), "the canonical region file carries no editor keys")

func _check_split_does_not_touch_content() -> void:
	print("\n[editor state split]")
	var scratch_id := "__content_source_check__"
	var scratch := {
		"region_id": scratch_id,
		"rooms": {
			"a": {"name": "A", "exits": {}, "_editor_pos": [10, 20]},
			"b": {"name": "B", "exits": {}, "_editor_pos": [30, 40], "_editor_exit_layout": {"east": {"placement": "stacked"}}},
		},
	}
	EditorLayout.split_region(scratch_id, scratch)
	var sidecar := DataRoot.region_editor_file(scratch_id)
	_assert(FileAccess.file_exists(sidecar), "split writes a sidecar beside the content")

	var clean := EditorLayout.strip_region(scratch)
	var text := JSON.stringify(clean)
	_assert(not text.contains("_editor_"), "stripped content carries no editor keys")
	_assert(text.contains("\"exits\""), "stripped content keeps real room data")

	var reloaded := EditorLayout.merge_region(scratch_id, clean.duplicate(true))
	_assert(reloaded["rooms"]["a"].has("_editor_pos"), "merge restores positions")
	_assert(reloaded["rooms"]["b"].has("_editor_exit_layout"), "merge restores exit layout")

	if FileAccess.file_exists(sidecar):
		DirAccess.remove_absolute(sidecar)
	_assert(not FileAccess.file_exists(sidecar), "scratch sidecar cleaned up")

func _check_quest_positions() -> void:
	print("\n[quest layout]")
	# Remember what was there before touching shared editor state.
	var layout_path := DataRoot.editor_file("quest_layout.json")
	var had_layout := FileAccess.file_exists(layout_path)
	var previous := FileAccess.get_file_as_string(layout_path) if had_layout else ""

	var quests := {
		"quest_example": {
			"title": "Example",
			"stages": [
				{"description": "One", "_editor_pos": [0, 0]},
				{"description": "Two", "_editor_pos": [250, 0]},
			],
		},
	}
	EditorLayout.split_quests(quests)
	_assert(FileAccess.file_exists(layout_path), "quest positions are written beside the quests")

	var stripped := EditorLayout.strip_quests(quests)
	_assert(not JSON.stringify(stripped).contains("_editor_"), "stripped quests carry no editor keys")
	_assert(JSON.stringify(stripped).contains("One"), "stripped quests keep their stages")

	var merged := EditorLayout.merge_quests(stripped.duplicate(true))
	_assert(merged["quest_example"]["stages"][1].has("_editor_pos"), "quest positions merge back")

	# `editor/quest_layout.json` is shared editor state, so put back whatever was
	# there: a self-check must not edit the author's layout.
	if had_layout:
		var file := FileAccess.open(layout_path, FileAccess.WRITE)
		if file:
			file.store_string(previous)
			file.close()
		_assert(FileAccess.get_file_as_string(layout_path) == previous, "existing quest layout restored")
	else:
		DirAccess.remove_absolute(layout_path)
		_assert(not FileAccess.file_exists(layout_path), "scratch quest layout cleaned up")
