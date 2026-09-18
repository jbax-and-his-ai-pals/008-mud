# scripts/ui/modals/DistrictModal.gd
class_name DistrictModal
extends Control

const DistrictBlueprint = preload("res://scripts/generators/DistrictBlueprint.gd")
const PREVIEW_SCRIPT = preload("res://scripts/ui/panels/GeneratorPreview.gd")
signal request_place_district(definition: Dictionary)

var id_field: LineEdit
var name_field: LineEdit
var kind_option: OptionButton
var algorithm_option: OptionButton
var seed_field: LineEdit
var size_field: SpinBox
var summary: Label
var preview: Control
var place_button: Button
var window_panel: Panel

func setup():
	hide(); set_anchors_preset(Control.PRESET_FULL_RECT); mouse_filter = Control.MOUSE_FILTER_STOP
	var dimmer := ColorRect.new(); dimmer.color = Color(0.015, 0.025, 0.05, 0.78); dimmer.set_anchors_preset(Control.PRESET_FULL_RECT)
	dimmer.gui_input.connect(func(event): if event is InputEventMouseButton and event.pressed: hide())
	add_child(dimmer)
	# A plain Panel is deliberate. PanelContainer adopts the combined minimum
	# size of its preview subtree, which made the window taller than requested
	# on high-DPI displays. The VBox below is laid out inside a fixed panel.
	window_panel = Panel.new()
	# CanvasLayer controls do not always resolve center anchor offsets before the
	# first layout pass.  Positioning against the live viewport is dependable.
	window_panel.set_anchors_preset(Control.PRESET_TOP_LEFT)
	var panel_style := StyleBoxFlat.new(); panel_style.bg_color = Color("172033"); panel_style.border_color = Color("4f82bd")
	panel_style.set_border_width_all(2); panel_style.set_corner_radius_all(12); panel_style.shadow_color = Color(0, 0, 0, 0.65); panel_style.shadow_size = 24
	panel_style.content_margin_left = 12; panel_style.content_margin_right = 12; panel_style.content_margin_top = 10; panel_style.content_margin_bottom = 10
	window_panel.add_theme_stylebox_override("panel", panel_style); add_child(window_panel)
	var outer := VBoxContainer.new(); outer.set_anchors_preset(Control.PRESET_FULL_RECT); outer.offset_left = 12; outer.offset_right = -12; outer.offset_top = 10; outer.offset_bottom = -10; outer.add_theme_constant_override("separation", 8); window_panel.add_child(outer)
	var title_row := HBoxContainer.new(); outer.add_child(title_row)
	title_row.add_child(_label("CREATE DISTRICT", Color("8fceff"), 22))
	var title_spacer := Control.new(); title_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; title_row.add_child(title_spacer)
	title_row.add_child(_label("SEED-BASED · NON-DESTRUCTIVE", Color("a2e6b3"), 11))
	outer.add_child(_label("Roll a shape here, then place its ghost footprint on the map before creating any rooms.", Color("b7c5d8"), 14)); outer.add_child(HSeparator.new())
	# The dialog has a responsive fixed frame; this row consumes the useful
	# center area and leaves the action row pinned at the lower edge.
	var content := HBoxContainer.new(); content.size_flags_vertical = Control.SIZE_EXPAND_FILL; content.add_theme_constant_override("separation", 12); outer.add_child(content)
	var controls := VBoxContainer.new(); controls.custom_minimum_size.x = 275; controls.add_theme_constant_override("separation", 5); content.add_child(controls)
	id_field = _line("market_block", "Stable district id"); _row(controls, "ID", id_field)
	name_field = _line("Market Block", "Display name"); _row(controls, "Name", name_field)
	kind_option = OptionButton.new()
	for kind in ["building", "street", "market", "residential", "civic", "wilderness"]:
		kind_option.add_item(kind)
	_row(controls, "Kind", kind_option)
	algorithm_option = OptionButton.new()
	for algorithm in ["grid", "hub", "house", "maze", "ring", "crescent", "highway", "spiral"]:
		algorithm_option.add_item(algorithm)
	_row(controls, "Shape", algorithm_option)
	seed_field = _line(str(randi()), "Seed"); _row(controls, "Seed", seed_field)
	size_field = SpinBox.new(); size_field.min_value = 3; size_field.max_value = 20; size_field.value = 5; _row(controls, "Scale", size_field)
	var help := _label("Drag to place it, then connect it to the rest of the region afterward -- the same way any other room connects.", Color("94a7c0"), 12); help.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; controls.add_child(help)
	var reroll := Button.new(); reroll.text = "↻  Reroll Preview"; _button_style(reroll, Color("294c70")); reroll.pressed.connect(func(): seed_field.text = str(randi()); _refresh_preview()); controls.add_child(reroll)
	var preview_box := PanelContainer.new(); preview_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL; preview_box.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var preview_style := StyleBoxFlat.new(); preview_style.bg_color = Color("0b1220"); preview_style.border_color = Color("314b68"); preview_style.set_border_width_all(1); preview_style.set_corner_radius_all(8); preview_box.add_theme_stylebox_override("panel", preview_style); content.add_child(preview_box)
	var preview_column := VBoxContainer.new(); preview_box.add_child(preview_column)
	# Keep this deliberately compact: it is a shape selector, not the map
	# placement canvas. The full-size ghost comes immediately after this step.
	preview = Control.new(); preview.custom_minimum_size = Vector2(430, 200); preview.size_flags_vertical = Control.SIZE_EXPAND_FILL; preview.set_script(PREVIEW_SCRIPT); preview_column.add_child(preview)
	summary = _label("", Color("aab9ca"), 12); summary.hide(); preview_column.add_child(summary)
	outer.add_child(HSeparator.new())
	var buttons := HBoxContainer.new(); outer.add_child(buttons)
	var cancel := Button.new(); cancel.text = "Cancel"; _button_style(cancel, Color("293548")); cancel.pressed.connect(hide); buttons.add_child(cancel)
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; buttons.add_child(spacer)
	place_button = Button.new(); place_button.text = "Place on Map  →"; _button_style(place_button, Color("23744d")); place_button.pressed.connect(_submit); buttons.add_child(place_button)
	for control in [id_field, name_field, seed_field]: control.text_changed.connect(func(_text): _refresh_preview())
	for control in [kind_option, algorithm_option]: control.item_selected.connect(func(_index): _refresh_preview())
	size_field.value_changed.connect(func(_value): _refresh_preview())

