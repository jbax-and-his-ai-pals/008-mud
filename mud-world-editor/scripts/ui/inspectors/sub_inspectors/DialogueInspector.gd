# scripts/ui/inspectors/sub_inspectors/DialogueInspector.gd
#
# Conversation authoring: `data/dialogue/<graph>.json`.
#
# This is the content system that can gate a reply on what the player has done,
# teach a recipe mid-sentence, or let a negotiation go two ways -- and it had no
# surface at all, so all nine shipped conversations were hand-written JSON.
#
# Three things it does that a plain JSON box would not:
#
#   * `next_node` and a check's success/fail targets are **pickers over this
#     graph's own node ids**, because the one mistake content validation reports
#     most is a link to a node that was renamed;
#   * conditions are built from `DialogueSchema`'s list of the kinds the engine
#     evaluates, with their fields -- an unrecognised kind fails *closed*, so a
#     typo silently closes a conversation, and the picker is how that stops;
#   * effects are picked from `KNOWN_EFFECTS` with a hint per effect saying what
#     shape the engine reads.
#
# Anything outside those vocabularies is shown as JSON and kept, and node ids can
# be renamed with their references updated, which is the operation a hand-edited
# graph gets wrong.

class_name DialogueInspector
extends RefCounted

signal database_modified

var container: VBoxContainer
var cur_data: Dictionary
var database_mgr: DatabaseManager
var nodes_box: VBoxContainer
var root_picker: OptionButton
var references_label: Label


func _init(c: VBoxContainer, db_mgr: DatabaseManager):
	container = c
	database_mgr = db_mgr


static func data_defaults() -> Dictionary:
	# What a brand-new conversation starts as: an opening node with one way out,
	# so it is a valid graph before the author types anything.
	return {
		"id": "",
		"root": "greeting",
		"nodes": {
			"greeting": {"text": "", "choices": [{"text": "Goodbye.", "end": true}]},
		},
	}


func build(graph_id: String, data: Dictionary, db_mgr: DatabaseManager = null):
	if db_mgr != null:
		database_mgr = db_mgr
	cur_data = data
	if not (cur_data.get("nodes") is Dictionary):
		cur_data["nodes"] = {}
	container.add_child(InspectorStyle.create_section_header(
		"DIALOGUE: %s" % str(cur_data.get("id", graph_id)).to_upper(), Color(0.86, 0.75, 0.95)))

	_build_graph_header()
	_build_nodes()
	_build_extras()


func _build_graph_header():
	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)

	vbox.add_child(InspectorStyle.lbl("Graph id (what an NPC's `properties.dialogue` names):", InspectorStyle.COLOR_TEXT_DIM))
	var id_ed := LineEdit.new(); id_ed.text = str(cur_data.get("id", ""))
	InspectorStyle.apply_input_style(id_ed)
	id_ed.text_changed.connect(func(text): cur_data["id"] = text.strip_edges(); database_modified.emit())
	vbox.add_child(id_ed)

	var root_row := HBoxContainer.new()
	root_row.add_child(InspectorStyle.lbl("Opening node:", InspectorStyle.COLOR_TEXT_DIM))
	root_picker = OptionButton.new()
	root_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_button_style(root_picker)
	root_picker.item_selected.connect(func(index):
		cur_data["root"] = str(root_picker.get_item_metadata(index))
		database_modified.emit()
	)
	root_row.add_child(root_picker)
	vbox.add_child(root_row)

	references_label = Label.new()
	references_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	references_label.add_theme_font_size_override("font_size", 11)
	references_label.modulate = Color(0.68, 0.7, 0.78)
	vbox.add_child(references_label)


func _node_ids() -> Array:
	var ids: Array = []
	var nodes: Dictionary = cur_data.get("nodes", {})
	for node_id in nodes: ids.append(str(node_id))
	ids.sort()
	return ids


