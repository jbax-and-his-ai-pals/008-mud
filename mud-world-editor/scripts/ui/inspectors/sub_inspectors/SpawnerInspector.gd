# scripts/ui/inspectors/sub_inspectors/SpawnerInspector.gd

class_name SpawnerInspector
extends RefCounted

signal data_modified

var container: VBoxContainer
var cur_data: Dictionary
var spawner_box: VBoxContainer

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
	
	vbox.add_child(InspectorStyle.lbl("Monster Weights:", InspectorStyle.COLOR_TEXT_DIM))
	spawner_box = VBoxContainer.new(); vbox.add_child(spawner_box)
	var btn_add_m = Button.new(); btn_add_m.text="Add Monster"; InspectorStyle.apply_button_style(btn_add_m, InspectorStyle.COLOR_SUCCESS.darkened(0.2))
	btn_add_m.pressed.connect(func():
		if not sp.has("monster_types"): sp.monster_types = {}
		sp.monster_types["new_monster"] = 1.0
		_refresh_spawner_box(); data_modified.emit()
	)
	vbox.add_child(btn_add_m)
	_refresh_spawner_box()

func _refresh_spawner_box():
	for c in spawner_box.get_children(): c.queue_free()
	var sp = cur_data.get("spawner", {})
	var types = sp.get("monster_types", {})
	
	for m_id in types:
		var panel = PanelContainer.new()
		var s = StyleBoxFlat.new(); s.bg_color = Color(0.12, 0.12, 0.14); s.set_corner_radius_all(4)
		panel.add_theme_stylebox_override("panel", s)
		var hb = HBoxContainer.new()
		panel.add_child(hb)
		
		var ed = LineEdit.new(); ed.text = m_id; ed.size_flags_horizontal=Control.SIZE_EXPAND_FILL
		ed.flat=true; InspectorStyle.apply_input_style(ed); ed.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
		ed.text_submitted.connect(func(t): 
			if t != m_id: var v=types[m_id]; types.erase(m_id); types[t]=v; _refresh_spawner_box(); data_modified.emit()
		)
		hb.add_child(ed)
		
		var sb = SpinBox.new(); sb.step=0.1; sb.value=types[m_id]
		InspectorStyle.apply_input_style(sb)
		sb.value_changed.connect(func(v): types[m_id]=v; data_modified.emit())
		hb.add_child(sb)
		
		var d = Button.new(); d.text="x"; d.flat=true; d.pressed.connect(func(): types.erase(m_id); _refresh_spawner_box(); data_modified.emit())
		hb.add_child(d)
		spawner_box.add_child(panel)