func open_for_rooms(_rooms: Dictionary):
	show(); move_to_front(); _center_window(); _refresh_preview()

func _notification(what):
	if what == NOTIFICATION_RESIZED and visible:
		_center_window()

func _center_window():
	if not is_instance_valid(window_panel): return
	var viewport_size := get_viewport_rect().size
	window_panel.size = viewport_size * 0.60
	window_panel.position = (viewport_size - window_panel.size) * 0.5

func _definition() -> Dictionary:
	var shape := algorithm_option.get_item_text(algorithm_option.selected); var scale := int(size_field.value); var seed := seed_field.text.hash()
	return {"id": id_field.text.strip_edges(), "name": name_field.text.strip_edges(), "kind": kind_option.get_item_text(kind_option.selected), "seed": seed,
		"generator": {"algorithm": shape, "params": {"seed": seed, "rows": scale, "cols": scale, "room_density": 0.72, "conn_density": 0.35, "max_radius": scale, "length": scale * 2, "room_count": scale}},
		"ports": [{"id": "entry", "direction": "north", "role": "entry"}], "reroll_policy": {"preserve_ports": true, "preserve_named_landmarks": true}}

func _refresh_preview():
	var result: Dictionary = DistrictBlueprint.generate(_definition()); var valid: bool = result.get("ok", false); place_button.disabled = not valid
	if valid:
		var stats := "%d rooms · %d reusable port role(s) · seed %s" % [result["rooms"].size(), result["district"]["ports"].size(), seed_field.text]
		preview.update_preview(result["rooms"]); preview.set_overlay("LIVE FOOTPRINT", stats); summary.text = stats; summary.modulate = Color("a2e6b3")
	else:
		var message := " · ".join(result.get("errors", []))
		preview.update_preview({}); preview.set_overlay("LIVE FOOTPRINT", message); summary.text = message; summary.modulate = Color("ffacac")

func _submit():
	var definition := _definition()
	if definition["id"] == "": summary.text = "A stable district ID is required."; summary.modulate = Color("ffacac"); return
	request_place_district.emit(definition); hide()

func _row(parent: VBoxContainer, title: String, control: Control):
	var row := HBoxContainer.new(); parent.add_child(row); var label := _label(title, Color("b7c5d8"), 12); label.custom_minimum_size.x = 78; row.add_child(label); control.size_flags_horizontal = Control.SIZE_EXPAND_FILL; row.add_child(control)

func _line(value: String, placeholder: String) -> LineEdit:
	var field := LineEdit.new(); field.text = value; field.placeholder_text = placeholder; return field

func _button_style(button: Button, color: Color):
	var style := StyleBoxFlat.new(); style.bg_color = color; style.set_corner_radius_all(6); style.content_margin_left = 14; style.content_margin_right = 14; style.content_margin_top = 7; style.content_margin_bottom = 7; button.add_theme_stylebox_override("normal", style)
	var hover := style.duplicate(); hover.bg_color = color.lightened(0.12); button.add_theme_stylebox_override("hover", hover)

func _label(text: String, color: Color, font_size: int = 14) -> Label:
	var label := Label.new(); label.text = text; label.modulate = color; label.add_theme_font_size_override("font_size", font_size); return label