func _refresh_root_picker():
	var ids := _node_ids()
	root_picker.clear()
	var current := str(cur_data.get("root", ""))
	for node_id in ids:
		root_picker.add_item(node_id)
		root_picker.set_item_metadata(root_picker.item_count - 1, node_id)
		if node_id == current:
			root_picker.select(root_picker.item_count - 1)
	if current == "" and not ids.is_empty():
		cur_data["root"] = str(ids[0])
		root_picker.select(0)
	# The graph id and the node list are what an NPC template and every choice
	# link depend on; say so here rather than making the author press Validate.
	var dangling: Array = []
	var nodes: Dictionary = cur_data.get("nodes", {})
	for node_id in nodes:
		var node = nodes[node_id]
		if not (node is Dictionary): continue
		for choice in node.get("choices", []) if node.get("choices") is Array else []:
			if not (choice is Dictionary): continue
			for target in DialogueSchema.choice_targets(choice):
				if not nodes.has(target):
					dangling.append("%s → %s" % [node_id, target])
	var lines: Array = ["%d node(s)." % ids.size()]
	if dangling.is_empty():
		lines.append("Every choice leads somewhere that exists.")
	else:
		lines.append("Leads nowhere: %s -- content validation will report these." % ", ".join(dangling))
	references_label.text = "\n".join(lines)


func _build_nodes():
	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.create_sub_header("Nodes"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var add := Button.new(); add.text = "+ Node"
	InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(add_node)
	header.add_child(add)
	container.add_child(header)

	nodes_box = VBoxContainer.new()
	nodes_box.add_theme_constant_override("separation", 10)
	container.add_child(nodes_box)
	_refresh_nodes()


# Public because it is the structural operation a caller (and a test) drives;
# a node with no id yet is given one that is not already taken.
func add_node() -> String:
	var nodes: Dictionary = cur_data.get("nodes", {})
	var index := nodes.size() + 1
	var node_id := "node_%d" % index
	while nodes.has(node_id):
		index += 1
		node_id = "node_%d" % index
	nodes[node_id] = {"text": "", "choices": [{"text": "Goodbye.", "end": true}]}
	cur_data["nodes"] = nodes
	if str(cur_data.get("root", "")) == "":
		cur_data["root"] = node_id
	database_modified.emit()
	_refresh_nodes()
	return node_id


func _refresh_nodes():
	if root_picker != null:
		_refresh_root_picker()
	for child in nodes_box.get_children(): child.queue_free()
	var nodes: Dictionary = cur_data.get("nodes", {})
	var ids := _node_ids()
	for node_id in ids:
		if nodes[node_id] is Dictionary:
			nodes_box.add_child(_node_card(node_id, nodes[node_id]))


func _node_card(node_id: String, node: Dictionary) -> PanelContainer:
	var pc := InspectorStyle.create_card()
	var vbox := pc.get_child(0).get_child(0)

	var header := HBoxContainer.new()
	var name_ed := LineEdit.new()
	name_ed.text = node_id
	name_ed.custom_minimum_size.x = 220
	name_ed.tooltip_text = "Node id. Renaming updates every choice that points here."
	InspectorStyle.apply_input_style(name_ed)
	name_ed.text_submitted.connect(func(text): _rename_node(node_id, text))
	header.add_child(name_ed)

	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)

	var is_root := str(cur_data.get("root", "")) == node_id
	if is_root:
		var badge := Label.new(); badge.text = "opening node"
		badge.modulate = Color(0.7, 0.9, 0.7)
		badge.add_theme_font_size_override("font_size", 11)
		header.add_child(badge)

	var remove := Button.new(); remove.text = "X"
	remove.tooltip_text = "Remove this node"
	InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
	remove.pressed.connect(func(): _remove_node(node_id))
	header.add_child(remove)
	vbox.add_child(header)

	vbox.add_child(InspectorStyle.lbl("What the NPC says:", InspectorStyle.COLOR_TEXT_DIM))
	var text_ed := TextEdit.new(); text_ed.custom_minimum_size.y = 54
	text_ed.text = _text_value(node)
	InspectorStyle.apply_input_style(text_ed)
	text_ed.text_changed.connect(func():
		var text := text_ed.text
		var existing = node.get("text", "")
		if existing is Dictionary:
			# A mode-variant node keeps its shape; this field edits the plain text.
			existing = existing.duplicate()
			existing["player"] = text
			node["text"] = existing
		else:
			node["text"] = text
		database_modified.emit()
	)
	vbox.add_child(text_ed)
	if node.get("text") is Dictionary:
		var variant := Label.new()
		variant.text = "This node has presentation variants: %s" % ", ".join((node["text"] as Dictionary).keys())
		variant.add_theme_font_size_override("font_size", 11)
		variant.modulate = Color(0.7, 0.72, 0.6)
		vbox.add_child(variant)

	_build_effects_row(vbox, node, "Node effects (applied when the node is reached)")

	var choices_header := HBoxContainer.new()
	choices_header.add_child(InspectorStyle.lbl("Choices", InspectorStyle.COLOR_TEXT_DIM))
	var choices_spacer := Control.new(); choices_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	choices_header.add_child(choices_spacer)
	var add_choice := Button.new(); add_choice.text = "+ Choice"
	InspectorStyle.apply_button_style(add_choice, Color(0.2, 0.3, 0.4))
	add_choice.pressed.connect(func():
		var choices: Array = node.get("choices", []) if node.get("choices") is Array else []
		choices.append({"text": "", "end": true})
		node["choices"] = choices
		database_modified.emit()
		_refresh_nodes()
	)
	choices_header.add_child(add_choice)
	vbox.add_child(choices_header)

	var choices: Array = node.get("choices", []) if node.get("choices") is Array else []
	if choices.is_empty():
		vbox.add_child(InspectorStyle.lbl("No replies: the conversation stops here.", InspectorStyle.COLOR_TEXT_DIM))
	for index in range(choices.size()):
		if choices[index] is Dictionary:
			vbox.add_child(_choice_card(node_id, node, choices[index], index))
	return pc


