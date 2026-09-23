class_name OpeningEditorDialog
extends "res://scripts/ui/modals/ConfigurationDialog.gd"

signal opening_saved
const DraftScript = preload("res://scripts/data/OpeningDraft.gd")
var draft
var status_label: Label
var scenario_label: Label
var heading: LineEdit
var intro: TextEdit
var objectives_heading: LineEdit
var objective_rows: VBoxContainer
var loading := false

func setup():
	_install_guard(); title = "Opening & First Session"; min_size = Vector2i(760, 620); ok_button_text = "Save Opening"; confirmed.connect(_save)
	var scroll := ScrollContainer.new(); scroll.custom_minimum_size = Vector2(730, 520); add_child(scroll)
	var box := VBoxContainer.new(); box.custom_minimum_size = Vector2(700, 0); box.add_theme_constant_override("separation", 9); scroll.add_child(box)
	status_label = InspectorStyle.lbl("", InspectorStyle.COLOR_TEXT_DIM); status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(status_label)
	scenario_label = InspectorStyle.lbl("", InspectorStyle.COLOR_TEXT_DIM); box.add_child(scenario_label)
	heading = _line(box, "Heading")
	intro = TextEdit.new(); intro.custom_minimum_size = Vector2(0, 110); intro.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY; InspectorStyle.apply_input_style(intro); intro.text_changed.connect(_mark_dirty); box.add_child(InspectorStyle.lbl("Intro", InspectorStyle.COLOR_TEXT_DIM)); box.add_child(intro)
	objectives_heading = _line(box, "Objectives heading")
	var row := HBoxContainer.new(); row.add_child(InspectorStyle.create_sub_header("Suggested first actions")); var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; row.add_child(spacer)
	var add := Button.new(); add.text = "+ Objective"; InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS); add.pressed.connect(func(): _add_objective({}, ""); _mark_dirty()); row.add_child(add); box.add_child(row)
	objective_rows = VBoxContainer.new(); objective_rows.add_theme_constant_override("separation", 5); box.add_child(objective_rows)
	DialogStyle.style_window(self); get_ok_button().custom_minimum_size = Vector2(300, 40); get_ok_button().disabled = true

func open_active():
	if visible: return
	draft = null; _form_baseline.clear()
	var manifest = JSON.parse_string(FileAccess.get_file_as_string(DataRoot.root().path_join("content_set.manifest.json")))
	var paths: Dictionary = manifest.get("paths", {}) if manifest is Dictionary and manifest.get("paths") is Dictionary else {}
	var start: Dictionary = manifest.get("start", {}) if manifest is Dictionary and manifest.get("start") is Dictionary else {}
	var relative := str(paths.get("opening", "")).strip_edges()
	if relative == "": status_label.text = "This content set does not declare an opening file."; status_label.modulate = DialogStyle.COLOR_DANGER; popup_centered(); return
	draft = DraftScript.new(); var result: Dictionary = draft.open(DataRoot.root().path_join(relative), str(start.get("scenario_id", "")).strip_edges())
	if not result.get("ok", false): status_label.text = str(result.get("error", "Could not load opening.")); status_label.modulate = DialogStyle.COLOR_DANGER; popup_centered(); return
	loading = true; scenario_label.text = "Scenario id: %s (matches the manifest start)" % draft.expected_scenario_id; heading.text = str(draft.data.get("heading", "")); intro.text = str(draft.data.get("intro", "")); objectives_heading.text = str(draft.data.get("objectives_heading", ""))
	for child in objective_rows.get_children(): _remove_row(child)
	for entry in draft.data.get("objectives", []): if entry is Dictionary: _add_objective(entry, str(entry.get("id", "")))
	_reset_form_baseline(); loading = false; get_ok_button().disabled = true; status_label.text = "Edit the first-session guidance. Untouched objective fields are preserved."; status_label.modulate = InspectorStyle.COLOR_TEXT_DIM; popup_centered()

func _line(parent: Control, label: String) -> LineEdit:
	parent.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM)); var field := LineEdit.new(); InspectorStyle.apply_input_style(field); field.text_changed.connect(func(_text): _mark_dirty()); parent.add_child(field); return field

func _add_objective(source: Dictionary, objective_id: String):
	var row := VBoxContainer.new(); row.set_meta("source", source.duplicate(true)); objective_rows.add_child(row)
	var fields := HBoxContainer.new(); var id := LineEdit.new(); id.placeholder_text = "id"; id.text = objective_id; id.custom_minimum_size.x = 120; InspectorStyle.apply_input_style(id); id.text_changed.connect(func(_text): _mark_dirty()); fields.add_child(id)
	var command := LineEdit.new(); command.placeholder_text = "suggested command"; command.text = str(source.get("command", "")); command.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(command); command.text_changed.connect(func(_text): _mark_dirty()); fields.add_child(command)
	var remove := Button.new(); remove.text = "×"; remove.tooltip_text = "Remove objective"; remove.pressed.connect(func(): _remove_row(row); _mark_dirty()); fields.add_child(remove); row.add_child(fields)
	var instruction := LineEdit.new(); instruction.placeholder_text = "what the player is invited to do"; instruction.text = str(source.get("instruction", "")); InspectorStyle.apply_input_style(instruction); instruction.text_changed.connect(func(_text): _mark_dirty()); row.add_child(instruction)

func _objectives() -> Array:
	var output: Array = []
	for row in objective_rows.get_children():
		var source: Dictionary = row.get_meta("source").duplicate(true); var fields: HBoxContainer = row.get_child(0); var id: LineEdit = fields.get_child(0); var command: LineEdit = fields.get_child(1); var instruction: LineEdit = row.get_child(1)
		source["id"] = id.text.strip_edges(); source["command"] = command.text.strip_edges(); source["instruction"] = instruction.text.strip_edges(); output.append(source)
	return output

func _mark_dirty():
	if loading or draft == null: return
	get_ok_button().disabled = not _form_changed(); status_label.text = "Unsaved opening changes." if not get_ok_button().disabled else "No unsaved changes."; status_label.modulate = Color("f2cf74") if not get_ok_button().disabled else InspectorStyle.COLOR_TEXT_DIM

func _save():
	if draft == null: return
	if not _form_changed(): _finish_save(); return
	draft.data = draft.original.duplicate(true); draft.data["heading"] = heading.text.strip_edges(); draft.data["intro"] = intro.text.strip_edges(); draft.data["objectives_heading"] = objectives_heading.text.strip_edges(); draft.data["objectives"] = _objectives()
	var result: Dictionary = draft.save()
	if not result.get("ok", false): status_label.text = str(result.get("error", "Could not save opening.")); status_label.modulate = DialogStyle.COLOR_DANGER; return
	opening_saved.emit(); _finish_save()
