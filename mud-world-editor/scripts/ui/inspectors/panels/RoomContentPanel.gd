# scripts/ui/inspectors/panels/RoomContentPanel.gd
class_name RoomContentPanel
extends RefCounted

signal data_modified

# Data
var cur_data: Dictionary
var database_mgr: DatabaseManager
# The room's own id and its region: a patrol point is a room id resolved in the
# placed NPC's home region, which is this one.
var room_id: String = ""
var region_mgr: RegionManager = null

# UI
var npc_box: VBoxContainer
var item_box: VBoxContainer

func build(parent_container: VBoxContainer, data: Dictionary, db_mgr: DatabaseManager, id: String = "", r_mgr: RegionManager = null):
	cur_data = data
	database_mgr = db_mgr
	room_id = id
	region_mgr = r_mgr

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
	for c in npc_box.get_children(): npc_box.remove_child(c); c.queue_free()
	for c in item_box.get_children(): item_box.remove_child(c); c.queue_free()
	
	# NPCs
	if cur_data.has("initial_npcs") and not cur_data.initial_npcs.is_empty():
		var idx = 0
		for n in cur_data.initial_npcs:
			var row = _create_content_row("npc", n, idx)
			row.name = "NPCPlacement_%d" % idx
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
			row.name = "ItemPlacement_%d" % idx
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

	_build_item_extra_overrides(card, placement, template)

	if not overrides.is_empty():
		var clear := Button.new(); clear.name = "ClearPlacementOverrides"; clear.text = "Clear placement overrides"
		InspectorStyle.apply_button_style(clear, Color(0.34, 0.18, 0.18))
		clear.pressed.connect(func(): placement.erase("properties_override"); data_modified.emit(); _refresh_content())
		card.add_child(clear)


# Keys the fields above do not cover: any other property the template has
# (or an extension added). Each keeps the type of the value it replaces --
# content_set.py::_item_placement_override_issues refuses anything else -- so
# the control is chosen by that type; arrays and objects are shown, not edited.
const _ITEM_FORM_OVERRIDES := ["name", "description", "is_open", "locked", "charges", "respawn_days"]

func _build_item_extra_overrides(card: VBoxContainer, placement: Dictionary, template: Dictionary) -> void:
	var overrides: Dictionary = placement.get("properties_override", {}) if placement.get("properties_override", {}) is Dictionary else {}
	var template_properties: Dictionary = template.get("properties", {}) if template.get("properties", {}) is Dictionary else {}
	var box := VBoxContainer.new(); box.name = "OtherItemOverrides"; box.add_theme_constant_override("separation", 2); card.add_child(box)
	for key in overrides.keys():
		if _ITEM_FORM_OVERRIDES.has(key) or str(key).begins_with("_"): continue
		box.add_child(_item_override_row(placement, str(key), overrides[key], template_properties.has(key)))
	var addable: Array = []
	for key in template_properties.keys():
		var value = template_properties[key]
		if overrides.has(key) or _ITEM_FORM_OVERRIDES.has(key) or str(key).begins_with("_"): continue
		if value is bool or value is int or value is float or value is String: addable.append(str(key))
	if addable.is_empty(): return
	addable.sort()
	var picker := OptionButton.new(); picker.name = "AddItemOverride"
	picker.add_item("Override a template property…"); picker.set_item_metadata(0, "")
	for key in addable:
		picker.add_item(key); picker.set_item_metadata(picker.item_count - 1, key)
	InspectorStyle.apply_button_style(picker)
	picker.item_selected.connect(func(index):
		var key := str(picker.get_item_metadata(index))
		if key.is_empty(): return
		var value = template_properties[key]
		_set_placement_override(placement, key, value.duplicate() if value is Array or value is Dictionary else value)
		_refresh_content.call_deferred())
	box.add_child(picker)


