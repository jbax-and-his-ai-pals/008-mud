# scripts/panels/CreatorModal.gd
class_name CreatorModal
extends Control

signal request_create_region(name, room_data)

var widgets: Dictionary = {}
var _temp_generated_rooms: Dictionary = {}

# UI Refs
var window_panel: Panel
var slider_density: HSlider
var slider_conns: HSlider
var lbl_density_val: Label
var lbl_conns_val: Label
var lbl_p1: Label
var lbl_p2: Label
var lbl_s1: Label
var lbl_s2: Label
var lbl_counts: Label
var container_dims: Control
var container_density: Control
var slider_p1: HSlider
var slider_p2: HSlider
var lbl_p1_val: Label
var lbl_p2_val: Label

const PREVIEW_SCRIPT = preload("res://scripts/ui/panels/GeneratorPreview.gd")
var generator_preview: Control

func setup():
	hide()
	anchor_left = 0.0; anchor_top = 0.0; anchor_right = 1.0; anchor_bottom = 1.0
	offset_left = 0; offset_top = 0; offset_right = 0; offset_bottom = 0
	mouse_filter = Control.MOUSE_FILTER_STOP; z_index = 100 
	
	var dimmer = ColorRect.new(); dimmer.color = Color(0, 0, 0, 0.6); dimmer.set_anchors_preset(Control.PRESET_FULL_RECT)
	dimmer.mouse_filter = Control.MOUSE_FILTER_STOP
	dimmer.gui_input.connect(func(ev): if ev is InputEventMouseButton and ev.button_index == MOUSE_BUTTON_LEFT and ev.pressed: hide())
	add_child(dimmer)
	
	window_panel = Panel.new(); window_panel.anchor_left = 0.2; window_panel.anchor_top = 0.1; window_panel.anchor_right = 0.8; window_panel.anchor_bottom = 0.9
	window_panel.mouse_filter = Control.MOUSE_FILTER_STOP
	var style = StyleBoxFlat.new(); style.bg_color = Color(0.15, 0.15, 0.18); style.set_border_width_all(2); style.border_color = Color(0.4, 0.6, 1.0)
	style.shadow_size = 10; style.shadow_color = Color(0, 0, 0, 0.5); window_panel.add_theme_stylebox_override("panel", style)
	add_child(window_panel)
	
	var main_hbox = HBoxContainer.new(); main_hbox.set_anchors_preset(Control.PRESET_FULL_RECT)
	main_hbox.offset_left = 20; main_hbox.offset_top = 20; main_hbox.offset_right = -20; main_hbox.offset_bottom = -20
	window_panel.add_child(main_hbox)
	
	var vbox = VBoxContainer.new(); vbox.size_flags_horizontal = 3; vbox.size_flags_stretch_ratio = 0.6; main_hbox.add_child(vbox)
	vbox.add_child(_lbl("Region Configuration"))
	widgets.name = LineEdit.new(); widgets.name.text = "new_region"; widgets.name.placeholder_text = "Region ID (Filename)"; _apply_style(widgets.name)
	vbox.add_child(widgets.name); vbox.add_child(HSeparator.new())
	
	vbox.add_child(_lbl("Algorithm"))
	widgets.algo = OptionButton.new()
	var algos = ["Grid", "Maze", "Hub", "Crescent", "Ring", "Cavern", "Sector", "Highway", "Spiral", "Fractal", "River", "Target", "House", "Town", "City", "Castle"]
	for i in range(algos.size()): widgets.algo.add_item(algos[i], i + 1)
	widgets.algo.add_item("Empty", 0)
	_apply_style(widgets.algo); vbox.add_child(widgets.algo); vbox.add_child(HSeparator.new())
	
	container_dims = VBoxContainer.new(); vbox.add_child(container_dims); container_dims.add_child(_lbl("Parameters"))
	var dim_hbox = HBoxContainer.new()
	var vb_p1 = VBoxContainer.new(); vb_p1.size_flags_horizontal = 3
	lbl_p1 = _lbl("Rows:"); vb_p1.add_child(lbl_p1)
	widgets.p1 = SpinBox.new(); widgets.p1.value = 10; widgets.p1.max_value = 100; _apply_style(widgets.p1); vb_p1.add_child(widgets.p1)
	slider_p1 = HSlider.new(); slider_p1.size_flags_horizontal = 3; slider_p1.visible = false; lbl_p1_val = _lbl("10"); lbl_p1_val.visible = false
	var hb_s1 = HBoxContainer.new(); hb_s1.add_child(slider_p1); hb_s1.add_child(lbl_p1_val); vb_p1.add_child(hb_s1)
	dim_hbox.add_child(vb_p1); dim_hbox.add_child(VSeparator.new())
	
	var vb_p2 = VBoxContainer.new(); vb_p2.size_flags_horizontal = 3
	lbl_p2 = _lbl("Cols:"); vb_p2.add_child(lbl_p2)
	widgets.p2 = SpinBox.new(); widgets.p2.value = 10; widgets.p2.max_value = 100; _apply_style(widgets.p2); vb_p2.add_child(widgets.p2)
	slider_p2 = HSlider.new(); slider_p2.size_flags_horizontal = 3; slider_p2.visible = false; lbl_p2_val = _lbl("0"); lbl_p2_val.visible = false
	var hb_s2 = HBoxContainer.new(); hb_s2.add_child(slider_p2); hb_s2.add_child(lbl_p2_val); vb_p2.add_child(hb_s2)
	dim_hbox.add_child(vb_p2); container_dims.add_child(dim_hbox); container_dims.add_child(HSeparator.new())
	
	container_density = VBoxContainer.new(); vbox.add_child(container_density)
	lbl_s1 = _lbl("Room Density"); container_density.add_child(lbl_s1)
	var hb_dens = HBoxContainer.new()
	slider_density = HSlider.new(); slider_density.size_flags_horizontal = 3; slider_density.min_value = 0.0; slider_density.max_value = 1.0; slider_density.step = 0.05; slider_density.value = 0.65
	lbl_density_val = _lbl("0.65"); lbl_density_val.custom_minimum_size.x = 40
	slider_density.value_changed.connect(func(v): lbl_density_val.text = str(v))
	hb_dens.add_child(slider_density); hb_dens.add_child(lbl_density_val); container_density.add_child(hb_dens)
	
	lbl_s2 = _lbl("Connection Density"); container_density.add_child(lbl_s2)
	var hb_conn = HBoxContainer.new()
	slider_conns = HSlider.new(); slider_conns.size_flags_horizontal = 3; slider_conns.min_value = 0.0; slider_conns.max_value = 1.0; slider_conns.step = 0.05; slider_conns.value = 0.5
	lbl_conns_val = _lbl("0.5"); lbl_conns_val.custom_minimum_size.x = 40
	slider_conns.value_changed.connect(func(v): lbl_conns_val.text = str(v))
	hb_conn.add_child(slider_conns); hb_conn.add_child(lbl_conns_val); container_density.add_child(hb_conn); vbox.add_child(HSeparator.new())
	
	widgets.algo.item_selected.connect(func(i): _update_ui_for_algo(); _update_gen_preview())
	widgets.p1.value_changed.connect(func(v): _update_gen_preview())
	widgets.p2.value_changed.connect(func(v): _update_gen_preview())
	slider_p1.value_changed.connect(func(v): lbl_p1_val.text = str(v); _update_gen_preview())
	slider_p2.value_changed.connect(func(v): lbl_p2_val.text = str(v); _update_gen_preview())
	slider_density.value_changed.connect(func(v): _update_gen_preview())
	slider_conns.value_changed.connect(func(v): _update_gen_preview())
	
	var btn_gen = Button.new(); btn_gen.text = "Roll / Generate Preview"; _apply_style(btn_gen, Color(0.2, 0.2, 0.3))
	btn_gen.pressed.connect(_update_gen_preview); vbox.add_child(btn_gen)
	
	var btn_create = Button.new(); btn_create.text = "Accept & Create"; btn_create.size_flags_vertical = 10
	_apply_style(btn_create, Color(0.2, 0.3, 0.2)); btn_create.pressed.connect(func(): 
		if _temp_generated_rooms.is_empty() and widgets.algo.get_item_id(widgets.algo.selected) != RegionGenerator.Algo.EMPTY: _update_gen_preview() 
		request_create_region.emit(widgets.name.text, _temp_generated_rooms); hide())
	vbox.add_child(btn_create)
	
	var btn_c = Button.new(); btn_c.text = "Cancel"; btn_c.pressed.connect(func(): hide()); _apply_style(btn_c); vbox.add_child(btn_c)

	var prev_panel = PanelContainer.new(); prev_panel.size_flags_horizontal = 3; prev_panel.size_flags_stretch_ratio = 1.5
	var prev_style = StyleBoxFlat.new(); prev_style.bg_color = Color(0.05, 0.05, 0.05); prev_style.set_border_width_all(1); prev_style.border_color = Color(0.3, 0.3, 0.3)
	prev_panel.add_theme_stylebox_override("panel", prev_style); main_hbox.add_child(prev_panel)
	
	var preview_vbox = VBoxContainer.new(); preview_vbox.size_flags_vertical = Control.SIZE_EXPAND_FILL; prev_panel.add_child(preview_vbox)
	generator_preview = Control.new(); generator_preview.size_flags_vertical = Control.SIZE_EXPAND_FILL; generator_preview.set_script(PREVIEW_SCRIPT); preview_vbox.add_child(generator_preview)
	lbl_counts = _lbl("0 Rooms, 0 Connections", Color.GRAY); lbl_counts.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT; preview_vbox.add_child(lbl_counts)
	
	_update_ui_for_algo(); visibility_changed.connect(func(): if visible: _update_gen_preview())

