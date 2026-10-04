# tests/editor_start_region_smoke.gd
#
# The editor opens on the region new players start in, as the manifest says, not on
# whichever region file sorts first. `ff4_slice` starts in Ilmara (`ilmara`)
# and its alphabetically first region is a cave.
#
#   godot --headless --path mud-world-editor --script tests/editor_start_region_smoke.gd

extends SceneTree

var failures := 0


func _initialize() -> void:
	var repo_root := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var expected := {
		"ff4_slice": "ilmara.json",
		"zelda_slice": "aldermark.json",
		"fantasy_frontier": "town.json",
		"orbital_salvage": "station.json",
	}
	# Main's own method, without building the whole editor around it.
	var main = load("res://scripts/core/Main.gd").new()
	for set_id in expected:
		DataRoot._resolved = repo_root.path_join("content_sets").path_join(set_id)
		DataRoot._source = "start region smoke"
		var opened: String = main._start_region_filename()
		_assert(opened == expected[set_id], "%s opens on %s (got %s)" % [set_id, expected[set_id], opened])
	DataRoot._resolved = ""
	DataRoot._source = ""
	main.free()
	if failures > 0: push_error("editor start region smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _assert(condition: bool, message: String) -> void:
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
