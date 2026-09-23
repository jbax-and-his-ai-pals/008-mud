# scripts/ui/inspectors/sub_inspectors/CampaignInspector.gd
#
# Campaign authoring: `data/campaigns/*.json` (`engine/campaign/campaign_manager.py`,
# `campaign_models.py`), one whole `CampaignDefinition` per file -- a branching
# graph of `CampaignNode`s (QUEST/DIALOGUE/CUTSCENE/END) linked by transitions.
#
# This is the envelope only: id, name, description and which node the campaign
# starts on. `nodes` is preserved byte-for-byte and shown read-only, the same
# rule the generic item-property table follows for a shape nothing here writes
# yet -- a dedicated node/transition graph editor is its own piece of work,
# the same size DialogueInspector's node editing was.

class_name CampaignInspector
extends RefCounted

signal database_modified

var container: VBoxContainer
var cur_data: Dictionary
var database_mgr: DatabaseManager
var start_node_picker: OptionButton


func _init(c: VBoxContainer, db_mgr: DatabaseManager):
	container = c
	database_mgr = db_mgr


func build(id: String, data: Dictionary):
	cur_data = data
	container.add_child(InspectorStyle.create_section_header("CAMPAIGN: %s" % id.to_upper(), Color(0.8, 0.65, 0.5)))
	_build_identity(id)
	_build_nodes_summary()


func _build_identity(id: String):
	var card := InspectorStyle.create_card()
	var vbox: VBoxContainer = card.get_child(0).get_child(0)
	container.add_child(card)

	vbox.add_child(InspectorStyle.lbl("Campaign ID:", InspectorStyle.COLOR_TEXT_DIM))
	var id_ed := LineEdit.new(); id_ed.text = str(cur_data.get("campaign_id", id))
	InspectorStyle.apply_input_style(id_ed)
	id_ed.text_changed.connect(func(text): cur_data["campaign_id"] = text.strip_edges(); database_modified.emit())
	vbox.add_child(id_ed)

	vbox.add_child(InspectorStyle.lbl("Name:", InspectorStyle.COLOR_TEXT_DIM))
	var name_ed := LineEdit.new(); name_ed.text = str(cur_data.get("name", ""))
	InspectorStyle.apply_input_style(name_ed)
	name_ed.text_changed.connect(func(text): cur_data["name"] = text; database_modified.emit())
	vbox.add_child(name_ed)

	vbox.add_child(InspectorStyle.lbl("Description:", InspectorStyle.COLOR_TEXT_DIM))
	var desc_ed := TextEdit.new(); desc_ed.custom_minimum_size.y = 54
	desc_ed.text = str(cur_data.get("description", ""))
	InspectorStyle.apply_input_style(desc_ed)
	desc_ed.text_changed.connect(func(): cur_data["description"] = desc_ed.text; database_modified.emit())
	vbox.add_child(desc_ed)

	var start_row := HBoxContainer.new()
	start_row.add_child(InspectorStyle.lbl("Start node:", InspectorStyle.COLOR_TEXT_DIM))
	start_node_picker = OptionButton.new()
	start_node_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_button_style(start_node_picker)
	var node_ids := _node_ids()
	var current := str(cur_data.get("start_node_id", ""))
	for node_id in node_ids:
		start_node_picker.add_item(node_id)
		start_node_picker.set_item_metadata(start_node_picker.item_count - 1, node_id)
		if node_id == current: start_node_picker.select(start_node_picker.item_count - 1)
	if current != "" and not node_ids.has(current):
		start_node_picker.add_item("Missing: " + current)
		start_node_picker.set_item_metadata(start_node_picker.item_count - 1, current)
		start_node_picker.select(start_node_picker.item_count - 1)
	start_node_picker.item_selected.connect(func(index):
		cur_data["start_node_id"] = str(start_node_picker.get_item_metadata(index))
		database_modified.emit())
	start_row.add_child(start_node_picker)
	vbox.add_child(start_row)


func _node_ids() -> Array:
	var ids: Array = []
	var nodes = cur_data.get("nodes", {})
	if nodes is Dictionary:
		for node_id in nodes: ids.append(str(node_id))
	ids.sort()
	return ids


## Read-only, the same rule the generic item-property table follows for a
## shape nothing here writes: `campaign_models.CampaignNode` is a branching
## graph (transitions, conditions, chance), not a flat list of fields, and a
## lossy editor here would be worse than none.
func _build_nodes_summary():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Nodes (read-only for now)"))
	var nodes = cur_data.get("nodes", {})
	if not (nodes is Dictionary) or nodes.is_empty():
		container.add_child(InspectorStyle.lbl("No nodes.", InspectorStyle.COLOR_TEXT_DIM))
		return
	var node_ids := _node_ids()
	for node_id in node_ids:
		var node = nodes[node_id]
		if not (node is Dictionary): continue
		var card := InspectorStyle.create_card()
		var vbox: VBoxContainer = card.get_child(0).get_child(0)
		container.add_child(card)
		var header := HBoxContainer.new()
		var id_label := Label.new(); id_label.text = str(node_id); id_label.modulate = Color.CYAN
		header.add_child(id_label)
		var type_label := InspectorStyle.lbl("  [%s]" % str(node.get("type", node.get("node_type", "QUEST"))), InspectorStyle.COLOR_TEXT_DIM)
		header.add_child(type_label)
		vbox.add_child(header)
		var description := str(node.get("description", ""))
		if description != "":
			var desc_label := InspectorStyle.lbl(description, InspectorStyle.COLOR_TEXT_DIM)
			desc_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			vbox.add_child(desc_label)
		var transitions = node.get("transitions", [])
		var transition_count: int = transitions.size() if transitions is Array else 0
		var summary_bits: Array = []
		if node.has("quest_template_id") and str(node.get("quest_template_id", "")) != "":
			summary_bits.append("quest: %s" % str(node["quest_template_id"]))
		if transition_count > 0:
			summary_bits.append("%d transition%s" % [transition_count, "" if transition_count == 1 else "s"])
		if node.has("outcome") and str(node.get("outcome", "")) != "":
			summary_bits.append("outcome: %s" % str(node["outcome"]))
		if not summary_bits.is_empty():
			vbox.add_child(InspectorStyle.lbl(", ".join(summary_bits), InspectorStyle.COLOR_TEXT_DIM))
