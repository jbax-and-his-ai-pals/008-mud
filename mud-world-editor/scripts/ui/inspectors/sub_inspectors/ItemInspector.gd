# scripts/ui/inspectors/sub_inspectors/ItemInspector.gd

class_name ItemInspector
extends RefCounted

signal database_modified

# The engine's item classes (ItemFactory.ITEM_CLASS_MAP). The list used to offer
# "Tool" and "Material", which are not classes: a template with one of those as
# its `type` names no engine class, so ItemFactory refuses to build it and the
# item cannot exist in the game at all.
const ITEM_CLASSES := [
	"Item", "Weapon", "Armor", "Consumable", "Container", "Key", "Treasure",
	"Junk", "Gem", "Lockpick", "ResourceNode", "Interactive",
]

var container: VBoxContainer
var cur_data: Dictionary
var props_box: VBoxContainer
var database_mgr: DatabaseManager
var catalog: ContractCatalog


func build(c: VBoxContainer, data: Dictionary, db_mgr: DatabaseManager = null):
	container = c
	cur_data = data
	database_mgr = db_mgr
	catalog = db_mgr.catalog if db_mgr != null else null
	_build_details()
	_build_salvage()
	_build_contract()
	_build_properties()

func _build_details():
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Details"))
	
	var card = InspectorStyle.create_card(); var vbox = card.get_child(0).get_child(0)
	container.add_child(card)
	
	# Type
	var hb = HBoxContainer.new()
	hb.add_child(InspectorStyle.lbl("Type:", InspectorStyle.COLOR_TEXT_DIM))
	var type_opt = OptionButton.new()
	var item_types := ITEM_CLASSES.duplicate()
	for t in item_types: type_opt.add_item(t)
	var current_type = str(cur_data.get("type", "Item"))
	var idx = item_types.find(current_type)
	if idx != -1: type_opt.selected = idx
	else:
		type_opt.add_item(current_type)
		type_opt.select(type_opt.item_count - 1)
	type_opt.item_selected.connect(func(i): cur_data["type"] = type_opt.get_item_text(i); database_modified.emit())
	# A template with a family resolves to the *family's* class
	# (item_class_for_template), so `type` is only the legacy fallback once a
	# family is named. Say that rather than letting an author edit a field that
	# no longer decides anything.
	if str(cur_data.get("item_family", "")) != "":
		type_opt.disabled = true
		type_opt.tooltip_text = "This template names a family, so the engine builds the family's class. Clear the family to edit this."
	else:
		type_opt.disabled = str(cur_data.get("type", "")) == "Gem"
	type_opt.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_button_style(type_opt)
	hb.add_child(type_opt)
	vbox.add_child(hb)
	
	# Weight & Value
	var hb2 = HBoxContainer.new()
	_add_spin_field(hb2, "Weight", "weight", 0.0)
	_add_spin_field(hb2, "Value", "value", 0)
	vbox.add_child(hb2)
	
	# Stackable
	var chk = CheckBox.new(); chk.text = "Stackable"
	chk.button_pressed = cur_data.get("stackable", false)
	chk.toggled.connect(func(b): cur_data["stackable"] = b; database_modified.emit())
	vbox.add_child(chk)


