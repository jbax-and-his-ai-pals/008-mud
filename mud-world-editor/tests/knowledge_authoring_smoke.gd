# tests/knowledge_authoring_smoke.gd
#
# Knowledge topics (`data/knowledge/topics.json`, `engine/core/knowledge_manager.py`)
# had no editor control at all -- `DatabaseManager` never loaded the file, so
# fantasy_frontier's 14 hand-authored topics (job, rumors, village_elder, ...)
# were only ever editable by hand. See docs/plan/editor-coverage-ledger.md
# family G.
#
#   godot --headless --path mud-world-editor --script tests/knowledge_authoring_smoke.gd
#
# A response's `conditions` are a separate vocabulary from the shared dialogue/
# title condition language (`KnowledgeInspector.gd`'s own header explains why);
# `effects` reuses DialogueSchema's exactly, so this checks that the picker
# comes from there rather than a second copy.

extends SceneTree

var failure_count := 0
var scratch: String = ""


func _init() -> void:
	scratch = ProjectSettings.globalize_path("res://").path_join("../tmp/knowledge_authoring")
	_rebuild_fixture()

	_check_a_shipped_topic_file_loads_with_common_topics()
	_check_opening_and_resaving_is_byte_identical()
	_check_editing_identity_and_keywords()
	_check_adding_a_response_with_a_condition_and_an_effect()
	_check_switching_a_conditions_kind()
	_check_removing_the_last_response_erases_the_key()
	_check_creating_and_deleting_a_topic()

	if failure_count > 0:
		push_error("knowledge authoring failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


func _check_a_shipped_topic_file_loads_with_common_topics() -> void:
	print("\n[loading the real shipped topics file]")
	var manager := _manager()
	_assert(manager.topics.has("job"), "fantasy_frontier's 'job' topic loaded")
	_assert(manager.common_topics.has("job"), "__common_topics__ loaded too (%s)" % str(manager.common_topics))


func _check_opening_and_resaving_is_byte_identical() -> void:
	print("\n[opening and resaving without editing]")
	var manager := _manager()
	var path := DataRoot.content_file("knowledge/topics.json")
	var before := FileAccess.get_file_as_string(path)
	_build_inspector_from("job", manager)
	var result: Dictionary = manager.save_all()
	_assert(result.get("ok", false), "the save reported ok: %s" % str(result.get("errors", [])))
	_assert(FileAccess.get_file_as_string(path) == before, "opening a topic and saving changed nothing")


func _check_editing_identity_and_keywords() -> void:
	print("\n[editing display name and keywords]")
	var manager := _manager()
	var holder := _build_inspector_from("probe_topic", manager)
	var name_field := _first_line_edit(holder)
	_edit(name_field, "Probe Rumor")
	_assert(manager.topics["probe_topic"]["display_name"] == "Probe Rumor", "the display name was written")
	var add_kw := _button_labeled(holder, "+ Keyword")
	add_kw.pressed.emit()
	var kw_field := _first_line_edit(holder.find_child("KeywordRows", true, false))
	_edit(kw_field, "gossip")
	_assert(manager.topics["probe_topic"]["keywords"] == ["gossip"], "the keyword was written")


func _check_adding_a_response_with_a_condition_and_an_effect() -> void:
	print("\n[adding a response, a condition, and an effect]")
	var manager := _manager()
	var holder := _build_inspector_from("probe_topic", manager)
	var add_response := _button_labeled(holder, "+ Response")
	add_response.pressed.emit()
	var responses: Array = manager.topics["probe_topic"]["responses"]
	_assert(responses.size() == 1, "one response was added")

	var text_ed := _first_text_edit(holder)
	text_ed.text = "The bridge is out."
	text_ed.text_changed.emit()
	_assert(responses[0]["text"] == "The bridge is out.", "the response text was written")

	var add_condition := _button_labeled(holder, "+ Condition")
	add_condition.pressed.emit()
	_assert(responses[0]["conditions"].has("region_id"), "a default condition (region_id) was added")
	var condition_field := _line_edit_in_row_with_button(holder, "region_id")
	_edit(condition_field, "town")
	_assert(responses[0]["conditions"]["region_id"] == "town", "the condition value was written")

	var add_effect := _button_labeled(holder, "+ Effect")
	add_effect.pressed.emit()
	_assert(not responses[0].get("effects", {}).is_empty(), "a default effect was added, from DialogueSchema's vocabulary")
	var effect_key: String = responses[0]["effects"].keys()[0]
	_assert(DialogueSchema.has_effect(effect_key), "the default effect key is one DialogueSchema actually knows (%s)" % effect_key)


func _check_switching_a_conditions_kind() -> void:
	print("\n[switching a condition's kind]")
	var manager := _manager()
	var holder := _build_inspector_from("probe_with_condition", manager)
	var picker := _first_option_button_with_text(holder, "region_id")
	_assert(picker != null, "the region_id condition's kind picker was found")
	var index := _index_of_text(picker, "faction")
	picker.item_selected.emit(index)
	var conditions: Dictionary = manager.topics["probe_with_condition"]["responses"][0]["conditions"]
	_assert(conditions.has("faction") and not conditions.has("region_id"), "the kind switched, dropping the old key (%s)" % str(conditions.keys()))


func _check_removing_the_last_response_erases_the_key() -> void:
	print("\n[removing the only response]")
	var manager := _manager()
	var holder := _build_inspector_from("probe_with_condition", manager)
	var remove := _button_labeled(holder, "Remove Response")
	remove.pressed.emit()
	_assert(not manager.topics["probe_with_condition"].has("responses"), "the now-empty responses key was erased")


func _check_creating_and_deleting_a_topic() -> void:
	print("\n[creating and deleting a topic]")
	var manager := _manager()
	manager.add_topic("fresh_topic", {"display_name": "Fresh", "keywords": [], "responses": []})
	var result: Dictionary = manager.save_all()
	_assert(result.get("ok", false), "creating a topic and saving reported ok")
	var reloaded := _manager()
	_assert(reloaded.topics.has("fresh_topic"), "the new topic reloads from disk")
	reloaded.delete_entry("topic", "fresh_topic")
	var delete_result: Dictionary = reloaded.save_all()
	_assert(delete_result.get("ok", false), "deleting a topic and saving reported ok")
	var after_delete := _manager()
	_assert(not after_delete.topics.has("fresh_topic"), "the deleted topic is gone after reload")
	_assert(after_delete.topics.has("job"), "an untouched topic survives")


# --- fixture ----------------------------------------------------------------

func _rebuild_fixture() -> void:
	_remove_recursive(scratch)
	_copy_recursive(
		ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir().path_join("content_sets/fantasy_frontier"),
		scratch,
	)
	var extra := {
		"probe_topic": {"display_name": "Probe", "keywords": [], "responses": []},
		"probe_with_condition": {
			"display_name": "Probe With Condition", "keywords": [],
			"responses": [{"text": "Hi.", "priority": 0, "conditions": {"region_id": "town"}}],
		},
	}
	var path := scratch.path_join("data/knowledge/topics.json")
	var existing: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	for key in extra: existing[key] = extra[key]
	# Through SaveIO, not a manual JSON.stringify: `JSON.parse_string` always
	# returns a float for a number (this merge just read `priority: 10` back
	# as `10.0`), and only SaveIO's own normalization turns it back into the
	# int a real save would write -- the exact defect class this project
	# keeps a tripwire for. Writing the fixture any other way would make the
	# "opening changes nothing" check below compare against a shape no real
	# save ever produces.
	var save_result: Dictionary = SaveIO.write_json(path, existing)
	if not save_result.get("ok", false):
		printerr("fixture setup failed to write topics.json: ", save_result.get("error", ""))


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


func _build_inspector_from(topic_id: String, manager: DatabaseManager) -> Node:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	var inspector := KnowledgeInspector.new(holder, manager)
	inspector.build(topic_id, manager.topics[topic_id])
	return holder


func _all_buttons(node: Node) -> Array:
	var out: Array = []
	if node is Button:
		out.append(node)
	for child in node.get_children():
		out.append_array(_all_buttons(child))
	return out


func _button_labeled(node: Node, text: String) -> Button:
	for child in _all_buttons(node):
		if str(child.text) == text:
			return child
	return null


func _first_line_edit(node: Node) -> LineEdit:
	if node is LineEdit:
		return node
	for child in node.get_children():
		var found := _first_line_edit(child)
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


## A row shaped like [OptionButton(kind), value fields..., remove Button] where
## the OptionButton's currently selected text is `kind_text`: returns the first
## LineEdit sibling after it.
func _line_edit_in_row_with_button(node: Node, kind_text: String) -> LineEdit:
	if node is HBoxContainer:
		var children := node.get_children()
		if children.size() > 0 and children[0] is OptionButton:
			var picker: OptionButton = children[0]
			if picker.item_count > 0 and str(picker.get_item_text(picker.selected)) == kind_text:
				for child in children:
					if child is LineEdit:
						return child
	for child in node.get_children():
		var found := _line_edit_in_row_with_button(child, kind_text)
		if found != null:
			return found
	return null


func _first_option_button_with_text(node: Node, selected_text: String) -> OptionButton:
	if node is OptionButton and node.item_count > 0 and str(node.get_item_text(node.selected)) == selected_text:
		return node
	for child in node.get_children():
		var found := _first_option_button_with_text(child, selected_text)
		if found != null:
			return found
	return null


func _index_of_text(picker: OptionButton, text: String) -> int:
	for index in range(picker.item_count):
		if str(picker.get_item_text(index)) == text:
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
