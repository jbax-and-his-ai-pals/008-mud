# scripts/ui/modals/ManifestEditorDialog.gd
#
# The content set's identity, start and capabilities, editable after creation.
#
# Before this, the manifest was written once by the scaffold and never again: an
# author who wanted a different start room, or to turn a system on, edited JSON by
# hand or copied the set. The fields it does *not* offer are as deliberate as the
# ones it does -- the id is the directory name and the identity saves are
# partitioned by, and paths are refused by `configuration_save.py` rather than
# half-supported here.
class_name ManifestEditorDialog
extends "res://scripts/ui/modals/ConfigurationDialog.gd"

signal manifest_saved

const DraftScript = preload("res://scripts/data/ManifestDraft.gd")
const Scaffold = preload("res://scripts/data/ContentSetScaffold.gd")

var draft
var status_label: Label
var identity_label: Label
var paths_label: Label
var title_field: LineEdit
var scenario_field: LineEdit
var region_field: LineEdit
var room_field: LineEdit
var capability_checks: Dictionary = {}
var form_dirty := false
var loading := false

func setup():
	_install_guard()
	title = "Content Set Manifest"
	min_size = Vector2i(780, 640)
	ok_button_text = "Save Manifest"
	confirmed.connect(_save)
	var scroll := ScrollContainer.new(); scroll.custom_minimum_size = Vector2(750, 520); add_child(scroll)
	var box := VBoxContainer.new(); box.custom_minimum_size = Vector2(720, 0); box.add_theme_constant_override("separation", 10); scroll.add_child(box)
	status_label = Label.new(); status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; status_label.modulate = InspectorStyle.COLOR_TEXT_DIM; box.add_child(status_label)
	box.add_child(InspectorStyle.create_sub_header("Identity (fixed)"))
	identity_label = InspectorStyle.lbl("", InspectorStyle.COLOR_TEXT_DIM); identity_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(identity_label)
	paths_label = InspectorStyle.lbl("", InspectorStyle.COLOR_TEXT_DIM); paths_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(paths_label)
	box.add_child(InspectorStyle.create_sub_header("Title"))
	title_field = _field(box, "Title")
	box.add_child(InspectorStyle.create_sub_header("Where a character starts"))
	var start_hint := InspectorStyle.lbl("The region and room must exist in this set. The engine refuses a start it cannot place.", InspectorStyle.COLOR_TEXT_DIM)
	start_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(start_hint)
	scenario_field = _field(box, "Scenario id (the opening file's scenario_id)")
	region_field = _field(box, "Region id")
	room_field = _field(box, "Room id")
	box.add_child(InspectorStyle.create_sub_header("Capabilities"))
	var capability_hint := InspectorStyle.lbl("A capability must agree with the ruleset's `systems` section: the engine refuses a contradiction, and the report says which one.", InspectorStyle.COLOR_TEXT_DIM)
	capability_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(capability_hint)
	var grid := GridContainer.new(); grid.columns = 2; box.add_child(grid)
	for capability in Scaffold.CAPABILITIES:
		var toggle := CheckBox.new(); toggle.text = str(capability); toggle.toggled.connect(func(_value): _mark_dirty()); grid.add_child(toggle)
		capability_checks[str(capability)] = toggle
	DialogStyle.style_window(self)
	get_ok_button().custom_minimum_size = Vector2(280, 40)
	get_ok_button().disabled = true

func open_active():
	if visible: return
	draft = null
	_form_baseline.clear()
	draft = DraftScript.new()
	var result: Dictionary = draft.open(DataRoot.root().path_join(Scaffold.MANIFEST_FILENAME))
	if not result.get("ok", false):
		status_label.text = str(result.get("error", "Could not load the manifest.")); status_label.modulate = DialogStyle.COLOR_DANGER
		get_ok_button().disabled = true; popup_centered(); return
	loading = true
	identity_label.text = "id: %s\nversion: %s   manifest schema: %s   engine API: %s - %s" % [
		str(draft.data.get("id", "")), str(draft.data.get("version", "")),
		str(draft.data.get("manifest_schema_version", "")),
		str(draft.data.get("engine_api_min", "")), str(draft.data.get("engine_api_max", "")),
	]
	var paths: Dictionary = draft.data.get("paths", {}) if draft.data.get("paths") is Dictionary else {}
	var lines: Array = []
	for key in paths:
		lines.append("%s: %s" % [key, str(paths[key])])
	paths_label.text = "Paths (not editable here): " + ("; ".join(lines) if not lines.is_empty() else "none declared")
	title_field.text = draft.title_value()
	scenario_field.text = draft.start_field("scenario_id")
	region_field.text = draft.start_field("region_id")
	room_field.text = draft.start_field("room_id")
	var declared: Array = draft.capabilities()
	for capability in capability_checks:
		capability_checks[capability].button_pressed = declared.has(capability)
	_reset_form_baseline()
	loading = false; form_dirty = false; get_ok_button().disabled = true
	status_label.text = "Editing %s. Changing a capability needs the game reloaded before it takes effect." % DataRoot.root().path_join(Scaffold.MANIFEST_FILENAME)
	status_label.modulate = InspectorStyle.COLOR_TEXT_DIM
	popup_centered()

func _save():
	if draft == null: return
	if not _form_changed(): _finish_save(); return
	if _field_changed(title_field): draft.set_title(title_field.text)
	draft.set_start(scenario_field.text, region_field.text, room_field.text)
	var chosen: Array = []
	for capability in capability_checks:
		if capability_checks[capability].button_pressed: chosen.append(capability)
	draft.set_capabilities(chosen)
	var result: Dictionary = draft.save()
	if not result.get("ok", false):
		status_label.text = str(result.get("error", "Could not save the manifest.")); status_label.modulate = DialogStyle.COLOR_DANGER; return
	form_dirty = false; get_ok_button().disabled = true
	manifest_saved.emit()
	_finish_save()

func _field(parent: VBoxContainer, label_text: String) -> LineEdit:
	var row := VBoxContainer.new(); row.add_child(InspectorStyle.lbl(label_text, InspectorStyle.COLOR_TEXT_DIM))
	var field := LineEdit.new(); InspectorStyle.apply_input_style(field); field.text_changed.connect(func(_text): _mark_dirty()); row.add_child(field)
	parent.add_child(row); return field

func _mark_dirty():
	if loading or draft == null: return
	form_dirty = _form_changed()
	get_ok_button().disabled = not form_dirty
	status_label.text = "Unsaved manifest changes." if form_dirty else "No unsaved changes."
	status_label.modulate = Color("f2cf74") if form_dirty else InspectorStyle.COLOR_TEXT_DIM