func _choice_card(node_id: String, node: Dictionary, choice: Dictionary, index: int) -> PanelContainer:
	var pc := PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.16, 0.16, 0.19)
	style.set_corner_radius_all(6)
	style.content_margin_left = 10; style.content_margin_right = 10
	style.content_margin_top = 6; style.content_margin_bottom = 6
	pc.add_theme_stylebox_override("panel", style)
	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 4)
	pc.add_child(vbox)

	var row := HBoxContainer.new()
	var text_ed := LineEdit.new()
	text_ed.text = str(choice.get("text", ""))
	text_ed.placeholder_text = "What the player says"
	text_ed.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(text_ed)
	text_ed.text_changed.connect(func(text): choice["text"] = text; database_modified.emit())
	row.add_child(text_ed)

	var remove := Button.new(); remove.text = "×"
	InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
	remove.pressed.connect(func():
		var choices: Array = node.get("choices", [])
		choices.remove_at(index)
		database_modified.emit()
		_refresh_nodes()
	)
	row.add_child(remove)
	vbox.add_child(row)

	var aliases := LineEdit.new()
	aliases.text = ", ".join(_as_string_list(choice.get("aliases", [])))
	aliases.placeholder_text = "aliases a player might type (comma separated)"
	InspectorStyle.apply_input_style(aliases)
	aliases.text_changed.connect(func(text):
		var values: Array = []
		for part in text.split(","):
			var trimmed: String = str(part).strip_edges()
			if trimmed != "": values.append(trimmed)
		if values.is_empty(): choice.erase("aliases")
		else: choice["aliases"] = values
		database_modified.emit()
	)
	vbox.add_child(aliases)

	_add_target_row(vbox, choice)
	_add_condition_row(vbox, choice)
	_build_effects_row(vbox, choice, "Choice effects")
	_add_check_row(vbox, choice)
	return pc


