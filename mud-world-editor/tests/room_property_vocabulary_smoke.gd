# tests/room_property_vocabulary_smoke.gd
#
# A room's properties are an open bag: any key is kept, and one nothing reads
# does nothing in play. RoomPropertiesPanel now names such keys under the tags
# (the ruleset's custody keys count as read), and its quick-add menu no longer
# offers `music`, which nothing reads. fantasy_frontier's ruleset is the
# fixture for the custody key.
#
#   godot --headless --path mud-world-editor --script tests/room_property_vocabulary_smoke.gd

extends SceneTree

var failures := 0
var panels: Array = []


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	DataRoot._resolved = repo.path_join("content_sets/fantasy_frontier")
	DataRoot._source = "test fixture"

	print("\n[unread keys]")
	var props := {"dark": true, "indoors": true, "underwater": true, "is_jail_cell": true, "_district_id": "docks", "icon": "tower"}
	var before := JSON.stringify(props)
	var holder := _panel(props)
	_assert(JSON.stringify(props) == before, "building the panel writes nothing")
	var note: Label = holder.find_child("UnreadRoomKeys", true, false)
	_assert(note != null and note.text.ends_with("indoors, underwater"), "keys nothing reads are named: %s" % (note.text if note else "(no note)"))
	_assert(note != null and not "is_jail_cell" in note.text, "the ruleset's custody key counts as read")
	_assert(note != null and not "_district_id" in note.text and not "icon" in note.text, "annotations and the editor's own map keys are not flagged")
	_assert(_panel({"dark": true, "outdoors": false}).find_child("UnreadRoomKeys", true, false) == null, "a room with only read keys shows no note")

	print("\n[quick-add menu]")
	var panel: RoomPropertiesPanel = panels[0]
	var offered: Array = []
	for index in range(panel.popup_menu.item_count): offered.append(panel.popup_menu.get_item_text(index))
	_assert(not "Music" in offered, "Music is no longer offered (nothing reads it)")
	for label in RoomPropertiesPanel.COMMON_PROPS:
		var key := str(RoomPropertiesPanel.COMMON_PROPS[label]["key"])
		_assert(RoomPropertiesPanel.ROOM_PROPERTY_KINDS.has(key), "the quick-add '%s' is a key something reads" % label)

	if failures > 0: push_error("room property vocabulary failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _panel(props: Dictionary) -> Node:
	var holder := VBoxContainer.new(); root.add_child(holder)
	var panel := RoomPropertiesPanel.new(); panels.append(panel)
	panel.build(holder, props)
	return holder


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
