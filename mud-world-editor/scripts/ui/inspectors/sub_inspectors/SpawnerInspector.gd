# scripts/ui/inspectors/sub_inspectors/SpawnerInspector.gd

class_name SpawnerInspector
extends RefCounted

signal data_modified

var container: VBoxContainer
var cur_data: Dictionary

func build(c: VBoxContainer, data: Dictionary):
	container = c
	cur_data = data
	_build_spawner()

func _build_spawner():
	container.add_child(InspectorStyle.create_section_header("SPAWNER CONFIG", Color.SALMON))
	var card = InspectorStyle.create_card(); var vbox = card.get_child(0).get_child(0)
	container.add_child(card)

	if not cur_data.has("spawner"): cur_data.spawner = {}
	var sp = cur_data.spawner

	var hb_lvl = HBoxContainer.new()
	hb_lvl.add_child(InspectorStyle.lbl("Level Range:"))
	var sb_min = SpinBox.new(); sb_min.value = sp.get("level_range", [1,1])[0]; var sb_max = SpinBox.new(); sb_max.value = sp.get("level_range", [1,1])[1]
	InspectorStyle.apply_input_style(sb_min); InspectorStyle.apply_input_style(sb_max)
	var update_range = func(_v): sp.level_range = [sb_min.value, sb_max.value]; data_modified.emit()
	sb_min.value_changed.connect(update_range); sb_max.value_changed.connect(update_range)
	hb_lvl.add_child(sb_min); hb_lvl.add_child(InspectorStyle.lbl("-")); hb_lvl.add_child(sb_max)
	vbox.add_child(hb_lvl)

	vbox.add_child(HSeparator.new())
	_build_toggle(vbox, sp, "monsters_enabled", "Spawn Monsters")
	_build_weight_section(vbox, sp, "monster_types", "Monster Weights:", "Add Monster", "new_monster")

	vbox.add_child(HSeparator.new())
	_build_toggle(vbox, sp, "npcs_enabled", "Spawn Wandering NPCs")
	_build_weight_section(vbox, sp, "npc_types", "NPC Weights:", "Add NPC", "new_npc")

# A region that doesn't want ambient monsters or wandering NPCs at all
# (e.g. a quiet instanced puzzle room) can turn either off without having
# to empty out its weight table -- World.Spawner checks these flags before
# doing any spawn work for that category.
func _build_toggle(vbox: VBoxContainer, sp: Dictionary, key: String, label: String):
	var cb := CheckBox.new()
	cb.text = label
	cb.button_pressed = bool(sp.get(key, true))
	cb.toggled.connect(func(pressed): sp[key] = pressed; data_modified.emit())
	vbox.add_child(cb)

func _build_weight_section(vbox: VBoxContainer, sp: Dictionary, config_key: String, label: String, add_button_text: String, new_entry_key: String):
	vbox.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var box := VBoxContainer.new(); vbox.add_child(box)

	var refresh: Callable
	refresh = func():
		for c in box.get_children(): c.queue_free()
		var types: Dictionary = sp.get(config_key, {})
		for entry_id in types:
			box.add_child(_create_weight_row(types, entry_id, refresh))

	var btn_add := Button.new(); btn_add.text = add_button_text
	InspectorStyle.apply_button_style(btn_add, InspectorStyle.COLOR_SUCCESS.darkened(0.2))
	btn_add.pressed.connect(func():
		if not sp.has(config_key): sp[config_key] = {}
		sp[config_key][new_entry_key] = 1.0
		refresh.call(); data_modified.emit()
	)
	vbox.add_child(btn_add)
	refresh.call()

func _create_weight_row(types: Dictionary, entry_id: String, refresh: Callable) -> PanelContainer:
	var panel = PanelContainer.new()
	var s = StyleBoxFlat.new(); s.bg_color = Color(0.12, 0.12, 0.14); s.set_corner_radius_all(4)
	panel.add_theme_stylebox_override("panel", s)
	var hb = HBoxContainer.new()
	panel.add_child(hb)

	var ed = LineEdit.new(); ed.text = entry_id; ed.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	ed.flat=true; InspectorStyle.apply_input_style(ed); ed.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
	ed.text_submitted.connect(func(t):
		if t != entry_id: var v=types[entry_id]; types.erase(entry_id); types[t]=v; refresh.call(); data_modified.emit()
	)
	hb.add_child(ed)

	var sb = SpinBox.new(); sb.step=0.1; sb.value=types[entry_id]
	InspectorStyle.apply_input_style(sb)
	sb.value_changed.connect(func(v): types[entry_id]=v; data_modified.emit())
	hb.add_child(sb)

	var d = Button.new(); d.text="x"; d.flat=true; d.pressed.connect(func(): types.erase(entry_id); refresh.call(); data_modified.emit())
	hb.add_child(d)
	return panel