func _item_override_row(placement: Dictionary, key: String, value, from_template: bool) -> HBoxContainer:
	var row := HBoxContainer.new(); row.name = "ItemOverride_%s" % key
	var caption := InspectorStyle.lbl(key, InspectorStyle.COLOR_TEXT_DIM); caption.custom_minimum_size.x = 92
	if not from_template: caption.tooltip_text = "Not a property of this item's template; kept as written."
	row.add_child(caption)
	var control: Control
	if value is bool:
		var check := CheckBox.new(); check.button_pressed = value
		check.toggled.connect(func(on): _set_placement_override(placement, key, on))
		control = check
	elif value is int or value is float:
		var number := SpinBox.new(); number.allow_greater = true; number.allow_lesser = true
		number.step = 1.0 if value is int or is_equal_approx(value, round(value)) else 0.01
		number.value = float(value); InspectorStyle.apply_input_style(number)
		number.value_changed.connect(func(amount): _set_placement_override(placement, key, int(amount) if number.step >= 1.0 else amount))
		control = number
	elif value is String:
		var text := LineEdit.new(); text.text = value; InspectorStyle.apply_input_style(text)
		# An empty string is a value here, not "remove": removal is the × button.
		text.text_changed.connect(func(changed): _set_placement_override_raw(placement, key, changed))
		control = text
	else:
		control = InspectorStyle.lbl(JSON.stringify(value), InspectorStyle.COLOR_TEXT_DIM)
		control.tooltip_text = "Edited outside this form; kept as written."
	control.name = "Value"; control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(control)
	var drop := Button.new(); drop.text = "×"; drop.flat = true; drop.tooltip_text = "Remove this override (the template's value applies)"
	drop.pressed.connect(func(): _erase_placement_override(placement, key); _refresh_content.call_deferred())
	row.add_child(drop)
	return row


func _set_placement_override_raw(placement: Dictionary, key: String, value) -> void:
	var overrides: Dictionary = placement.get("properties_override", {}) if placement.get("properties_override", {}) is Dictionary else {}
	overrides[key] = value
	placement["properties_override"] = overrides
	data_modified.emit()


func _erase_placement_override(placement: Dictionary, key: String) -> void:
	var overrides = placement.get("properties_override")
	if not overrides is Dictionary or not overrides.erase(key): return
	if overrides.is_empty(): placement.erase("properties_override")
	data_modified.emit()


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
	for value in NPCVocabulary.BEHAVIOR_TYPES:
		behaviour.add_item(value.capitalize()); behaviour.set_item_metadata(behaviour.item_count - 1, value)
	var selected := str(overrides.get("behavior_type", "")); var selected_index := 0
	for index in range(1, behaviour.item_count):
		if str(behaviour.get_item_metadata(index)) == selected: selected_index = index
	behaviour.select(selected_index); InspectorStyle.apply_button_style(behaviour)
	# The route section depends on the behaviour, so a change rebuilds the row.
	behaviour.item_selected.connect(func(index): _set_npc_placement_override(placement, "behavior_type", str(behaviour.get_item_metadata(index))); _refresh_content.call_deferred())
	behaviour_row.add_child(behaviour); card.add_child(behaviour_row)
	_build_patrol_route(card, placement, template)
	_build_placement_tuning(card, placement, template)
	if not overrides.is_empty():
		var clear := Button.new(); clear.name = "ClearNPCPlacementOverrides"; clear.text = "Clear placement overrides"
		InspectorStyle.apply_button_style(clear, Color(0.34, 0.18, 0.18))
		clear.pressed.connect(func(): placement.erase("overrides"); data_modified.emit(); _refresh_content())
		card.add_child(clear)