# What this template *is*, to the contract system: the family the engine resolves
# its class and behaviour from, and the roll tables if it generates instances.
# These are the fields content validation checks and the loader reads, and until
# now the editor had no control for either of them.
# What this template breaks down into.
#
# Salvage is asked in three places, most specific first, and this is the most
# specific: the item's own answer beats the family rule in the ruleset, which
# beats the engine class rule. The property is a nested object, and the property
# editor below only offers string/number/bool/equip-slot rows -- so this was
# hand-written JSON, which is why eleven templates in the fantasy set were the
# only ones that could say "this is leather, not iron".
func _build_salvage():
	container.add_child(HSeparator.new())
	var header := HBoxContainer.new()
	header.add_child(InspectorStyle.create_sub_header("Salvage"))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	var toggle := CheckBox.new()
	toggle.text = "declare its own output"
	InspectorStyle.apply_button_style(toggle)
	header.add_child(toggle)
	container.add_child(header)

	var hint := Label.new()
	hint.add_theme_font_size_override("font_size", 11)
	hint.modulate = Color(0.65, 0.68, 0.74)
	hint.text = "Leave this off and the ruleset's family rule answers instead."
	container.add_child(hint)

	var card := InspectorStyle.create_card()
	var vbox := card.get_child(0).get_child(0)
	container.add_child(card)

	if not cur_data.has("properties"): cur_data["properties"] = {}
	var properties: Dictionary = cur_data["properties"]
	var authored = properties.get("salvage_output")
	toggle.button_pressed = authored is Dictionary

	var row_holder := HBoxContainer.new()
	row_holder.add_theme_constant_override("separation", 6)
	row_holder.add_child(InspectorStyle.lbl("Breaks into:", InspectorStyle.COLOR_TEXT_DIM))
	vbox.add_child(row_holder)

	var rate_holder := HBoxContainer.new()
	rate_holder.add_theme_constant_override("separation", 6)
	rate_holder.add_child(InspectorStyle.lbl("Per unit of weight:", InspectorStyle.COLOR_TEXT_DIM))
	vbox.add_child(rate_holder)

	# The switch is what writes the property; the controls below edit the dict
	# that would be written, so turning it on is never a surprise.
	if not (authored is Dictionary):
		authored = {}
	var editor := ReferenceEditor.new()
	var _reference_row := editor.build(row_holder, authored, Callable(self, "_salvage_suggestions"))

	var rate := SpinBox.new()
	rate.min_value = 0.0; rate.max_value = 20.0; rate.step = 0.1
	rate.value = float(authored.get("quantity_per_weight", 1.0))
	rate.tooltip_text = "how much comes back per unit of the item's weight"
	rate.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(rate)
	rate.value_changed.connect(func(value):
		authored["quantity_per_weight"] = float(value)
		if toggle.button_pressed:
			properties["salvage_output"] = authored
		database_modified.emit()
	)
	rate_holder.add_child(rate)

	# Typing in either control is itself the decision; the switch only says
	# whether the template answers at all.
	editor.changed.connect(func():
		if toggle.button_pressed:
			properties["salvage_output"] = authored
		database_modified.emit()
	)
	toggle.toggled.connect(func(pressed):
		if pressed: properties["salvage_output"] = authored
		else: properties.erase("salvage_output")
		database_modified.emit()
	)


func _salvage_suggestions(kind: String) -> Array:
	match kind:
		"item_family":
			return catalog.family_ids() if catalog != null else []
		"capability":
			return catalog.capability_ids() if catalog != null else []
		_:
			return database_mgr.get_item_ids() if database_mgr != null else []


