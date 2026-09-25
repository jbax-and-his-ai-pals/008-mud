class_name CombatVocabularyDialog
extends "res://scripts/ui/modals/ConfigurationDialog.gd"

signal combat_vocabulary_saved
const COMBAT_VOCABULARY_DRAFT_SCRIPT = preload("res://scripts/data/CombatVocabularyDraft.gd")
var draft
var types: LineEdit
var default_type: LineEdit
var hazard_rows: VBoxContainer
var flavor_rows: VBoxContainer
# What magic/effects.py shows when a spell finds a weakness or resistance, per
# channel; `default` covers every channel without its own (and is required).
const FLAVOR_LINES := [["weakness", "Weak to it"], ["resistance", "Resists it"], ["strong_resistance", "Resists it strongly (50+)"]]
var status: Label
var loading := false
var dirty := false

func setup():
	_install_guard()
	title = "Combat Vocabulary"
	min_size = Vector2i(820, 620)
	ok_button_text = "Save Combat Changes"
	confirmed.connect(_save)
	# The status line stays put; everything else scrolls, because the flavor and
	# hazard lists together are taller than most screens.
	var frame := VBoxContainer.new(); frame.custom_minimum_size = Vector2(780, 530); frame.add_theme_constant_override("separation", 8); add_child(frame)
	status = Label.new(); status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; status.custom_minimum_size.x = 760; status.modulate = InspectorStyle.COLOR_TEXT_DIM; frame.add_child(status)
	var body := ScrollContainer.new(); body.name = "Body"; body.size_flags_vertical = Control.SIZE_EXPAND_FILL; body.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED; frame.add_child(body)
	var root := VBoxContainer.new(); root.size_flags_horizontal = Control.SIZE_EXPAND_FILL; root.add_theme_constant_override("separation", 8); body.add_child(root)
	root.add_child(InspectorStyle.create_sub_header("Damage Channels"))
	types = _field(root, "Channels (comma-separated)"); default_type = _field(root, "Default channel")
	root.add_child(InspectorStyle.create_sub_header("Hit Flavor"))
	var flavor_hint := InspectorStyle.lbl("What a spell hit says about a weakness or resistance, per channel. {target_name} is filled in; `default` covers every channel without its own.", InspectorStyle.COLOR_TEXT_DIM)
	flavor_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; flavor_hint.custom_minimum_size.x = 740; root.add_child(flavor_hint)
	flavor_rows = VBoxContainer.new(); flavor_rows.name = "FlavorRows"; flavor_rows.add_theme_constant_override("separation", 6); root.add_child(flavor_rows)
	var add_flavor := Button.new(); add_flavor.name = "AddFlavor"; add_flavor.text = "+ Channel Flavor"; InspectorStyle.apply_button_style(add_flavor, InspectorStyle.COLOR_SUCCESS)
	add_flavor.pressed.connect(func(): _add_flavor("", {}); _mark_dirty()); root.add_child(add_flavor)
	root.add_child(InspectorStyle.create_sub_header("Room Hazards"))
	hazard_rows = VBoxContainer.new(); hazard_rows.add_theme_constant_override("separation", 8); root.add_child(hazard_rows)
	var add := Button.new(); add.text = "+ Add Hazard"; InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS); add.pressed.connect(func(): _add_hazard("", {}); _mark_dirty()); root.add_child(add)
	DialogStyle.style_window(self); get_ok_button().custom_minimum_size = Vector2(300, 40); get_ok_button().disabled = true

