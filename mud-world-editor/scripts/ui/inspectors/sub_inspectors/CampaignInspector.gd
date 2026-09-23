# scripts/ui/inspectors/sub_inspectors/CampaignInspector.gd
#
# Campaign authoring: `data/campaigns/*.json` (`engine/campaign/campaign_manager.py`,
# `campaign_models.py`), one whole campaign per file: an envelope (id, name,
# description, start node) and a graph of nodes linked by transitions.
#
# What the engine does with a node decides what this form offers: a QUEST node
# starts its quest, and the quest's reported resolution picks the first matching
# transition; an END node records its outcome. NODE_TYPES and TRIGGERS copy the
# engine's CAMPAIGN_NODE_TYPES and CAMPAIGN_TRIGGERS (schema_parity_smoke.gd
# checks them); content_set.py::_validate_campaigns refuses the rest on save.
# Nodes and transitions are edited in place, so keys this form does not show
# survive; switching a node's type drops only the fields the new type ignores.

class_name CampaignInspector
extends RefCounted

signal database_modified

const NODE_TYPES := ["QUEST", "END"]
const TRIGGERS := ["SUCCESS", "PEACEFUL_SUCCESS", "VIOLENT_SUCCESS"]
const TYPE_KEYS := {
	"QUEST": ["description", "quest_template_id", "type", "transitions"],
	"END": ["description", "type", "outcome"],
}

var container: VBoxContainer
var cur_data: Dictionary
var database_mgr: DatabaseManager
var start_node_picker: OptionButton
var nodes_box: VBoxContainer


func _init(c: VBoxContainer, db_mgr: DatabaseManager):
	container = c
	database_mgr = db_mgr


func build(id: String, data: Dictionary):
	cur_data = data
	container.add_child(InspectorStyle.create_section_header("CAMPAIGN: %s" % id.to_upper(), Color(0.8, 0.65, 0.5)))
	_build_identity(id)
	_build_nodes()


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
	start_node_picker = OptionButton.new(); start_node_picker.name = "StartNode"
	start_node_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_button_style(start_node_picker)
	start_node_picker.item_selected.connect(func(index):
		cur_data["start_node_id"] = str(start_node_picker.get_item_metadata(index))
		database_modified.emit()
		_refresh_nodes())
	start_row.add_child(start_node_picker)
	vbox.add_child(start_row)
	_refresh_start_picker()


func _refresh_start_picker():
	_fill(start_node_picker, _node_ids(), str(cur_data.get("start_node_id", "")))


func _node_ids() -> Array:
	var ids: Array = []
	var nodes = cur_data.get("nodes", {})
	if nodes is Dictionary:
		for node_id in nodes: ids.append(str(node_id))
	ids.sort()
	return ids


func _nodes() -> Dictionary:
	if not (cur_data.get("nodes") is Dictionary): cur_data["nodes"] = {}
	return cur_data["nodes"]


# --- nodes --------------------------------------------------------------------

func _build_nodes():
	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.create_sub_header("Nodes"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var add := Button.new(); add.text = "+ Node"
	InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS)
	add.pressed.connect(add_node)
	header.add_child(add)
	container.add_child(header)
	var hint := InspectorStyle.lbl("A quest node starts its quest; when the quest ends, the first transition whose trigger matches the result is followed (SUCCESS matches any success). An end node finishes the campaign with its outcome.", InspectorStyle.COLOR_TEXT_DIM)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	container.add_child(hint)
	nodes_box = VBoxContainer.new(); nodes_box.add_theme_constant_override("separation", 10)
	container.add_child(nodes_box)
	_refresh_nodes()


## A new node is an END node, which is valid on its own; retype it to QUEST to
## give it a quest and transitions.
func add_node() -> String:
	var nodes := _nodes()
	var index := nodes.size() + 1
	var node_id := "node_%d" % index
	while nodes.has(node_id):
		index += 1
		node_id = "node_%d" % index
	nodes[node_id] = {"description": "", "type": "END", "outcome": "complete"}
	if str(cur_data.get("start_node_id", "")) == "": cur_data["start_node_id"] = node_id
	database_modified.emit()
	_refresh_nodes()
	return node_id


func _refresh_nodes():
	if start_node_picker != null: _refresh_start_picker()
	for child in nodes_box.get_children(): nodes_box.remove_child(child); child.queue_free()
	var nodes := _nodes()
	for node_id in _node_ids():
		if nodes[node_id] is Dictionary: nodes_box.add_child(_node_card(node_id, nodes[node_id]))


