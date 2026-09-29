# scripts/ui/inspectors/panels/RoomTriggersPanel.gd
#
# The triggers that fire in this room, listed on the room inspector so an author looking
# at a room can see what will happen when the player walks in. Read-only: a trigger is
# edited in the Content Library (Triggers), where its condition and effects have room to
# breathe. Reached through `preload`, not a `class_name` (see TriggerSchema.gd).
extends RefCounted

const SCHEMA = preload("res://scripts/data/TriggerSchema.gd")


func build(parent: VBoxContainer, region_id: String, room_id: String, database_mgr: DatabaseManager) -> void:
	parent.add_child(InspectorStyle.create_section_header("TRIGGERS IN THIS ROOM", InspectorStyle.COLOR_ACCENT))
	var card := InspectorStyle.create_card()
	var box: VBoxContainer = card.get_child(0).get_child(0)
	box.name = "RoomTriggers"
	box.add_theme_constant_override("separation", 4)
	parent.add_child(card)
	var here: Array = triggers_in(database_mgr, region_id, room_id)
	if here.is_empty():
		box.add_child(InspectorStyle.lbl("None. Add one in the Content Library under Triggers.", InspectorStyle.COLOR_TEXT_DIM))
		return
	for id in here:
		var trigger: Dictionary = database_mgr.triggers[id]
		var row := HBoxContainer.new()
		row.name = "Trigger_%s" % id
		row.add_child(InspectorStyle.lbl(str(id), Color(0.9, 0.9, 0.92)))
		var how := ""
		for choice in SCHEMA.ONCE_CHOICES:
			if str(choice["value"]) == SCHEMA.once_choice_of(trigger):
				how = str(choice["label"]).to_lower()
		var note := str(trigger.get("note", ""))
		row.add_child(InspectorStyle.lbl("  %s%s" % [how, ("  -  " + note) if note != "" else ""], InspectorStyle.COLOR_TEXT_DIM))
		box.add_child(row)


## The ids of the triggers whose `on` names this room, in id order.
static func triggers_in(database_mgr: DatabaseManager, region_id: String, room_id: String) -> Array:
	var found: Array = []
	if database_mgr == null:
		return found
	var ids: Array = database_mgr.triggers.keys()
	ids.sort()
	for id in ids:
		var trigger = database_mgr.triggers[id]
		if not (trigger is Dictionary):
			continue
		var on = trigger.get("on")
		if on is Dictionary and str(on.get("region", "")) == region_id and str(on.get("room", "")) == room_id:
			found.append(id)
	return found