func _get_gen_params() -> Dictionary:
	var p1_val = widgets.p1.value if widgets.p1.visible else slider_p1.value
	var p2_val = widgets.p2.value if widgets.p2.visible else slider_p2.value
	return { "rows": int(p1_val), "cols": int(p2_val), "room_density": slider_density.value, "conn_density": slider_conns.value }

func _update_gen_preview():
	var algo = widgets.algo.get_item_id(widgets.algo.selected)
	var params = _get_gen_params()
	_temp_generated_rooms = RegionGenerator.generate(algo, params)
	generator_preview.update_preview(_temp_generated_rooms)
	var r_count = _temp_generated_rooms.size()
	var c_count = 0
	for rid in _temp_generated_rooms: c_count += _temp_generated_rooms[rid].get("exits", {}).size()
	lbl_counts.text = "%d Rooms, %d Exits" % [r_count, c_count]

func _update_ui_for_algo():
	var id = widgets.algo.get_item_id(widgets.algo.selected)
	var cfg = _get_algo_config(id)
	container_dims.visible = (id != RegionGenerator.Algo.EMPTY); container_density.visible = (id != RegionGenerator.Algo.EMPTY)
	if id == RegionGenerator.Algo.EMPTY: return

	var setup_ctl = func(ctl, slide, lbl, c):
		if c.type == "none": ctl.visible = false; slide.visible = false; lbl.visible = false
		else:
			if c.type == "spin": ctl.visible = true; slide.visible = false; lbl.visible = false; ctl.min_value = c.get("min", 1); ctl.max_value = c.get("max", 100); ctl.value = c.val
			else: ctl.visible = false; slide.visible = true; lbl.visible = true; slide.min_value = c.get("min", 0); slide.max_value = c.get("max", 360); slide.value = c.val; lbl.text = str(c.val)

	lbl_p1.visible = (cfg.p1.type != "none"); if lbl_p1.visible: lbl_p1.text = cfg.p1.label
	lbl_p2.visible = (cfg.p2.type != "none"); if lbl_p2.visible: lbl_p2.text = cfg.p2.label
	setup_ctl.call(widgets.p1, slider_p1, lbl_p1_val, cfg.p1)
	setup_ctl.call(widgets.p2, slider_p2, lbl_p2_val, cfg.p2)

	if cfg.s1 == null: lbl_s1.visible = false; slider_density.visible = false; lbl_density_val.visible = false
	else: lbl_s1.visible = true; slider_density.visible = true; lbl_density_val.visible = true; lbl_s1.text = cfg.s1.label; slider_density.value = cfg.s1.val; lbl_density_val.text = str(cfg.s1.val)

	if cfg.s2 == null: lbl_s2.visible = false; slider_conns.visible = false; lbl_conns_val.visible = false
	else: lbl_s2.visible = true; slider_conns.visible = true; lbl_conns_val.visible = true; lbl_s2.text = cfg.s2.label; slider_conns.value = cfg.s2.val; lbl_conns_val.text = str(cfg.s2.val)