func _build_contract():
	if catalog == null or catalog.family_ids().is_empty():
		return
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Contract"))
	var card = InspectorStyle.create_card(); var vbox = card.get_child(0).get_child(0)
	container.add_child(card)

	var family_id := str(cur_data.get("item_family", ""))

	var family_row := HBoxContainer.new()
	family_row.add_child(InspectorStyle.lbl("Family:", InspectorStyle.COLOR_TEXT_DIM))
	var family_picker := OptionButton.new()
	family_picker.name = "FamilyPicker"
	family_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var family_ids: Array = ["(no family)"] + catalog.family_ids()
	for id in family_ids:
		family_picker.add_item(str(id))
		if str(id) == family_id:
			family_picker.select(family_picker.item_count - 1)
	if family_id == "":
		family_picker.select(0)
	InspectorStyle.apply_button_style(family_picker)
	family_picker.item_selected.connect(func(index):
		var chosen := str(family_ids[index])
		if chosen == "(no family)":
			cur_data.erase("item_family")
		else:
			cur_data["item_family"] = chosen
		database_modified.emit()
		_refresh_contract_summary()
	)
	family_row.add_child(family_picker)
	vbox.add_child(family_row)

	# Every generation profile in the set, plus the option of following the
	# family's own -- a template may override which tables it rolls on.
	var profile_row := HBoxContainer.new()
	profile_row.add_child(InspectorStyle.lbl("Roll tables:", InspectorStyle.COLOR_TEXT_DIM))
	var profile_picker := OptionButton.new()
	profile_picker.name = "ProfilePicker"
	profile_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var authored_profile := str(cur_data.get("generation_profile", ""))
	var profile_ids: Array = ["(family default)"] + catalog.profile_ids()
	for id in profile_ids:
		profile_picker.add_item(str(id))
		if str(id) == authored_profile:
			profile_picker.select(profile_picker.item_count - 1)
	if authored_profile == "":
		profile_picker.select(0)
	InspectorStyle.apply_button_style(profile_picker)
	profile_picker.item_selected.connect(func(index):
		var chosen := str(profile_ids[index])
		if chosen == "(family default)":
			cur_data.erase("generation_profile")
		else:
			cur_data["generation_profile"] = chosen
		database_modified.emit()
		_refresh_contract_summary()
	)
	profile_row.add_child(profile_picker)
	vbox.add_child(profile_row)

	var summary := Label.new()
	summary.name = "ContractSummary"
	summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	summary.add_theme_font_size_override("font_size", 11)
	vbox.add_child(summary)
	_refresh_contract_summary()

	if _rolls_instances():
		_build_generation_definition(vbox)


func _refresh_contract_summary():
	var summary := container.find_child("ContractSummary", true, false)
	if summary == null or not (summary is Label):
		return
	var lines: Array = []
	var family_id := str(cur_data.get("item_family", ""))
	if family_id == "":
		lines.append("No family: the engine builds this template's `type` and nothing else.")
	elif not catalog.has_family(family_id):
		lines.append("Family '%s' is not declared in this content set -- the loader will refuse it." % family_id)
	else:
		var engine_class := catalog.item_class_for_family(family_id)
		lines.append("Family makes the engine build: %s" % engine_class)
		if engine_class != str(cur_data.get("type", "")):
			lines.append("(its legacy `type` says %s; the family decides)" % str(cur_data.get("type", "")))
		var capabilities := catalog.family_capabilities(family_id)
		if not capabilities.is_empty():
			lines.append("capabilities: %s" % ", ".join(capabilities))
		var trailing: Array = []
		var icon := catalog.family_icon_style(family_id)
		if icon != "": trailing.append("icon: %s" % icon)
		var profile := _effective_profile()
		if profile != "": trailing.append("rolls on: %s" % profile)
		if not trailing.is_empty():
			lines.append("  |  ".join(trailing))
	summary.text = "\n".join(lines)


# The profile that will actually be used: the template's own if it names one,
# else the family's.
func _effective_profile() -> String:
	var authored := str(cur_data.get("generation_profile", ""))
	if authored != "": return authored
	return catalog.generation_profile_for_family(str(cur_data.get("item_family", "")))


func _rolls_instances() -> bool:
	var profile := _effective_profile()
	if profile == "": return false
	return catalog.family_capabilities(str(cur_data.get("item_family", ""))).has("generated_instance")