# Where the choice goes. `end: true` and `next_node` are alternatives, so this is
# one picker rather than two fields an author could set contradictorily.
func _add_target_row(parent: VBoxContainer, choice: Dictionary):
	var row := HBoxContainer.new()
	row.add_child(InspectorStyle.lbl("Leads to", InspectorStyle.COLOR_TEXT_DIM))
	var picker := OptionButton.new()
	picker.name = "TargetPicker"
	picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var options: Array = ["(ends the conversation)"] + _node_ids()
	for option in options: picker.add_item(str(option))
	var current := DialogueSchema.value_of(choice.get("next_node", ""))
	var selected := options.find(current) if current != "" else 0
	picker.select(selected if selected >= 0 else 0)
	if current != "" and selected < 0:
		picker.add_item(current)
		picker.select(picker.item_count - 1)
	InspectorStyle.apply_button_style(picker)
	picker.item_selected.connect(func(index):
		var chosen := str(options[index]) if index < options.size() else ""
		if chosen == "(ends the conversation)":
			choice.erase("next_node")
			choice["end"] = true
		else:
			choice["next_node"] = chosen
			choice.erase("end")
		database_modified.emit()
		_refresh_nodes()
	)
	row.add_child(picker)
	parent.add_child(row)


func _add_condition_row(parent: VBoxContainer, choice: Dictionary):
	var row := HBoxContainer.new()
	row.add_child(InspectorStyle.lbl("Only if", InspectorStyle.COLOR_TEXT_DIM))

	var condition = choice.get("condition")
	var picker := OptionButton.new()
	picker.name = "ConditionPicker"
	var kinds: Array = ["(always offered)"] + DialogueSchema.condition_kinds()
	if condition is Dictionary and condition.has("kind"):
		var kind := str(condition["kind"])
		if not DialogueSchema.has_condition_kind(kind): kinds.append(kind)
	for kind in kinds: picker.add_item(str(kind))
	var current_kind := str(condition.get("kind", "")) if condition is Dictionary else ""
	var index := kinds.find(current_kind) if current_kind != "" else 0
	picker.select(index if index >= 0 else 0)
	InspectorStyle.apply_button_style(picker)
	row.add_child(picker)
	parent.add_child(row)

	# The current condition's own fields.
	if not (condition is Dictionary) or not condition.has("kind"):
		if condition is Dictionary and not condition.is_empty():
			_condition_json_row(parent, choice, condition)
		picker.item_selected.connect(func(selected):
			var chosen := str(kinds[selected])
			if chosen == "(always offered)":
				choice.erase("condition")
			else:
				choice["condition"] = {"kind": chosen}
			database_modified.emit()
			_refresh_nodes()
		)
		return
	var note := Label.new()
	note.text = DialogueSchema.condition_note(str(condition["kind"]))
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	note.add_theme_font_size_override("font_size", 11)
	note.modulate = Color(0.68, 0.7, 0.78)
	parent.add_child(note)

	var fields := DialogueSchema.condition_fields(str(condition["kind"]))
	for field in fields:
		_add_condition_field(parent, condition, str(field), str(fields[field]))
	# Any key the schema does not name (a composite, or a field added to the
	# engine since) stays visible and editable.
	var extras: Array = []
	for key in condition:
		if str(key) != "kind" and not fields.has(str(key)):
			extras.append(key)
	if not extras.is_empty():
		_condition_json_row(parent, choice, condition, extras)

	picker.item_selected.connect(func(selected):
		var chosen := str(kinds[selected])
		if chosen == "(always offered)":
			choice.erase("condition")
		else:
			choice["condition"] = {"kind": chosen}
		database_modified.emit()
		_refresh_nodes()
	)


func _add_condition_field(parent: VBoxContainer, condition: Dictionary, key: String, kind: String):
	var row := HBoxContainer.new()
	row.add_child(InspectorStyle.lbl("    " + key.replace("_", " "), InspectorStyle.COLOR_TEXT_DIM))
	var editor_kind := kind
	var line := LineEdit.new()
	line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	match editor_kind:
		"int":
			line.text = str(int(condition.get(key, 0)))
		_:
			line.text = str(condition.get(key, ""))
	line.placeholder_text = kind
	InspectorStyle.apply_input_style(line)
	line.text_changed.connect(func(text):
		var trimmed: String = str(text).strip_edges()
		if trimmed == "":
			condition.erase(key)
		elif kind == "int" and trimmed.is_valid_int():
			condition[key] = int(trimmed)
		else:
			condition[key] = trimmed
		database_modified.emit()
	)
	row.add_child(line)
	if kind == "item_id":
		InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_item_ids())
	elif kind == "npc_id":
		InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_npc_ids())
	elif kind == "quest_id":
		InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_ids("quest"))
	elif kind == "recipe_id":
		InspectorStyle.add_suggestion_button(row, line, func(): return database_mgr.get_recipe_ids())
	parent.add_child(row)


