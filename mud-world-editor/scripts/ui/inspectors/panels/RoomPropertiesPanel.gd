# scripts/ui/inspectors/panels/RoomPropertiesPanel.gd
class_name RoomPropertiesPanel
extends RefCounted

signal data_modified

# Data
var cur_props: Dictionary

# UI
var props_box: VBoxContainer
var flow_container: HFlowContainer
var creation_tag: PanelContainer = null
var popup_menu: PopupMenu # New property to hold a direct reference

# "Music" used to be offered here; nothing reads `music`, so it is gone.
const COMMON_PROPS = {
	"Dark": {"key": "dark", "val": true},
	"Outdoors": {"key": "outdoors", "val": true},
	"Safe Zone": {"key": "safe_zone", "val": true},
	"Noisy": {"key": "noisy", "val": true},
	"Start Node": {"key": "is_start_node", "val": true},
	"Icon": {"key": "icon", "val": "none"},
	"Smell": {"key": "smell", "val": "damp earth"},
	"Weather": {"key": "weather", "val": "clear"},
}

# The room properties something reads (engine `room.py` ROOM_PROPERTY_KINDS
# plus this editor's own map keys), kept equal by schema_parity_smoke.gd. The
# bag is open, so any other key is kept and does nothing; the panel says so.
const ROOM_PROPERTY_KINDS := {
	"dark": "boolean", "noisy": "boolean", "smell": "string", "temperature": "string", "outdoors": "boolean",
	"safe_zone": "boolean", "weather": "string",
	"hazard_type": "string", "hazard_damage": "number", "hazard_tick_interval": "number",
	"weather_hazard_multipliers": "object", "exit_requirements": "object", "hidden_exits": "object",
	"env_interactions": "object", "locked_by": "string", "entered_by_system": "string",
	"is_start_node": "boolean", "icon": "string",
}

func build(parent_container: VBoxContainer, properties_data: Dictionary):
	cur_props = properties_data
	
	var header_box = HBoxContainer.new()
	header_box.add_child(InspectorStyle.create_section_header("PROPERTIES"))
	var spacer = Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header_box.add_child(spacer)
	
	var btn_add = MenuButton.new(); btn_add.text = "+ Tag"; btn_add.flat = true
	btn_add.add_theme_color_override("font_color", InspectorStyle.COLOR_ACCENT)
	btn_add.add_theme_color_override("font_hover_color", Color.WHITE)
	header_box.add_child(btn_add)
	parent_container.add_child(header_box)
	
	var card = InspectorStyle.create_card()
	var vbox = card.get_child(0).get_child(0)
	parent_container.add_child(card)
	
	popup_menu = btn_add.get_popup() # Store the reference here
	popup_menu.id_pressed.connect(_on_add_tag_selected)
	
	props_box = VBoxContainer.new()
	vbox.add_child(props_box)
	_refresh_props()

func _on_add_tag_selected(id):
	var item_text = popup_menu.get_item_text(id) # Use the stored reference
	if item_text == "Custom...":
		_show_creation_tag()
	else:
		var key = COMMON_PROPS[item_text].key
		var val = COMMON_PROPS[item_text].val
		if not cur_props.has(key):
			cur_props[key] = val
			data_modified.emit()
			_refresh_props()

func _show_creation_tag():
	if is_instance_valid(creation_tag): return # Already adding one
	
	creation_tag = PanelContainer.new()
	var style = StyleBoxFlat.new(); style.bg_color = Color(0.3, 0.3, 0.35); style.set_corner_radius_all(12)
	style.content_margin_left = 6; style.content_margin_right = 6; style.content_margin_top = 2; style.content_margin_bottom = 2
	creation_tag.add_theme_stylebox_override("panel", style)
	
	var hb = HBoxContainer.new(); creation_tag.add_child(hb)
	
	var key_edit = LineEdit.new(); key_edit.placeholder_text = "key"; key_edit.name = "KeyEdit"
	InspectorStyle.apply_input_style(key_edit); hb.add_child(key_edit)
	
	var type_select = OptionButton.new(); type_select.name = "TypeSelect"
	type_select.add_item("String"); type_select.add_item("Number"); type_select.add_item("Bool")
	InspectorStyle.apply_button_style(type_select); hb.add_child(type_select)
	
	var val_edit = LineEdit.new(); val_edit.placeholder_text = "value"; val_edit.name = "ValueEdit"
	InspectorStyle.apply_input_style(val_edit); hb.add_child(val_edit)
	
	var confirm_btn = Button.new(); confirm_btn.text = "✔"
	InspectorStyle.apply_button_style(confirm_btn, InspectorStyle.COLOR_SUCCESS); hb.add_child(confirm_btn)
	
	var cancel_btn = Button.new(); cancel_btn.text = "✖"
	InspectorStyle.apply_button_style(cancel_btn, InspectorStyle.COLOR_DANGER); hb.add_child(cancel_btn)
	
	flow_container.add_child(creation_tag)
	key_edit.grab_focus()
	
	confirm_btn.pressed.connect(_finalize_new_prop)
	cancel_btn.pressed.connect(_cancel_new_prop)
	key_edit.text_submitted.connect(func(_t): _finalize_new_prop())
	val_edit.text_submitted.connect(func(_t): _finalize_new_prop())

