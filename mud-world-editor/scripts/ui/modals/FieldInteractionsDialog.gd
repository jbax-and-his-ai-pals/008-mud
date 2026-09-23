# scripts/ui/modals/FieldInteractionsDialog.gd
#
# Ambient fields (`data/world/field_interactions.json`): the fields a world
# spreads, their polarity, and how strongly one damps another where they
# overlap. Only what the author changes is written; other keys in the file
# survive a save as they were.

class_name FieldInteractionsDialog
extends "res://scripts/ui/modals/ConfigurationDialog.gd"

var draft: FieldInteractionsDraft
var status: Label
var default_field: LineEdit
var fallback: SpinBox
var polarity_rows: VBoxContainer
var rule_rows: VBoxContainer
var loading := false


func setup():
	_install_guard()
	title = "Ambient Fields"
	min_size = Vector2i(760, 600)
	ok_button_text = "Save Ambient Fields"
	confirmed.connect(_save)
	var scroll := ScrollContainer.new(); scroll.custom_minimum_size = Vector2(730, 510); add_child(scroll)
	var box := VBoxContainer.new(); box.custom_minimum_size = Vector2(700, 0); box.add_theme_constant_override("separation", 10); scroll.add_child(box)
	status = Label.new(); status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; status.modulate = InspectorStyle.COLOR_TEXT_DIM; box.add_child(status)

	box.add_child(InspectorStyle.create_sub_header("Fields"))
	_hint(box, "Each field spreads across the world grid. Where a positive and a negative field overlap, the positive one damps the other unless a rule below says otherwise.")
	polarity_rows = _list(box, "+ Field", func(): _add_polarity_row("", "neutral"); _mark_dirty())
	var default_row := VBoxContainer.new(); box.add_child(default_row)
	default_row.add_child(InspectorStyle.lbl("Default field (seeded when the world starts)", InspectorStyle.COLOR_TEXT_DIM))
	default_field = LineEdit.new(); default_field.name = "DefaultField"; default_field.placeholder_text = "blight"; InspectorStyle.apply_input_style(default_field)
	default_field.text_changed.connect(func(_t): _mark_dirty()); default_row.add_child(default_field)

	box.add_child(InspectorStyle.create_sub_header("Suppression"))
	var fallback_row := HBoxContainer.new(); fallback_row.add_theme_constant_override("separation", 8); box.add_child(fallback_row)
	fallback_row.add_child(InspectorStyle.lbl("Positive damps negative by", InspectorStyle.COLOR_TEXT_DIM))
	fallback = _coefficient_spin(0.6); fallback.name = "Fallback"; fallback_row.add_child(fallback)
	_hint(box, "Rules override that default for a specific pair: the source field damps the target by this share of its own strength (0 = never, 1 = entirely).")
	rule_rows = _list(box, "+ Rule", func(): _add_rule_row("", "", 0.5); _mark_dirty())

	DialogStyle.style_window(self)
	get_ok_button().custom_minimum_size = Vector2(300, 40)
	get_ok_button().disabled = true


func open_active():
	if visible: return
	draft = null
	_form_baseline.clear()
	var result := FieldInteractionsDraft.load(FieldInteractionsDraft.config_path())
	if not result.get("ok", false):
		status.text = str(result.get("error", "Could not load ambient fields.")); status.modulate = DialogStyle.COLOR_DANGER
		get_ok_button().disabled = true; popup_centered(); return
	draft = result["draft"]
	loading = true
	for rows in [polarity_rows, rule_rows]:
		for child in rows.get_children(): _remove_row(child)
	var polarities: Dictionary = draft.data.get("polarities", {})
	for field_id in polarities: _add_polarity_row(str(field_id), str(polarities[field_id]))
	var rules: Dictionary = draft.data.get("pairwise_rules", {})
	for source_id in rules:
		for target_id in rules[source_id]: _add_rule_row(str(source_id), str(target_id), float(rules[source_id][target_id]))
	default_field.text = str(draft.data.get("default_field_id", ""))
	fallback.value = float(draft.data.get("fallback_positive_suppresses_negative", 0.6))
	_reset_form_baseline()
	loading = false
	get_ok_button().disabled = true
	if draft.exists:
		status.text = "Editing %s." % draft.path; status.modulate = InspectorStyle.COLOR_TEXT_DIM
	else:
		status.text = "This content set has no ambient fields. Saving creates field_interactions.json, which turns the field system on."; status.modulate = Color("f2cf74")
	popup_centered()