func _get_algo_config(id: int) -> Dictionary:
	var p_spin = func(l, v, mn=1, mx=100): return {"label": l, "type": "spin", "val": v, "min": mn, "max": mx}
	var p_slide = func(l, v, mn=0, mx=360): return {"label": l, "type": "slider", "val": v, "min": mn, "max": mx}
	var p_none = func(): return {"type": "none"}
	var s_val = func(l, v): return {"label": l, "val": v}
	match id:
		RegionGenerator.Algo.GRID: return { "p1": p_spin.call("Rows:", 10), "p2": p_spin.call("Cols:", 10), "s1": s_val.call("Room Density:", 0.65), "s2": s_val.call("Connection Density:", 0.5) }
		RegionGenerator.Algo.MAZE: return { "p1": p_spin.call("Width:", 20), "p2": p_spin.call("Height:", 20), "s1": null, "s2": s_val.call("Loop Chance:", 0.1) }
		RegionGenerator.Algo.HUB: return { "p1": p_spin.call("Max Radius:", 15), "p2": p_none.call(), "s1": s_val.call("Branching %:", 0.5), "s2": s_val.call("Webbing %:", 0.5) }
		RegionGenerator.Algo.CRESCENT: return { "p1": p_slide.call("Diameter:", 20, 5, 50), "p2": p_slide.call("Rotation:", 0, 0, 360), "s1": s_val.call("Thickness:", 0.5), "s2": s_val.call("Connect %:", 0.5) }
		RegionGenerator.Algo.RING: return { "p1": p_spin.call("Diameter:", 15), "p2": p_none.call(), "s1": s_val.call("Thickness:", 0.5), "s2": s_val.call("Bridge Density:", 0.5) }
		RegionGenerator.Algo.TARGET: return { "p1": p_spin.call("Rings Count:", 3, 1, 10), "p2": p_spin.call("Spacing:", 2, 1, 5), "s1": null, "s2": s_val.call("Bridge Density:", 0.5) }
		RegionGenerator.Algo.CAVERN: return { "p1": p_spin.call("Width:", 25), "p2": p_spin.call("Height:", 20), "s1": s_val.call("Initial Fill:", 0.45), "s2": s_val.call("Connect %:", 0.8) }
		RegionGenerator.Algo.SECTOR: return { "p1": p_spin.call("Width:", 30), "p2": p_spin.call("Height:", 20), "s1": s_val.call("Min Room Size:", 0.5), "s2": null }
		RegionGenerator.Algo.HIGHWAY: return { "p1": p_spin.call("Length:", 30), "p2": p_slide.call("Angle:", 0), "s1": s_val.call("Town Freq:", 0.3), "s2": s_val.call("Winding:", 0.5) }
		RegionGenerator.Algo.SPIRAL: return { "p1": p_spin.call("Length:", 50, 10, 200), "p2": p_spin.call("Spacing:", 1, 1, 5), "s1": null, "s2": s_val.call("Shortcuts %:", 0.0) }
		RegionGenerator.Algo.FRACTAL: return { "p1": p_spin.call("Room Count:", 40, 10, 200), "p2": p_spin.call("Branches:", 2, 1, 4), "s1": null, "s2": s_val.call("Cross-Connect %:", 0.1) }
		RegionGenerator.Algo.RIVER: return { "p1": p_spin.call("Length:", 30, 10, 100), "p2": p_spin.call("Width:", 5, 2, 20), "s1": s_val.call("Wave Height:", 0.3), "s2": s_val.call("Wave Freq:", 0.2) }
		RegionGenerator.Algo.HOUSE: return { "p1": p_spin.call("Room Count:", 10, 3, 30), "p2": p_spin.call("Complexity:", 2, 1, 5), "s1": null, "s2": s_val.call("Loops:", 0.2) }
		RegionGenerator.Algo.TOWN: return { "p1": p_spin.call("Road Len:", 20, 10, 50), "p2": p_spin.call("Branches:", 5, 1, 10), "s1": s_val.call("Building Density:", 0.7), "s2": s_val.call("Alleys:", 0.3) }
		RegionGenerator.Algo.CITY: return { "p1": p_spin.call("Area Scale:", 25, 10, 100), "p2": p_spin.call("Districts:", 5, 2, 15), "s1": s_val.call("Density:", 0.8), "s2": s_val.call("Winding:", 0.3) }
		RegionGenerator.Algo.CASTLE: return { "p1": p_spin.call("Wall Size:", 20, 10, 50), "p2": p_spin.call("Keep Size:", 6, 2, 12), "s1": s_val.call("Tower Freq:", 0.3), "s2": s_val.call("Yard Fill:", 0.1) }
	return {"p1": p_none.call(), "p2": p_none.call(), "s1": null, "s2": null}

func _apply_style(node: Control, bg_color = Color(0.15, 0.15, 0.18)):
	var style = StyleBoxFlat.new(); style.bg_color = bg_color; style.set_border_width_all(1); style.border_color = Color(0.4, 0.4, 0.45); style.set_corner_radius_all(4); style.content_margin_left = 8; style.content_margin_right = 8; style.content_margin_top = 4; style.content_margin_bottom = 4
	if node is Button: node.add_theme_stylebox_override("normal", style); node.add_theme_stylebox_override("hover", style.duplicate()); node.add_theme_stylebox_override("pressed", style.duplicate()); node.get_theme_stylebox("hover").bg_color = bg_color.lightened(0.1); node.get_theme_stylebox("pressed").bg_color = bg_color.darkened(0.1)
	elif node is LineEdit or node is SpinBox: style.bg_color = Color(0.08, 0.08, 0.1); node.add_theme_stylebox_override("normal", style)

func _lbl(t, c=Color.WHITE): var l = Label.new(); l.text = t; l.modulate = c; return l
