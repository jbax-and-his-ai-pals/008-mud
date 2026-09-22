# scripts/ui/inspectors/panels/RoomContentPanel.gd
class_name RoomContentPanel
extends RefCounted

signal data_modified

# Data
var cur_data: Dictionary
var database_mgr: DatabaseManager

# UI
var npc_box: VBoxContainer
var item_box: VBoxContainer

func build(parent_container: VBoxContainer, data: Dictionary, db_mgr: DatabaseManager):
	cur_data = data
	database_mgr = db_mgr

	parent_container.add_child(InspectorStyle.create_section_header("CONTENT"))
	var card = InspectorStyle.create_card()
	var vbox = card.get_child(0).get_child(0)
	parent_container.add_child(card)
	
	vbox.add_child(InspectorStyle.lbl("NPCs", InspectorStyle.COLOR_TEXT_DIM))
	npc_box = VBoxContainer.new(); npc_box.add_theme_constant_override("separation", 6)
	vbox.add_child(npc_box)
	
	vbox.add_child(HSeparator.new())
	
	vbox.add_child(InspectorStyle.lbl("Items", InspectorStyle.COLOR_TEXT_DIM))
	item_box = VBoxContainer.new(); item_box.add_theme_constant_override("separation", 6)
	vbox.add_child(item_box)
	
	_refresh_content()

func _refresh_content():
	for c in npc_box.get_children(): c.queue_free()
	for c in item_box.get_children(): c.queue_free()
	
	# NPCs
	if cur_data.has("initial_npcs") and not cur_data.initial_npcs.is_empty():
		var idx = 0
		for n in cur_data.initial_npcs:
			var row = _create_content_row("npc", n, idx)
			npc_box.add_child(row)
			idx += 1
	else:
		var l = Label.new(); l.text="No NPCs."; l.modulate=Color(1,1,1,0.3); l.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER
		l.size_flags_vertical = Control.SIZE_SHRINK_CENTER; npc_box.add_child(l)
		
	var btn_n = Button.new(); btn_n.text="+ Add NPC"; btn_n.alignment = HORIZONTAL_ALIGNMENT_CENTER
	InspectorStyle.apply_button_style(btn_n, Color(0.2, 0.2, 0.25))
	btn_n.pressed.connect(func():
		if not cur_data.has("initial_npcs"): cur_data.initial_npcs = []
		cur_data.initial_npcs.append({"template_id": "villager"})
		data_modified.emit(); _refresh_content()
	)
	npc_box.add_child(btn_n)
	
	# Items
	if cur_data.has("items") and not cur_data.items.is_empty():
		var idx = 0
		for i in cur_data.items:
			var row = _create_content_row("item", i, idx)
			item_box.add_child(row)
			idx += 1
	else:
		var l = Label.new(); l.text="No Items."; l.modulate=Color(1,1,1,0.3); l.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER
		l.size_flags_vertical = Control.SIZE_SHRINK_CENTER; item_box.add_child(l)
		
	var btn_i = Button.new(); btn_i.text="+ Add Item"; btn_i.alignment = HORIZONTAL_ALIGNMENT_CENTER
	InspectorStyle.apply_button_style(btn_i, Color(0.2, 0.2, 0.25))
	btn_i.pressed.connect(func():
		if not cur_data.has("items"): cur_data.items = []
		# An empty authored row is deliberately invalid until the author chooses a
		# template.  Guessing a content-set-specific coin here made a newly added
		# row look valid while silently coupling every set to fantasy content.
		cur_data.items.append({"item_id": "", "quantity": 1})
		data_modified.emit(); _refresh_content()
	)
	item_box.add_child(btn_i)