func _finalize_new_prop():
	if not is_instance_valid(creation_tag): return
	
	var key = creation_tag.get_node("KeyEdit").text.strip_edges()
	var type_idx = creation_tag.get_node("TypeSelect").selected
	var val_str = creation_tag.get_node("ValueEdit").text.strip_edges()
	
	if key.is_empty() or cur_props.has(key):
		# Visual feedback for error would be good here, but for now we just cancel
		_cancel_new_prop()
		return

	var final_val
	match type_idx:
		0: # String
			final_val = val_str
		1: # Number
			if val_str.is_valid_float(): final_val = val_str.to_float()
			else: final_val = 0.0
		2: # Bool
			final_val = val_str.to_lower() in ["true", "1", "yes", "on"]
	
	cur_props[key] = final_val
	creation_tag.queue_free()
	creation_tag = null
	data_modified.emit()
	_refresh_props()

func _cancel_new_prop():
	if is_instance_valid(creation_tag):
		creation_tag.queue_free()
		creation_tag = null

func _refresh_props():
	if is_instance_valid(flow_container):
		for c in flow_container.get_children():
			if c != creation_tag:
				c.queue_free()
	else:
		for c in props_box.get_children(): c.queue_free()
		flow_container = HFlowContainer.new()
		flow_container.add_theme_constant_override("h_separation", 8)
		flow_container.add_theme_constant_override("v_separation", 8)
		props_box.add_child(flow_container)

	# Update the dropdown menu for adding tags
	popup_menu.clear() # Use the stored reference
	var sorted_common_keys = COMMON_PROPS.keys()
	sorted_common_keys.sort()
	for k in sorted_common_keys:
		if not cur_props.has(COMMON_PROPS[k].key):
			popup_menu.add_item(k)
	popup_menu.add_separator()
	popup_menu.add_item("Custom...")
	
	if cur_props.is_empty():
		var l = Label.new(); l.text = "None."; l.modulate = Color(1,1,1,0.3); l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		flow_container.add_child(l)
		return

	# Which properties this panel may edit is not a decision made here: a nested
	# value rendered into a LineEdit is stringified and then written back over the
	# object. Six shipped rooms carry one -- `hidden_exits` on obsidian_trial's
	# hall_of_gates is a real traversable link the engine reads -- so the rule
	# lives in PropertyTagRow, shared with RegionInspector, which had it and this
	# panel did not.
	for key in PropertyTagRow.editable_keys(cur_props):
		flow_container.add_child(PropertyTagRow.build_row(
			key, cur_props[key], cur_props, _on_row_modified, _refresh_props
		))

	# Added to props_box rather than the flow container: a structured value is a
	# full-width note, not another chip in the row.
	PropertyTagRow.add_nested_rows(props_box, cur_props, "the room's own editor")
	_note_unread_keys()


# The ruleset's custody section names two room keys of its own.
static func ruleset_room_keys() -> Array:
	var keys: Array = []
	var text := FileAccess.get_file_as_string(DataRoot.ruleset_path()) if FileAccess.file_exists(DataRoot.ruleset_path()) else ""
	var ruleset = JSON.parse_string(text) if text != "" else null
	var custody = ruleset.get("crime", {}).get("custody", {}) if ruleset is Dictionary and ruleset.get("crime") is Dictionary else {}
	if custody is Dictionary:
		if str(custody.get("room_property", "")).strip_edges() != "": keys.append(str(custody["room_property"]).strip_edges())
		keys.append(str(custody.get("release_destination_property", "release_destination")).strip_edges())
	return keys


static func unread_keys(properties: Dictionary, extra_known: Array = []) -> Array:
	var out: Array = []
	for key in properties.keys():
		if str(key).begins_with("_") or ROOM_PROPERTY_KINDS.has(key) or extra_known.has(key): continue
		out.append(str(key))
	out.sort()
	return out


func _note_unread_keys() -> void:
	var existing := props_box.get_node_or_null("UnreadRoomKeys")
	if existing != null: props_box.remove_child(existing); existing.queue_free()
	var unread := unread_keys(cur_props, ruleset_room_keys())
	if unread.is_empty(): return
	var note := InspectorStyle.lbl("Read by nothing, so no effect in play: %s" % ", ".join(PackedStringArray(unread)), InspectorStyle.COLOR_DANGER)
	note.name = "UnreadRoomKeys"; note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	note.tooltip_text = "Room properties the engine reads: %s." % ", ".join(PackedStringArray(ROOM_PROPERTY_KINDS.keys()))
	props_box.add_child(note)

func _on_row_modified() -> void:
	data_modified.emit()