func _condition_json_row(parent: VBoxContainer, choice: Dictionary, condition: Dictionary, keys: Array = []):
	var row := HBoxContainer.new()
	row.add_child(InspectorStyle.lbl("    other fields", InspectorStyle.COLOR_TEXT_DIM))
	var line := LineEdit.new()
	var subset := {}
	if keys.is_empty():
		for key in condition: subset[key] = condition[key]
	else:
		for key in keys: subset[key] = condition[key]
	line.text = JSON.stringify(subset)
	line.tooltip_text = "Composite conditions (all/any/not) and fields the editor does not model are edited here."
	line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(line)
	line.text_changed.connect(func(text):
		var parsed = JSON.parse_string(str(text).strip_edges())
		if typeof(parsed) != TYPE_DICTIONARY:
			line.modulate = Color(1.0, 0.6, 0.6)
			return
		line.modulate = Color.WHITE
		if keys.is_empty():
			choice["condition"] = parsed
		else:
			for key in keys: condition.erase(key)
			for key in parsed: condition[key] = parsed[key]
		database_modified.emit()
	)
	row.add_child(line)
	parent.add_child(row)


func _add_check_row(parent: VBoxContainer, choice: Dictionary):
	var row := HBoxContainer.new()
	row.add_child(InspectorStyle.lbl("Skill check", InspectorStyle.COLOR_TEXT_DIM))
	var line := LineEdit.new()
	line.text = JSON.stringify(choice.get("check")) if choice.has("check") else ""
	line.placeholder_text = "{skill, difficulty, success_node, fail_node}"
	line.tooltip_text = "A check routes the reply two ways; both targets must be nodes in this graph."
	line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(line)
	line.text_changed.connect(func(text):
		var trimmed: String = str(text).strip_edges()
		if trimmed == "":
			choice.erase("check")
			line.modulate = Color.WHITE
			database_modified.emit()
			return
		var parsed = JSON.parse_string(trimmed)
		if typeof(parsed) == TYPE_DICTIONARY:
			choice["check"] = parsed
			line.modulate = Color.WHITE
		else:
			line.modulate = Color(1.0, 0.6, 0.6)
		database_modified.emit()
	)
	row.add_child(line)
	parent.add_child(row)


