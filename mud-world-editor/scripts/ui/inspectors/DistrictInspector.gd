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
	header.add_child(InspectorStyle.lbl(str(district.get("name", district_id)), Color.WHITE))

	var members: Array = district.get("members", district.get("rooms", []))
	var rooms: Dictionary = region_data.get("rooms", {})
	vbox.add_child(InspectorStyle.lbl("%s · %d rooms · seed %s" % [district.get("kind", "generic"), members.size(), district.get("seed", "?")], InspectorStyle.COLOR_TEXT_DIM))

	var reroll := Button.new(); reroll.text = "Reroll District (undoable)"
	reroll.tooltip_text = "Regenerates interior rooms from a new seed while preserving the district's external port roles."
	reroll.disabled = action_handler == null
	reroll.pressed.connect(func(): action_handler.reroll_district(district_id, randi()); data_modified.emit())
	vbox.add_child(reroll)

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
