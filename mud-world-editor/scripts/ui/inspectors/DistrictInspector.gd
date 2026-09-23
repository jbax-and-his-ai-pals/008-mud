# scripts/ui/inspectors/DistrictInspector.gd
# Shown when a click in the local room graph lands inside a district's
# territory but not on any room node -- the district itself is the thing
# being inspected, the same way clicking a room shows RoomInspector.
class_name DistrictInspector
extends RefCounted

signal data_modified
signal request_jump_to_room(room_id)

var container: VBoxContainer
var region_data: Dictionary
var district_id: String
var action_handler: ActionHandler

# Same vocabulary RegionInspector's REGION PROPERTIES offers, so a district
# can override its region's atmosphere (dark, outdoors, etc.) the same way
# a room overrides its district's -- World.get_env_property resolves all
# three tiers with the same flat-key convention.
const COMMON_PROPS = {
	"Dark": {"key": "dark", "val": true},
	"Outdoors": {"key": "outdoors", "val": true},
	"Safe Zone": {"key": "safe_zone", "val": true},
	"Noisy": {"key": "noisy", "val": true},
	"Smell": {"key": "smell", "val": "damp earth"},
	"Weather": {"key": "weather", "val": "clear"},
	"Music": {"key": "music", "val": "default_theme"}
}
# The district dict's own structural fields -- never offered or edited as a
# free-form property tag, since that would silently corrupt the district.
const RESERVED_KEYS := ["id", "name", "kind", "seed", "generator", "ports", "members", "rooms", "reroll_policy", "color", "shape"]

var district_ref: Dictionary
var props_flow: HFlowContainer
var props_popup: PopupMenu
var props_creation_tag: PanelContainer = null

func _init(c: VBoxContainer, handler: ActionHandler = null):
	container = c
	action_handler = handler

func build(id: String, r_data: Dictionary):
	district_id = id
	region_data = r_data
	var district: Dictionary = _district()
	if district.is_empty():
		container.add_child(InspectorStyle.lbl("This district no longer exists.", InspectorStyle.COLOR_TEXT_DIM))
		return
	district_ref = district

	container.add_child(InspectorStyle.create_section_header("DISTRICT", Color.CYAN))
	var card = InspectorStyle.create_card(); var vbox = card.get_child(0).get_child(0)
	container.add_child(card)

	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 8)
	vbox.add_child(header)
	var swatch := ColorRect.new()
	swatch.custom_minimum_size = Vector2(16, 16)
	swatch.color = Color.from_string(str(district.get("color", "#5d83a6")), Color("5d83a6"))
	header.add_child(swatch)
	var name_edit := LineEdit.new()
	name_edit.text = str(district.get("name", district_id))
	name_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name_edit.tooltip_text = "District name (shown on the map and in the room header in-game)"
	InspectorStyle.apply_input_style(name_edit)
	name_edit.text_changed.connect(func(t): district_ref["name"] = t; data_modified.emit())
	header.add_child(name_edit)

	var members: Array = district.get("members", district.get("rooms", []))
	var rooms: Dictionary = region_data.get("rooms", {})
	vbox.add_child(InspectorStyle.lbl("%s · %d rooms · seed %s" % [district.get("kind", "generic"), members.size(), district.get("seed", "?")], InspectorStyle.COLOR_TEXT_DIM))

	var reroll := Button.new(); reroll.text = "Reroll District (undoable)"
	reroll.tooltip_text = "Regenerates interior rooms from a new seed while preserving the district's external port roles."
	reroll.disabled = action_handler == null
	reroll.pressed.connect(func(): action_handler.reroll_district(district_id, randi()); data_modified.emit())
	vbox.add_child(reroll)

	var arrange := Button.new(); arrange.text = "Arrange Rooms in District (undoable)"
	arrange.tooltip_text = "Re-lays-out this district's own rooms without moving anything outside it."
	arrange.disabled = action_handler == null
	arrange.pressed.connect(func(): action_handler.arrange_district_rooms(district_id); data_modified.emit())
	vbox.add_child(arrange)

	var delete := Button.new(); delete.text = "Delete District (undoable)"
	delete.tooltip_text = "Removes the district grouping. Its rooms stay in the region, no longer in any district."
	delete.disabled = action_handler == null
	InspectorStyle.apply_button_style(delete, DialogStyle.COLOR_DANGER)
	delete.pressed.connect(func(): action_handler.delete_district(district_id); data_modified.emit())
	vbox.add_child(delete)

	var ports: Array = district.get("ports", [])
	if not ports.is_empty():
		vbox.add_child(InspectorStyle.lbl("Ports (connect to the rest of the region):", InspectorStyle.COLOR_TEXT_DIM))
		for port in ports:
			if not port is Dictionary: continue
			var port_room_id := str(port.get("room_id", ""))
			var port_room_name := str(rooms.get(port_room_id, {}).get("name", port_room_id)) if port_room_id != "" else str(port.get("id", "?"))
			var port_role := str(port.get("role", "?"))
			var port_direction := str(port.get("direction", ""))
			var port_desc := ("%s, %s" % [port_direction, port_role]) if port_direction != "" else port_role
			vbox.add_child(InspectorStyle.lbl("  %s (%s)" % [port_room_name, port_desc], Color(0.75, 0.78, 0.84)))

	_build_district_props()

	container.add_child(InspectorStyle.create_section_header("ROOMS (%d)" % members.size()))
	var sorted_members := members.duplicate(); sorted_members.sort()
	for room_id_variant in sorted_members:
		var room_id := str(room_id_variant)
		var room_name := str(rooms.get(room_id, {}).get("name", room_id))
		var btn := Button.new(); btn.text = room_name; btn.flat = true
		btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
		btn.add_theme_color_override("font_color", Color(0.75, 0.85, 1.0))
		btn.pressed.connect(func(): request_jump_to_room.emit(room_id))
		container.add_child(btn)

