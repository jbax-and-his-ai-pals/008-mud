# tests/campaign_authoring_smoke.gd
#
# Campaigns (`data/campaigns/*.json`, `engine/campaign/campaign_manager.py`)
# were loaded but never saveable (`DatabaseManager.gd`'s `save_all` skipped
# them entirely -- any edit made by hand-opening a campaign in a text editor
# and re-saving through the world editor would be silently discarded) and had
# no library category at all. See docs/plan/editor-coverage-ledger.md family G.
#
#   godot --headless --path mud-world-editor --script tests/campaign_authoring_smoke.gd
#
# This is envelope authoring only (id, name, description, start node): `nodes`
# is a branching graph (CampaignNode/CampaignTransition) preserved byte-for-
# byte and shown read-only, the same rule the generic item-property table
# follows for a shape nothing here writes yet.

extends SceneTree

var failure_count := 0
var scratch: String = ""


func _init() -> void:
	scratch = ProjectSettings.globalize_path("res://").path_join("../tmp/campaign_authoring")
	_rebuild_fixture()

	_check_a_shipped_campaign_loads_with_its_nodes_intact()
	_check_opening_and_resaving_a_campaign_is_byte_identical()
	_check_editing_the_envelope()
	_check_the_start_node_picker_offers_declared_nodes()
	_check_switching_the_start_node()
	_check_an_undeclared_start_node_is_shown_not_dropped()
	_check_creating_a_campaign_writes_its_own_file()
	_check_deleting_a_campaign_removes_its_file()

	if failure_count > 0:
		push_error("campaign authoring failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


func _check_a_shipped_campaign_loads_with_its_nodes_intact() -> void:
	print("\n[loading a real shipped campaign]")
	var manager := _manager()
	_assert(manager.campaigns.has("bandit_rebellion"), "fantasy_frontier's bandit_rebellion campaign loaded")
	var nodes: Dictionary = manager.campaigns.get("bandit_rebellion", {}).get("nodes", {})
	_assert(not nodes.is_empty(), "its nodes graph loaded too")


func _check_opening_and_resaving_a_campaign_is_byte_identical() -> void:
	print("\n[opening and resaving without editing]")
	var manager := _manager()
	var path := DataRoot.content_dir("campaigns").path_join("bandit_rebellion.json")
	var before := FileAccess.get_file_as_string(path)
	_build_inspector_from("bandit_rebellion", manager)
	var result: Dictionary = manager.save_all()
	_assert(result.get("ok", false), "the save reported ok: %s" % str(result.get("errors", [])))
	_assert(FileAccess.get_file_as_string(path) == before, "opening the panel and saving changed nothing")


func _check_editing_the_envelope() -> void:
	print("\n[editing name/description]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_probe_campaign", manager)
	var name_field := _line_edit_after_label(holder, "Name:")
	_edit(name_field, "The Renamed Uprising")
	_assert(manager.campaigns["npc_probe_campaign"]["name"] == "The Renamed Uprising", "the name was written")
	var desc_field := _first_text_edit(holder)
	desc_field.text = "A new synopsis."
	desc_field.text_changed.emit()
	_assert(manager.campaigns["npc_probe_campaign"]["description"] == "A new synopsis.", "the description was written")


func _check_the_start_node_picker_offers_declared_nodes() -> void:
	print("\n[the start node picker]")
	var holder := _build_inspector("npc_probe_campaign")
	var picker := _start_node_picker(holder)
	_assert(picker != null, "the picker was found")
	var offered := _picker_ids(picker)
	_assert(offered == ["end", "start"], "it offers every declared node, sorted (%s)" % str(offered))
	_assert(str(picker.get_item_metadata(picker.selected)) == "start", "it preselects the authored start_node_id")


func _check_switching_the_start_node() -> void:
	print("\n[switching the start node]")
	var manager := _manager()
	var holder := _build_inspector_from("npc_probe_campaign", manager)
	var picker := _start_node_picker(holder)
	var index := _index_for_id(picker, "end")
	picker.item_selected.emit(index)
	_assert(manager.campaigns["npc_probe_campaign"]["start_node_id"] == "end", "the new start node was written")


func _check_an_undeclared_start_node_is_shown_not_dropped() -> void:
	print("\n[a start_node_id nothing declares]")
	var holder := _build_inspector("npc_probe_bad_start")
	var picker := _start_node_picker(holder)
	_assert(str(picker.get_item_metadata(picker.selected)) == "nowhere", "the undeclared start node stays selected")
	_assert(str(picker.text).begins_with("Missing:"), "and is shown as missing (%s)" % picker.text)


func _check_creating_a_campaign_writes_its_own_file() -> void:
	print("\n[creating a new campaign]")
	var manager := _manager()
	var fresh := {
		"campaign_id": "fresh_saga", "name": "New Campaign", "description": "",
		"start_node_id": "start",
		"nodes": {"start": {"description": "The story ends.", "type": "END", "outcome": "complete"}},
	}
	manager.add_campaign("fresh_saga", fresh)
	var result: Dictionary = manager.save_all()
	_assert(result.get("ok", false), "the save reported ok: %s" % str(result.get("errors", [])))
	var path := DataRoot.content_dir("campaigns").path_join("fresh_saga.json")
	_assert(FileAccess.file_exists(path), "a new file was written for the new campaign")
	var second := {"campaign_id": "second_saga", "name": "Second", "description": "", "start_node_id": "start", "nodes": {"start": {"description": "", "type": "END"}}}
	manager.add_campaign("second_saga", second)
	manager.save_all()
	_assert(FileAccess.file_exists(path), "the first new campaign's file is untouched by adding a second")
	_assert(FileAccess.file_exists(DataRoot.content_dir("campaigns").path_join("second_saga.json")), "and the second got its own file")


func _check_deleting_a_campaign_removes_its_file() -> void:
	print("\n[deleting a campaign]")
	var manager := _manager()
	var path := DataRoot.content_dir("campaigns").path_join("npc_probe_campaign.json")
	_assert(FileAccess.file_exists(path), "the campaign's file exists before deletion")
	manager.delete_entry("campaign", "npc_probe_campaign")
	var result: Dictionary = manager.save_all()
	_assert(result.get("ok", false), "the save after deletion reported ok")
	_assert(not FileAccess.file_exists(path), "its file was removed")
	_assert(FileAccess.file_exists(DataRoot.content_dir("campaigns").path_join("npc_probe_bad_start.json")), "an untouched campaign's file survives")


# --- fixture ----------------------------------------------------------------

func _rebuild_fixture() -> void:
	_remove_recursive(scratch)
	_copy_recursive(
		ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir().path_join("content_sets/fantasy_frontier"),
		scratch,
	)
	_write("data/campaigns/npc_probe_campaign.json", {
		"campaign_id": "npc_probe_campaign", "name": "Probe Uprising", "description": "A test campaign.",
		"start_node_id": "start",
		"nodes": {
			"start": {"description": "It begins.", "type": "QUEST", "quest_template_id": "quest_probe", "transitions": [{"trigger": "SUCCESS", "target_node_id": "end"}]},
			"end": {"description": "It ends.", "type": "END", "outcome": "complete"},
		},
	})
	_write("data/campaigns/npc_probe_bad_start.json", {
		"campaign_id": "npc_probe_bad_start", "name": "Broken Start", "description": "",
		"start_node_id": "nowhere",
		"nodes": {"start": {"description": "Unreachable.", "type": "END", "outcome": "complete"}},
	})


func _write(relative: String, payload: Dictionary) -> void:
	var path := scratch.path_join(relative)
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(payload, "  "))
	file.close()


