# scripts/ui/inspectors/RegionInspector.gd

class_name RegionInspector
extends RefCounted

signal data_modified
signal request_delete_region

var container: VBoxContainer
var cur_data: Dictionary
var cur_id: String
var action_handler: ActionHandler
var database_mgr: DatabaseManager

var props_box: VBoxContainer
var flow_container: HFlowContainer
var creation_tag: PanelContainer = null
var popup_menu: PopupMenu

var spawner_inspector: SpawnerInspector

const SPAWNER_INSP_SCRIPT = preload("res://scripts/ui/inspectors/sub_inspectors/SpawnerInspector.gd")

const COMMON_PROPS = {
	"Dark": {"key": "dark", "val": true},
	"Outdoors": {"key": "outdoors", "val": true},
	"Safe Zone": {"key": "safe_zone", "val": true},
	"Noisy": {"key": "noisy", "val": true},
	"Smell": {"key": "smell", "val": "damp earth"},
	"Weather": {"key": "weather", "val": "clear"},
	"Music": {"key": "music", "val": "default_theme"}
}

func _init(c: VBoxContainer, handler: ActionHandler = null, db_mgr: DatabaseManager = null):
	container = c
	action_handler = handler
	database_mgr = db_mgr

func build(id: String, data: Dictionary):
	cur_id = id
	cur_data = data
	_build_general()
	_build_global_props()
	_build_districts()
	
	spawner_inspector = SPAWNER_INSP_SCRIPT.new()
	spawner_inspector.build(container, cur_data, database_mgr)
	spawner_inspector.data_modified.connect(func(): data_modified.emit())

func _build_general():
	container.add_child(InspectorStyle.create_section_header("REGION SETTINGS", Color.GOLD))
	var card = InspectorStyle.create_card()
	var vbox = card.get_child(0).get_child(0)
	container.add_child(card)
	
	vbox.add_child(InspectorStyle.lbl("Region ID:", InspectorStyle.COLOR_TEXT_DIM))
	var lbl_id = LineEdit.new(); lbl_id.text = cur_id; lbl_id.editable = false; InspectorStyle.apply_input_style(lbl_id); vbox.add_child(lbl_id)
	
	vbox.add_child(InspectorStyle.lbl("Region Name:", InspectorStyle.COLOR_TEXT_DIM))
	var name_ed = LineEdit.new(); name_ed.text = cur_data.get("name", "")
	name_ed.text_changed.connect(func(t): cur_data.name = t; data_modified.emit())
	InspectorStyle.apply_input_style(name_ed); vbox.add_child(name_ed)

	vbox.add_child(InspectorStyle.lbl("Global Description:", InspectorStyle.COLOR_TEXT_DIM))
	var desc_ed = TextEdit.new(); desc_ed.custom_minimum_size.y = 100
	desc_ed.text = cur_data.get("description", "")
	desc_ed.text_changed.connect(func(): cur_data.description = desc_ed.text; data_modified.emit())
	InspectorStyle.apply_input_style(desc_ed); vbox.add_child(desc_ed)

	var delete := Button.new(); delete.text = "Delete Region..."
	delete.tooltip_text = "Removes this region's file. Refused while anything else still links to it; the engine checks the set afterwards."
	InspectorStyle.apply_button_style(delete, DialogStyle.COLOR_DANGER)
	delete.pressed.connect(func(): request_delete_region.emit())
	vbox.add_child(delete)

func _build_global_props():
	var header_box = HBoxContainer.new()
	header_box.add_child(InspectorStyle.create_section_header("REGION PROPERTIES"))
	var spacer = Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header_box.add_child(spacer)
	
	var btn_add = MenuButton.new(); btn_add.text = "+ Tag"; btn_add.flat = true
	btn_add.add_theme_color_override("font_color", InspectorStyle.COLOR_ACCENT)
	btn_add.add_theme_color_override("font_hover_color", Color.WHITE)
	header_box.add_child(btn_add)
	container.add_child(header_box)
	
	var card = InspectorStyle.create_card()
	var vbox = card.get_child(0).get_child(0)
	container.add_child(card)
	
	if not cur_data.has("properties"): cur_data.properties = {}
	
	popup_menu = btn_add.get_popup()
	popup_menu.id_pressed.connect(_on_add_tag_selected)
	
	props_box = VBoxContainer.new()
	vbox.add_child(props_box)
	_build_weather_profile_editor(vbox)
	_refresh_props()