func _build_generation_definition(parent: VBoxContainer):
	container.add_child(HSeparator.new())
	container.add_child(InspectorStyle.create_sub_header("Generated instances"))
	var card = InspectorStyle.create_card(); var vbox = card.get_child(0).get_child(0)
	container.add_child(card)
	var profile := _effective_profile()
	vbox.add_child(InspectorStyle.lbl(
		"This family rolls instances on '%s': each found one rolls its own bands." % profile,
		InspectorStyle.COLOR_TEXT_DIM))

	# Intrinsic rarity, from the profile's own bands. The list used to be the four
	# fantasy rarity names, which a set that names its bands differently could not
	# express at all.
	var rarity_ids := catalog.tier_ids(profile, "rarity_tiers")
	if not rarity_ids.is_empty():
		var rarity_row := HBoxContainer.new()
		rarity_row.add_child(InspectorStyle.lbl("Intrinsic rarity", InspectorStyle.COLOR_TEXT_DIM))
		var rarity := OptionButton.new(); rarity.name = "RarityPicker"; rarity.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var options: Array = ["(infer from value)"] + rarity_ids
		for rarity_id in options: rarity.add_item(str(rarity_id))
		var current_rarity := str(cur_data.get("rarity", "")).to_lower()
		var rarity_index := options.find(current_rarity)
		rarity.select(rarity_index if rarity_index >= 0 else 0)
		rarity.item_selected.connect(func(index):
			if index == 0: cur_data.erase("rarity")
			else: cur_data["rarity"] = str(options[index])
			database_modified.emit()
		)
		InspectorStyle.apply_button_style(rarity)
		rarity_row.add_child(rarity); vbox.add_child(rarity_row)

	var biases: Dictionary = cur_data.get("gem_generation", {})
	if not (biases is Dictionary):
		biases = {}
	if biases.is_empty():
		biases = {"size_bias": 0.0, "quality_bias": 0.0}
	_add_gem_bias(vbox, "Size tendency (this template)", "size_bias", biases, "Smaller ← → larger")
	_add_gem_bias(vbox, "Quality tendency (this template)", "quality_bias", biases, "Flawed ← → perfect")

func _add_gem_bias(parent: VBoxContainer, label: String, key: String, profile: Dictionary, hint: String):
	var group := VBoxContainer.new()
	var heading := HBoxContainer.new()
	heading.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var value_label := Label.new(); value_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT; value_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	heading.add_child(value_label); group.add_child(heading)
	var slider := HSlider.new(); slider.min_value = -2.0; slider.max_value = 2.0; slider.step = 0.5
	slider.value = float(profile.get(key, 0.0)); slider.tooltip_text = hint
	value_label.text = "%+.1f  %s" % [slider.value, hint]
	slider.value_changed.connect(func(value):
		profile[key] = value
		cur_data["gem_generation"] = profile
		value_label.text = "%+.1f  %s" % [value, hint]
		database_modified.emit()
	)
	group.add_child(slider); parent.add_child(group)

func _add_spin_field(parent, label, key, default):
	var vb = VBoxContainer.new(); vb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vb.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var sb = SpinBox.new(); sb.value = cur_data.get(key, default)
	sb.value_changed.connect(func(v): cur_data[key] = v; database_modified.emit())
	InspectorStyle.apply_input_style(sb)
	vb.add_child(sb); parent.add_child(vb)

func _build_properties():
	container.add_child(HSeparator.new())
	var hb = HBoxContainer.new()
	hb.add_child(InspectorStyle.create_sub_header("Item Properties"))
	var spacer = Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; hb.add_child(spacer)
	var btn_add = Button.new(); btn_add.text = "+ Prop"; InspectorStyle.apply_button_style(btn_add)
	
	var pp = PopupMenu.new()
	pp.add_item("String"); pp.add_item("Number"); pp.add_item("Bool"); pp.add_item("Equip Slot")
	pp.id_pressed.connect(_add_item_prop)
	btn_add.pressed.connect(func(): pp.position = Vector2i(btn_add.get_screen_position()) + Vector2i(0, 30); pp.popup())
	container.add_child(pp)
	
	hb.add_child(btn_add); container.add_child(hb)
	
	props_box = VBoxContainer.new(); props_box.add_theme_constant_override("separation", 6)
	container.add_child(props_box)
	
	if not cur_data.has("properties"): cur_data["properties"] = {}
	_refresh_props()

func _add_item_prop(id):
	var k = "new_prop"
	var v = ""
	if id == 1: v = 0
	elif id == 2: v = false
	elif id == 3: k = "equip_slot"; v = []
	cur_data.properties[k] = v
	database_modified.emit()
	_refresh_props()