# `overrides.properties_override` merges over the template's `properties`
# (npc_factory.py), so a placement can tune how this one NPC behaves: the same
# values NPCInspector's Behavior Tuning edits, and checked by the same rules
# (content_set.py::_npc_property_errors). A value is written only while its
# Override box is ticked; unticked, the template's value (or the engine
# default) applies. Other keys are listed and can be removed, never rewritten.
const _PLACEMENT_TUNING_INTEGERS := [
	["move_cooldown", "Move cooldown (s)", 10, 0],
	["respawn_cooldown", "Respawn (s, -1 never)", 600, -1],
]

func _build_placement_tuning(card: VBoxContainer, placement: Dictionary, template: Dictionary) -> void:
	var overrides: Dictionary = placement.get("overrides", {}) if placement.get("overrides", {}) is Dictionary else {}
	var own: Dictionary = overrides.get("properties_override", {}) if overrides.get("properties_override", {}) is Dictionary else {}
	var inherited: Dictionary = template.get("properties", {}) if template.get("properties", {}) is Dictionary else {}
	var box := VBoxContainer.new(); box.name = "NPCPlacementTuning"; box.add_theme_constant_override("separation", 2); card.add_child(box)
	box.add_child(InspectorStyle.lbl("Behaviour tuning (this placement)", InspectorStyle.COLOR_TEXT_DIM))
	var known: Array = []
	for spec in NPCInspector._BEHAVIOR_FRACTIONS:
		known.append(spec[0])
		box.add_child(_tuning_row(placement, own, inherited, str(spec[0]), str(spec[1]), float(spec[2]), 0.0, 1.0, 0.05, str(spec[3])))
	for spec in _PLACEMENT_TUNING_INTEGERS:
		known.append(spec[0])
		box.add_child(_tuning_row(placement, own, inherited, str(spec[0]), str(spec[1]), float(spec[2]), float(spec[3]), 99999.0, 1.0, ""))
	for key in own.keys():
		if known.has(key): continue
		var row := HBoxContainer.new(); row.name = "OtherProperty_%s" % key
		var text := InspectorStyle.lbl("%s = %s" % [key, JSON.stringify(own[key])], InspectorStyle.COLOR_TEXT_DIM)
		text.size_flags_horizontal = Control.SIZE_EXPAND_FILL; text.tooltip_text = "Set outside this form; kept as written."
		row.add_child(text)
		var drop := Button.new(); drop.text = "×"; drop.flat = true; drop.tooltip_text = "Remove this property override"
		drop.pressed.connect(func(): _erase_npc_property_override(placement, str(key)); _refresh_content())
		row.add_child(drop); box.add_child(row)


func _tuning_row(placement: Dictionary, own: Dictionary, inherited: Dictionary, key: String, label: String, engine_default: float, min_value: float, max_value: float, step: float, tip: String) -> HBoxContainer:
	var row := HBoxContainer.new(); row.name = "Tuning_%s" % key
	var toggle := CheckBox.new(); toggle.name = "Override"; toggle.text = label; toggle.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	toggle.button_pressed = own.has(key); toggle.tooltip_text = tip
	row.add_child(toggle)
	var fallback := float(inherited.get(key, engine_default))
	var value := SpinBox.new(); value.name = "Value"; value.min_value = min_value; value.max_value = max_value; value.step = step
	value.value = float(own.get(key, fallback)); value.editable = own.has(key); value.custom_minimum_size.x = 80
	value.tooltip_text = "Template: %s" % str(inherited.get(key, "engine default %s" % str(engine_default)))
	InspectorStyle.apply_input_style(value)
	var written := func(amount: float): return int(amount) if step >= 1.0 else amount
	value.value_changed.connect(func(amount):
		if toggle.button_pressed: _set_npc_property_override(placement, key, written.call(amount)))
	toggle.toggled.connect(func(on):
		value.editable = on
		if on: _set_npc_property_override(placement, key, written.call(value.value))
		else:
			_erase_npc_property_override(placement, key)
			value.set_value_no_signal(fallback))
	row.add_child(value)
	return row


