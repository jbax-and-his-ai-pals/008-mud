# scripts/ui/inspectors/sub_inspectors/SpawnerInspector.gd

class_name SpawnerInspector
extends RefCounted

signal data_modified

var container: VBoxContainer
var root_container: VBoxContainer
var cur_data: Dictionary
var database_mgr: DatabaseManager

func build(c: VBoxContainer, data: Dictionary, db_mgr: DatabaseManager):
	container = c
	cur_data = data
	database_mgr = db_mgr
	root_container = VBoxContainer.new()
	root_container.add_theme_constant_override("separation", 8)
	container.add_child(root_container)
	_build_spawner()

func _build_spawner():
	root_container.add_child(InspectorStyle.create_section_header("SPAWNER CONFIG", Color.SALMON))
	var card = InspectorStyle.create_card(); var vbox = card.get_child(0).get_child(0)
	root_container.add_child(card)

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
	if bool(sp.get("monsters_enabled", true)):
		_build_weight_section(vbox, sp, "monster_types", "Monster Weights:", "Monster")

	vbox.add_child(HSeparator.new())
	_build_toggle(vbox, sp, "npcs_enabled", "Spawn Wandering NPCs")
	if bool(sp.get("npcs_enabled", true)):
		_build_weight_section(vbox, sp, "npc_types", "NPC Weights:", "NPC")

# A region that doesn't want ambient monsters or wandering NPCs at all
# (e.g. a quiet instanced puzzle room) can turn either off without having
# to empty out its weight table -- World.Spawner checks these flags before
# doing any spawn work for that category.
func _build_toggle(vbox: VBoxContainer, sp: Dictionary, key: String, label: String):
	var cb := CheckBox.new()
	cb.text = label
	cb.button_pressed = bool(sp.get(key, true))
	# Rebuild to hide the associated list completely while preserving it in
	# the spawner dictionary. Turning the category back on restores weights.
	cb.toggled.connect(func(pressed):
		sp[key] = pressed
		data_modified.emit()
		_rebuild_after_toggle()
	)
	vbox.add_child(cb)

func _rebuild_after_toggle():
	if not is_instance_valid(root_container): return
	for child in root_container.get_children(): child.queue_free()
	_build_spawner()

func _build_weight_section(vbox: VBoxContainer, sp: Dictionary, config_key: String, label: String, category: String):
	vbox.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var box := VBoxContainer.new(); vbox.add_child(box)
	var catalog := _get_catalog(category)

	# A method, not a lambda that hands itself to its rows: a GDScript lambda
	# captures `refresh` by value when it is made, before it is assigned, so every
	# row got a null Callable -- removing or re-picking a creature changed the
	# data and then errored, leaving the stale row on screen.
	var refresh := func(): _refresh_weight_rows(box, sp, config_key, catalog)

	var add_row := HBoxContainer.new()
	var picker := OptionButton.new()
	picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(picker)
	for entry in catalog:
		if not sp.get(config_key, {}).has(entry.id):
			picker.add_item(entry.label)
			picker.set_item_metadata(picker.item_count - 1, entry.id)
	if picker.item_count == 0:
		picker.add_item("No additional %ss available" % category.to_lower())
		picker.disabled = true
	add_row.add_child(picker)

	var btn_add := Button.new(); btn_add.text = "Add " + category
	InspectorStyle.apply_button_style(btn_add, InspectorStyle.COLOR_SUCCESS.darkened(0.2))
	btn_add.pressed.connect(func():
		if picker.disabled or picker.selected < 0: return
		var entry_id := str(picker.get_item_metadata(picker.selected))
		if entry_id.is_empty(): return
		if not sp.has(config_key): sp[config_key] = {}
		# The picker is built once, so it can still offer a creature already
		# added; adding it again must not reset that creature's weight.
		if sp[config_key].has(entry_id): return
		sp[config_key][entry_id] = 1.0
		refresh.call(); data_modified.emit()
	)
	btn_add.disabled = picker.disabled
	add_row.add_child(btn_add)
	vbox.add_child(add_row)
	refresh.call()

func _refresh_weight_rows(box: VBoxContainer, sp: Dictionary, config_key: String, catalog: Array):
	for c in box.get_children(): box.remove_child(c); c.queue_free()
	var types: Dictionary = sp.get(config_key, {})
	var entry_ids: Array = types.keys()
	entry_ids.sort()
	var refresh := func(): _refresh_weight_rows(box, sp, config_key, catalog)
	for entry_id in entry_ids:
		box.add_child(_create_weight_row(types, str(entry_id), catalog, refresh))

func _create_weight_row(types: Dictionary, entry_id: String, catalog: Array, refresh: Callable) -> PanelContainer:
	var panel = PanelContainer.new()
	var s = StyleBoxFlat.new(); s.bg_color = Color(0.12, 0.12, 0.14); s.set_corner_radius_all(4)
	panel.add_theme_stylebox_override("panel", s)
	var hb = HBoxContainer.new()
	panel.add_child(hb)

	var picker := OptionButton.new(); picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(picker)
	var selected_index := -1
	for entry in catalog:
		picker.add_item(entry.label)
		picker.set_item_metadata(picker.item_count - 1, entry.id)
		if entry.id == entry_id: selected_index = picker.item_count - 1
	# Keep legacy/missing entries visible and intact instead of silently
	# deleting them just because their database definition was removed.
	if selected_index == -1:
		picker.add_item("Missing: " + entry_id)
		picker.set_item_metadata(picker.item_count - 1, entry_id)
		selected_index = picker.item_count - 1
	picker.select(selected_index)
	picker.item_selected.connect(func(index):
		var selected_id := str(picker.get_item_metadata(index))
		if selected_id == entry_id or types.has(selected_id): return
		var weight = types[entry_id]
		types.erase(entry_id)
		types[selected_id] = weight
		refresh.call(); data_modified.emit()
	)
	hb.add_child(picker)

	var sb = SpinBox.new(); sb.step=0.1; sb.value=types[entry_id]
	InspectorStyle.apply_input_style(sb)
	sb.value_changed.connect(func(v): types[entry_id]=v; data_modified.emit())
	hb.add_child(sb)

	var d = Button.new(); d.text="x"; d.flat=true; d.pressed.connect(func(): types.erase(entry_id); refresh.call(); data_modified.emit())
	hb.add_child(d)
	return panel

# Monsters and wandering NPCs are both stored in the NPC database today;
# `friendly` is the stable content distinction already used by the database
# browser. This keeps existing content compatible while giving the spawner
# two clear, non-overlapping pickers.
func _get_catalog(category: String) -> Array:
	var entries: Array = []
	if database_mgr == null: return entries
	var want_monster := category == "Monster"
	for entry_id in database_mgr.npcs:
		var entry: Dictionary = database_mgr.npcs[entry_id]
		var is_monster := not bool(entry.get("friendly", true))
		if is_monster != want_monster: continue
		entries.append({
			"id": str(entry_id),
			"label": str(entry.get("name", entry_id)).capitalize()
		})
	entries.sort_custom(func(a, b): return str(a.label).nocasecmp_to(str(b.label)) < 0)
	return entries