func _refresh_props():
	for c in props_box.get_children(): c.queue_free()
	var props = cur_data.properties
	for key in props:
		var val = props[key]
		# Objects and arrays cannot make a lossless trip through a LineEdit:
		# `str(value)` is GDScript debug syntax, not editable JSON. Keep them
		# visible but read-only until their dedicated item-property controls exist.
		# `equip_slot` is the one structured property this inspector owns.
		if key != "equip_slot" and not PropertyTagRow.is_inline_editable(val):
			props_box.add_child(PropertyTagRow.build_nested_row(
				str(key), val, "a dedicated item-property editor (not available here yet)"
			))
			continue
		var panel = PanelContainer.new()
		var style = StyleBoxFlat.new(); style.bg_color = Color(0.25, 0.25, 0.28); style.set_corner_radius_all(6)
		style.content_margin_left = 10; style.content_margin_right = 10; style.content_margin_top = 4; style.content_margin_bottom = 4
		panel.add_theme_stylebox_override("panel", style)
		
		var hb = HBoxContainer.new(); panel.add_child(hb)
		
		if key == "equip_slot":
			var l = Label.new(); l.text = "Equip Slots"; l.modulate = Color.CYAN; hb.add_child(l)
		else:
			var ed_k = LineEdit.new(); ed_k.text = key; ed_k.custom_minimum_size.x = 120
			InspectorStyle.apply_input_style(ed_k)
			ed_k.text_submitted.connect(func(t): 
				if t != key and not props.has(t):
					props[t] = val; props.erase(key); database_modified.emit(); _refresh_props()
			)
			hb.add_child(ed_k)
		
		var spacer = Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; hb.add_child(spacer)
		
		if key == "equip_slot" and typeof(val) == TYPE_ARRAY:
			var btn_slots = MenuButton.new(); btn_slots.text = "Select Slots..."
			if not val.is_empty(): btn_slots.text = ",".join(val)
			InspectorStyle.apply_button_style(btn_slots)
			var popup = btn_slots.get_popup()
			popup.hide_on_checkable_item_selection = false
			var slots = ["head", "body", "legs", "feet", "main_hand", "off_hand", "neck", "hands", "ring"]
			for s in slots:
				popup.add_check_item(s)
				popup.set_item_checked(popup.item_count-1, val.has(s))
			popup.index_pressed.connect(func(idx):
				var s_name = slots[idx]
				if val.has(s_name): val.erase(s_name)
				else: val.append(s_name)
				popup.set_item_checked(idx, val.has(s_name))
				btn_slots.text = ",".join(val) if not val.is_empty() else "Select Slots..."
				database_modified.emit()
			)
			hb.add_child(btn_slots)
		elif typeof(val) == TYPE_BOOL:
			var chk = CheckBox.new(); chk.button_pressed = val; chk.text = "True" if val else "False"
			chk.toggled.connect(func(b): props[key] = b; chk.text = "True" if b else "False"; database_modified.emit())
			hb.add_child(chk)
		elif typeof(val) == TYPE_FLOAT or typeof(val) == TYPE_INT:
			var sb = SpinBox.new(); sb.step = 0.1; sb.allow_greater = true; sb.allow_lesser = true
			sb.value = val; sb.custom_minimum_size.x = 80
			# SpinBox emits floats. Preserve authored integer fields so the number
			# gate does not later reject an editor-produced `2.0` for `2`.
			InspectorStyle.apply_input_style(sb); sb.value_changed.connect(func(v):
				props[key] = int(v) if typeof(val) == TYPE_INT else v
				database_modified.emit()
			)
			hb.add_child(sb)
		else:
			var ed_v = LineEdit.new(); ed_v.text = str(val); ed_v.custom_minimum_size.x = 150
			InspectorStyle.apply_input_style(ed_v); ed_v.text_changed.connect(func(t): props[key] = t; database_modified.emit())
			hb.add_child(ed_v)
			
		var btn_x = Button.new(); btn_x.text = "×"; btn_x.flat = true
		btn_x.add_theme_color_override("font_color", Color(0.6, 0.6, 0.6))
		btn_x.add_theme_color_override("font_hover_color", Color.RED)
		btn_x.pressed.connect(func(): props.erase(key); database_modified.emit(); _refresh_props())
		hb.add_child(btn_x)
		
		props_box.add_child(panel)