func _set_npc_property_override(placement: Dictionary, key: String, value) -> void:
	var overrides: Dictionary = placement.get("overrides", {}) if placement.get("overrides", {}) is Dictionary else {}
	var own: Dictionary = overrides.get("properties_override", {}) if overrides.get("properties_override", {}) is Dictionary else {}
	if own.get(key) == value and own.has(key): return
	own[key] = value
	overrides["properties_override"] = own; placement["overrides"] = overrides
	data_modified.emit()


func _erase_npc_property_override(placement: Dictionary, key: String) -> void:
	var overrides: Dictionary = placement.get("overrides", {}) if placement.get("overrides", {}) is Dictionary else {}
	var own = overrides.get("properties_override")
	if not own is Dictionary or not own.erase(key): return
	if own.is_empty(): overrides.erase("properties_override")
	if overrides.is_empty(): placement.erase("overrides")
	data_modified.emit()


# The route `npcs/ai/movement.py::perform_patrol` walks: the template's
# `patrol_points` unless this placement sets its own, starting at `patrol_index`.
# Points are offered from this region only, since that is where they resolve;
# the engine refuses one the NPC cannot walk to when the region is saved.
func _build_patrol_route(card: VBoxContainer, placement: Dictionary, template: Dictionary) -> void:
	var overrides: Dictionary = placement.get("overrides", {}) if placement.get("overrides", {}) is Dictionary else {}
	var behaviour := str(overrides.get("behavior_type", template.get("behavior_type", "")))
	var own_route: bool = overrides.has("patrol_points")
	var template_points: Array = template.get("patrol_points", []) if template.get("patrol_points", []) is Array else []
	if behaviour != "patrol" and not own_route: return
	var box := VBoxContainer.new(); box.name = "PatrolRoute"; box.add_theme_constant_override("separation", 4); card.add_child(box)
	box.add_child(InspectorStyle.lbl("Patrol route", InspectorStyle.COLOR_TEXT_DIM))
	if behaviour != "patrol":
		box.add_child(_hint("Only a Patrol NPC walks a route; this one's behaviour is %s, so the route is ignored." % (behaviour if behaviour != "" else "unset")))
	if not own_route:
		box.add_child(_hint("Template route: " + (" → ".join(PackedStringArray(template_points)) if not template_points.is_empty() else "none, so it stands still")))
		var customise := Button.new(); customise.name = "SetPatrolRoute"; customise.text = "Set a route for this placement"
		InspectorStyle.apply_button_style(customise, Color(0.2, 0.25, 0.3))
		customise.pressed.connect(func():
			var first: Array = template_points.duplicate() if not template_points.is_empty() else ([room_id] if room_id != "" else [])
			_set_npc_placement_override(placement, "patrol_points", first); _refresh_content())
		box.add_child(customise)
		return
	var points: Array = overrides["patrol_points"] if overrides["patrol_points"] is Array else []
	if points.is_empty(): box.add_child(_hint("No points: a Patrol NPC with an empty route stands still."))
	for index in points.size(): box.add_child(_patrol_point_row(placement, points, index))
	var actions := HBoxContainer.new(); box.add_child(actions)
	var add := Button.new(); add.name = "AddPatrolPoint"; add.text = "+ Point"; add.flat = true
	add.pressed.connect(func():
		var rooms := _region_room_ids()
		points.append(room_id if room_id != "" else (rooms[0] if not rooms.is_empty() else ""))
		data_modified.emit(); _refresh_content())
	actions.add_child(add)
	actions.add_child(InspectorStyle.lbl("Starts at", InspectorStyle.COLOR_TEXT_DIM))
	var start := SpinBox.new(); start.name = "PatrolStart"; start.min_value = 1; start.max_value = max(1, points.size()); start.step = 1
	start.value = int(overrides.get("patrol_index", 0)) + 1; InspectorStyle.apply_input_style(start)
	start.tooltip_text = "Which point it heads for first."
	start.value_changed.connect(func(value):
		if int(value) <= 1: _erase_npc_placement_override(placement, "patrol_index")
		else: _set_npc_placement_override(placement, "patrol_index", int(value) - 1))
	actions.add_child(start)
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; actions.add_child(spacer)
	var reset := Button.new(); reset.name = "UseTemplateRoute"; reset.text = "Use template route"; reset.flat = true
	reset.pressed.connect(func():
		_erase_npc_placement_override(placement, "patrol_points"); _erase_npc_placement_override(placement, "patrol_index"); _refresh_content())
	actions.add_child(reset)