func _build_effects_row(parent: VBoxContainer, owner: Dictionary, label_text: String):
	var header := HBoxContainer.new()
	var label := InspectorStyle.lbl(label_text, InspectorStyle.COLOR_TEXT_DIM)
	label.add_theme_font_size_override("font_size", 11)
	header.add_child(label)
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var add := Button.new(); add.text = "+ Effect"
	InspectorStyle.apply_button_style(add, Color(0.2, 0.3, 0.4))
	add.pressed.connect(func():
		var effects: Dictionary = owner.get("effects", {}) if owner.get("effects") is Dictionary else {}
		effects["set_flag"] = "flag_name"
		owner["effects"] = effects
		database_modified.emit()
		_refresh_nodes()
	)
	header.add_child(add)
	parent.add_child(header)

	var effects: Dictionary = owner.get("effects", {}) if owner.get("effects") is Dictionary else {}
	if effects.is_empty():
		return
	for key in effects.keys():
		var row := HBoxContainer.new()
		var picker := OptionButton.new()
		var keys: Array = DialogueSchema.effect_keys()
		if not DialogueSchema.has_effect(str(key)): keys.append(str(key))
		for candidate in keys: picker.add_item(str(candidate))
		var index := keys.find(str(key))
		picker.select(index if index >= 0 else 0)
		picker.custom_minimum_size.x = 210
		InspectorStyle.apply_button_style(picker)
		var value = effects[key]
		picker.item_selected.connect(func(selected):
			var chosen := str(keys[selected])
			if chosen != str(key):
				effects.erase(key)
				effects[chosen] = value
				database_modified.emit()
				_refresh_nodes()
		)
		row.add_child(picker)

		var value_ed := LineEdit.new()
		value_ed.text = JSON.stringify(value) if (value is Dictionary or value is Array) else str(value)
		value_ed.placeholder_text = DialogueSchema.effect_shape(str(key))
		value_ed.tooltip_text = DialogueSchema.effect_shape(str(key))
		value_ed.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_input_style(value_ed)
		value_ed.text_changed.connect(func(text):
			var trimmed: String = str(text).strip_edges()
			if trimmed == "":
				effects.erase(key)
				value_ed.modulate = Color.WHITE
			elif trimmed.begins_with("{") or trimmed.begins_with("["):
				var parsed = JSON.parse_string(trimmed)
				if parsed == null:
					value_ed.modulate = Color(1.0, 0.6, 0.6)
					return
				effects[key] = parsed
				value_ed.modulate = Color.WHITE
			elif trimmed.is_valid_int():
				effects[key] = int(trimmed)
				value_ed.modulate = Color.WHITE
			else:
				effects[key] = trimmed
				value_ed.modulate = Color.WHITE
			database_modified.emit()
		)
		row.add_child(value_ed)

		var remove := Button.new(); remove.text = "×"
		InspectorStyle.apply_button_style(remove, Color(0.4, 0.1, 0.1))
		remove.pressed.connect(func():
			effects.erase(key)
			if effects.is_empty(): owner.erase("effects")
			database_modified.emit()
			_refresh_nodes()
		)
		row.add_child(remove)
		parent.add_child(row)


func _build_extras():
	var known := ["id", "root", "nodes", "_filename"]
	var extras: Array = []
	for key in cur_data:
		if not known.has(str(key)):
			extras.append(key)
	extras.sort()
	if extras.is_empty():
		return
	var note := Label.new()
	note.text = "Other graph fields (kept as authored): %s" % ", ".join(extras)
	note.add_theme_font_size_override("font_size", 11)
	note.modulate = Color(0.7, 0.72, 0.6)
	container.add_child(note)


# --- structure ----------------------------------------------------------------

# Renaming a node updates every reference to it. A hand-edited graph gets this
# wrong, and content validation then reports a choice that leads nowhere.
func _rename_node(old_id: String, new_id: String):
	var clean := str(new_id).strip_edges()
	var nodes: Dictionary = cur_data.get("nodes", {})
	if clean == "" or clean == old_id or nodes.has(clean):
		_refresh_nodes()
		return
	var node = nodes[old_id]
	nodes.erase(old_id)
	nodes[clean] = node
	for node_id in nodes:
		var other = nodes[node_id]
		if not (other is Dictionary): continue
		for choice in other.get("choices", []) if other.get("choices") is Array else []:
			if not (choice is Dictionary): continue
			if str(choice.get("next_node", "")) == old_id:
				choice["next_node"] = clean
			var check = choice.get("check")
			if check is Dictionary:
				for key in ["success_node", "fail_node"]:
					if str(check.get(key, "")) == old_id:
						check[key] = clean
	if str(cur_data.get("root", "")) == old_id:
		cur_data["root"] = clean
	database_modified.emit()
	_refresh_nodes()


func _remove_node(node_id: String):
	var nodes: Dictionary = cur_data.get("nodes", {})
	nodes.erase(node_id)
	if str(cur_data.get("root", "")) == node_id:
		cur_data["root"] = str(_node_ids()[0]) if not _node_ids().is_empty() else ""
	database_modified.emit()
	_refresh_nodes()


func _text_value(node: Dictionary) -> String:
	var text = node.get("text", "")
	if text is Dictionary:
		return str(text.get("player", text.get("test", "")))
	return str(text)


func _as_string_list(value) -> Array:
	if value is Array:
		var out: Array = []
		for entry in value: out.append(str(entry))
		return out
	return []