## The file this dialog would write, composed from what the author changed.
func compose() -> Dictionary:
	var out := draft.original.duplicate(true)
	var polarities := {}
	for row in polarity_rows.get_children():
		var field_id := (row.get_node("FieldId") as LineEdit).text.strip_edges()
		var picker: OptionButton = row.get_node("Polarity")
		if field_id != "": polarities[field_id] = picker.get_item_text(picker.selected)
	_put(out, "polarities", polarities)
	var rules := {}
	for row in rule_rows.get_children():
		var source_id := (row.get_node("Source") as LineEdit).text.strip_edges()
		var target_id := (row.get_node("Target") as LineEdit).text.strip_edges()
		if source_id == "" or target_id == "": continue
		if not rules.has(source_id): rules[source_id] = {}
		rules[source_id][target_id] = snappedf((row.get_node("Coefficient") as SpinBox).value, 0.01)
	_put(out, "pairwise_rules", rules)
	if _field_changed(default_field):
		if default_field.text.strip_edges() == "": out.erase("default_field_id")
		else: out["default_field_id"] = default_field.text.strip_edges()
	if _field_changed(fallback): out["fallback_positive_suppresses_negative"] = snappedf(fallback.value, 0.01)
	return out


func _save():
	if draft == null: return
	if not _form_changed(): _finish_save(); return
	draft.data = compose()
	var result := draft.save()
	if not result.get("ok", false):
		status.text = str(result.get("error", "Could not save ambient fields.")); status.modulate = DialogStyle.COLOR_DANGER; return
	get_ok_button().disabled = true
	_finish_save()


## Replaces `key` only when its rows differ from the file, so an untouched
## section keeps its original numbers and order.
func _put(out: Dictionary, key: String, value: Dictionary):
	var before = draft.original.get(key, {})
	if JSON.stringify(SaveIO._normalize_numbers(value)) == JSON.stringify(SaveIO._normalize_numbers(before)): return
	if value.is_empty(): out.erase(key)
	else: out[key] = value


func _add_polarity_row(field_id: String, polarity: String):
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6); polarity_rows.add_child(row)
	var id_field := LineEdit.new(); id_field.name = "FieldId"; id_field.text = field_id; id_field.placeholder_text = "field id"; id_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(id_field); id_field.text_changed.connect(func(_t): _mark_dirty()); row.add_child(id_field)
	var picker := OptionButton.new(); picker.name = "Polarity"; picker.custom_minimum_size.x = 130
	var options: Array = FieldInteractionsDraft.POLARITIES.duplicate()
	if not options.has(polarity): options.append(polarity)
	for option in options: picker.add_item(option)
	picker.select(options.find(polarity)); InspectorStyle.apply_button_style(picker)
	picker.item_selected.connect(func(_i): _mark_dirty()); row.add_child(picker)
	row.add_child(_remove_button(row))


func _add_rule_row(source_id: String, target_id: String, coefficient: float):
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6); rule_rows.add_child(row)
	for spec in [["Source", source_id, "source field"], ["Target", target_id, "target field"]]:
		var field := LineEdit.new(); field.name = spec[0]; field.text = spec[1]; field.placeholder_text = spec[2]; field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_input_style(field); field.text_changed.connect(func(_t): _mark_dirty()); row.add_child(field)
		if spec[0] == "Source": row.add_child(InspectorStyle.lbl("damps", InspectorStyle.COLOR_TEXT_DIM))
	row.add_child(InspectorStyle.lbl("by", InspectorStyle.COLOR_TEXT_DIM))
	var spin := _coefficient_spin(coefficient); spin.name = "Coefficient"; row.add_child(spin)
	row.add_child(_remove_button(row))


func _coefficient_spin(value: float) -> SpinBox:
	var spin := SpinBox.new(); spin.min_value = 0; spin.max_value = 1; spin.step = 0.01; spin.value = value
	spin.custom_minimum_size.x = 80; InspectorStyle.apply_input_style(spin)
	spin.value_changed.connect(func(_v): _mark_dirty())
	return spin


func _remove_button(row: Control) -> Button:
	var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
	remove.pressed.connect(func(): _remove_row(row); _mark_dirty())
	return remove


func _list(box: VBoxContainer, button_text: String, on_add: Callable) -> VBoxContainer:
	var rows := VBoxContainer.new(); rows.add_theme_constant_override("separation", 5); box.add_child(rows)
	var add := Button.new(); add.text = button_text; InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS); add.pressed.connect(on_add); box.add_child(add)
	return rows


func _hint(box: VBoxContainer, text: String):
	var label := InspectorStyle.lbl(text, InspectorStyle.COLOR_TEXT_DIM); label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(label)


func _mark_dirty():
	if loading or draft == null: return
	var dirty := _form_changed()
	get_ok_button().disabled = not dirty
	status.text = "Unsaved ambient field changes." if dirty else "No unsaved changes."; status.modulate = Color("f2cf74")