func _create_content_row(type, data, idx) -> PanelContainer:
	var pc = PanelContainer.new()
	var style = StyleBoxFlat.new(); style.bg_color = Color(0.15, 0.15, 0.17); style.set_corner_radius_all(4)
	pc.add_theme_stylebox_override("panel", style)
	
	var m = MarginContainer.new(); m.add_theme_constant_override("margin_left", 5); m.add_theme_constant_override("margin_right", 5)
	pc.add_child(m)
	
	var hb = HBoxContainer.new(); m.add_child(hb)
	var ico = Label.new(); ico.text = "👤" if type == "npc" else "📦"; hb.add_child(ico)
	
	var vb_in = VBoxContainer.new(); vb_in.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vb_in.add_theme_constant_override("separation", 2); hb.add_child(vb_in)
	
	if type == "npc":
		var hb1 = HBoxContainer.new(); hb1.add_child(InspectorStyle.lbl("T:", InspectorStyle.COLOR_TEXT_DIM))
		var ed_t = LineEdit.new(); ed_t.text = data.get("template_id", ""); ed_t.placeholder_text = "Template ID"
		ed_t.size_flags_horizontal = Control.SIZE_EXPAND_FILL; ed_t.flat = true
		InspectorStyle.apply_input_style(ed_t); ed_t.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
		ed_t.text_submitted.connect(func(t): data.template_id = t; data_modified.emit()); hb1.add_child(ed_t)
		InspectorStyle.add_suggestion_button(hb1, ed_t, func(): return database_mgr.get_npc_ids()); vb_in.add_child(hb1)
		
		var hb2 = HBoxContainer.new(); hb2.add_child(InspectorStyle.lbl("I:", InspectorStyle.COLOR_TEXT_DIM))
		var ed_i = LineEdit.new(); ed_i.text = data.get("instance_id", ""); ed_i.placeholder_text = "Instance (Opt)"
		ed_i.size_flags_horizontal = Control.SIZE_EXPAND_FILL; ed_i.flat = true
		InspectorStyle.apply_input_style(ed_i); ed_i.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
		ed_i.text_changed.connect(func(t): data.instance_id = t; data_modified.emit()); hb2.add_child(ed_i); vb_in.add_child(hb2)
		_build_npc_placement_overrides(vb_in, data)
	else:
		var hb1 = HBoxContainer.new()
		var ed_id = LineEdit.new(); ed_id.name = "ItemTemplate"; ed_id.text = data.get("item_id", "")
		ed_id.placeholder_text = "Choose item template"
		ed_id.size_flags_horizontal = Control.SIZE_EXPAND_FILL; ed_id.flat = true
		InspectorStyle.apply_input_style(ed_id); ed_id.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
		ed_id.text_submitted.connect(func(t): data.item_id = t.strip_edges(); data_modified.emit(); _refresh_content()); hb1.add_child(ed_id)
		InspectorStyle.add_suggestion_button(hb1, ed_id, func(): return database_mgr.get_item_ids())
		
		hb1.add_child(InspectorStyle.lbl("x", InspectorStyle.COLOR_TEXT_DIM))
		var sb = SpinBox.new(); sb.name = "PlacementQuantity"; sb.min_value = 1; sb.max_value = 999; sb.step = 1; sb.value = max(1, int(data.get("quantity", 1))); sb.custom_minimum_size.x = 60
		InspectorStyle.apply_input_style(sb); sb.value_changed.connect(func(v): data.quantity = int(v); data_modified.emit()); hb1.add_child(sb)
		vb_in.add_child(hb1)
		_build_item_placement_overrides(vb_in, data)
	
	var btn_del = Button.new(); btn_del.text = "🗑"; btn_del.flat = true
	btn_del.pressed.connect(func(): 
		if type == "npc": cur_data.initial_npcs.remove_at(idx)
		else: cur_data.items.remove_at(idx)
		data_modified.emit(); _refresh_content()
	)
	hb.add_child(btn_del)
	
	return pc


