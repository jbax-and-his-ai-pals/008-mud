class_name CombatVocabularyDialog
extends "res://scripts/ui/modals/ConfigurationDialog.gd"

signal combat_vocabulary_saved
const COMBAT_VOCABULARY_DRAFT_SCRIPT = preload("res://scripts/data/CombatVocabularyDraft.gd")
var draft
var types: LineEdit
var default_type: LineEdit
var hazard_rows: VBoxContainer
var status: Label
var loading := false
var dirty := false

func setup():
	_install_guard()
	title = "Combat Vocabulary"
	min_size = Vector2i(820, 620)
	ok_button_text = "Save Combat Changes"
	confirmed.connect(_save)
	var root := VBoxContainer.new(); root.custom_minimum_size = Vector2(780, 530); root.add_theme_constant_override("separation", 8); add_child(root)
	status = Label.new(); status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; status.modulate = InspectorStyle.COLOR_TEXT_DIM; root.add_child(status)
	root.add_child(InspectorStyle.create_sub_header("Damage Channels"))
	types = _field(root, "Channels (comma-separated)"); default_type = _field(root, "Default channel")
	root.add_child(InspectorStyle.create_sub_header("Room Hazards"))
	var scroll := ScrollContainer.new(); scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL; root.add_child(scroll)
	hazard_rows = VBoxContainer.new(); hazard_rows.add_theme_constant_override("separation", 8); scroll.add_child(hazard_rows)
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
	var result: Dictionary = draft.save()
	if not result.get("ok", false): status.text = str(result.get("error", "Could not save combat vocabulary.")); status.modulate = DialogStyle.COLOR_DANGER; return
	dirty = false; get_ok_button().disabled = true; combat_vocabulary_saved.emit()
	_finish_save()

func _mark_dirty():
	if loading or draft == null: return
	dirty = _form_changed(); get_ok_button().disabled = not dirty; status.text = "Unsaved combat vocabulary changes." if dirty else "No unsaved changes."; status.modulate = Color("f2cf74")