## Region weather profiles are ruleset vocabulary, not arbitrary scalar tags.
## The free-form tag remains readable for older worlds, but this picker makes a
## typo impossible and exposes the fact that a profile is optional.
func _build_weather_profile_editor(vbox: VBoxContainer):
	var ruleset = JSON.parse_string(FileAccess.get_file_as_string(DataRoot.ruleset_path()))
	var weather: Dictionary = ruleset.get("weather", {}) if ruleset is Dictionary and ruleset.get("weather") is Dictionary else {}
	var profiles: Dictionary = weather.get("profiles", {}) if weather.get("profiles") is Dictionary else {}
	var selected := str(cur_data.properties.get("weather_profile", ""))
	if profiles.is_empty() and selected == "": return
	var row := HBoxContainer.new(); row.add_child(InspectorStyle.lbl("Weather profile", InspectorStyle.COLOR_TEXT_DIM))
	var picker := OptionButton.new(); picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_button_style(picker)
	picker.add_item("No regional profile"); picker.set_item_metadata(0, "")
	var ids: Array = profiles.keys(); ids.sort()
	for profile_id in ids:
		picker.add_item(str(profile_id)); picker.set_item_metadata(picker.item_count - 1, str(profile_id))
		if str(profile_id) == selected: picker.select(picker.item_count - 1)
	if selected != "" and picker.selected == 0:
		picker.add_item("Missing: " + selected); picker.set_item_metadata(picker.item_count - 1, selected); picker.select(picker.item_count - 1)
	picker.item_selected.connect(func(index):
		var profile := str(picker.get_item_metadata(index))
		if profile == "": cur_data.properties.erase("weather_profile")
		else: cur_data.properties["weather_profile"] = profile
		data_modified.emit(); _refresh_props()
	)
	row.add_child(picker); vbox.add_child(row)

func _build_districts():
	var districts: Dictionary = cur_data.get("properties", {}).get("districts", {})
	if districts.is_empty(): return
	container.add_child(InspectorStyle.create_section_header("DISTRICTS", Color.CYAN))
	for district_id in districts:
		var district: Dictionary = districts[district_id]
		var card = InspectorStyle.create_card(); var box = card.get_child(0).get_child(0); container.add_child(card)
		box.add_child(InspectorStyle.lbl(str(district.get("name", district_id)), Color.WHITE))
		box.add_child(InspectorStyle.lbl("%s · %d rooms · seed %s" % [district.get("kind", "generic"), district.get("members", []).size(), district.get("seed", "?")], InspectorStyle.COLOR_TEXT_DIM))
		var reroll := Button.new(); reroll.text = "Reroll District (undoable)"
		reroll.tooltip_text = "Regenerates interior rooms from a new seed while preserving the district's external port roles."
		reroll.disabled = action_handler == null
		reroll.pressed.connect(func(): action_handler.reroll_district(str(district_id), randi()); data_modified.emit())
		box.add_child(reroll)

func _on_add_tag_selected(id: int):
	var item_text = popup_menu.get_item_text(id)
	if item_text == "Custom...":
		_show_creation_tag()
	else:
		var key = COMMON_PROPS[item_text].key
		var val = COMMON_PROPS[item_text].val
		if not cur_data.properties.has(key):
			cur_data.properties[key] = val
			data_modified.emit()
			_refresh_props()

func _show_creation_tag():
	if is_instance_valid(creation_tag): return
	
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
	
	if key.is_empty() or cur_data.properties.has(key):
		_cancel_new_prop()
		return

	var final_val
	match type_idx:
		0: final_val = val_str
		1: final_val = val_str.to_float() if val_str.is_valid_float() else 0.0
		2: final_val = val_str.to_lower() in ["true", "1", "yes", "on"]
	
	cur_data.properties[key] = final_val
	creation_tag.queue_free(); creation_tag = null
	data_modified.emit(); _refresh_props()

func _cancel_new_prop():
	if is_instance_valid(creation_tag):
		creation_tag.queue_free(); creation_tag = null

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
	
	popup_menu.clear() 
	var sorted_common_keys = COMMON_PROPS.keys(); sorted_common_keys.sort()
	for k in sorted_common_keys:
		if not cur_data.properties.has(COMMON_PROPS[k].key):
			popup_menu.add_item(k)
	popup_menu.add_separator(); popup_menu.add_item("Custom...")
	
	# Structured properties (districts, level_band, ...) get their own dedicated
	# section/editor elsewhere -- rendering one here as a flat tag would dump its
	# entire nested contents into a single unbounded LineEdit, which has no wrap
	# and no max width, blowing the panel out past the screen edge instead of just
	# looking odd. It would also write the stringified form back over the object.
	#
	# The rule is PropertyTagRow's, not this panel's: RoomPropertiesPanel is the
	# same shape and did not have the guard, so the two panels disagreed about
	# which values they could edit and only one of them was safe.
	var scalar_keys: Array = PropertyTagRow.editable_keys(cur_data.properties)
	# The controlled picker above owns this string, so do not render a competing
	# raw tag that could reintroduce a profile id the ruleset does not declare.
	scalar_keys.erase("weather_profile")

	if scalar_keys.is_empty():
		var l = Label.new(); l.text = "None."; l.modulate = Color(1,1,1,0.3); l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		flow_container.add_child(l)
		return

	for key in scalar_keys:
		flow_container.add_child(PropertyTagRow.build_row(
			key, cur_data.properties[key], cur_data.properties, _on_row_modified, _refresh_props
		))

	PropertyTagRow.add_nested_rows(props_box, cur_data.properties, "the region's own editor")

func _on_row_modified() -> void:
	data_modified.emit()