# A room placement is an instance recipe, not a second item template.  The
# template continues to define its durable contract; this compact disclosure
# exposes the handful of context-dependent values an author can reasonably
# vary from room to room.  Unknown keys are never rewritten, so old or
# extension-owned overrides survive an editor visit intact.
func _build_item_placement_overrides(parent: VBoxContainer, placement: Dictionary) -> void:
	var template_id := str(placement.get("item_id", ""))
	var template: Dictionary = database_mgr.items.get(template_id, {}) if database_mgr != null else {}
	var item_class := str(template.get("type", "Item"))
	var overrides: Dictionary = placement.get("properties_override", {}) if placement.get("properties_override", {}) is Dictionary else {}
	var toggle := Button.new(); toggle.name = "PlacementOverridesToggle"
	toggle.text = "Placement overrides" if overrides.is_empty() else "Placement overrides • configured"
	toggle.tooltip_text = "Change this placed instance without changing its item template."
	InspectorStyle.apply_button_style(toggle, Color(0.16, 0.27, 0.34))
	parent.add_child(toggle)
	var card := VBoxContainer.new(); card.name = "PlacementOverrides"; card.visible = not overrides.is_empty()
	card.add_theme_constant_override("separation", 4)
	parent.add_child(card)
	toggle.pressed.connect(func(): card.visible = not card.visible)

	var note := InspectorStyle.lbl("These values apply only to this room placement.", InspectorStyle.COLOR_TEXT_DIM)
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	card.add_child(note)
	var name := LineEdit.new(); name.name = "PlacementName"; name.text = str(overrides.get("name", "")); name.placeholder_text = "Display name (template default)"; name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(name)
	name.text_changed.connect(func(value): _set_placement_override(placement, "name", str(value).strip_edges()))
	card.add_child(_placement_field("Display name", name))
	var description := TextEdit.new(); description.name = "PlacementDescription"; description.text = str(overrides.get("description", "")); description.placeholder_text = "Description (template default)"; description.custom_minimum_size.y = 54; description.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	InspectorStyle.apply_input_style(description)
	description.text_changed.connect(func(): _set_placement_override(placement, "description", description.text.strip_edges()))
	card.add_child(_placement_field("Description", description))

	if item_class == "Container":
		var container_properties: Dictionary = template.get("properties", {}) if template.get("properties", {}) is Dictionary else {}
		var state := HBoxContainer.new(); state.name = "ContainerPlacementState"
		var starts_open := CheckBox.new(); starts_open.text = "Starts open"; starts_open.button_pressed = bool(overrides.get("is_open", container_properties.get("is_open", false)))
		starts_open.toggled.connect(func(value): _set_placement_override(placement, "is_open", value))
		state.add_child(starts_open)
		var locked := CheckBox.new(); locked.text = "Locked"; locked.button_pressed = bool(overrides.get("locked", container_properties.get("locked", false)))
		locked.toggled.connect(func(value): _set_placement_override(placement, "locked", value))
		state.add_child(locked); card.add_child(state)
	elif item_class == "ResourceNode":
		var resource := HBoxContainer.new(); resource.name = "ResourcePlacementState"
		var template_properties: Dictionary = template.get("properties", {}) if template.get("properties", {}) is Dictionary else {}
		for pair in [["Charges", "charges", int(template_properties.get("charges", 3))], ["Respawn days", "respawn_days", int(template_properties.get("respawn_days", 0))]]:
			var field := VBoxContainer.new(); field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			field.add_child(InspectorStyle.lbl(pair[0], InspectorStyle.COLOR_TEXT_DIM))
			var amount := SpinBox.new(); amount.name = "Placement" + str(pair[1]).capitalize(); amount.min_value = 0; amount.max_value = 999; amount.step = 1; amount.value = int(overrides.get(pair[1], pair[2]))
			InspectorStyle.apply_input_style(amount)
			amount.value_changed.connect(func(value): _set_placement_override(placement, str(pair[1]), int(value)))
			field.add_child(amount); resource.add_child(field)
		card.add_child(resource)

	if not overrides.is_empty():
		var clear := Button.new(); clear.name = "ClearPlacementOverrides"; clear.text = "Clear placement overrides"
		InspectorStyle.apply_button_style(clear, Color(0.34, 0.18, 0.18))
		clear.pressed.connect(func(): placement.erase("properties_override"); data_modified.emit(); _refresh_content())
		card.add_child(clear)


func _placement_field(label: String, control: Control) -> HBoxContainer:
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
	var caption := InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM); caption.custom_minimum_size.x = 92
	row.add_child(caption); row.add_child(control)
	return row


func _set_placement_override(placement: Dictionary, key: String, value) -> void:
	var overrides: Dictionary = placement.get("properties_override", {}) if placement.get("properties_override", {}) is Dictionary else {}
	if value is String and str(value).is_empty():
		overrides.erase(key)
	else:
		overrides[key] = value
	if overrides.is_empty(): placement.erase("properties_override")
	else: placement["properties_override"] = overrides
	data_modified.emit()