func _patrol_point_row(placement: Dictionary, points: Array, index: int) -> HBoxContainer:
	var row := HBoxContainer.new(); row.name = "PatrolPoint_%d" % index
	row.add_child(InspectorStyle.lbl("%d." % (index + 1), InspectorStyle.COLOR_TEXT_DIM))
	var picker := OptionButton.new(); picker.name = "Room"; picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var current := str(points[index])
	var rooms := _region_room_ids()
	for room in rooms:
		picker.add_item(_room_label(room)); picker.set_item_metadata(picker.item_count - 1, room)
		if room == current: picker.select(picker.item_count - 1)
	if not rooms.has(current):
		picker.add_item("Missing: %s" % current); picker.set_item_metadata(picker.item_count - 1, current); picker.select(picker.item_count - 1)
	InspectorStyle.apply_button_style(picker)
	picker.item_selected.connect(func(choice):
		points[index] = str(picker.get_item_metadata(choice)); data_modified.emit())
	row.add_child(picker)
	for pair in [["^", -1], ["v", 1]]:
		var move := Button.new(); move.text = pair[0]; move.flat = true
		move.disabled = index + int(pair[1]) < 0 or index + int(pair[1]) >= points.size()
		move.pressed.connect(func():
			var other := index + int(pair[1])
			var held = points[other]; points[other] = points[index]; points[index] = held
			data_modified.emit(); _refresh_content())
		row.add_child(move)
	var drop := Button.new(); drop.text = "×"; drop.flat = true; drop.tooltip_text = "Remove this point"
	drop.pressed.connect(func():
		points.remove_at(index)
		# A start past the end raises in the AI tick.
		if int(placement.get("overrides", {}).get("patrol_index", 0)) >= points.size(): _erase_npc_placement_override(placement, "patrol_index")
		data_modified.emit(); _refresh_content())
	row.add_child(drop)
	return row


func _region_room_ids() -> Array:
	var ids: Array = []
	if region_mgr != null and region_mgr.data.get("rooms") is Dictionary: ids = region_mgr.data.rooms.keys()
	ids.sort()
	return ids


func _room_label(room: String) -> String:
	var rooms: Dictionary = region_mgr.data.get("rooms", {}) if region_mgr != null else {}
	var name := str(rooms[room].get("name", "")) if rooms.get(room) is Dictionary else ""
	return "%s (%s)" % [name, room] if name != "" and name != room else room


func _hint(text: String) -> Label:
	var label := InspectorStyle.lbl(text, InspectorStyle.COLOR_TEXT_DIM)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	return label


func _erase_npc_placement_override(placement: Dictionary, key: String) -> void:
	var overrides: Dictionary = placement.get("overrides", {}) if placement.get("overrides", {}) is Dictionary else {}
	if not overrides.erase(key): return
	if overrides.is_empty(): placement.erase("overrides")
	data_modified.emit()


func _set_npc_placement_override(placement: Dictionary, key: String, value) -> void:
	var overrides: Dictionary = placement.get("overrides", {}) if placement.get("overrides", {}) is Dictionary else {}
	if value is String and str(value).is_empty(): overrides.erase(key)
	else: overrides[key] = value
	if overrides.is_empty(): placement.erase("overrides")
	else: placement["overrides"] = overrides
	data_modified.emit()