func _node_card(node_id: String, node: Dictionary) -> PanelContainer:
	var card := InspectorStyle.create_card(); card.name = "Node_" + node_id
	var vbox: VBoxContainer = card.get_child(0).get_child(0)
	var header := HBoxContainer.new(); header.add_theme_constant_override("separation", 6); vbox.add_child(header)
	var id_ed := LineEdit.new(); id_ed.name = "NodeId"; id_ed.text = node_id; id_ed.custom_minimum_size.x = 180
	id_ed.tooltip_text = "Node id. Renaming updates every transition that leads here, and the start node."
	InspectorStyle.apply_input_style(id_ed)
	id_ed.text_submitted.connect(func(text): _rename_node(node_id, text))
	header.add_child(id_ed)
	var kind := str(node.get("type", "QUEST"))
	var type_picker := OptionButton.new(); type_picker.name = "Type"
	_fill(type_picker, NODE_TYPES, kind)
	InspectorStyle.apply_button_style(type_picker)
	type_picker.item_selected.connect(func(index): _retype(node, str(type_picker.get_item_metadata(index))))
	header.add_child(type_picker)
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	if str(cur_data.get("start_node_id", "")) == node_id:
		var badge := InspectorStyle.lbl("start", Color(0.7, 0.9, 0.7)); header.add_child(badge)
	var remove := Button.new(); remove.text = "Remove Node"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
	remove.pressed.connect(func(): _remove_node(node_id))
	header.add_child(remove)

	vbox.add_child(InspectorStyle.lbl("Description:", InspectorStyle.COLOR_TEXT_DIM))
	var desc := TextEdit.new(); desc.name = "Description"; desc.custom_minimum_size.y = 48; desc.text = str(node.get("description", ""))
	InspectorStyle.apply_input_style(desc)
	desc.text_changed.connect(func(): node["description"] = desc.text; database_modified.emit())
	vbox.add_child(desc)

	if kind == "END":
		var row := HBoxContainer.new(); vbox.add_child(row)
		row.add_child(InspectorStyle.lbl("Outcome:", InspectorStyle.COLOR_TEXT_DIM))
		var outcome := LineEdit.new(); outcome.name = "Outcome"; outcome.text = str(node.get("outcome", "")); outcome.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		outcome.tooltip_text = "Recorded when the campaign ends here; knowledge topics can ask for it (campaign_outcome)."
		InspectorStyle.apply_input_style(outcome)
		outcome.text_changed.connect(func(text): node["outcome"] = text.strip_edges(); database_modified.emit())
		row.add_child(outcome)
		return card

	var quest_row := HBoxContainer.new(); vbox.add_child(quest_row)
	quest_row.add_child(InspectorStyle.lbl("Quest:", InspectorStyle.COLOR_TEXT_DIM))
	var quest := OptionButton.new(); quest.name = "Quest"; quest.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	QuestGenerationSection._fill_picker(quest, database_mgr.get_ids("quest") if database_mgr != null else [], {}, str(node.get("quest_template_id", "")), "Choose quest")
	InspectorStyle.apply_button_style(quest)
	quest.item_selected.connect(func(index):
		var value := str(quest.get_item_metadata(index))
		if value == "": node.erase("quest_template_id")
		else: node["quest_template_id"] = value
		database_modified.emit())
	quest_row.add_child(quest)

	var t_header := HBoxContainer.new(); vbox.add_child(t_header)
	t_header.add_child(InspectorStyle.lbl("Transitions (first match wins)", InspectorStyle.COLOR_TEXT_DIM))
	var t_spacer := Control.new(); t_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; t_header.add_child(t_spacer)
	var add_t := Button.new(); add_t.text = "+ Transition"; InspectorStyle.apply_button_style(add_t, InspectorStyle.COLOR_SUCCESS)
	add_t.pressed.connect(func():
		var list: Array = node.get("transitions", []) if node.get("transitions") is Array else []
		var others := _node_ids().filter(func(other): return other != node_id)
		list.append({"trigger": "SUCCESS", "target_node_id": others[0] if not others.is_empty() else node_id, "narrative_text": ""})
		node["transitions"] = list
		database_modified.emit(); _refresh_nodes())
	t_header.add_child(add_t)
	var transitions: Array = node.get("transitions", []) if node.get("transitions") is Array else []
	if transitions.is_empty():
		vbox.add_child(InspectorStyle.lbl("No transitions: finishing the quest leads nowhere.", DialogStyle.COLOR_DANGER))
	for index in range(transitions.size()):
		if transitions[index] is Dictionary: vbox.add_child(_transition_row(node, transitions, index))
	return card