func _copy_recursive(from_dir: String, to_dir: String) -> void:
	DirAccess.make_dir_recursive_absolute(to_dir)
	var dir := DirAccess.open(from_dir)
	if not dir:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			var from_path := from_dir.path_join(name)
			var to_path := to_dir.path_join(name)
			if dir.current_is_dir():
				if name != "editor" and name != "saves":
					_copy_recursive(from_path, to_path)
			else:
				DirAccess.copy_absolute(from_path, to_path)
		name = dir.get_next()
	dir.list_dir_end()


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if name != "." and name != "..":
			var child := path.path_join(name)
			if dir.current_is_dir():
				_remove_recursive(child)
			else:
				DirAccess.remove_absolute(child)
		name = dir.get_next()
	dir.list_dir_end()
	DirAccess.remove_absolute(path)


# --- harness ------------------------------------------------------------------

func _manager() -> DatabaseManager:
	DataRoot._resolved = scratch
	DataRoot._source = "test fixture"
	return DatabaseManager.new()


func _build_inspector(campaign_id: String) -> Node:
	return _build_inspector_from(campaign_id, _manager())


func _build_inspector_from(campaign_id: String, manager: DatabaseManager) -> Node:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	var inspector := CampaignInspector.new(holder, manager)
	inspector.build(campaign_id, manager.campaigns[campaign_id])
	return holder


func _line_edit_after_label(node: Node, label_text: String) -> LineEdit:
	var children := node.get_children()
	for index in range(children.size() - 1):
		if children[index] is Label and str(children[index].text) == label_text and children[index + 1] is LineEdit:
			return children[index + 1]
	for child in children:
		var found := _line_edit_after_label(child, label_text)
		if found != null:
			return found
	return null


func _first_text_edit(node: Node) -> TextEdit:
	if node is TextEdit:
		return node
	for child in node.get_children():
		var found := _first_text_edit(child)
		if found != null:
			return found
	return null


func _start_node_picker(node: Node) -> OptionButton:
	var children := node.get_children()
	for index in range(children.size() - 1):
		if children[index] is Label and str(children[index].text) == "Start node:" and children[index + 1] is OptionButton:
			return children[index + 1]
	for child in children:
		var found := _start_node_picker(child)
		if found != null:
			return found
	return null


func _picker_ids(picker: OptionButton) -> Array:
	var out: Array = []
	for index in range(picker.item_count):
		var id := str(picker.get_item_metadata(index))
		if id != "":
			out.append(id)
	out.sort()
	return out


func _index_for_id(picker: OptionButton, id: String) -> int:
	for index in range(picker.item_count):
		if str(picker.get_item_metadata(index)) == id:
			return index
	return -1


func _edit(field: LineEdit, value: String) -> void:
	field.text = value
	field.text_changed.emit(value)


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		printerr("  FAIL ", message)