func open_active():
	if visible: return
	draft = null
	_form_baseline.clear()
	var result: Dictionary = COMBAT_VOCABULARY_DRAFT_SCRIPT.load(DataRoot.root().path_join("data/combat/elements.json"))
	if not result.get("ok", false): status.text = str(result.get("error", "Could not load combat vocabulary.")); status.modulate = DialogStyle.COLOR_DANGER; get_ok_button().disabled = true; popup_centered(); return
	draft = result["draft"]; loading = true
	types.text = ", ".join(draft.data.get("valid_damage_types", [])); default_type.text = str(draft.data.get("default_damage_type", ""))
	for child in hazard_rows.get_children(): _remove_row(child)
	var hazards: Dictionary = draft.data.get("hazards", {}) if draft.data.get("hazards", {}) is Dictionary else {}
	for hazard_id in hazards: if hazards[hazard_id] is Dictionary: _add_hazard(str(hazard_id), hazards[hazard_id])
	for child in flavor_rows.get_children(): _remove_row(child)
	var flavor: Dictionary = draft.data.get("flavor_text", {}) if draft.data.get("flavor_text", {}) is Dictionary else {}
	if not flavor.has("default"): _add_flavor("default", {})
	for channel in flavor:
		if not str(channel).begins_with("_") and flavor[channel] is Dictionary: _add_flavor(str(channel), flavor[channel])
	_reset_form_baseline()
	loading = false; dirty = false; get_ok_button().disabled = true; status.text = "Editing shared combat vocabulary. Room hazards must use one of these channels."; status.modulate = InspectorStyle.COLOR_TEXT_DIM; popup_centered()

func _field(parent: VBoxContainer, label_text: String) -> LineEdit:
	var row := VBoxContainer.new(); row.add_child(InspectorStyle.lbl(label_text, InspectorStyle.COLOR_TEXT_DIM)); var field := LineEdit.new(); InspectorStyle.apply_input_style(field); field.text_changed.connect(func(_value): _mark_dirty()); row.add_child(field); parent.add_child(row); return field

func _add_hazard(hazard_id: String, source: Dictionary):
	var entry: Dictionary = source.duplicate(true)
	var card := InspectorStyle.create_card(); var box: VBoxContainer = card.get_child(0).get_child(0); box.set_meta("hazard_id", hazard_id); box.set_meta("entry", entry); hazard_rows.add_child(card)
	var header := HBoxContainer.new(); box.add_child(header); var title := InspectorStyle.lbl("Hazard", InspectorStyle.COLOR_ACCENT); title.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(title)
	var remove := Button.new(); remove.text = "Remove"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER); remove.pressed.connect(func(): _remove_row(card); _mark_dirty()); header.add_child(remove)
	var grid := GridContainer.new(); grid.columns = 2; box.add_child(grid)
	_hazard_field(grid, box, "ID", hazard_id, "hazard_id")
	_hazard_field(grid, box, "Damage channel", str(entry.get("channel", "")), "channel")
	_hazard_field(grid, box, "Damage", str(entry.get("damage", 1)), "damage")
	_hazard_field(grid, box, "Tick interval", str(entry.get("tick_interval", 5)), "tick_interval")
	box.add_child(InspectorStyle.lbl("Player-facing flavor", InspectorStyle.COLOR_TEXT_DIM)); var flavor := TextEdit.new(); flavor.text = str(entry.get("flavor", "")); flavor.custom_minimum_size.y = 62; InspectorStyle.apply_input_style(flavor)
	flavor.text_changed.connect(func():
		if flavor.text == str(source.get("flavor", "")):
			if source.has("flavor"): entry["flavor"] = source["flavor"]
			else: entry.erase("flavor")
		else: entry["flavor"] = flavor.text.strip_edges()
		_mark_dirty()
	); box.add_child(flavor)

func _add_flavor(channel: String, source: Dictionary):
	var box := VBoxContainer.new(); box.name = "Flavor_" + (channel if channel != "" else "new"); box.set_meta("row_kind", "Flavor"); box.set_meta("source", source.duplicate(true))
	var header := HBoxContainer.new(); box.add_child(header)
	var channel_field := LineEdit.new(); channel_field.name = "Channel"; channel_field.text = channel; channel_field.placeholder_text = "damage channel"
	channel_field.editable = channel != "default"; channel_field.custom_minimum_size.x = 160; InspectorStyle.apply_input_style(channel_field)
	channel_field.text_changed.connect(func(_t): _mark_dirty()); header.add_child(channel_field)
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	if channel != "default":
		var remove := Button.new(); remove.text = "Remove"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
		remove.pressed.connect(func(): _remove_row(box); _mark_dirty()); header.add_child(remove)
	var grid := GridContainer.new(); grid.columns = 2; box.add_child(grid)
	for spec in FLAVOR_LINES:
		grid.add_child(InspectorStyle.lbl(str(spec[1]), InspectorStyle.COLOR_TEXT_DIM))
		var line := LineEdit.new(); line.name = str(spec[0]); line.text = str(source.get(spec[0], "")); line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_input_style(line); line.text_changed.connect(func(_t): _mark_dirty()); grid.add_child(line)
	flavor_rows.add_child(box)