func _transition_row(node: Dictionary, transitions: Array, index: int) -> VBoxContainer:
	var transition: Dictionary = transitions[index]
	var box := VBoxContainer.new(); box.name = "Transition_%d" % index
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6); box.add_child(row)
	var trigger := OptionButton.new(); trigger.name = "Trigger"
	_fill(trigger, TRIGGERS, str(transition.get("trigger", "SUCCESS")))
	InspectorStyle.apply_button_style(trigger)
	trigger.item_selected.connect(func(i): transition["trigger"] = str(trigger.get_item_metadata(i)); database_modified.emit())
	row.add_child(trigger)
	row.add_child(InspectorStyle.lbl("->", InspectorStyle.COLOR_TEXT_DIM))
	var target := OptionButton.new(); target.name = "Target"; target.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_fill(target, _node_ids(), str(transition.get("target_node_id", "")))
	InspectorStyle.apply_button_style(target)
	target.item_selected.connect(func(i): transition["target_node_id"] = str(target.get_item_metadata(i)); database_modified.emit())
	row.add_child(target)
	row.add_child(InspectorStyle.lbl("chance", InspectorStyle.COLOR_TEXT_DIM))
	var chance := SpinBox.new(); chance.name = "Chance"; chance.min_value = 0.01; chance.max_value = 1.0; chance.step = 0.01
	chance.value = float(transition.get("chance", 1.0)); chance.custom_minimum_size.x = 70; InspectorStyle.apply_input_style(chance)
	chance.value_changed.connect(func(value):
		if is_equal_approx(value, 1.0): transition.erase("chance")
		else: transition["chance"] = snappedf(value, 0.01)
		database_modified.emit())
	row.add_child(chance)
	for spec in [["^", -1], ["v", 1]]:
		var move := Button.new(); move.text = spec[0]; move.tooltip_text = "Move up" if spec[1] < 0 else "Move down"
		move.disabled = index + spec[1] < 0 or index + spec[1] >= transitions.size()
		var step: int = spec[1]
		move.pressed.connect(func():
			var other := index + step
			var held = transitions[index]; transitions[index] = transitions[other]; transitions[other] = held
			database_modified.emit(); _refresh_nodes())
		row.add_child(move)
	var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
	remove.pressed.connect(func():
		transitions.remove_at(index)
		database_modified.emit(); _refresh_nodes())
	row.add_child(remove)
	var narrative := LineEdit.new(); narrative.name = "Narrative"; narrative.text = str(transition.get("narrative_text", ""))
	narrative.placeholder_text = "narrative shown when this transition is taken (optional)"
	InspectorStyle.apply_input_style(narrative)
	narrative.text_changed.connect(func(text): transition["narrative_text"] = text; database_modified.emit())
	box.add_child(narrative)
	return box


func _retype(node: Dictionary, kind: String) -> void:
	node["type"] = kind
	for key in node.keys():
		if not str(key).begins_with("_") and not (key in TYPE_KEYS[kind]): node.erase(key)
	if kind == "END" and str(node.get("outcome", "")) == "": node["outcome"] = "complete"
	if kind == "QUEST" and not (node.get("transitions") is Array): node["transitions"] = []
	database_modified.emit()
	_refresh_nodes()


func _rename_node(old_id: String, new_id: String) -> void:
	var clean := new_id.strip_edges()
	var nodes := _nodes()
	if clean == "" or clean == old_id or nodes.has(clean):
		_refresh_nodes(); return
	# Rebuilt in place, keeping order, so a holder of this dictionary stays current.
	var entries: Array = []
	for key in nodes: entries.append([clean if key == old_id else key, nodes[key]])
	nodes.clear()
	for entry in entries: nodes[entry[0]] = entry[1]
	for node in nodes.values():
		if not (node is Dictionary): continue
		for transition in node.get("transitions", []) if node.get("transitions") is Array else []:
			if transition is Dictionary and str(transition.get("target_node_id", "")) == old_id: transition["target_node_id"] = clean
	if str(cur_data.get("start_node_id", "")) == old_id: cur_data["start_node_id"] = clean
	database_modified.emit()
	_refresh_nodes()


## Transitions that led to the removed node are left in place and shown as
## "Missing:", as the dialogue editor does; the save's engine check refuses them.
func _remove_node(node_id: String) -> void:
	_nodes().erase(node_id)
	if str(cur_data.get("start_node_id", "")) == node_id:
		var ids := _node_ids()
		cur_data["start_node_id"] = ids[0] if not ids.is_empty() else ""
	database_modified.emit()
	_refresh_nodes()


## A picker over `options`, keeping an unknown current value visible as "Missing:".
static func _fill(picker: OptionButton, options: Array, current: String) -> void:
	picker.clear()
	for option in options:
		picker.add_item(str(option)); picker.set_item_metadata(picker.item_count - 1, str(option))
		if str(option) == current: picker.select(picker.item_count - 1)
	if current != "" and not options.has(current):
		picker.add_item("Missing: " + current); picker.set_item_metadata(picker.item_count - 1, current); picker.select(picker.item_count - 1)