func _district() -> Dictionary:
	return region_data.get("properties", {}).get("districts", {}).get(district_id, {})

# A district only needs to author one of these when it departs from its
# region's norm (e.g. a "Riverside" district that's outdoors while the rest
# of the region defaults to indoors) -- World.get_env_property picks this
# up as the middle tier between a room's own properties and the region's.
func _build_district_props():
	var header_box := HBoxContainer.new()
	header_box.add_child(InspectorStyle.create_section_header("PROPERTIES (overrides region default)"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header_box.add_child(spacer)

	var btn_add := MenuButton.new(); btn_add.text = "+ Tag"; btn_add.flat = true
	btn_add.add_theme_color_override("font_color", InspectorStyle.COLOR_ACCENT)
	btn_add.add_theme_color_override("font_hover_color", Color.WHITE)
	header_box.add_child(btn_add)
	container.add_child(header_box)

	var card := InspectorStyle.create_card()
	var vbox = card.get_child(0).get_child(0)
	container.add_child(card)

	props_popup = btn_add.get_popup()
	props_popup.id_pressed.connect(_on_add_district_tag_selected)

	var props_box := VBoxContainer.new()
	vbox.add_child(props_box)
	props_flow = HFlowContainer.new()
	props_flow.add_theme_constant_override("h_separation", 8)
	props_flow.add_theme_constant_override("v_separation", 8)
	props_box.add_child(props_flow)
	_refresh_district_props()

func _district_prop_keys() -> Array:
	var keys: Array = []
	for key in district_ref.keys():
		if not (key in RESERVED_KEYS): keys.append(key)
	return keys

func _on_add_district_tag_selected(id: int):
	var item_text := props_popup.get_item_text(id)
	if item_text == "Custom...":
		_show_district_creation_tag()
		return
	var key: String = COMMON_PROPS[item_text].key
	var val = COMMON_PROPS[item_text].val
	if not district_ref.has(key):
		district_ref[key] = val
		data_modified.emit()
		_refresh_district_props()

func _show_district_creation_tag():
	if is_instance_valid(props_creation_tag): return

	props_creation_tag = PanelContainer.new()
	var style := StyleBoxFlat.new(); style.bg_color = Color(0.3, 0.3, 0.35); style.set_corner_radius_all(12)
	style.content_margin_left = 6; style.content_margin_right = 6; style.content_margin_top = 2; style.content_margin_bottom = 2
	props_creation_tag.add_theme_stylebox_override("panel", style)

	var hb := HBoxContainer.new(); props_creation_tag.add_child(hb)

	var key_edit := LineEdit.new(); key_edit.placeholder_text = "key"; key_edit.name = "KeyEdit"
	InspectorStyle.apply_input_style(key_edit); hb.add_child(key_edit)

	var type_select := OptionButton.new(); type_select.name = "TypeSelect"
	type_select.add_item("String"); type_select.add_item("Number"); type_select.add_item("Bool")
	InspectorStyle.apply_button_style(type_select); hb.add_child(type_select)

	var val_edit := LineEdit.new(); val_edit.placeholder_text = "value"; val_edit.name = "ValueEdit"
	InspectorStyle.apply_input_style(val_edit); hb.add_child(val_edit)

	var confirm_btn := Button.new(); confirm_btn.text = "✔"
	InspectorStyle.apply_button_style(confirm_btn, InspectorStyle.COLOR_SUCCESS); hb.add_child(confirm_btn)

	var cancel_btn := Button.new(); cancel_btn.text = "✖"
	InspectorStyle.apply_button_style(cancel_btn, InspectorStyle.COLOR_DANGER); hb.add_child(cancel_btn)

	props_flow.add_child(props_creation_tag)
	key_edit.grab_focus()

	confirm_btn.pressed.connect(_finalize_new_district_prop)
	cancel_btn.pressed.connect(_cancel_new_district_prop)
	key_edit.text_submitted.connect(func(_t): _finalize_new_district_prop())
	val_edit.text_submitted.connect(func(_t): _finalize_new_district_prop())

func _finalize_new_district_prop():
	if not is_instance_valid(props_creation_tag): return

	var key: String = props_creation_tag.get_node("KeyEdit").text.strip_edges()
	var type_idx: int = props_creation_tag.get_node("TypeSelect").selected
	var val_str: String = props_creation_tag.get_node("ValueEdit").text.strip_edges()

	if key.is_empty() or key in RESERVED_KEYS or district_ref.has(key):
		_cancel_new_district_prop()
		return

	var final_val
	match type_idx:
		0: final_val = val_str
		1: final_val = val_str.to_float() if val_str.is_valid_float() else 0.0
		2: final_val = val_str.to_lower() in ["true", "1", "yes", "on"]

	district_ref[key] = final_val
	props_creation_tag.queue_free(); props_creation_tag = null
	data_modified.emit(); _refresh_district_props()

func _cancel_new_district_prop():
	if is_instance_valid(props_creation_tag):
		props_creation_tag.queue_free(); props_creation_tag = null

func _refresh_district_props():
	for c in props_flow.get_children():
		if c != props_creation_tag: c.queue_free()

	props_popup.clear()
	var sorted_common_keys := COMMON_PROPS.keys(); sorted_common_keys.sort()
	for k in sorted_common_keys:
		if not district_ref.has(COMMON_PROPS[k].key):
			props_popup.add_item(k)
	props_popup.add_separator(); props_popup.add_item("Custom...")

	var keys := _district_prop_keys()
	if keys.is_empty():
		var l := Label.new(); l.text = "None."; l.modulate = Color(1, 1, 1, 0.3); l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		props_flow.add_child(l)
		return

	for key in keys:
		props_flow.add_child(_create_district_prop_tag(key, district_ref[key]))

func _create_district_prop_tag(key, val) -> PanelContainer:
	var panel := PanelContainer.new()
	var style := StyleBoxFlat.new(); style.bg_color = Color(0.25, 0.25, 0.28); style.set_corner_radius_all(12)
	style.content_margin_left = 10; style.content_margin_right = 6; style.content_margin_top = 2; style.content_margin_bottom = 2
	panel.add_theme_stylebox_override("panel", style)

	var hb := HBoxContainer.new(); panel.add_child(hb)

	var lbl := Label.new(); lbl.text = str(key) + ": "; lbl.modulate = Color(0.7, 0.9, 1.0)
	lbl.add_theme_font_size_override("font_size", 12); hb.add_child(lbl)

	if typeof(val) == TYPE_BOOL:
		var btn := Button.new(); btn.text = str(val).to_upper(); btn.flat = true
		btn.add_theme_font_size_override("font_size", 12)
		btn.add_theme_color_override("font_color", InspectorStyle.COLOR_SUCCESS if val else InspectorStyle.COLOR_DANGER)
		btn.pressed.connect(func(): district_ref[key] = !val; data_modified.emit(); _refresh_district_props())
		hb.add_child(btn)
	else:
		var ed := LineEdit.new(); ed.text = str(val); ed.flat = true; ed.expand_to_text_length = true; ed.custom_minimum_size.x = 30
		ed.add_theme_font_size_override("font_size", 12); ed.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
		ed.text_submitted.connect(func(t):
			if typeof(val) == TYPE_FLOAT or typeof(val) == TYPE_INT:
				district_ref[key] = t.to_float() if t.is_valid_float() else val
			else:
				district_ref[key] = t
			data_modified.emit(); _refresh_district_props()
		)
		hb.add_child(ed)

	var del := Button.new(); del.text = "×"; del.flat = true
	del.add_theme_font_size_override("font_size", 14); del.add_theme_color_override("font_color", Color(0.5, 0.5, 0.5))
	del.add_theme_color_override("font_hover_color", Color(1, 0.5, 0.5))
	del.pressed.connect(func(): district_ref.erase(key); data_modified.emit(); _refresh_district_props()); hb.add_child(del)
	return panel