# The flavor table as it should be written: each row over its own source (so
# unknown keys survive), `_` keys of the original kept.
func _flavor_text() -> Dictionary:
	var out: Dictionary = {}
	var original = draft.original.get("flavor_text", {})
	if original is Dictionary:
		for key in original:
			if str(key).begins_with("_"): out[key] = original[key]
	for box in flavor_rows.get_children():
		if box.get_meta("row_kind", "") != "Flavor": continue
		var channel := (box.find_child("Channel", true, false) as LineEdit).text.strip_edges()
		if channel == "": continue
		var lines: Dictionary = box.get_meta("source", {}).duplicate(true)
		for spec in FLAVOR_LINES:
			var text := (box.find_child(str(spec[0]), true, false) as LineEdit).text.strip_edges()
			if text == "": lines.erase(spec[0])
			else: lines[spec[0]] = text
		out[channel] = lines
	return out


func _hazard_field(parent: GridContainer, box: VBoxContainer, label_text: String, value: String, key: String):
	parent.add_child(InspectorStyle.lbl(label_text, InspectorStyle.COLOR_TEXT_DIM)); var field := LineEdit.new(); field.text = value; InspectorStyle.apply_input_style(field)
	var original: Dictionary = box.get_meta("entry").duplicate(true)
	field.text_changed.connect(func(text):
		field.set_meta("input_error", "")
		if key == "hazard_id": box.set_meta("hazard_id", text.strip_edges())
		elif text == value:
			if original.has(key): box.get_meta("entry")[key] = original[key]
			else: box.get_meta("entry").erase(key)
		elif key in ["damage", "tick_interval"]:
			if text.is_valid_float() and is_finite(float(text)): box.get_meta("entry")[key] = float(text)
			else: field.set_meta("input_error", "%s must be a finite number." % label_text)
		else: box.get_meta("entry")[key] = text.strip_edges()
		_mark_dirty()
	); parent.add_child(field)

func _save():
	if draft == null: return
	if not _form_changed(): _finish_save(); return
	var hazards: Dictionary = {}
	var errors := _input_errors()
	for card in hazard_rows.get_children():
		var box: VBoxContainer = card.get_child(0).get_child(0)
		var hazard_id := str(box.get_meta("hazard_id")).strip_edges()
		if hazard_id == "": errors.append("Each hazard needs an ID.")
		elif hazards.has(hazard_id): errors.append("Repeated hazard ID: %s." % hazard_id)
		else: hazards[hazard_id] = box.get_meta("entry")
	if not errors.is_empty():
		status.text = "\n".join(errors); status.modulate = DialogStyle.COLOR_DANGER; return
	draft.data = draft.original.duplicate(true)
	if _field_changed(types): draft.data["valid_damage_types"] = Array(types.text.split(",", true)).map(func(value): return str(value).strip_edges())
	if _field_changed(default_type): draft.data["default_damage_type"] = default_type.text.strip_edges()
	if hazards != draft.original.get("hazards", {}): draft.set_hazards(hazards)
	var flavor := _flavor_text()
	var original_flavor = draft.original.get("flavor_text", null)
	if JSON.stringify(flavor) != JSON.stringify(original_flavor if original_flavor is Dictionary else {}) and not (original_flavor == null and flavor.keys() == ["default"] and flavor["default"].is_empty()):
		draft.data["flavor_text"] = flavor
	var result: Dictionary = draft.save()
	if not result.get("ok", false): status.text = str(result.get("error", "Could not save combat vocabulary.")); status.modulate = DialogStyle.COLOR_DANGER; return
	dirty = false; get_ok_button().disabled = true; combat_vocabulary_saved.emit()
	_finish_save()

func _mark_dirty():
	if loading or draft == null: return
	dirty = _form_changed(); get_ok_button().disabled = not dirty; status.text = "Unsaved combat vocabulary changes." if dirty else "No unsaved changes."; status.modulate = Color("f2cf74")