# NPC templates own broad combat/social definition.  A placement only owns the
# small, runtime-supported difference between two uses of that template: a
# named encounter can be wounded, stronger, or stationary without becoming a
# new NPC template.  The behaviour picker mirrors the engine's closed author
# vocabulary; "template default" deliberately writes nothing.
func _build_npc_placement_overrides(parent: VBoxContainer, placement: Dictionary) -> void:
	var template_id := str(placement.get("template_id", ""))
	var template: Dictionary = database_mgr.npcs.get(template_id, {}) if database_mgr != null else {}
	var overrides: Dictionary = placement.get("overrides", {}) if placement.get("overrides", {}) is Dictionary else {}
	var toggle := Button.new(); toggle.name = "NPCPlacementOverridesToggle"
	toggle.text = "Placement overrides" if overrides.is_empty() else "Placement overrides • configured"
	toggle.tooltip_text = "Change this NPC instance without changing its template."
	InspectorStyle.apply_button_style(toggle, Color(0.25, 0.22, 0.35))
	parent.add_child(toggle)
	var card := VBoxContainer.new(); card.name = "NPCPlacementOverrides"; card.visible = not overrides.is_empty()
	card.add_theme_constant_override("separation", 4); parent.add_child(card)
	toggle.pressed.connect(func(): card.visible = not card.visible)
	var note := InspectorStyle.lbl("These values apply only to this room placement.", InspectorStyle.COLOR_TEXT_DIM)
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; card.add_child(note)
	var name := LineEdit.new(); name.name = "NPCPlacementName"; name.text = str(overrides.get("name", "")); name.placeholder_text = "Display name (template default)"; name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(name); name.text_changed.connect(func(value): _set_npc_placement_override(placement, "name", str(value).strip_edges()))
	card.add_child(_placement_field("Display name", name))
	var numbers := HBoxContainer.new(); numbers.name = "NPCPlacementStats"
	for pair in [["Level", "level", int(template.get("level", 1)), 1], ["Health", "health", int(template.get("health", 1)), 1], ["Max health", "max_health", int(template.get("max_health", 1)), 1], ["Ability", "mana", int(template.get("max_mana", 0)), 0]]:
		var field := VBoxContainer.new(); field.size_flags_horizontal = Control.SIZE_EXPAND_FILL; field.add_child(InspectorStyle.lbl(pair[0], InspectorStyle.COLOR_TEXT_DIM))
		var amount := SpinBox.new(); amount.name = "NPCPlacement" + str(pair[1]).capitalize(); amount.min_value = int(pair[3]); amount.max_value = 9999; amount.step = 1; amount.value = int(overrides.get(pair[1], pair[2]))
		InspectorStyle.apply_input_style(amount); amount.value_changed.connect(func(value): _set_npc_placement_override(placement, str(pair[1]), int(value)))
		field.add_child(amount); numbers.add_child(field)
	card.add_child(numbers)
	var behaviour_row := HBoxContainer.new(); behaviour_row.add_child(InspectorStyle.lbl("Behaviour", InspectorStyle.COLOR_TEXT_DIM))
	var behaviour := OptionButton.new(); behaviour.name = "NPCPlacementBehaviour"; behaviour.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	behaviour.add_item("Template default"); behaviour.set_item_metadata(0, "")
	for value in ["stationary", "wanderer", "aggressive", "patrol", "follower", "scheduled", "healer", "minion"]:
		behaviour.add_item(value.capitalize()); behaviour.set_item_metadata(behaviour.item_count - 1, value)
	var selected := str(overrides.get("behavior_type", "")); var selected_index := 0
	for index in range(1, behaviour.item_count):
		if str(behaviour.get_item_metadata(index)) == selected: selected_index = index
	behaviour.select(selected_index); InspectorStyle.apply_button_style(behaviour)
	behaviour.item_selected.connect(func(index): _set_npc_placement_override(placement, "behavior_type", str(behaviour.get_item_metadata(index))))
	behaviour_row.add_child(behaviour); card.add_child(behaviour_row)
	if not overrides.is_empty():
		var clear := Button.new(); clear.name = "ClearNPCPlacementOverrides"; clear.text = "Clear placement overrides"
		InspectorStyle.apply_button_style(clear, Color(0.34, 0.18, 0.18))
		clear.pressed.connect(func(): placement.erase("overrides"); data_modified.emit(); _refresh_content())
		card.add_child(clear)


func _set_npc_placement_override(placement: Dictionary, key: String, value) -> void:
	var overrides: Dictionary = placement.get("overrides", {}) if placement.get("overrides", {}) is Dictionary else {}
	if value is String and str(value).is_empty(): overrides.erase(key)
	else: overrides[key] = value
	if overrides.is_empty(): placement.erase("overrides")
	else: placement["overrides"] = overrides
	data_modified.emit()
